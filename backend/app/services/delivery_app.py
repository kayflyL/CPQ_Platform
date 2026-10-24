# -*- coding: utf-8 -*-
"""delivery_app —— 交付工作流（成本表 → 报价单）的事务应用声明。

首个在 transaction_engine 内核上登记的应用（import 即注册）。本模块只声明三件事：
探针表（各节点产物是否已落，查业务真实表）、旗标表（工具事实→状态槽）、案台事实行
（大脑每轮看的现场）。业务实现唯一出处 = delivery_core（与页面同源）；编排逻辑零行——
顺序在 DB 流节点，推进在内核。
"""
from __future__ import annotations

import logging

from app.services.transaction_engine import TransactionApp, register

logger = logging.getLogger(__name__)

FLOW_KEY = "delivery_to_quotation"
STATE_SLOT = "delivery_flow"  # 沿用首版槽名（旗标可现算重得，无需迁移）


# ── 域事实（案台的交付侧）─────────────────────────────────────────────────


def _thread_opportunity(thread_id: str) -> dict:
    """线程绑定商机（须真实存在——悬空绑定视为未绑定）。"""
    from app.repository.assistant_repo import AssistantRepository
    repo = AssistantRepository()
    try:
        thr = repo.get_thread(thread_id) or {}
    finally:
        repo.close()
    opp_id = str(thr.get("opportunity_id") or "")
    if not opp_id:
        return {}
    info = {"opportunity_id": opp_id}
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        orr = OpportunityRepository()
        try:
            opp = orr.get_opportunity(opp_id) or {}
        finally:
            orr.close()
        if not opp:
            return {}
        info["customer_name"] = str(opp.get("customer_name") or "")
    except Exception:
        logger.exception("案台探针读商机失败 opp=%s", opp_id)
        return {}
    return info


def _price_field_strategy() -> dict:
    """目标层的价格字段策略（字段 key=l6_price/kp_price，ask=true 的列参与缺价闸）。
    未配置＝空表＝不拦（兼容老流配置；价格必填完全由画布字段策略驱动）。"""
    from app.services.transaction_engine import load_flow_rules
    try:
        rules = load_flow_rules(FLOW_KEY)
    except Exception:
        logger.exception("价格字段策略读取失败 flow=%s", FLOW_KEY)
        return {}
    out: dict = {}
    for s in rules.get("steps") or []:
        for f in s.get("fields") or []:
            k = str(f.get("key") or "")
            if k in ("l6_price", "kp_price"):
                out[k] = bool(f.get("ask"))
    return out


def _missing_prices(configs: list, strategy: dict) -> dict:
    """按字段策略数缺价。KP=逐行（kp_rows base_price 空/0 视为缺）；
    L6=配置级整价（l6_cost——页面成本核算同口径：L6 是整机一口价，
    l6_rows 只是明细展示，2026-10-22 用户定）。策略里没开的列不数。"""
    kp = l6 = 0
    for c in configs or []:
        if not isinstance(c, dict):
            continue
        if strategy.get("kp_price"):
            kp += sum(1 for r in (c.get("kp_rows") or []) if not r.get("base_price"))
        if strategy.get("l6_price") and not c.get("l6_cost"):
            l6 += 1
    return {"kp_missing": kp, "l6_missing": l6}


def _latest_cost_sheet(opp_id: str, strategy: dict = None) -> dict:
    """商机当前成本表（list_cost_sheets 排序：current > draft > archived，取首个非归档）。
    带字段策略时现算缺价行数与 price_ready（完成探针 sheet.price_ready 用）。"""
    from app.repository.flow_repo import FlowRepository
    repo = FlowRepository()
    try:
        rows = repo.list_cost_sheets(opp_id) or []
    finally:
        repo.close()
    strategy = strategy or {}
    for r in rows:
        if str(r.get("status") or "") == "archived":
            continue
        cfgs = r.get("configs")
        cfg_list = cfgs if isinstance(cfgs, list) else []
        miss = _missing_prices(cfg_list, strategy)
        ready = (not strategy) or (miss["kp_missing"] == 0 and miss["l6_missing"] == 0)
        return {"sheet_id": r.get("id"), "name": r.get("name"), "status": r.get("status"),
                "config_count": len(cfg_list),
                "kp_missing": miss["kp_missing"], "l6_missing": miss["l6_missing"],
                "price_ready": ready}
    return {}


def _active_quotation(user: dict, opp_id: str) -> dict:
    from app.services import delivery_core as dcore
    try:
        q = dcore.margin_resolve_quotation(user, opp_id=opp_id, quotation_id="")
    except Exception:
        logger.exception("案台探针读报价单失败 opp=%s", opp_id)
        return {}
    if not q.get("ok"):
        return {}
    ver = str(q.get("version") or "1").lstrip("vV") or "1"
    return {"quotation_id": q.get("quotation_id"), "name": q.get("quotation_name") or "",
            "version": ver}


def _staged_attachments(user: dict) -> list:
    if not isinstance(user, dict) or not user.get("user_id"):
        return []
    try:
        from app.repository.feed_repo import FeedRepository
        repo = FeedRepository()
        try:
            rows = repo.list_staged_attachments(str(user["user_id"])) or []
        finally:
            repo.close()
    except Exception:
        logger.exception("案台探针读暂存附件失败")
        return []
    return [{"attachment_id": r.get("attachment_id"),
             "filename": r.get("original_filename") or ""} for r in rows[:3]]


def _latest_bom_scheme(opp_id: str) -> dict:
    """商机当前方案表（draft/current 优先，archived 不计）。"""
    from app.repository.flow_repo import FlowRepository
    repo = FlowRepository()
    try:
        rows = repo.list_bom_schemes(opp_id) or []
    finally:
        repo.close()
    for r in rows:
        if str(r.get("status") or "") == "archived":
            continue
        cfgs = r.get("configs")
        return {"bom_scheme_id": r.get("id"), "name": r.get("name"),
                "status": r.get("status"), "config_count": len(cfgs) if isinstance(cfgs, list) else 0}
    return {}


def _context(thread_id: str, user: dict) -> dict:
    """交付案台域事实：商机 / 成本表 / 报价单 / 方案表 / 会话暂存附件。"""
    opp = _thread_opportunity(thread_id)
    opp_id = opp.get("opportunity_id") or ""
    strategy = _price_field_strategy()
    return {
        "opp": opp,
        "sheet": _latest_cost_sheet(opp_id, strategy) if opp_id else {},
        "scheme": _latest_bom_scheme(opp_id) if opp_id else {},
        "quotation": _active_quotation(user, opp_id) if opp_id else {},
        "staged": _staged_attachments(user),
    }


# ── 探针表（键 = DB 流节点 id；节点序里第一个不过者 = 当前步骤）──────────────



# ── 案台事实行 ────────────────────────────────────────────────────────────


def _digest_lines(view: dict) -> list:
    lines = []
    staged = view.get("staged") or []
    if staged:
        for a in staged:
            lines.append(f"· 会话暂存附件: {a['filename']}（attachment_id={a['attachment_id']}）")
    else:
        lines.append("· 会话暂存附件: 无")
    opp = view.get("opp") or {}
    if opp.get("opportunity_id"):
        lines.append(f"· 商机: 已绑定（customer_name={opp.get('customer_name') or '未知'}，"
                     f"opportunity_id={opp['opportunity_id']}）")
    else:
        lines.append("· 商机: 未绑定")
    sh = view.get("sheet") or {}
    if sh:
        miss = []
        if sh.get("kp_missing"):
            miss.append(f"KP {sh['kp_missing']} 行")
        if sh.get("l6_missing"):
            miss.append(f"L6 整价 {sh['l6_missing']} 个配置")
        tail = (f"，缺价：{'、'.join(miss)}——停下用 ask_user_card 出补价表单卡向用户要价"
                "（L6 按配置要一个整机价，KP 按行：配置名+Catalogue；"
                "聊天报价用 set_cost_prices 回写，或让用户在成本表产物卡编辑模式自补），补齐才继续"
                if miss else "，价格齐全")
        lines.append(f"· 成本表: 「{sh.get('name')}」sheet_id={sh.get('sheet_id')}，"
                     f"状态 {sh.get('status')}，{sh.get('config_count')} 个配置{tail}")
    else:
        lines.append("· 成本表: 无")
    sc = view.get("scheme") or {}
    if sc:
        lines.append(f"· 方案表: 「{sc.get('name')}」bom_scheme_id={sc.get('bom_scheme_id')}，"
                     f"状态 {sc.get('status')}，{sc.get('config_count')} 个配置")
    else:
        lines.append("· 方案表: 无")
    q = view.get("quotation") or {}
    margin = (view.get("flags") or {}).get("margin") or {}
    if q:
        if margin.get("pct") is not None:
            lines.append(f"· 报价单: {q['quotation_id']}（已执行加价 {margin['pct']:g}%）")
        else:
            lines.append(f"· 报价单: {q['quotation_id']}（未记录加价）")
    else:
        lines.append("· 报价单: 无")
    share = (view.get("flags") or {}).get("share") or {}
    lines.append("· 分享链接: " + (str(share.get("share_path") or "已出件")
                                if share else "无"))
    return lines


# ── 旗标表 ────────────────────────────────────────────────────────────────
# 工具事实 → 状态旗标的映射已声明化：flow 127 的 graph.flag_rules
# （import_cost_sheet→lane=cost、import_bom_scheme→lane=scheme+scheme、
#   derive_cost_from_scheme→lane=scheme+derived、set_quote_margin→margin、
#   share_quote→share）。内核 apply_facts 按声明表回写——分支分流零代码建。
# 历史注（2026-10-22 架构修）：手写钩子 _flags_from_facts 已删，
# 新增/调整分流旗标改在流程配置里改声明表，不再写 Python。

APP = TransactionApp(
    flow_key=FLOW_KEY,
    state_slot=STATE_SLOT,
    context_fn=_context,
    digest_lines=_digest_lines,
)
register(APP)
