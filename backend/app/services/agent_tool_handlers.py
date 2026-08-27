# -*- coding: utf-8 -*-
"""agent_tool_handlers —— 工具 handler 适配层。只做参数适配 + 结果 digest，业务实现来自 domain services。"""
import asyncio
import logging
from typing import Any, Dict, List, Optional
from app.services.agent_tool_registry import _truncate

# ── 工具 handler：把现有确定性函数包成 agent 工具（结果压成 digest） ──────

async def _tool_select_models(args: dict) -> Any:
    """select_models → 候选机型 digest（名称/系列/形态/盘位/卖点，给 LLM 推理）。"""
    from app.api.candidate_search import select_models
    _limit_arg = args.get("limit")
    try:
        limit = int(_limit_arg) if _limit_arg not in (None, "", 0) else None
    except (TypeError, ValueError):
        limit = None
    baselines = select_models(
        usage=args.get("usage") or "",
        server_type_name=args.get("server_type_name"),
        series=args.get("series"),
        form=args.get("form"),
        limit=limit,
        fallback_order=args.get("fallback_order") or ["exact", "same_series", "same_form", "all"],
    )
    if not baselines:
        return {"count": 0, "candidates": [],
                "note": "无匹配机型；建议放宽 server_type/form，或补 usage 关键词"}
    note = (baselines[0].get("fallback_note") or "")
    digest = [{
        "config_id": b.get("id"),
        "server_model_id": b.get("server_model_id"),
        "name": b.get("name") or "",
        "server_type_name": b.get("server_type_name") or "",
        "series": b.get("series") or "",
        "form": b.get("form") or "",
        "bays": b.get("bays"),
        "recommend_level": b.get("recommend_level") or "",
        "selling_points": _truncate(b.get("selling_points") or "", 300),
        "match_stage": b.get("match_stage"),
        "fallback_note": b.get("fallback_note") or "",
    } for b in baselines]
    result = {"count": len(digest), "candidates": digest, "note": note}
    if args.get("include_raw"):
        result["raw"] = baselines
    return result


async def _tool_list_kp_categories(args: dict) -> Any:
    """list_kp_categories -> 真实配件类目目录（规则键/库类目/数量/别名）。"""
    from app.services.part_selector import list_kp_categories
    cats = list_kp_categories()
    return {"count": len(cats), "categories": cats}


async def _tool_select_parts(args: dict) -> Any:
    """select_parts → 干净版配件匹配 digest（pn/name/category/qty，供 agent 编排）。"""
    from app.services.part_selector import select_parts
    _kw = args.get("keywords") or []
    picks = select_parts(
        categories=args.get("categories"),
        server_type_name=args.get("server_type_name"),
        search=args.get("search") or (_kw[0] if _kw and isinstance(_kw, list) else None),
        qty_map=args.get("qty_map"),
        search_map=args.get("search_map"),
        representative_pick=args.get("representative_pick") or "min_price",
        cpu_signal=args.get("cpu_signal"),
        mem_signal=args.get("mem_signal"),
        drive_groups=args.get("drive_groups"),
        gpu_groups=args.get("gpu_groups"),
        raid_groups=args.get("raid_groups"),
        psu_signal=args.get("psu_signal"),
        multi_spec_filters=args.get("multi_spec_filters"),
    )
    if not picks:
        return {"count": 0, "parts": [], "note": "无品类/无常可配，请补 categories 或 server_type_name"}
    digest = [{
        "category": p.get("category") or "",
        "pn": p.get("pn") or "",
        "name": p.get("name") or "",
        "qty": p.get("qty") or 1,
        "matched_spec": p.get("matched_spec") or "",
        "unit_price": float(p.get("unit_price") or 0),
        "currency": p.get("currency") or "RMB",
        "unmatched": bool(p.get("unmatched")),
        "unmatched_reason": p.get("unmatched_reason") or "",
        "request_spec": p.get("request_spec") or "",
        "grounded_spec": p.get("grounded_spec") or "",
        "spec_mismatch": bool(p.get("spec_mismatch")),
    } for p in picks]
    from app.services.skill_contracts import grounding_envelope
    return {"count": len(digest), "parts": digest, "grounding": grounding_envelope(digest)}


async def _tool_resolve_part_alias(args: dict) -> Any:
    """resolve_part_alias → 语义别名/同义术语 → 料号候选（兆芯→KH50000 等）。"""
    from app.services.part_selector import resolve_part_alias
    return await asyncio.to_thread(resolve_part_alias, args.get("term"), args.get("category"))


async def _tool_compose_memory(args: dict) -> Any:
    """compose_memory → 内存容量组合求解（128G → 64G×2 / 32G×4）。"""
    from app.services.part_selector import compose_memory
    total = args.get("total_gb")
    if total in (None, ""):
        return {"error": "缺 total_gb"}
    try:
        total = int(total)
    except (TypeError, ValueError):
        return {"error": "total_gb 必须是整数"}
    return await asyncio.to_thread(compose_memory, total, args.get("slots"))


async def _tool_build_plan(args: dict) -> Any:
    """build_plan → 整机方案 digest（机型/成本/未匹配件，给 LLM 推荐理由用）。"""
    from app.api.candidate_search import build_plan
    baseline = args.get("baseline")
    kp_parts = args.get("kp_parts")
    if not baseline or kp_parts is None:
        return {"error": "缺 baseline 或 kp_parts"}
    plan = build_plan(baseline, kp_parts)
    return {
        "name": plan.get("name") or "",
        "model": plan.get("model") or "",
        "series": plan.get("series") or "",
        "form": plan.get("form") or "",
        "summary": plan.get("summary") or {},
        "unmatched": plan.get("unmatched") or [],
        "selling_points": _truncate(plan.get("selling_points") or "", 400),
    }


async def _tool_cost_breakdown(args: dict) -> Any:
    """cost_breakdown → 整机方案成本结构 digest（L6 底盘 / KP 关键件 / 总成本）。"""
    plan = args.get("plan")
    if not isinstance(plan, dict):
        return {"error": "缺 plan 对象"}
    summary = plan.get("summary") or {}
    if not isinstance(summary, dict):
        return {"error": "plan 缺少 summary 成本摘要"}
    if summary.get("total_cost") is None and summary.get("l6_cost") is None and summary.get("kp_cost") is None:
        return {"error": "plan 缺少成本摘要，请先通过 build_plan 生成方案"}
    return {
        "name": plan.get("name") or "",
        "model": plan.get("model") or "",
        "series": plan.get("series") or "",
        "form": plan.get("form") or "",
        "cost": {
            "l6_cost": summary.get("l6_cost"),
            "kp_cost": summary.get("kp_cost"),
            "total_cost": summary.get("total_cost"),
            "currency": summary.get("currency") or "RMB",
            "rates": summary.get("rates") or {},
        },
        "parts_count": summary.get("parts_count"),
        "kp_count": summary.get("kp_count"),
        "unmatched_count": summary.get("unmatched_count"),
        "unmatched": plan.get("unmatched") or [],
    }


async def _tool_quote_draft(args: dict) -> Any:
    """quote_draft → 整机方案报价草稿 digest（基准成本 / 建议毛利 / 含税报价）。"""
    plan = args.get("plan")
    if not isinstance(plan, dict):
        return {"error": "缺 plan 对象"}
    summary = plan.get("summary") or {}
    if not isinstance(summary, dict):
        return {"error": "plan 缺少 summary 成本摘要"}
    total_cost = float(summary.get("total_cost") or 0)
    if total_cost <= 0:
        return {"error": "plan 缺少有效总成本，请先通过 build_plan 生成方案"}
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            margin_rate = float(repo.get_value("profit_margin", 0.1) or 0.1)
        finally:
            repo.close()
    except Exception:
        margin_rate = 0.1
    return {
        "draft": {
            "name": f"方案-{plan.get('name') or plan.get('model') or '未命名'}",
            "model": plan.get("model") or "",
            "series": plan.get("series") or "",
            "form": plan.get("form") or "",
            "base_cost": round(total_cost, 2),
            "margin_pct": round(margin_rate * 100, 2),
            "final_price": round(total_cost * (1 + margin_rate), 2),
            "currency": summary.get("currency") or "RMB",
            "status": "draft",
            "note": "草稿未落库，需用户确认后才能转为正式报价单",
        },
        "cost": {
            "l6_cost": summary.get("l6_cost"),
            "kp_cost": summary.get("kp_cost"),
            "total_cost": summary.get("total_cost"),
        },
    }


def _search_cases_handler(case_cfg: dict):
    """构造 search_cases 工具 handler（闭包捕获用户可配的 case_source/top_k/match）。

    底层复用 CaseProvider（InternalBomCaseProvider 查 rules.bom_cases，只读不入库）。
    case_cfg 来自 llm_agent 节点 config（画布抽屉可改）：case_source / case_top_k / case_match。
    """
    top_k_default = int(case_cfg.get("case_top_k") or 2)
    provider_cfg = {
        "case_source": case_cfg.get("case_source", "internal"),
        "case_match": case_cfg.get("case_match", "tags_keyword"),
    }

    async def _h(args: dict) -> Any:
        from app.services.case_provider import get_case_provider
        provider = get_case_provider(provider_cfg)
        query = args.get("query") or args.get("requirement") or ""
        tags = args.get("tags") if isinstance(args.get("tags"), list) else None
        try:
            top_k = int(args.get("top_k") or top_k_default)
        except (TypeError, ValueError):
            top_k = top_k_default
        cases = provider.retrieve(query, tags=tags, top_k=top_k)
        return {"count": len(cases), "cases": cases}
    return _h

# ── 数据工具：query_cpq_data —— CPQ 业务数据查询（统计/分布/排行/趋势/重点商机）──
_DATA_PERIODS = ("week", "last_week", "month", "half_year", "year", "custom")
_DATA_FOCUS = ("all", "kpi", "platform", "chassis", "rank", "trend", "highlights", "profit", "opportunities")

def _normalize_period(value: Any) -> str:
    """仅接受数据工具枚举值；非法输入回退默认 week。"""
    raw = str(value or "week").strip()
    return raw if raw in _DATA_PERIODS else "week"

def _normalize_focus(value: Any) -> str:
    """仅接受数据工具枚举值；非法输入回退默认 all。"""
    raw = str(value or "all").strip()
    return raw if raw in _DATA_FOCUS else "all"


def _resolve_data_range(period: str, start: Any, end: Any):
    """把查询参数映射为 dashboard summary 的 (period, start, end)。"""
    from datetime import datetime, timedelta
    today = datetime.now()
    if period == "last_week":
        # 上周一 ~ 上周日（与驾驶舱「上周」预设算法一致）
        s = today - timedelta(days=today.weekday() + 7)
        e = s + timedelta(days=6)
        return "custom", s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
    if period == "half_year":
        return "custom", (today - timedelta(days=180)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if period == "custom":
        return "custom", start, end
    return period, None, None


def _fmt_data_text(summary: dict, focus: str = "all") -> str:
    """把 dashboard summary dict 转紧凑文本，作为查询结果给 LLM。"""
    if not isinstance(summary, dict):
        return "(无数据)"
    if focus == "profit":
        boxes = ((summary.get("charts") or {}).get("chart5") or {}).get("boxes") or []
        if not boxes:
            return "【机型利润率】暂无利润率样本。"
        lines = ["【机型利润率（按中位数降序，% 为报价单利润率百分点）】"]
        for b in boxes[:12]:
            name = b.get("name") or "未命名机型"
            med = b.get("median")
            n = b.get("n")
            lines.append(f"{name}：中位 {med}%（样本 {n}）" if med is not None else f"{name}：样本 {n}")
        return "\n".join(lines)
    label = summary.get("period_label") or ""
    kpi = summary.get("kpi") or {}
    parts = [f"【{label}】"]
    if focus in ("all", "kpi"):
        parts.append(
            f"核心指标：总商机 {kpi.get('total_opportunities', 0)}、总配置 {kpi.get('total_configs', 0)}、"
            f"新增商机 {kpi.get('new_opportunities', 0)}、新增配置 {kpi.get('new_configs', 0)}"
        )
    if focus in ("all", "platform"):
        plats = (summary.get("structure") or {}).get("platforms") or []
        if plats:
            parts.append("平台分布：" + "、".join(f"{p.get('name') or '未分类'} {p.get('count', 0)} 个" for p in plats))
    if focus in ("all", "chassis"):
        chassis = (summary.get("structure") or {}).get("chassis") or []
        if chassis:
            parts.append("机箱分布：" + "、".join(f"{c.get('name') or '未分类'} {c.get('count', 0)} 个" for c in chassis))
    if focus in ("all", "rank"):
        top = (summary.get("sales_rank") or {}).get("top") or []
        if top:
            parts.append("销售排行：" + "、".join(
                f"{t.get('name')} {t.get('count', 0)} 个" + (f"（成交 {t.get('won', 0)}）" if t.get("won") else "")
                for t in top
            ))
    if focus in ("all", "trend"):
        series = ((summary.get("charts") or {}).get("chart1") or {}).get("total_series") or []
        if series:
            parts.append(f"逐期趋势（{len(series)} 期）：" + "、".join(f"{d.get('date')}:{d.get('value')}" for d in series))
    return "\n".join(p for p in parts if p)


def _query_opportunities(args: dict) -> str:
    """查商机列表明细（最近 N 条，默认 20，上限 50）。"""
    try:
        limit = int(args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    limit = max(1, min(limit or 20, 50))
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            items, total = repo.list_opportunities(False, 1, limit, sort_by="updated_at", sort_order="desc")
        finally:
            repo.close()
    except Exception as e:  # noqa: BLE001
        logger.exception("商机列表查询失败")
        return f"商机列表查询失败：{e}"
    if not items:
        return "【商机列表】暂无商机。"
    lines = [f"【商机列表（最近 {len(items)} 条 / 共 {total} 条）】"]
    for it in items:
        lines.append(
            f"{it.get('customer_name') or '未命名'} / 销售 {it.get('sales_person') or '-'} / "
            f"{it.get('platform_type') or '-'} / {it.get('chassis_form') or '-'} / "
            f"{it.get('purchase_qty') or 0} 台 / {it.get('config_count') or 0} 配置 / "
            f"状态 {it.get('status') or '-'} / 结果 {it.get('result') or '-'}"
        )
    return "\n".join(lines)


def _query_cpq_data_sync(args: dict) -> str:
    """执行 CPQ 业务数据查询（同步 DB 调用，调用方经 asyncio.to_thread）。"""
    args = args or {}
    period = _normalize_period(args.get("period") or "week")
    focus = _normalize_focus(args.get("focus") or "all")
    start = args.get("start")
    end = args.get("end")
    if period not in _DATA_PERIODS:
        return f"不支持的周期：{period}（可选 {'/'.join(_DATA_PERIODS)}）"
    if focus not in _DATA_FOCUS:
        focus = "all"
    if focus == "highlights":
        limit = 0
        try:
            limit = int(args.get("limit") or 0)
        except (TypeError, ValueError):
            limit = 0
        if not limit:
            limit = 10
        limit = max(1, min(limit, 50))
        from app.api.dashboard import get_highlights
        rows = get_highlights(limit)
        if not rows:
            return "【近期重点商机】近半年内暂无重点商机。"
        lines = [
            f"{r['customer_name'] or '未命名'} / {r['platform_type'] or '-'} / {r['chassis_form'] or '-'} / "
            f"{r['purchase_qty'] or 0} 台 / {r['config_count']} 配置 / {r['result'] or '-'}"
            for r in rows
        ]
        return f"【近期重点商机（近半年，按台数 Top {len(rows)}）】\n" + "\n".join(lines)
    if focus == "profit":
        # 利润率不限周期（chart5 取全量利润样本），period 仅作占位
        from app.api.dashboard import get_dashboard_summary
        summary = get_dashboard_summary(period="month", start=None, end=None)
        return _fmt_data_text(summary, "profit")
    if focus == "opportunities":
        return _query_opportunities(args)
    if period == "custom" and (not start or not end):
        return "自定义区间需要同时提供 start 与 end（YYYY-MM-DD）"
    rp, rs, re = _resolve_data_range(period, start, end)
    try:
        from app.api.dashboard import get_dashboard_summary
        summary = get_dashboard_summary(period=rp, start=rs, end=re)
    except Exception as e:  # noqa: BLE001 —— 查询结果要给 LLM 看，异常转文本
        logger.exception("query_cpq_data 查询失败")
        return f"统计查询失败：{e}"
    return _fmt_data_text(summary, focus)


async def _tool_query_cpq_data(args: dict) -> Any:
    """query_cpq_data 工具 handler：查 CPQ 业务数据（周期统计/分布/排行/趋势/重点商机）。"""
    return await asyncio.to_thread(_query_cpq_data_sync, args or {})





# ── 服务器机型只读工具：真实读取 server_types / server_models ──

async def _server_catalog_repo():
    from app.repository.server_catalog_repo import ServerCatalogRepository
    return ServerCatalogRepository()


async def _tool_list_server_types(args: dict) -> Any:
    """list_server_types -> 服务器类型目录 digest。"""
    repo = await _server_catalog_repo()
    types = await asyncio.to_thread(repo.list_types)
    digest = [{
        "id": t.get("id"),
        "name": t.get("name") or "",
        "description": _truncate(t.get("description") or "", 300),
    } for t in types]
    return {"count": len(digest), "server_types": digest}


async def _tool_list_server_models(args: dict) -> Any:
    """list_server_models -> 机型目录 digest（名称/系列/形态/盘位/状态）。"""
    repo = await _server_catalog_repo()
    type_id = args.get("server_type_id")
    try:
        if type_id not in (None, ""):
            type_id = int(type_id)
    except (TypeError, ValueError):
        return {"error": "server_type_id 必须是整数"}
    models = await asyncio.to_thread(
        repo.list_models,
        type_id=type_id,
        series=args.get("series"),
        form=args.get("form"),
        published_only=bool(args.get("published_only")),
    )
    digest = []
    for m in models:
        bc = m.get("base_config") or {}
        digest.append({
            "id": m.get("id"),
            "name": m.get("name") or "",
            "server_type_id": m.get("server_type_id"),
            "use": m.get("use") or "",
            "description": _truncate(m.get("description") or "", 300),
            "lifecycle_status": m.get("lifecycle_status") or "",
            "is_published": bool(m.get("is_published")),
            "series": bc.get("series") or "",
            "form": bc.get("form") or "",
            "bays": bc.get("bays"),
        })
    return {"count": len(digest), "server_models": digest}


async def _tool_get_server_model(args: dict) -> Any:
    """get_server_model -> 单个机型详情 digest（含产品内容/配置变体）。"""
    raw_id = args.get("server_model_id") or args.get("id")
    if raw_id in (None, ""):
        return {"error": "缺 server_model_id"}
    try:
        model_id = int(raw_id)
    except (TypeError, ValueError):
        return {"error": "server_model_id 必须是整数"}
    repo = await _server_catalog_repo()
    m = await asyncio.to_thread(repo.get_model, model_id)
    if not m:
        return {"error": f"未找到机型: {model_id}"}
    bc = m.get("base_config") or {}
    configs = m.get("configs") or []
    import json
    pc = m.get("product_content")
    product_content_text = None
    if pc is not None:
        try:
            product_content_text = _truncate(json.dumps(pc, ensure_ascii=False), 1200)
        except Exception:
            product_content_text = _truncate(str(pc), 1200)
    return {
        "id": m.get("id"),
        "name": m.get("name") or "",
        "server_type_id": m.get("server_type_id"),
        "use": m.get("use") or "",
        "description": _truncate(m.get("description") or "", 800),
        "lifecycle_status": m.get("lifecycle_status") or "",
        "is_published": bool(m.get("is_published")),
        "series": bc.get("series") or "",
        "form": bc.get("form") or "",
        "bays": bc.get("bays"),
        "product_content_text": product_content_text,
        "configs": [{
            "id": c.get("id"),
            "name": c.get("name") or "",
            "series": c.get("series") or "",
            "form": c.get("form") or "",
            "bays": c.get("bays"),
        } for c in configs],
    }


_SERVER_TYPE_WRITE_FIELDS = {"name", "description", "sort_order", "showcase_config"}
_SERVER_MODEL_WRITE_FIELDS = {
    "name", "server_type_id", "base_config_id", "sort_order",
    "description", "image_url", "lifecycle_status", "product_content", "is_published",
}
_LIFECYCLE_STATUSES = {"new", "active", "eol", "discontinued"}


def _server_type_update_payload(args: dict) -> dict:
    updates = {k: args[k] for k in _SERVER_TYPE_WRITE_FIELDS if k in args and args[k] is not None}
    if "name" in updates and not str(updates["name"]).strip():
        raise ValueError("name 不能为空")
    if "sort_order" in updates:
        try:
            updates["sort_order"] = int(updates["sort_order"])
        except (TypeError, ValueError):
            raise ValueError("sort_order 必须是整数")
    if not updates:
        raise ValueError("没有可更新的服务器类型字段")
    return updates


def _server_model_update_payload(args: dict) -> dict:
    updates = {k: args[k] for k in _SERVER_MODEL_WRITE_FIELDS if k in args and args[k] is not None}
    if "name" in updates and not str(updates["name"]).strip():
        raise ValueError("name 不能为空")
    for key in ("server_type_id", "base_config_id", "sort_order"):
        if key in updates:
            try:
                updates[key] = int(updates[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} 必须是整数")
    if "lifecycle_status" in updates and updates["lifecycle_status"] not in _LIFECYCLE_STATUSES:
        raise ValueError("lifecycle_status 只能是 new/active/eol/discontinued")
    if "product_content" in updates and not isinstance(updates["product_content"], (dict, list)):
        raise ValueError("product_content 必须是对象或数组")
    if not updates:
        raise ValueError("没有可更新的机型字段")
    return updates


async def _tool_update_server_type(args: dict) -> Any:
    """update_server_type -> 生成服务器类型/产品系列内容草稿，不直接落库。"""
    raw_id = args.get("server_type_id") or args.get("id")
    if raw_id in (None, ""):
        return {"error": "缺 server_type_id"}
    try:
        type_id = int(raw_id)
    except (TypeError, ValueError):
        return {"error": "server_type_id 必须是整数"}
    try:
        updates = _server_type_update_payload(args)
    except ValueError as e:
        return {"error": str(e)}
    repo = await _server_catalog_repo()
    before = await asyncio.to_thread(repo.get_type, type_id)
    if not before:
        return {"error": f"服务器类型不存在: {type_id}"}
    return {
        "server_type_id": type_id,
        "updates": updates,
        "before": {
            "id": before.get("id"),
            "name": before.get("name") or "",
            "description": _truncate(before.get("description") or "", 300),
        },
        "message": "已生成服务器类型/产品系列内容草稿，等待审批后落库",
    }


async def _tool_update_server_model(args: dict) -> Any:
    """update_server_model -> 生成机型内容草稿，不直接落库。"""
    raw_id = args.get("server_model_id") or args.get("id")
    if raw_id in (None, ""):
        return {"error": "缺 server_model_id"}
    try:
        model_id = int(raw_id)
    except (TypeError, ValueError):
        return {"error": "server_model_id 必须是整数"}
    try:
        updates = _server_model_update_payload(args)
    except ValueError as e:
        return {"error": str(e)}
    repo = await _server_catalog_repo()
    before = await asyncio.to_thread(repo.get_model, model_id)
    if not before:
        return {"error": f"机型不存在: {model_id}"}
    return {
        "server_model_id": model_id,
        "updates": updates,
        "before": {
            "id": before.get("id"),
            "name": before.get("name") or "",
            "server_type_id": before.get("server_type_id"),
            "lifecycle_status": before.get("lifecycle_status") or "",
            "is_published": bool(before.get("is_published")),
        },
        "message": "已生成机型内容草稿，等待审批后落库",
    }



