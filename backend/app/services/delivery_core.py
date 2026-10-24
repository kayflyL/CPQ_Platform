# -*- coding: utf-8 -*-
"""delivery_core —— 交付业务核心层（聊天工具与交付工作流共用的唯一实现）。

与页面同源原则不变：写动作直调对应 API 路由函数本体（懒导入）——权限校验、阶段门、
影子建单、流程卡、通知等连带效应与页面操作走同一份代码。

与对话解耦的三条纪律：
1. 无 TOOL_CTX：身份(user dict)、商机定位、价格门(price_ok)全部显式传参；
   调用方（聊天适配层/工作流节点）各自解析自己的上下文；
2. 无确认闸、无话术：两阶段确认是调用方的会话语义（聊天=agent_write_confirm，
   工作流=暂停/确认卡）；核心层只提供 preview / execute 两段纯执行；
3. 结果只摆事实：{ok, ...事实字段} 或 {ok:False, error, ...原因码}——
   转述、建议、下一步指引由调用方叠加。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

COST_SHEET_EXTS = {".xlsx", ".xls", ".csv"}
# 商机环节桶（与 feed.py 的环节→category 映射同源）
CATEGORY_FOLDER = {
    "lead_requirement": "线索登记",
    "technical": "BOM方案",
    "requirement": "成本核算",
    "sent_quote": "报价单",
}


def err(message: str, **extra: Any) -> dict:
    return {"ok": False, "error": message, **extra}


def call_route(fn, *args, **kwargs) -> dict:
    """直调路由函数本体；HTTPException 翻译成结果 dict。"""
    from fastapi import HTTPException
    try:
        data = fn(*args, **kwargs)
    except HTTPException as exc:
        return err(str(exc.detail), status=exc.status_code)
    return {"ok": True, **(data or {})}


def financial_rates() -> tuple[float, float]:
    """加价重算的汇率/税率，与报价工作台同源（system_config，缺省 7.0 / 0.13）。"""
    from app.repository.system_config_repo import SystemConfigRepository
    repo = SystemConfigRepository()
    try:
        tax = repo.get_value("tax_rate", 0.13)
        usd = repo.get_value("usd_to_rmb", 7.0)
    finally:
        repo.close()
    try:
        tax = float(tax)
    except (TypeError, ValueError):
        tax = 0.13
    try:
        usd = float(usd)
    except (TypeError, ValueError):
        usd = 7.0
    return usd, tax


def unit_cost_rmb(base_price: Any, currency: Any, usd_rate: float, tax_rate: float) -> float:
    """quoteCommon.calcUnitCost 的后端镜像：USD 行 = 基准价 × 汇率 × (1+税率)。"""
    base = float(base_price or 0)
    if str(currency or "").strip().upper() == "USD":
        return base * usd_rate * (1 + tax_rate)
    return base


# ── 商机定位（自然标识）──────────────────────────────────────────────────


def resolve_opportunity(user: dict, *, opportunity_id: str = "",
                        customer_name: str = "",
                        fallback_opp_id: str = "") -> dict:
    """商机定位：显式 opportunity_id > customer_name（精确→模糊）> fallback（调用方的
    会话绑定商机）。返回 {ok, opportunity_id}；歧义时 {ok:False, candidates:[...]}。

    案台跟随（2026-10-22 设计总纲）：工作流是在操作商机详情页——工具解析命中哪个
    商机，案台就是哪个商机。命中即把会话绑定跟随过去，不依赖大脑记得先建档
    （按名解析/按名归档这些"页面式"动作天然带商机身份，不该被绑定副通道卡死）。"""
    ref = str(opportunity_id or "").strip()
    name = str(customer_name or "").strip()
    fallback = str(fallback_opp_id or "").strip()
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    hit: Optional[str] = None
    try:
        if ref:
            opp = repo.get_opportunity(ref)
            if not opp:
                return err(f"商机 {ref} 不存在")
            hit = ref
        elif name:
            rows, total = repo.list_opportunities(search=name, page_size=10)
            exact = [r for r in rows if (r.get("customer_name") or "").strip() == name]
            if len(exact) == 1:
                hit = exact[0]["opportunity_id"]
            elif not exact and len(rows) == 1:
                hit = rows[0]["opportunity_id"]
            elif rows:
                return err(f"客户名含「{name}」命中 {min(total, 10)} 个商机，请确认是哪一个",
                           candidates=[{"opportunity_id": r.get("opportunity_id"),
                                        "customer_name": r.get("customer_name") or "",
                                        "created_at": r.get("created_at") or ""} for r in rows[:5]])
            else:
                return err(f"没有找到客户名含「{name}」的商机：确认名字，或先新建商机")
    finally:
        repo.close()
    if hit:
        try:
            from app.services.skill_tool_context import TOOL_CTX
            ctx = TOOL_CTX.get() if isinstance(TOOL_CTX.get(), dict) else {}
            tid = str(ctx.get("thread_id") or "")
            if tid:
                from app.repository.assistant_repo import AssistantRepository
                ar = AssistantRepository()
                try:
                    thr = ar.get_thread(tid) or {}
                    if str(thr.get("opportunity_id") or "") != hit:
                        ar.update_thread_opportunity_id(tid, hit)
                finally:
                    ar.close()
        except Exception:
            logger.exception("案台跟随绑定失败 opp=%s", hit)
        return {"ok": True, "opportunity_id": hit}
    if fallback:
        return {"ok": True, "opportunity_id": fallback}
    return err("无法定位商机：请提供 opportunity_id 或 customer_name")


# ── 附件选取 / 读取 / 归档绑定 ───────────────────────────────────────────


def pick_attachment(user: dict, opp_id: Optional[str], attachment_id: str = "",
                    exts: Optional[set] = None) -> tuple:
    """附件选取：显式 attachment_id > 商机桶最新 > 本人暂存最新。
    opp_id=None（仅解析预览）时跳过商机桶。exts=None=不限扩展名。返回 (att, error)。"""
    from app.repository.feed_repo import FeedRepository
    feed_repo = FeedRepository()
    try:
        if attachment_id:
            att = feed_repo.get_attachment(attachment_id)
            if not att:
                return None, err("附件不存在")
            att_opp = att.get("opportunity_id")
            if att_opp and att_opp != opp_id:
                from fastapi import HTTPException
                from app.api.deps import ensure_opportunity_access
                try:
                    ensure_opportunity_access(att_opp, user)
                except HTTPException as exc:
                    return None, err(str(exc.detail), status=exc.status_code)
            if not att_opp and att.get("uploader_user_id") != user.get("user_id"):
                return None, err("暂存附件只属于上传者本人")
            return att, None
        if opp_id:
            cands = [a for a in feed_repo.list_attachments(opp_id)
                     if exts is None or Path(a.get("original_filename") or "").suffix.lower() in exts]
            if cands:
                return cands[0], None
        staged = [a for a in feed_repo.list_staged_attachments(user.get("user_id") or "")
                  if exts is None or Path(a.get("original_filename") or "").suffix.lower() in exts]
        if staged:
            return staged[0], None
        if opp_id:
            return None, err("没有可用的表格附件（商机附件与会话暂存都没有）")
        return None, err("会话暂存里没有可用附件：请先传文件或指定 attachment_id")
    finally:
        feed_repo.close()


def read_attachment_bytes(att: dict):
    from app.services.storage_adapter import get_storage
    try:
        return get_storage().read_bytes(att.get("storage_key") or "")
    except Exception as exc:
        return err(f"读取附件文件失败：{exc}")


def bind_staged_to_opportunity(att: dict, opp: dict, content: bytes,
                               category: Optional[str]) -> Optional[dict]:
    """暂存附件归档进商机桶：存盘（原始名+短UUID，环节子文件夹）→ 改绑行 → 删暂存文件。"""
    from app.repository.feed_repo import FeedRepository
    from app.services.storage_adapter import build_object_id, get_storage
    storage = get_storage()
    filename = att.get("original_filename") or "file"
    ext = Path(filename).suffix.lower() or ".bin"
    subfolder = CATEGORY_FOLDER.get(category or "", "")
    new_key = storage.save_bytes(
        opp.get("opportunity_id") or "", build_object_id(filename), content, ext,
        customer_name=opp.get("customer_name") or "", subfolder=subfolder)
    feed_repo = FeedRepository()
    try:
        bound = feed_repo.bind_attachment(
            att.get("attachment_id") or "",
            opportunity_id=opp.get("opportunity_id"),
            storage_key=new_key, category=category)
    finally:
        feed_repo.close()
    try:
        storage.delete(att.get("storage_key") or "")
    except Exception:
        pass
    return bound


def set_attachment_category(attachment_id: str, category: str) -> Optional[dict]:
    from app.repository.feed_repo import FeedRepository
    fr = FeedRepository()
    try:
        return fr.bind_attachment(attachment_id, category=category)
    finally:
        fr.close()


# ── 解析（纯函数段，零落库）──────────────────────────────────────────────


def parse_cost_sheet(content: bytes, filename: str,
                     parse_overrides: Optional[dict] = None) -> dict:
    """解析成本表 → 结构化 configs（含 digest）。零落库零归档。
    返回 {ok, configs(完整), digest(摘要), parse_result} 或 {ok:False, error}。"""
    from app.api.portal import _parse_result_to_cost_configs
    from app.services.quote_service import QuoteService
    service = QuoteService()
    try:
        result = service.process_upload(content, filename, parse_overrides=parse_overrides)
        if result.get("status") == "error":
            return err(f"成本表解析失败：{result.get('message') or '未知错误'}")
        configs = _parse_result_to_cost_configs(result.get("configs") or {})
        if not configs:
            return err("未识别到有效配置：请检查成本表格式")
        digest = [{
            "name": c.get("name"),
            "server_model": c.get("server_model") or "",
            "qty": c.get("qty") or 1,
            "kp_rows": len(c.get("kp_rows") or []),
            "l6_cost": c.get("l6_cost") or 0,
        } for c in configs]
        return {"ok": True, "configs": configs, "digest": digest, "parse_result": result}
    finally:
        service.close()


def cost_sheet_name(filename: str) -> str:
    from app.api.portal import _cost_sheet_name_from_filename
    return _cost_sheet_name_from_filename(filename)


def get_cost_sheet(opp_id: str, sheet_id: int) -> Optional[dict]:
    """按 id 取成本表（页面同源）。"""
    from app.repository.flow_repo import FlowRepository
    repo = FlowRepository()
    try:
        return repo.get_cost_sheet(opp_id, sheet_id)
    finally:
        repo.close()


def latest_cost_sheet(opp_id: str) -> Optional[dict]:
    """商机最新未归档成本表（与页面/案台同序：current > draft > archived 取首个）。"""
    from app.repository.flow_repo import FlowRepository
    repo = FlowRepository()
    try:
        for r in repo.list_cost_sheets(opp_id) or []:
            if str(r.get("status") or "") != "archived":
                return r
    finally:
        repo.close()
    return None


def filled_price_count(configs: list) -> int:
    """已填价计数：kp/l6 行 base_price 非空各计 1，配置级 l6_cost 整价计 1。
    重导护栏用——重解析若会把这些人工输入清掉，必须先拦。"""
    n = 0
    for c in configs or []:
        if not isinstance(c, dict):
            continue
        if c.get("l6_cost"):
            n += 1
        for r in (c.get("kp_rows") or []) + (c.get("l6_rows") or []):
            if isinstance(r, dict) and r.get("base_price"):
                n += 1
    return n


def set_cost_prices(user: dict, opp_id: str, sheet_id: Optional[int],
                    prices: list) -> dict:
    """缺价补充：把聊天里报来的价格回写进成本表草稿（页面同源保存，保留方案挂接）。
    prices 支持两种写法：[{config_name, l6_price}]（L6 整机一口价→配置级 l6_cost，
    与页面成本核算同口径）和 [{config_name, catalogue, base_price}]（KP 逐行）。
    行按 配置名+Catalogue(去空格) 精确定位。
    返回 {ok, sheet_id, sheet_name, applied, missed} | err。零提交零通知——
    价格补齐后案台探针自然放行（缺价闸在节点完成条件上，不在这里）。"""
    from app.repository.flow_repo import FlowRepository
    flow_repo = FlowRepository()
    try:
        if sheet_id:
            sheet = flow_repo.get_cost_sheet(opp_id, sheet_id)
        else:
            rows = [r for r in (flow_repo.list_cost_sheets(opp_id) or [])
                    if str(r.get("status") or "") != "archived"]
            sheet = rows[0] if rows else None
        if not sheet:
            return err("未找到可补价的成本表草稿（缺省取最新未归档，也可带 sheet_id）")
        if str(sheet.get("status") or "") != "draft":
            return err("仅草稿成本表可补价")
        configs = sheet.get("configs") or []
        applied, missed = [], []
        for p in prices if isinstance(prices, list) else []:
            if not isinstance(p, dict):
                continue
            cname = str(p.get("config_name") or "").strip()
            cfg = next((c for c in configs if str(c.get("name") or "").strip() == cname), None)
            # 配置级 L6 整价（页面口径：l6_cost 一口价，l6_rows 只是明细展示——
            # 2026-10-22 用户定："L6 是整体价格，8 行只是明细"）。一个配置一个数。
            if p.get("l6_price") not in (None, ""):
                if not cfg:
                    missed.append(f"{cname or '?'}：配置不存在")
                    continue
                try:
                    cfg["l6_cost"] = round(float(p.get("l6_price")), 2)
                except (TypeError, ValueError):
                    missed.append(f"{cname or '?'}：L6 整价不是数字")
                    continue
                applied.append(f"{cname} L6整价={cfg['l6_cost']:g}")
                continue
            cat = str(p.get("catalogue") or "").strip()
            try:
                price = round(float(p.get("base_price")), 2)
            except (TypeError, ValueError):
                missed.append(f"{cname or '?'}/{cat or '?'}：价格不是数字")
                continue
            if not cfg:
                missed.append(f"{cname or '?'}/{cat or '?'}：配置不存在")
                continue
            row = next((r for r in ((cfg.get("kp_rows") or []) + (cfg.get("l6_rows") or []))
                        if str(r.get("catalogue") or "").strip() == cat), None)
            if not row:
                missed.append(f"{cname or '?'}/{cat or '?'}：行不存在")
                continue
            row["base_price"] = price
            applied.append(f"{cname}/{cat}={price:g}")
        if not applied:
            detail = "；".join(missed[:6]) if missed else "prices 为空"
            return err(f"没有一行价格写入：{detail}")
        sheet = flow_repo.save_cost_sheet_draft(
            opp_id, sheet.get("id"), sheet.get("name"), configs,
            bom_scheme_id=sheet.get("bom_scheme_id"),
            quotation_id=sheet.get("quotation_id") or "",
            created_by=user.get("name") or "")
        return {"ok": True, "sheet_id": sheet.get("id"),
                "sheet_name": sheet.get("name"), "applied": applied,
                "missed": missed,
                "note": f"已补 {len(applied)} 行价格进成本表草稿（未提交）"}
    finally:
        flow_repo.close()


def save_cost_draft(user: dict, opp_id: str, sheet_id: Optional[int], name: str,
                    configs: list) -> dict:
    """落成本草稿（同名原地更新或新建）+ 流程卡。返回 {ok, sheet_id, sheet_name} | err。"""
    from app.api.portal import _attach_entity_card
    from app.repository.flow_repo import FlowRepository
    flow_repo = FlowRepository()
    try:
        if sheet_id:
            existing = flow_repo.get_cost_sheet(opp_id, sheet_id)
            if not existing or existing.get("status") != "draft":
                return err("要原地更新的成本表不存在或不是草稿")
            name = existing.get("name") or name
        else:
            taken = {s.get("name") for s in flow_repo.list_cost_sheets(opp_id)}
            base, seq = name, 2
            while name in taken:
                name = f"{base}-v{seq}"
                seq += 1
        sheet = flow_repo.save_cost_sheet_draft(
            opp_id, sheet_id, name, configs, bom_scheme_id=None,
            quotation_id="", created_by=user.get("name") or "",
        )
        _attach_entity_card(opp_id, "cost", sheet["id"], origin_node="costing",
                            current_node="costing", flow_status="draft",
                            created_by=user.get("name") or "", card_id=None,
                            visible_upstream=False)
        return {"ok": True, "sheet_id": sheet.get("id"), "sheet_name": name}
    except ValueError as exc:
        return err(str(exc))
    finally:
        flow_repo.close()


# ── 建商机 / 需求草稿 / 归档 ──────────────────────────────────────────────


def create_opportunity(user: dict, *, customer_name: str, sales_person: str = "") -> dict:
    from app.api.opportunities import CreateOpportunityRequest, create_empty_opportunity
    req = CreateOpportunityRequest(customer_name=customer_name, sales_person=sales_person)
    result = call_route(create_empty_opportunity, req, user)
    if not result.get("ok"):
        return result
    return {"ok": True, "opportunity_id": result.get("opportunity_id"),
            "customer_name": customer_name}


def save_requirement_draft(user: dict, *, opp_id: str, requirement_text: str,
                           slots: Optional[dict] = None) -> dict:
    from fastapi import HTTPException

    from app.api.deps import ensure_opportunity_access
    from app.api.portal import RequirementBody
    from app.api.portal import save_requirement_draft as _route
    try:
        ensure_opportunity_access(opp_id, user)
    except HTTPException as exc:
        return err(str(exc.detail), status=exc.status_code)
    result = call_route(_route, opp_id,
                        RequirementBody(slots=slots or {},
                                        requirement_text=str(requirement_text or "")[:8000]),
                        user)
    if not result.get("ok"):
        return result
    req = result.get("requirement") or {}
    return {"ok": True, "opportunity_id": opp_id, "version": req.get("version"),
            "status": req.get("status")}


def archive_attachment(user: dict, *, opp: dict, att: dict, content: bytes,
                       category: Optional[str]) -> dict:
    """归档：暂存件移入商机桶并改绑；已属本商机的仅归类。返回归档后的事实。"""
    bound = None
    if not att.get("opportunity_id"):
        bound = bind_staged_to_opportunity(att, opp, content, category)
    elif category:
        bound = set_attachment_category(att["attachment_id"], category)
    label = CATEGORY_FOLDER.get(category or "", "未分类")
    return {"ok": True, "attachment_id": att.get("attachment_id"),
            "opportunity_id": opp.get("opportunity_id"),
            "category": (bound or {}).get("category") or category or "",
            "bucket_label": label}


def set_attachment_category(attachment_id: str, category: str) -> Optional[dict]:
    from app.repository.feed_repo import FeedRepository
    fr = FeedRepository()
    try:
        return fr.bind_attachment(attachment_id, category=category)
    finally:
        fr.close()


# ── 提交推进（提交 + 转报价草稿）─────────────────────────────────────────


def submit_and_convert(user: dict, opp_id: str, sheet_id: int,
                       assignee_name: str = "") -> dict:
    from fastapi import HTTPException

    from app.api.deps import ensure_opportunity_access, user_has_permission
    from app.api.portal import (ConvertCostBody, SubmitAssigneeBody,
                                convert_cost_to_quotation,
                                submit_cost_sheet as _submit_route)
    from app.repository.flow_repo import FlowRepository
    flow_repo = FlowRepository()
    try:
        sheet = flow_repo.get_cost_sheet(opp_id, sheet_id)
    finally:
        flow_repo.close()
    if not sheet:
        return err("成本表不存在或不属于该商机")
    if sheet.get("status") != "draft":
        return err("仅草稿成本表可提交")
    try:
        ensure_opportunity_access(opp_id, user)
    except HTTPException as exc:
        return err(str(exc.detail), status=exc.status_code)

    sub = call_route(_submit_route, opp_id, sheet_id,
                     SubmitAssigneeBody(assignee_name=assignee_name), user)
    if not sub.get("ok"):
        return sub
    quotation_id = sub.get("quotation_id") or ""
    conv = call_route(convert_cost_to_quotation, opp_id,
                      ConvertCostBody(quotation_id=quotation_id), user)
    return {"ok": True, "sheet_id": sheet_id, "quotation_id": quotation_id,
            "converted": bool(conv.get("ok")),
            "convert_error": None if conv.get("ok") else conv.get("error")}


# ── 加价（预览 / 执行 两段）──────────────────────────────────────────────


def cfg_totals(rows: list, l6_cost: float, l6_margin: float,
               warranty: dict, usd_rate: float, tax_rate: float) -> dict:
    """store/quote.ts calcConfigTotals + recalculateAll 的后端镜像（口径一致，勿改公式）。"""
    warranty = warranty if isinstance(warranty, dict) else {}
    rate_l6 = float((warranty.get("l6") or {}).get("rate") or 0)
    rate_kp = float((warranty.get("kp") or {}).get("rate") or 0)
    kp_cost = kp_sales = warranty_cost = warranty_sales = 0.0
    for it in rows:
        cat = it.get("category") or ""
        if cat in ("L6", "整机"):  # L6 行不进 items（防旧脏数据），价格走 l6_custom_price
            continue
        qty = int(it.get("qty") or 1)
        unit_cost = unit_cost_rmb(it.get("base_price"), it.get("currency"), usd_rate, tax_rate)
        unit_sales = unit_cost * (1 + float(it.get("profit_margin") or 0) / 100)
        if cat == "Warranty":
            warranty_cost += unit_cost * qty
            warranty_sales += unit_sales * qty
        else:
            kp_cost += unit_cost * qty
            kp_sales += unit_sales * qty
    l6_sales = l6_cost * (1 + l6_margin / 100)
    warranty_fee = l6_cost * rate_l6 + kp_cost * rate_kp
    total_cost = l6_cost + kp_cost + warranty_cost
    total_sales = l6_sales + kp_sales + warranty_sales + warranty_fee
    profit = total_sales - total_cost
    margin_pct = (profit / total_cost * 100) if total_cost > 0 else 0.0
    return {"total_cost": total_cost, "total_sales": total_sales,
            "margin_pct": margin_pct, "l6_sales": l6_sales}


def _margin_model(user: dict, *, opp_id: str, quotation_id: str,
                  margin: float, apply_to: str) -> dict:
    """加价的纯计算模型：读单+行，产出改前/改后两套口径与保存 payload。失败返回 err。"""
    from fastapi import HTTPException

    from app.api.deps import ensure_quotation_access
    from app.repository.quotation_repo import QuotationRepository
    quote_repo = QuotationRepository()
    try:
        quotation = quote_repo.get_by_id(quotation_id)
        if not quotation or quotation.opportunity_id != opp_id:
            return err("报价单不存在或不属于该商机")
        try:
            ensure_quotation_access(quotation_id, user)
        except HTTPException as exc:
            return err(str(exc.detail), status=exc.status_code)
        usd_rate, tax_rate = financial_rates()
        items = [it.to_dict() for it in quote_repo.get_items(quotation_id)]
        extra: dict = {}
        if quotation.extra_fields:
            try:
                extra = json.loads(quotation.extra_fields) or {}
            except (json.JSONDecodeError, TypeError):
                extra = {}
        picks = extra.get("config_l6_picks") or {}
        if not isinstance(picks, dict):
            picks = {}
        warranty_info = (quotation.config_warranty_info
                         if isinstance(quotation.config_warranty_info, dict) else {})

        def _totals_of(items_view: list, picks_view: dict) -> dict:
            groups: dict = {}
            for it in items_view:
                groups.setdefault(it.get("config_name") or "", []).append(it)
            out = {}
            for name, rows in groups.items():
                pick = picks_view.get(name) if isinstance(picks_view.get(name), dict) else {}
                l6_cost = float(pick.get("l6_custom_price") or 0)
                raw_margin = pick.get("l6_profit_margin")
                l6_margin = float(raw_margin) if raw_margin is not None else 10
                out[name] = cfg_totals(rows, l6_cost, l6_margin, warranty_info,
                                       usd_rate, tax_rate)
            return out

        before = _totals_of(items, picks)
        new_items = [dict(it) for it in items]
        for it in new_items:
            it.pop("item_id", None)
            it.pop("quotation_id", None)
        new_picks = {k: (dict(v) if isinstance(v, dict) else v) for k, v in picks.items()}
        for it in new_items:
            cat = it.get("category") or ""
            if cat in ("L6", "整机"):
                continue
            if apply_to in ("kp", "kp+l6") and cat == "Key Parts":
                it["profit_margin"] = margin
            unit_cost = unit_cost_rmb(it.get("base_price"), it.get("currency"),
                                      usd_rate, tax_rate)
            it["final_price"] = round(
                unit_cost * (1 + float(it.get("profit_margin") or 0) / 100) * 100) / 100
        if apply_to in ("l6", "kp+l6"):
            for pick in new_picks.values():
                if isinstance(pick, dict):
                    pick["l6_profit_margin"] = margin
        after = _totals_of(new_items, new_picks)

        relation = quotation.config_relation or "compose"
        primary = quotation.primary_config or ""
        cfg_names = list(after.keys())
        target = primary if primary in after else (cfg_names[0] if cfg_names else "")
        qty_factor = 1
        if relation == "alternative":
            dq = int(quotation.total_qty or 0)
            qty_factor = dq if dq > 0 else 1
        t_before = before.get(target) or {}
        t_after = after.get(target) or {}
        return {"ok": True, "quotation": quotation, "items": items,
                "new_items": new_items, "new_picks": new_picks,
                "before": before, "after": after,
                "target": target, "qty_factor": qty_factor,
                "t_before": t_before, "t_after": t_after}
    finally:
        quote_repo.close()


def margin_preview(user: dict, *, opp_id: str, quotation_id: str,
                   margin: float, apply_to: str, price_ok: bool) -> dict:
    """加价预览（零写入）：返回改前/改后口径，供确认卡/工作流暂停。
    price_ok 为必传显式门——调用方（聊天/工作流）各自解析后传入， False 即拒。"""
    if not price_ok:
        return err("无价格权限：未开通价格访问（price_access），已拒绝改价")
    model = _margin_model(user, opp_id=opp_id, quotation_id=quotation_id,
                          margin=margin, apply_to=apply_to)
    if not model.get("ok"):
        return model
    t_before, t_after = model["t_before"], model["t_after"]
    qf = model["qty_factor"]
    before, after = model["before"], model["after"]
    return {
        "ok": True,
        "各配置合计（单台口径）": [
            {"name": n,
             "改前总额": round((before.get(n) or {}).get("total_sales", 0), 2),
             "改后总额": round((after.get(n) or {}).get("total_sales", 0), 2)}
            for n in after.keys() if n in before
        ],
        "整单快照（主配置）": {
            "改前": {"total_price": round(t_before.get("total_sales", 0) * qf, 2),
                     "profit_margin": round(t_before.get("margin_pct", 0), 2)},
            "改后": {"total_price": round(t_after.get("total_sales", 0) * qf, 2),
                     "profit_margin": round(t_after.get("margin_pct", 0), 2),
                     "l6_price": round(t_after.get("l6_sales", 0) * qf, 2)},
        },
    }


def margin_execute(user: dict, *, opp_id: str, quotation_id: str,
                   margin: float, apply_to: str, price_ok: bool) -> dict:
    """加价执行（写库）：模型重算后走与页面同源的保存路由。price_ok 必传显式门。"""
    if not price_ok:
        return err("无价格权限：未开通价格访问（price_access），已拒绝改价")
    model = _margin_model(user, opp_id=opp_id, quotation_id=quotation_id,
                          margin=margin, apply_to=apply_to)
    if not model.get("ok"):
        return model
    t_after = model["t_after"]
    qf = model["qty_factor"]
    payload = {
        "items": model["new_items"],
        "config_l6_picks": model["new_picks"],
        "total_price": round(t_after.get("total_sales", 0) * qf, 2),
        "profit_margin": round(t_after.get("margin_pct", 0), 2),
        "l6_price": round(t_after.get("l6_sales", 0) * qf, 2),
    }
    from app.api.quotations import save_quotation_items as _save_route
    result = call_route(_save_route, quotation_id, payload, user)
    if not result.get("ok"):
        return result
    return {"ok": True, "quotation_id": quotation_id, "margin_pct": margin,
            "saved_items": result.get("saved"), "totals": payload["total_price"]}


def margin_resolve_quotation(user: dict, opp_id: str, quotation_id: str = "") -> dict:
    """报价单定位：显式 id 校验归属；缺省取商机最新 active。返回 {ok, quotation_id, name, version} | err。"""
    from fastapi import HTTPException

    from app.api.deps import ensure_opportunity_access, ensure_quotation_access
    from app.repository.quotation_repo import QuotationRepository
    try:
        ensure_opportunity_access(opp_id, user)
    except HTTPException as exc:
        return err(str(exc.detail), status=exc.status_code)
    quote_repo = QuotationRepository()
    try:
        quotation_id = str(quotation_id or "").strip()
        if quotation_id:
            quotation = quote_repo.get_by_id(quotation_id)
            if not quotation or quotation.opportunity_id != opp_id:
                return err("报价单不存在或不属于该商机")
        else:
            quotes = quote_repo.get_by_opportunity(opp_id)  # version 倒序、仅 active
            if not quotes:
                return err("该商机暂无报价单：先提交成本表生成报价草稿，或提供 quotation_id")
            quotation = quotes[0]
            quotation_id = quotation.quotation_id
        try:
            ensure_quotation_access(quotation_id, user)
        except HTTPException as exc:
            return err(str(exc.detail), status=exc.status_code)
        return {"ok": True, "quotation_id": quotation_id,
                "quotation_name": quotation.quotation_name or "",
                "version": quotation.version}
    finally:
        quote_repo.close()


# ── 出件（分享）───────────────────────────────────────────────────────────


def share_quote(user: dict, *, opp_id: str, quotation_id: str,
                view: str = "internal", expiry_days: int = 7) -> dict:
    view = str(view or "internal").strip()
    if view == "customer":
        return err("customer 视角=报价外发，必须走外发审批闸，助手/工作流不代办")
    if view not in ("scheme", "internal", "cost"):
        return err("view 只支持 scheme / internal / cost")
    try:
        expiry = int(expiry_days or 7)
    except (TypeError, ValueError):
        expiry = 7
    expiry = max(1, min(expiry, 30))

    from fastapi import HTTPException

    from app.api.deps import ensure_opportunity_access, field_visible
    try:
        ensure_opportunity_access(opp_id, user)
    except HTTPException as exc:
        return err(str(exc.detail), status=exc.status_code)
    if view == "cost" and not field_visible(user, "field.quote.export_internal"):
        return err("cost 视角含成本价，需要对内导出权限（field.quote.export_internal）")

    from app.repository.quotation_repo import QuotationRepository
    quote_repo = QuotationRepository()
    try:
        quotation_id = str(quotation_id or "").strip()
        if quotation_id:
            quotation = quote_repo.get_by_id(quotation_id)
            if not quotation or quotation.opportunity_id != opp_id:
                return err("报价单不存在或不属于该商机")
        else:
            quotes = quote_repo.get_by_opportunity(opp_id)
            if not quotes:
                return err("该商机暂无报价单可分享")
            quotation = quotes[0]
            quotation_id = quotation.quotation_id
    finally:
        quote_repo.close()

    from app.api.artifact_share import ShareCreateBody, create_artifact_share
    result = call_route(create_artifact_share, opp_id,
                        ShareCreateBody(source_type="quote", source_id=quotation_id,
                                        view=view, expiry_days=expiry), user)
    if not result.get("ok"):
        return result
    return {"ok": True, "quotation_id": quotation_id, "view": view,
            "share_path": result.get("share_path"), "expiry_days": expiry}


# ── 方案表分支（M2）：落位 → 库价推导 ────────────────────────────────────


def _kp_search_part(token: str) -> Optional[dict]:
    """配件搜索：按名称/描述在 KP 库中匹配，返回含 latest_price 的部件记录。"""
    if not token or len(token.strip()) < 2:
        return None
    from app.repository.kp_repo import KPRepository
    repo = KPRepository()
    try:
        results = repo.get_latest_prices(search=token.strip())
        return results[0] if results else None
    except Exception:
        return None
    finally:
        repo.close()


def scheme_name(filename: str) -> str:
    base = re.sub(r"\.(xlsx|xls|csv)$", "", os.path.basename(filename or ""), flags=re.I).strip()
    return f"方案-{base}"



def import_bom_scheme(user: dict, opp_id: str, attachment_id: str = "") -> dict:
    """方案表落位：解析上传的结构表 → 方案表草稿（不要求价格列）。
    解析器复用成本表解析（结构同源），价格列自然缺失不报错。"""
    from app.repository.flow_repo import FlowRepository
    from app.api.deps import ensure_opportunity_access
    att, aerr = pick_attachment(user, opp_id, attachment_id=attachment_id, exts=COST_SHEET_EXTS)
    if aerr:
        return aerr
    content = read_attachment_bytes(att)
    if isinstance(content, dict):
        return content
    filename = att.get("original_filename") or "方案表.xlsx"
    parsed = parse_cost_sheet(content, filename)
    if not parsed.get("ok"):
        return {k: v for k, v in parsed.items() if k != "parse_result"}
    name = scheme_name(filename)
    flow_repo = FlowRepository()
    try:
        scheme = flow_repo.save_bom_scheme_draft(
            opp_id, None, name=name, configs=parsed["configs"],
            created_by=(user or {}).get("name") or "")
    except ValueError as exc:
        return err(str(exc))
    finally:
        flow_repo.close()
    try:
        opp = ensure_opportunity_access(opp_id, user)
    except Exception as exc:
        return err(str(getattr(exc, "detail", exc)))
    out = {
        "ok": True,
        "bom_scheme_id": scheme.get("id"),
        "scheme_name": scheme.get("name"),
        "configs": parsed["digest"],
        "note": "方案表已落草稿（未提交；价格列缺失不影响落位）",
    }
    if not att.get("opportunity_id"):
        bound = bind_staged_to_opportunity(att, opp, content, category="requirement")
        if bound:
            out["archived"] = {"attachment_id": bound.get("attachment_id"), "category": "requirement"}
    return out


def derive_cost_from_scheme(user: dict, opp_id: str, bom_scheme_id: str = "") -> dict:
    """成本核算：由方案表推导成本表草稿，KP 行按配件库价填充（查不到留空并计数）。
    方案推进与人工「提交方案配置」同源（转 current + 流程推进 + 通知），成本表挂 bom_scheme_id。"""
    from fastapi import HTTPException
    from app.repository.flow_repo import FlowRepository
    from app.api.deps import ensure_opportunity_access
    flow_repo = FlowRepository()
    try:
        schemes = flow_repo.list_bom_schemes(opp_id) or []
    finally:
        flow_repo.close()
    scheme = None
    if bom_scheme_id:
        for sc in schemes:
            if sc.get("id") == int(bom_scheme_id):
                scheme = sc
                break
        if not scheme:
            return err("方案表不存在或不属于该商机")
    else:
        for sc in schemes:
            if sc.get("status") in ("draft", "current"):
                scheme = sc
                break
    if not scheme:
        return err("该商机没有可推导的方案表：先落方案表草稿")

    # 推进方案配置→成本核算（与人工按钮同一入口：转 current + 流程推进 + 通知）
    from app.api.portal import submit_bom_scheme as _submit_scheme, SubmitAssigneeBody
    try:
        out = _submit_scheme(opp_id, scheme["id"], body=SubmitAssigneeBody(), user=user)
        scheme = out["scheme"]
    except HTTPException as exc:
        return err(str(exc.detail), status=exc.status_code)

    # 库价填充：方案 configs 的 KP 行按配件库最新价自动匹配（机械查询，非人工判断）
    configs = scheme.get("configs") or []
    price_matched = 0
    for cfg in configs:
        for row in (cfg.get("kp_rows") or []):
            token = (row.get("catalogue") or row.get("description") or "").strip()
            if not token:
                continue
            part = _kp_search_part(token)
            if part and part.get("latest_price") is not None:
                row["base_price"] = round(float(part["latest_price"]), 2)
                price_matched += 1

    name = f"成本-{scheme.get('name')}"
    flow_repo = FlowRepository()
    try:
        sheet = flow_repo.save_cost_sheet_draft(
            opp_id, None, name=name, configs=configs,
            created_by=(user or {}).get("name") or "", bom_scheme_id=scheme.get("id"))
    finally:
        flow_repo.close()
    return {
        "ok": True,
        "sheet_id": sheet.get("id"),
        "sheet_name": sheet.get("name"),
        "bom_scheme_id": scheme.get("id"),
        "configs": [{"name": c.get("name"), "rows": len(c.get("items") or [])} for c in configs],
        "price_matched": price_matched,
        "note": f"成本表草稿已由方案表推导生成，{price_matched} 行已按配件库价填充",
    }
