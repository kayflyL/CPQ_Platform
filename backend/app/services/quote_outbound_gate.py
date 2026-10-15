"""报价外发审批闸门 — 三口一闸的共享逻辑。

出口：客户版导出冻结（quotations.export）、平台内发送（portal 发送端点）、
规格书 PDF（前端前置检查；服务端 print-pdf 是通用渲染器，不区分对内/外发，不挂闸）。
语义：批准 = 对 content_hash（报价行+单头关键值）的「外发许可」，改价 → 失配 → 失效重批。
责任总监由调度面板 approval 节点规则按业务路由（FlowAssignmentRule），规则未命中降级广播。
"""
import hashlib
import json
from datetime import datetime
from typing import Optional

from fastapi import HTTPException

from app.api.deps import user_has_permission
from app.repository.feed_user_repo import FeedUserRepository
from app.repository.flow_repo import FlowRepository, assignee_to_uid
from app.repository.pricing_approval_repo import PricingApprovalRepository, waited_hours
from app.repository.quotation_repo import QuotationRepository
from app.repository.strategy_repo import StrategyRepository

# 调度面板里的审批节点键（FlowAssignmentRule.node_key）
APPROVAL_NODE_KEY = "approval"
# 免外发审批权限（设置→角色可勾；admin 恒有；director 种子自带）
BYPASS_PERMISSION = "action.quote.export_bypass_approval"


def can_bypass(user: Optional[dict]) -> bool:
    """持免审批权限者跳过外发审批闸（导出/发送/分享直通）。"""
    return bool(user) and user_has_permission(user or {}, BYPASS_PERMISSION)


def gate_config() -> Optional[dict]:
    """读策略中心 margin_alert：审批红线 approval_threshold + 超时提醒 approval_remind_hours。
    未配置/未启用 → None（闸门随告警开关走）。"""
    try:
        repo = StrategyRepository()
        try:
            rows = repo.list(domain="pricing", status="active", type="margin_alert")
        finally:
            repo.close()
    except Exception:
        return None
    if not rows:
        return None
    body = rows[0].get("body")
    if not isinstance(body, dict) or not body.get("enabled"):
        return None
    try:
        threshold = float(body.get("approval_threshold", body.get("threshold")))
    except (TypeError, ValueError):
        return None
    try:
        remind_hours = float(body.get("approval_remind_hours", 24) or 24)
    except (TypeError, ValueError):
        remind_hours = 24.0
    return {"approval_threshold": threshold, "remind_hours": remind_hours}


def overall_margin(quotation) -> Optional[float]:
    """报价单整体毛利率（后端权威）：导出成本快照的综合加权 marginPct，
    缺快照时回落报价单 profit_margin 列。"""
    snap = quotation.cost_snapshot if isinstance(quotation.cost_snapshot, dict) else None
    if snap:
        try:
            overall = (snap.get("totals") or {}).get("marginPct")
            if overall is not None:
                return float(overall)
        except (TypeError, ValueError):
            pass
    try:
        return float(quotation.profit_margin) if quotation.profit_margin is not None else None
    except (TypeError, ValueError):
        return None


def compute_content_hash(repo: QuotationRepository, quotation) -> str:
    """内容指纹：报价行（配置/品类/型号/描述/数量/底价/售价/毛利/币种）+ 单头总价的
    稳定序列化 sha256 前 16 位。任何价格/数量/配置变化都会改变指纹。"""
    items = repo.get_items(quotation.quotation_id)
    rows = sorted(
        (
            [
                (i.config_name or ""), (i.category or ""), (i.catalogue or ""),
                (i.description or ""), str(i.qty or 0),
                repr(round(float(i.base_price or 0), 4)), repr(round(float(i.final_price or 0), 4)),
                repr(round(float(i.profit_margin or 0), 4)), (i.currency or "RMB"),
            ]
            for i in items
        ),
        key=lambda r: r[0:5],
    )
    payload = json.dumps(
        {
            "total": repr(round(float(quotation.total_price or 0), 4)),
            "version": quotation.version,
            "rows": rows,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def route_director(opportunity_id: str) -> dict:
    """按调度面板 approval 节点规则指派唯一总监：业务默认规则 → '*' 兜底。
    无规则 → 空 assigned = 广播降级（全体持审批权限者先到先批）。"""
    flow_repo = FlowRepository()
    try:
        name = (flow_repo.resolve_node_assignee(opportunity_id, APPROVAL_NODE_KEY) or "").strip()
    finally:
        flow_repo.close()
    if not name:
        return {"assigned_uid": "", "assigned_name": "", "basis": "broadcast",
                "basis_text": "无路由规则，广播全体审批人（先到先批）"}
    return {"assigned_uid": assignee_to_uid(name) or "", "assigned_name": name,
            "basis": "rule", "basis_text": "调度规则指派（业务承接）"}


def approver_accounts() -> list:
    """全体持「报价审批」权限的账号（uid+姓名）——转交选择器候选。"""
    user_repo = FeedUserRepository()
    try:
        users = user_repo.list_all()
    finally:
        user_repo.close()
    return [{"user_id": u.get("user_id") or "", "name": u.get("name") or ""}
            for u in users
            if user_has_permission(u, "action.flow.approve.pricing")]


def approver_uids() -> list:
    return [a["user_id"] for a in approver_accounts() if a["user_id"]]


def approval_state(quotation, user: Optional[dict] = None) -> dict:
    """报价单当前外发审批状态（工作台弹窗/闸门共用）：state ∈ none|pending|approved|stale|rejected。"""
    config = gate_config()
    threshold = (config or {}).get("approval_threshold", 0.0)
    repo = QuotationRepository()
    try:
        content_hash = compute_content_hash(repo, quotation)
    finally:
        repo.close()
    approval_repo = PricingApprovalRepository()
    try:
        latest = approval_repo.latest_for_quotation(quotation.quotation_id) or {}
    finally:
        approval_repo.close()
    status = latest.get("status") or ""
    if status == "approved" and latest.get("content_hash") != content_hash:
        state = "stale"  # 批准后内容已变更 → 许可失效，须重批
    else:
        state = status or "none"
    return {
        "state": state,
        "approval": latest or None,
        "content_hash": content_hash,
        "margin_pct": overall_margin(quotation),
        "threshold": threshold,
        "remind_hours": (config or {}).get("remind_hours", 24.0),
        "waited_hours": round(waited_hours(latest.get("created_at")), 1) if status == "pending" else 0,
        "route": route_director(quotation.opportunity_id),
        "bypass": can_bypass(user),
    }


def create_outbound_approval(opportunity_id: str, customer_name: str, quotation,
                             requested_by: str, note: str = "",
                             notify=None) -> dict:
    """发起外发审批：路由责任总监 → 建单 → 通知责任人（广播降级时通知全体审批人）。"""
    repo = QuotationRepository()
    try:
        content_hash = compute_content_hash(repo, quotation)
    finally:
        repo.close()
    margin = overall_margin(quotation) or 0.0
    config = gate_config()
    threshold = (config or {}).get("approval_threshold", 0.0)
    reason = "low_margin" if (margin and threshold and margin < threshold) else "outbound"
    route = route_director(opportunity_id)
    route_snapshot = json.dumps(route, ensure_ascii=False)
    approval_repo = PricingApprovalRepository()
    try:
        latest = approval_repo.latest_for_quotation(quotation.quotation_id) or {}
        if latest.get("status") == "pending":
            raise HTTPException(status_code=409, detail="该报价单已有待审批的外发申请，请等待审批结果")
        approval = approval_repo.create(
            opportunity_id=opportunity_id,
            quotation_id=quotation.quotation_id,
            margin_pct=margin,
            threshold=threshold,
            requested_by=requested_by,
            trigger_reason=reason,
            content_hash=content_hash,
            assigned_to=route["assigned_uid"],
            assigned_name=route["assigned_name"],
            route_snapshot=route_snapshot,
            request_note=note or "",
        )
    finally:
        approval_repo.close()
    if notify is not None:
        title = f"报价外发待审批：{customer_name} · 毛利率 {margin:.2f}%"
        body = f"{requested_by} 申请导出/发送报价单（v{quotation.version}）" + (
            f"，低于审批红线 {threshold:.0f}%" if reason == "low_margin" else "")
        if route["assigned_uid"]:
            notify([route["assigned_uid"]], "pricing_approval_requested", title,
                   body=body, opportunity_id=opportunity_id,
                   payload={"approval_id": approval.get("id"), "quotation_id": quotation.quotation_id})
        else:
            uids = [u for u in approver_uids()]
            if uids:
                notify(uids, "pricing_approval_requested", title,
                       body=body + "（无路由规则，先到先批）", opportunity_id=opportunity_id,
                       payload={"approval_id": approval.get("id"), "quotation_id": quotation.quotation_id})
    return approval


def ensure_outbound_approved(quotation, user: Optional[dict] = None) -> None:
    """外发闸门（冻结/发送/分享端点共用）：持有效许可（approved 且指纹一致）才放行，否则 409。
    持免审批权限（action.quote.export_bypass_approval，admin/director 种子自带）者直通。"""
    if can_bypass(user):
        return
    state = approval_state(quotation)
    s = state["state"]
    if s == "approved":
        return
    if s == "pending":
        raise HTTPException(
            status_code=409,
            detail=f"外发审批中（已等待 {state['waited_hours']:.0f} 小时，"
                   f"责任人 {state['approval'].get('assigned_name') or '全体审批人'}），批准后即可导出/发送")
    if s == "stale":
        raise HTTPException(status_code=409,
                            detail="报价内容在批准后已变更，外发许可失效——请重新发起审批")
    if s == "rejected":
        cmt = (state["approval"] or {}).get("comment") or ""
        raise HTTPException(status_code=409,
                            detail="最近一次外发审批被驳回" + (f"：{cmt}" if cmt else "，请调整后重新发起审批"))
    raise HTTPException(status_code=409,
                        detail="该报价单尚未取得外发许可——请在报价工作台导出处发起总监审批")


def maybe_escalate(rows: list, notify=None) -> None:
    """懒超时提醒：pending 且等待超过 remind_hours 且未升级过 → 再推一次责任人并标记。
    只在队列/状态读取时触发（无常驻调度器）；只提醒，绝不自动批/拒。"""
    config = gate_config()
    if not config or notify is None:
        return
    limit = config.get("remind_hours", 24.0)
    approval_repo = PricingApprovalRepository()
    try:
        for a in rows:
            if a.get("status") != "pending" or a.get("escalated_at"):
                continue
            if waited_hours(a.get("created_at")) < limit:
                continue
            title = (f"审批超时提醒：{a.get('opportunity_id')} 报价单已等待 "
                     f"{waited_hours(a.get('created_at')):.0f} 小时未审批")
            if a.get("assigned_to"):
                notify([a["assigned_to"]], "pricing_approval_requested", title,
                       body="该外发审批已超过提醒时限，请尽快处理",
                       opportunity_id=a.get("opportunity_id") or "",
                       payload={"approval_id": a.get("id"), "quotation_id": a.get("quotation_id")})
            else:
                uids = approver_uids()
                if uids:
                    notify(uids, "pricing_approval_requested", title,
                           body="该外发审批已超过提醒时限（广播单），请尽快处理",
                           opportunity_id=a.get("opportunity_id") or "",
                           payload={"approval_id": a.get("id"), "quotation_id": a.get("quotation_id")})
            approval_repo.mark_escalated(a.get("id"))
            a["escalated_at"] = "just-now"
    finally:
        approval_repo.close()
