"""统一门户 API — 业务商机详情页（/api/portal/opp/{opp_id}，设计：docs/协作流程方案/02-business-detail.md）。

可见性后端强制（真安全）：business 角色的时间线中间节点交付物按 field_visible 裁剪；
最终报价单仅在 exported_at（定稿）后返回。
"""
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pathlib import Path
from pydantic import BaseModel

from app.api.deps import get_current_user, require_admin, field_visible, user_has_permission, user_can_access_opportunity
from app.repository.flow_repo import FlowRepository
from app.repository.flow_card_repo import FlowCardRepository
from app.repository.feed_repo import FeedRepository
from app.repository.feed_user_repo import FeedUserRepository
from app.repository.opportunity_repo import OpportunityRepository
from app.repository.quotation_repo import QuotationRepository
from app.services.feed_hub import hub
from app.services.preview_data_loader import load_preview_data
from app.services.quote_service import QuoteService
from app.services.storage_adapter import get_storage, build_object_id, StorageError

logger = logging.getLogger(__name__)
router = APIRouter(tags=["portal"])

# 中间节点交付物默认锁住（business）；管理员可对角色放开（field_visible 体系）
_LOCKED_ARTIFACT_PERMS = {
    "boming": "field.flow.bom",
    "costing": "field.flow.cost",
}

_RETURN_PERMS = {
    "boming": "action.flow.return.boming",
    "costing": "action.flow.return.costing",
    "quoting": "action.flow.return.quoting",
}

_RETURN_TARGETS = {
    "boming": "requirement",
    "costing": "boming",
    "quoting": "costing",
}

_CARD_NODE_ROLE = {
    "requirement": "business",
    "boming": "te",
    "costing": "cost",
    "quoting": "quote",
}

_APPROVAL_NODES = [
    {"key": "basic", "label": "商机基本信息", "default_assignee": "业务"},
    {"key": "requirement", "label": "需求单", "default_assignee": "业务"},
    {"key": "boming", "label": "BOM单", "default_assignee": "技术支持"},
    {"key": "costing", "label": "成本核算", "default_assignee": "成本核算"},
    {"key": "quoting", "label": "报价单", "default_assignee": "市场报价"},
]

_ASSIGNEE_REQUIRED_DETAIL = "下游处理人未配置，请选择"


def _svc(opp_id: str, user: Optional[dict] = None) -> tuple[dict, dict]:
    """商机 + 流程（无流程自动建）；404 早退。"""
    opp_repo = OpportunityRepository()
    try:
        opp = opp_repo.get_opportunity(opp_id)
    finally:
        opp_repo.close()
    if not opp:
        raise HTTPException(status_code=404, detail="商机不存在")
    if user and not user_can_access_opportunity(user, opp):
        raise HTTPException(status_code=403, detail="无权查看该商机")
    flow_repo = FlowRepository()
    try:
        flow = flow_repo.get_or_create_flow(opp_id)
        flow_dict = flow.to_dict()
    finally:
        flow_repo.close()
    return opp, flow_dict


def _attach_entity_card(opp_id: str, entity_type: str, entity_id,
                        *, origin_node: str, current_node: str,
                        created_by: str = "", card_id: Optional[int] = None,
                        flow_status: str = "draft", assignee_name: str = None,
                        visible_upstream: bool = True) -> dict:
    repo = FlowCardRepository()
    try:
        if card_id:
            repo.link_entity(card_id, entity_type, entity_id, opportunity_id=opp_id)
            card = repo.update_card(card_id, current_node=current_node, flow_status=flow_status)
        else:
            card = repo.get_card_for_entity(opp_id, entity_type, entity_id)
            if not card:
                card = repo.ensure_card(
                    opp_id,
                    origin_node=origin_node,
                    current_node=current_node,
                    created_by=created_by,
                    assignee_name=assignee_name,
                    visible_upstream=visible_upstream,
                    flow_status=flow_status,
                )
            else:
                card = repo.update_card(card["id"], current_node=current_node, flow_status=flow_status)
            repo.link_entity(card["id"], entity_type, entity_id, opportunity_id=opp_id)
        return repo.get_card(card["id"]) or card
    finally:
        repo.close()


def _unlink_entity_card(opp_id: str, entity_type: str, entity_id) -> None:
    repo = FlowCardRepository()
    try:
        card = repo.get_card_for_entity(opp_id, entity_type, entity_id)
        if not card:
            return
        repo.unlink_entity(card["id"], entity_type, entity_id, opportunity_id=opp_id)
        repo.delete_card_if_empty(card["id"])
    finally:
        repo.close()


def _opp_summary(opp: dict, current_requirement: Optional[dict] = None) -> dict:
    slots = (current_requirement or {}).get("slots") or {}
    return {
        "opportunity_id": opp["opportunity_id"],
        "customer_name": opp.get("customer_name") or "",
        "sales_person": opp.get("sales_person") or "",
        "fae": opp.get("fae") or "",
        "quotation_person": opp.get("quotation_person") or "",
        "industry": opp.get("industry") or "",
        "delivery_region": opp.get("delivery_region") or "",
        "delivery_cycle": opp.get("delivery_cycle") or "",
        "order_type": opp.get("order_type") or "",
        "warranty_years": slots.get("warranty_years") or opp.get("warranty_years") or "",
        "platform_type": slots.get("platform_type") or opp.get("platform_type") or "",
        "chassis_form": slots.get("chassis_form") or opp.get("chassis_form") or "",
        "purchase_qty": slots.get("purchase_qty") or opp.get("purchase_qty") or 0,
        "result": opp.get("result") or "pending",
    }


def _lock_nodes(nodes: List[dict], user: dict) -> List[dict]:
    for n in nodes:
        perm = _LOCKED_ARTIFACT_PERMS.get(n.get("node_key"))
        if perm and not field_visible(user, perm):
            n["artifacts"] = {}
            n["locked"] = True
    return nodes


def _mask_quote_if_needed(quote: dict, user: dict) -> dict:
    if quote and not field_visible(user, "field.opportunity.quote_price"):
        from app.utils.price_mask import mask_price_fields
        return mask_price_fields(quote)
    return quote


def _approvals(flow: dict, nodes: List[dict], current_requirement: Optional[dict]) -> List[dict]:
    """从 flow + 时间线推导每个流程节点的审批人/审批状态。"""
    raw_current = flow.get("current_node") or "requirement"
    current_stage = "requirement" if raw_current == "assign" else raw_current
    stage_index = next((i for i, n in enumerate(_APPROVAL_NODES) if n["key"] == current_stage), 0)
    nodes_by_key: dict = {}
    for n in nodes:
        nodes_by_key.setdefault(n.get("node_key"), []).append(n)

    result = []
    for idx, node in enumerate(_APPROVAL_NODES):
        key = node["key"]
        events = nodes_by_key.get(key, [])
        assignee = (flow.get("assignees") or {}).get(key) or node["default_assignee"]

        if key == "basic":
            state = "done"
        elif key == "requirement":
            if current_requirement:
                state = "current" if stage_index <= idx else "done"
            else:
                # 无需求单记录但流程已推进过需求节点 → 视为已完成，避免一直显示“处理中”
                state = "done" if stage_index > idx else "current"
        elif key in {"boming", "costing", "quoting"}:
            if idx < stage_index:
                state = "done"
            elif idx == stage_index:
                state = "done" if (key == "quoting" and flow.get("status") == "done") else "current"
            else:
                state = "pending"
        else:
            state = "pending"

        latest = events[-1] if events else None
        has_return = bool(
            latest
            and latest.get("action") == "return"
            and key == current_stage
            and flow.get("status") == "returned"
        )
        status_label = {
            "pending": "待处理",
            "current": "处理中",
            "done": "已完成",
        }[state]
        if has_return:
            status_label = "已退回"

        result.append({
            "key": key,
            "label": node["label"],
            "assignee": assignee,
            "state": state,
            "status_label": status_label,
            "has_return": has_return,
            "latest_time": (latest or {}).get("created_at") or "",
            "latest_comment": (latest or {}).get("comment") or "",
            "latest_action": (latest or {}).get("action") or "",
        })
    return result


@router.get("/api/portal/opps")
def list_portal_opps(page: int = 1, page_size: int = 20, search: str = "",
                     sort_by: str = "updated_at", sort_order: str = "desc",
                     user: dict = Depends(get_current_user)):
    """门户商机卡片列表：商机摘要 + 流程当前节点（点进 /portal/{opp_id}）。

    流程/需求单批量查（一次 IN），避免逐商机 N+1；无需求单的商机只给流程节点。
    """
    view_all = user_has_permission(user, "page.opportunities_all")
    user_id = user.get("user_id") or ""
    personal_name = user.get("name") or ""
    opp_repo = OpportunityRepository()
    try:
        opps, total = opp_repo.list_opportunities(
            page=page, page_size=page_size, search=search,
            sales_person=None,
            owner_user_id=None if view_all else user_id,
            owner_sales_person=None if view_all else personal_name,
            sort_by=sort_by, sort_order=sort_order,
        )
        all_opps = opps
        if total > len(opps):
            all_opps, _ = opp_repo.list_opportunities(
                page=1, page_size=max(total, 1), search=search,
                sales_person=None,
                owner_user_id=None if view_all else user_id,
                owner_sales_person=None if view_all else personal_name,
                sort_by=sort_by, sort_order=sort_order,
            )
    finally:
        opp_repo.close()
    flow_repo = FlowRepository()
    try:
        flows = flow_repo.list_flows_bulk([o["opportunity_id"] for o in all_opps])
        reqs = flow_repo.list_current_requirements_bulk([o["opportunity_id"] for o in opps])
    finally:
        flow_repo.close()
    summary = {
        "total": total,
        "returned": sum(1 for f in flows.values() if f.get("status") == "returned"),
        "in_progress": sum(1 for f in flows.values() if f.get("current_node") in {"boming", "costing", "quoting"} and f.get("status") not in {"done", "returned"}),
        "done": sum(1 for f in flows.values() if f.get("status") == "done"),
    }
    cards = []
    for o in opps:
        oid = o["opportunity_id"]
        flow = flows.get(oid) or {}
        req = reqs.get(oid) or {}
        slots = req.get("slots") or {}
        cards.append({
            "opportunity_id": oid,
            "customer_name": o.get("customer_name") or "",
            "sales_person": o.get("sales_person") or "",
            "platform_type": slots.get("platform_type") or "",
            "chassis_form": slots.get("chassis_form") or "",
            "purchase_qty": slots.get("purchase_qty") or 0,
            "industry": o.get("industry") or "",
            "config_count": o.get("config_count") or 0,
            "result": o.get("result") or "pending",
            "created_at": o.get("created_at") or "",
            "updated_at": o.get("updated_at") or "",
            "current_node": flow.get("current_node") or "requirement",
            "flow_status": flow.get("status") or "running",
        })
    return {"cards": cards, "total": total, "summary": summary}


@router.get("/api/portal/opp/{opp_id}")
def get_portal_opp(opp_id: str, user: dict = Depends(get_current_user)):
    """商机基本信息（只读）+ 流程状态。"""
    opp, flow = _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        reqs = flow_repo.list_requirements(opp_id)
        current = next((r for r in reqs if r["status"] == "current"), None)
    finally:
        flow_repo.close()
    return {
        "opportunity": _opp_summary(opp, current),
        "flow": flow,
    }


def _current_cost_sheet_for_quote(cost_sheets, selected):
    """挑选报价工作台应展示的当前成本表。

    优先选与当前报价单同源的 current 成本表；没有匹配时退回第一张 current 成本表。
    历史/手工报价单没有成本表时返回 None，由旧报价单预览作为兜底。
    """
    if not cost_sheets:
        return None
    selected_id = getattr(selected, "quotation_id", None)
    for sheet in cost_sheets:
        if sheet.get("status") != "current":
            continue
        if selected_id and sheet.get("quotation_id") == selected_id:
            return sheet
    return next((s for s in cost_sheets if s.get("status") == "current"), None)


def _current_bom_scheme_for_sheet(bom_schemes, cost_sheet):
    """根据成本表回找其 BOM 方案；找不到时退回第一张 current 方案。"""
    if not bom_schemes:
        return None
    bom_id = cost_sheet.get("bom_scheme_id") if cost_sheet else None
    if bom_id:
        for scheme in bom_schemes:
            if scheme.get("id") == bom_id:
                return scheme
    return next((s for s in bom_schemes if s.get("status") == "current"), None)


def _sheet_config_to_bom_config(cfg):
    """把成本表/BOM 表 config 转成报价工作台 BOM 摘要结构。"""
    if not isinstance(cfg, dict):
        return {
            "name": "", "server_model": "", "description": "",
            "qty": 1, "l6_rows": [], "kp_rows": [],
        }
    return {
        "name": cfg.get("name") or "",
        "server_model": cfg.get("server_model") or "",
        "description": cfg.get("description") or "",
        "qty": int(cfg.get("qty") or 1),
        "l6_rows": [
            {
                "catalogue": row.get("catalogue") or "",
                "description": row.get("description") or "",
                "qty": int(row.get("qty") or 0),
            }
            for row in (cfg.get("l6_rows") or [])
            if isinstance(row, dict)
        ],
        "kp_rows": [
            {
                "part_category": row.get("part_category") or "",
                "catalogue": row.get("catalogue") or "",
                "description": row.get("description") or "",
                "qty": int(row.get("qty") or 0),
            }
            for row in (cfg.get("kp_rows") or [])
            if isinstance(row, dict)
        ],
    }


def _sheet_config_to_cost_config(cfg):
    """把成本表 config 转成报价工作台成本摘要结构，并由成本表自身字段重算 totals。"""
    if not isinstance(cfg, dict):
        return {
            "name": "", "server_model": "", "description": "", "qty": 1,
            "totals": _empty_sheet_totals(), "l6_items": [], "kp_items": [],
        }
    l6_rows = [dict(row) for row in (cfg.get("l6_rows") or []) if isinstance(row, dict)]
    kp_rows = [dict(row) for row in (cfg.get("kp_rows") or []) if isinstance(row, dict)]
    l6_cost = float(cfg.get("l6_cost") or 0)
    l6_margin = float(cfg.get("l6_margin") or 0)
    l6_sales = l6_cost * (1 + l6_margin / 100) if l6_cost else sum(
        float(row.get("final_price") or 0) * int(row.get("qty") or 0)
        for row in l6_rows
    )
    kp_cost = sum(float(row.get("base_price") or 0) * int(row.get("qty") or 0) for row in kp_rows)
    kp_sales = sum(float(row.get("final_price") or 0) * int(row.get("qty") or 0) for row in kp_rows)
    total_cost = l6_cost + kp_cost
    total_sales = l6_sales + kp_sales
    totals = {
        "l6Cost": l6_cost,
        "l6Sales": l6_sales,
        "kpCost": kp_cost,
        "kpSales": kp_sales,
        "warrantyCost": 0,
        "warrantySales": 0,
        "totalCost": total_cost,
        "totalSales": total_sales,
        "profit": total_sales - total_cost,
        "marginPct": (total_sales - total_cost) / total_cost * 100 if total_cost else 0,
    }
    return {
        "name": cfg.get("name") or "",
        "server_model": cfg.get("server_model") or "",
        "description": cfg.get("description") or "",
        "qty": int(cfg.get("qty") or 1),
        "totals": totals,
        "l6_items": [
            {
                "catalogue": row.get("catalogue") or "",
                "description": row.get("description") or "",
                "qty": int(row.get("qty") or 0),
                "base_price": row.get("base_price") or 0,
                "final_price": row.get("final_price") or 0,
                "profit_margin": row.get("profit_margin") or 0,
            }
            for row in l6_rows
        ],
        "kp_items": [
            {
                "item_id": row.get("item_id"),
                "cat": row.get("part_category") or "",
                "name": row.get("catalogue") or "",
                "description": row.get("description") or "",
                "qty": int(row.get("qty") or 0),
                "cost": row.get("base_price") or 0,
                "sales": row.get("final_price") or 0,
                "margin": row.get("profit_margin") or 0,
                "currency": row.get("currency") or "RMB",
                "note": row.get("note") or "",
            }
            for row in kp_rows
        ],
    }


def _empty_sheet_totals():
    return {
        "l6Cost": 0,
        "l6Sales": 0,
        "kpCost": 0,
        "kpSales": 0,
        "warrantyCost": 0,
        "warrantySales": 0,
        "totalCost": 0,
        "totalSales": 0,
        "profit": 0,
        "marginPct": 0,
    }


@router.get("/api/portal/opp/{opp_id}/board")
def get_portal_board(opp_id: str, user: dict = Depends(get_current_user)):
    """三栏流程看板：商机、需求、BOM、成本、报价、审批状态一次取齐。

    中间交付物仍走 field_visible 后端裁剪；前端不需要再拼多个接口。
    """
    opp, flow = _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        reqs = flow_repo.list_requirements(opp_id)
        current = next((r for r in reqs if r["status"] == "current"), None)
        nodes = flow_repo.list_nodes(flow["flow_id"])
        bom_schemes = flow_repo.list_bom_schemes(opp_id)
        cost_sheets = flow_repo.list_cost_sheets(opp_id)
    finally:
        flow_repo.close()

    card_repo = FlowCardRepository()
    try:
        flow_cards = []
        for card in card_repo.list_cards(opp_id):
            if not _card_visible_to_user(card, user):
                continue
            flow_cards.append(card)
    finally:
        card_repo.close()

    quote_repo = QuotationRepository()
    try:
        quotes = quote_repo.get_by_opportunity(opp_id)
        exported_quote_ids = {q.quotation_id for q in quotes if getattr(q, "exported_at", None)}
        active_quote_ids = {q.quotation_id for q in quotes}
        for sheet in cost_sheets:
            sheet["quotation_exported"] = bool(
                sheet.get("quotation_id") and sheet["quotation_id"] in exported_quote_ids
            )
            sheet["quotation_deleted"] = bool(
                sheet.get("quotation_id") and sheet["quotation_id"] not in active_quote_ids
            )
        final = next((q for q in quotes if getattr(q, "exported_at", None)), None)
        selected = final or (quotes[0] if quotes else None)

        # 报价/成本/BOM 段是否走“旧报价单兜底”分支：只有完全没有成本表、也没有
        # BOM 方案时，才需要用 load_preview_data 从明细重新汇总；否则直接用成本表/
        # BOM 方案里已存的快照，避免每次进详情页都全量白算报价段。
        flow_cost_sheet = _current_cost_sheet_for_quote(cost_sheets, selected)
        flow_bom_scheme = _current_bom_scheme_for_sheet(bom_schemes, flow_cost_sheet)

        bom_configs = []
        cost_configs = []
        if selected and flow_cost_sheet is None and flow_bom_scheme is None:
            preview = load_preview_data(opp_id, selected.quotation_id)
            preview_configs = preview.get("configs") or []
            summary_by_name = {
                item.get("config_name"): item
                for item in (preview.get("config_summary") or [])
                if isinstance(item, dict)
            }
            desc_map = selected.config_descriptions or {}
            raw_items = quote_repo.get_items(selected.quotation_id) or []
            raw_items_by_cfg: dict = {}
            for raw in raw_items:
                raw_dict = raw.to_dict()
                raw_items_by_cfg.setdefault(raw.config_name or "", []).append(raw_dict)

            extra = {}
            if selected.extra_fields:
                try:
                    extra = json.loads(selected.extra_fields) or {}
                except (json.JSONDecodeError, TypeError):
                    extra = {}
            l6_picks = extra.get("config_l6_picks") or {}

            for cfg in preview_configs:
                name = cfg.get("config_name") or ""
                if not name:
                    continue
                summary = summary_by_name.get(name) or {}
                server_model = cfg.get("server_model") or (selected.config_server_models or {}).get(name, "")
                description = summary.get("description") or desc_map.get(name, "")
                qty = cfg.get("quantity") or (selected.config_quantities or {}).get(name, 1) or 1

                l6_rows = [
                    {
                        "catalogue": row.get("catalogue") or "",
                        "description": row.get("description") or "",
                        "qty": row.get("qty") or 0,
                        "base_price": row.get("base_price") or 0,
                        "final_price": row.get("final_price") or 0,
                        "profit_margin": row.get("profit_margin") or 0,
                    }
                    for row in (cfg.get("l6_details") or [])
                ]
                kp_raw_rows = [
                    row for row in raw_items_by_cfg.get(name, [])
                    if (row.get("category") or "") == "Key Parts"
                ]
                kp_rows = [
                    {
                        "item_id": row.get("item_id"),
                        "part_category": row.get("part_category") or "",
                        "catalogue": row.get("catalogue") or "",
                        "description": row.get("description") or "",
                        "qty": row.get("qty") or 0,
                        "base_price": row.get("base_price") or 0,
                        "final_price": row.get("final_price") or 0,
                        "profit_margin": row.get("profit_margin") or 0,
                        "currency": row.get("currency") or "RMB",
                        "note": row.get("note") or "",
                    }
                    for row in kp_raw_rows
                ]

                bom_configs.append({
                    "name": name,
                    "server_model": server_model,
                    "description": description,
                    "qty": qty,
                    "l6_rows": [
                        {
                            "catalogue": row.get("catalogue") or "",
                            "description": row.get("description") or "",
                            "qty": row.get("qty") or 0,
                        }
                        for row in l6_rows
                    ],
                    "kp_rows": [
                        {
                            "part_category": row.get("part_category") or "",
                            "catalogue": row.get("catalogue") or "",
                            "description": row.get("description") or "",
                            "qty": row.get("qty") or 0,
                        }
                        for row in kp_rows
                    ],
                })

                raw_pick = l6_picks.get(name)
                pick = raw_pick if isinstance(raw_pick, dict) else {}
                l6_cost = float(pick.get("l6_custom_price") or 0)
                l6_margin = float(pick.get("l6_profit_margin") or 0)
                l6_sales = l6_cost * (1 + l6_margin / 100) if l6_cost else sum(
                    float(row.get("final_price") or 0) * float(row.get("qty") or 0)
                    for row in l6_rows
                )
                kp_cost = sum(float(row.get("base_price") or 0) * float(row.get("qty") or 0) for row in kp_rows)
                kp_sales = sum(float(row.get("final_price") or 0) * float(row.get("qty") or 0) for row in kp_rows)
                total_cost = l6_cost + kp_cost
                total_sales = l6_sales + kp_sales
                totals = {
                    "l6Cost": l6_cost,
                    "l6Sales": l6_sales,
                    "kpCost": kp_cost,
                    "kpSales": kp_sales,
                    "warrantyCost": 0,
                    "warrantySales": 0,
                    "totalCost": total_cost,
                    "totalSales": total_sales,
                    "profit": total_sales - total_cost,
                    "marginPct": (total_sales - total_cost) / total_cost * 100 if total_cost else 0,
                }
                cost_configs.append({
                    "name": name,
                    "server_model": server_model,
                    "description": description,
                    "qty": qty,
                    "totals": totals,
                    "l6_items": l6_rows,
                    "kp_items": [
                        {
                            "item_id": row.get("item_id"),
                            "cat": row.get("part_category") or "",
                            "name": row.get("catalogue") or "",
                            "description": row.get("description") or "",
                            "qty": row.get("qty") or 0,
                            "cost": row.get("base_price") or 0,
                            "sales": row.get("final_price") or 0,
                            "margin": row.get("profit_margin") or 0,
                            "currency": row.get("currency") or "RMB",
                            "note": row.get("note") or "",
                        }
                        for row in kp_rows
                    ],
                })
    finally:
        quote_repo.close()

    bom_visible = field_visible(user, "field.flow.bom")
    cost_visible = field_visible(user, "field.flow.cost")
    bom_editable = bom_visible
    cost_editable = cost_visible
    bom_locked = not bom_editable
    cost_locked = not cost_editable
    final_dict = _mask_quote_if_needed(final.to_dict(), user) if final else None
    cost_snapshot = None if not cost_visible else (selected.cost_snapshot if selected else None)

    if flow_cost_sheet:
        cost_source = flow_cost_sheet.get("configs") or []
        bom_source = (flow_bom_scheme or {}).get("configs") or cost_source
        context_bom_configs = [_sheet_config_to_bom_config(c) for c in bom_source if isinstance(c, dict)]
        context_cost_configs = [_sheet_config_to_cost_config(c) for c in cost_source if isinstance(c, dict)]
        context_worktable_quotation_id = flow_cost_sheet.get("quotation_id") or (selected.quotation_id if selected else "")
        context_legacy_fallback = False
    elif flow_bom_scheme:
        bom_source = flow_bom_scheme.get("configs") or []
        context_bom_configs = [_sheet_config_to_bom_config(c) for c in bom_source if isinstance(c, dict)]
        context_cost_configs = []
        context_worktable_quotation_id = selected.quotation_id if selected else ""
        context_legacy_fallback = False
    else:
        context_bom_configs = bom_configs
        context_cost_configs = cost_configs
        context_worktable_quotation_id = selected.quotation_id if selected else ""
        context_legacy_fallback = bool(selected)

    worktable_cost_sheets = []
    for sheet in cost_sheets:
        if sheet.get("status") == "draft" or not sheet.get("quotation_id"):
            continue
        sheet_bom = _current_bom_scheme_for_sheet(bom_schemes, sheet)
        cost_source = sheet.get("configs") or []
        bom_source = (sheet_bom or {}).get("configs") or cost_source
        worktable_cost_sheets.append({
            "sheet_id": sheet.get("id"),
            "sheet_name": sheet.get("name") or "",
            "status": sheet.get("status"),
            "quotation_id": sheet.get("quotation_id"),
            "quotation_exported": bool(sheet.get("quotation_exported")),
            "quotation_deleted": bool(sheet.get("quotation_deleted")),
            "bom_configs": [
                _sheet_config_to_bom_config(c) for c in bom_source if isinstance(c, dict)
            ],
            "cost_configs": [
                _sheet_config_to_cost_config(c) for c in cost_source if isinstance(c, dict)
            ],
        })

    quote_context = {
        "bom_configs": [] if not bom_visible else context_bom_configs,
        "cost_configs": [] if not cost_visible else context_cost_configs,
        "worktable_quotation_id": context_worktable_quotation_id or None,
        "cost_snapshot": cost_snapshot if context_legacy_fallback else None,
        "worktable_cost_sheets": [] if not cost_visible else worktable_cost_sheets,
    }

    return {
        "opportunity": _opp_summary(opp, current),
        "flow": flow,
        "nodes": _lock_nodes(nodes, user),
        "requirements": reqs,
        "draft_requirement": next((r for r in reqs if r["status"] == "draft"), None),
        "current_version": current["version"] if current else None,
        "requirement": current,
        "bom_schemes": [] if not field_visible(user, "field.flow.bom") else bom_schemes,
        "cost_sheets": [] if not field_visible(user, "field.flow.cost") else cost_sheets,
        "bom": {
            "locked": bom_locked,
            "quotation_id": quote_context["worktable_quotation_id"],
            "quotation_name": selected.quotation_name if selected else "",
            "configs": quote_context["bom_configs"],
        },
        "cost": {
            "locked": cost_locked,
            "snapshot": quote_context["cost_snapshot"],
            "configs": quote_context["cost_configs"],
        },
        "quote_context": quote_context,
        "quote": final_dict,
        "approvals": _approvals(flow, _lock_nodes(nodes, user), current),
        "flow_cards": flow_cards,
    }


class CardReturnBody(BaseModel):
    comment: str = ""


class CardWithdrawBody(BaseModel):
    comment: str = ""


class CardApproveBody(BaseModel):
    reason: str = ""


class SubmitAssigneeBody(BaseModel):
    assignee_name: str = ""


def _assign_if_unset(flow_repo: FlowRepository, opp_id: str,
                     node_key: str, assignee_name: str, actor: str) -> None:
    """提交推进后，若下游节点未配置处理人且调用方提供了人选，则写入指派。"""
    if not assignee_name:
        return
    flow = flow_repo.get_flow(opp_id) or {}
    if (flow.get("current_node") or "") != node_key:
        return
    if (flow.get("assignees") or {}).get(node_key):
        return
    flow_repo.assign_task(flow["flow_id"], node_key, assignee_name, actor=actor)


def _ensure_downstream_assignee(flow_repo: FlowRepository, opp_id: str,
                                node_key: str, assignee_name: str) -> None:
    """提交前校验：下游节点默认处理人为空且调用方未提供人选时，要求先选择。"""
    if assignee_name:
        return
    flow = flow_repo.get_flow(opp_id) or {}
    if (flow.get("assignees") or {}).get(node_key):
        return
    if flow_repo.resolve_node_assignee(opp_id, node_key):
        return
    raise HTTPException(status_code=409, detail=_ASSIGNEE_REQUIRED_DETAIL)


def _card_visible_to_user(card: dict, user: dict) -> bool:
    if _portal_is_admin(user):
        return True
    role = user.get("role") or ""
    origin = card.get("origin_node") or "requirement"
    current = card.get("current_node") or origin
    if origin == "requirement":
        return role == "business" or role == _CARD_NODE_ROLE.get(current)
    if card.get("visible_upstream") is False:
        return role == _CARD_NODE_ROLE.get(current)
    return role == _CARD_NODE_ROLE.get(origin) or role == _CARD_NODE_ROLE.get(current)

@router.get("/api/portal/opp/{opp_id}/cards")
def list_portal_cards(opp_id: str, user: dict = Depends(get_current_user)):
    """商机卡片队列：路由元数据；业务内容仍由各交付物接口按权限裁剪。"""
    _svc(opp_id, user)
    repo = FlowCardRepository()
    try:
        cards = repo.list_cards(opp_id)
    finally:
        repo.close()
    cards = [c for c in cards if _card_visible_to_user(c, user)]
    return {"cards": cards}


@router.post("/api/portal/opp/{opp_id}/cards/{card_id}/return")
def return_portal_card(opp_id: str, card_id: int, body: CardReturnBody,
                       user: dict = Depends(get_current_user)):
    """退回当前卡到上一节点；只影响这一张卡，不再使用全局节点退回。"""
    _svc(opp_id, user)
    repo = FlowCardRepository()
    try:
        card = repo.get_card(card_id)
        if not card or card.get("opportunity_id") != opp_id:
            raise HTTPException(status_code=404, detail="流转卡不存在")
        from_node = card.get("current_node") or "requirement"
        if from_node == "assign":
            from_node = "requirement"
        target_node = _RETURN_TARGETS.get(from_node)
        if not target_node:
            raise HTTPException(status_code=400, detail="当前节点不支持退回")
        if not user_has_permission(user, _RETURN_PERMS.get(from_node, "")):
            raise HTTPException(status_code=403, detail="无权限退回该卡")
        if from_node == "quoting":
            quote_entities = [e.get("entity_id") for e in card.get("entities") or [] if e.get("entity_type") == "quote"]
            if quote_entities:
                quote_repo = QuotationRepository()
                try:
                    raw_quote = quote_repo.get_raw_by_id(str(quote_entities[0]))
                finally:
                    quote_repo.close()
                if raw_quote and raw_quote.status == "active" and raw_quote.source != "worktable":
                    raise HTTPException(
                        status_code=409,
                        detail="该报价单已转为正式报价单，请先删除报价单再退回成本表",
                    )
        updated = repo.return_card(card_id, target_node, user.get("name") or "", body.comment)
        repo.revert_card_deliverables(card_id, from_node)

        flow_repo = FlowRepository()
        try:
            flow = flow_repo.get_or_create_flow(opp_id)
            flow_repo.append_node(
                flow.flow_id,
                target_node,
                "return",
                actor=user.get("name") or "",
                comment=body.comment or "",
                artifacts={"card_id": card_id, "from_node": from_node},
            )
        finally:
            flow_repo.close()
        return {"card": updated}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        repo.close()


@router.post("/api/portal/opp/{opp_id}/cards/{card_id}/withdraw")
def request_withdraw_portal_card(opp_id: str, card_id: int, body: CardWithdrawBody,
                                 user: dict = Depends(get_current_user)):
    """上游申请撤回已提交卡；仅已提交状态可申请。"""
    _svc(opp_id, user)
    repo = FlowCardRepository()
    try:
        card = repo.get_card(card_id)
        if not card or card.get("opportunity_id") != opp_id:
            raise HTTPException(status_code=404, detail="流转卡不存在")
        if not _portal_is_admin(user) and card.get("created_by") not in {"", user.get("name") or ""}:
            raise HTTPException(status_code=403, detail="只有该卡发起人可申请撤回")
        updated = repo.request_withdraw(card_id, body.comment)
        return {"card": updated}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        repo.close()


@router.post("/api/portal/opp/{opp_id}/cards/{card_id}/withdraw/approve")
def approve_withdraw_portal_card(opp_id: str, card_id: int, user: dict = Depends(get_current_user)):
    _svc(opp_id, user)
    repo = FlowCardRepository()
    try:
        card = repo.get_card(card_id)
        if not card or card.get("opportunity_id") != opp_id:
            raise HTTPException(status_code=404, detail="流转卡不存在")
        required_role = _CARD_NODE_ROLE.get(card.get("current_node") or "requirement")
        if not _portal_is_admin(user) and user.get("role") != required_role:
            raise HTTPException(status_code=403, detail="当前角色无权处理撤回申请")
        from_node = card.get("current_node") or "requirement"
        target_node = _RETURN_TARGETS.get(from_node)
        if not target_node:
            raise HTTPException(status_code=400, detail="当前节点不支持撤回")
        updated = repo.approve_withdraw(card_id, target_node)
        repo.revert_card_deliverables(card_id, from_node)
        return {"card": updated}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        repo.close()


@router.post("/api/portal/opp/{opp_id}/cards/{card_id}/withdraw/reject")
def reject_withdraw_portal_card(opp_id: str, card_id: int, body: CardApproveBody,
                                user: dict = Depends(get_current_user)):
    _svc(opp_id, user)
    repo = FlowCardRepository()
    try:
        card = repo.get_card(card_id)
        if not card or card.get("opportunity_id") != opp_id:
            raise HTTPException(status_code=404, detail="流转卡不存在")
        required_role = _CARD_NODE_ROLE.get(card.get("current_node") or "requirement")
        if not _portal_is_admin(user) and user.get("role") != required_role:
            raise HTTPException(status_code=403, detail="当前角色无权处理撤回申请")
        updated = repo.reject_withdraw(card_id, body.reason)
        return {"card": updated}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        repo.close()


def _sync_sheet_to_quotation(opp: dict, quotation_id: Optional[str],
                             configs: List[dict], sheet_name: str = "") -> str:
    """把成本工作底表同步到 opportunities.quotations（回写 L6 整机成本与 KP 成本价）。

    sheet_name（成本表名）用于在新建报价单时生成可区分的名称，避免多张成本表
    生成同名的「方案-客户」报价单导致无法分辨。
    """
    quote_repo = QuotationRepository()
    try:
        if quotation_id:
            quotation = quote_repo.get_by_id(quotation_id)
            if not quotation or quotation.opportunity_id != opp.get("opportunity_id"):
                raise HTTPException(status_code=404, detail="报价单不存在或不属于该商机")
        else:
            customer = opp.get("customer_name") or "工作表"
            base = (sheet_name or "").strip()
            if base.startswith("成本-"):
                base = base[3:].strip() or base
            base = base or "成本表"
            quotation = quote_repo.create(
                opp.get("opportunity_id"),
                quotation_name=f"报价-{customer}-{base}",
            )
            # 同一成本表重复提交会生成新版本，附版本号避免重名
            quote_repo.update(
                quotation.quotation_id,
                quotation_name=f"报价-{customer}-{base}-{quotation.version}",
            )
        # 仅在新建工作底表或当前仍为工作底表时标记 worktable；
        # 已转正式报价单（source 非 worktable）不降级，避免正式单被隐藏。
        if not quotation_id or quotation.source in (None, "", "worktable"):
            quote_repo.update(quotation.quotation_id, source="worktable")

        normalized_configs = []
        config_quantities = {}
        config_server_models = {}
        config_descriptions = {}
        for cfg in configs or []:
            name = (cfg.get("name") or cfg.get("config_name") or "").strip()
            if not name:
                continue
            normalized = dict(cfg)
            normalized["name"] = name
            normalized["l6_rows"] = [
                dict(row) for row in (cfg.get("l6_rows") or [])
                if isinstance(row, dict)
            ]
            normalized["kp_rows"] = [
                dict(row) for row in (cfg.get("kp_rows") or [])
                if isinstance(row, dict)
            ]
            normalized_configs.append(normalized)
            config_quantities[name] = int(cfg.get("qty") or 1)
            config_server_models[name] = cfg.get("server_model") or ""
            config_descriptions[name] = cfg.get("description") or ""

        if not normalized_configs:
            raise HTTPException(status_code=400, detail="至少保留一个配置")

        config_relation = str(opp.get("config_relation") or "compose")
        primary_config = str(opp.get("primary_config") or "")
        # 方案备选：设备数量取需求台数(purchase_qty)，不把各配置台数相加
        if config_relation == "alternative":
            total_qty = int(opp.get("purchase_qty") or 0) or sum(config_quantities.values())
        else:
            total_qty = sum(config_quantities.values())
        quote_repo.update(
            quotation.quotation_id,
            config_quantities=config_quantities,
            config_server_models=config_server_models,
            config_descriptions=config_descriptions,
            config_count=len(config_quantities),
            total_qty=total_qty,
            config_relation=config_relation,
            primary_config=primary_config,
        )

        extra = {}
        if quotation.extra_fields:
            try:
                extra = json.loads(quotation.extra_fields) or {}
            except (json.JSONDecodeError, TypeError):
                extra = {}
        picks = extra.get("config_l6_picks") or {}
        if not isinstance(picks, dict):
            picks = {}
        submitted_names = set(config_quantities.keys())

        def _kp_snapshot_rows(cfg: dict) -> list:
            rows = []
            for row in cfg.get("kp_rows") or []:
                if not isinstance(row, dict):
                    continue
                rows.append({
                    "item_id": row.get("item_id"),
                    "category": "Key Parts",
                    "catalogue": row.get("catalogue") or "",
                    "description": row.get("description") or "",
                    "part_category": row.get("part_category") or "",
                    "qty": int(row.get("qty") or 0),
                    "base_price": row.get("base_price") or 0,
                    "final_price": row.get("final_price") or 0,
                    "profit_margin": row.get("profit_margin") or 0,
                    "currency": row.get("currency") or "RMB",
                    "note": row.get("note") or "",
                })
            return rows

        for cfg in normalized_configs:
            name = cfg["name"]
            pick = picks.get(name) or {}
            if not isinstance(pick, dict):
                pick = {}
            if "l6_cost" in cfg:
                pick["l6_custom_price"] = float(cfg.get("l6_cost") or 0)
                pick["l6_price_manual"] = True

            if not pick.get("bom_source"):
                pick["bom_source"] = "excel"
                pick["bom_excel_rows"] = []

            if pick.get("bom_source") == "excel":
                l6_existing = [
                    row for row in (pick.get("bom_excel_rows") or [])
                    if isinstance(row, dict) and (row.get("category") or "") in ("L6", "整机")
                ]
                l6_rows = cfg.get("l6_rows")
                if isinstance(l6_rows, list) and l6_rows:
                    for idx, row in enumerate(l6_rows):
                        if idx < len(l6_existing) and isinstance(l6_existing[idx], dict):
                            for key in ("base_price", "final_price", "profit_margin", "note"):
                                if key in row:
                                    l6_existing[idx][key] = row[key]
                        else:
                            l6_existing.append(row)
                pick["bom_excel_rows"] = l6_existing + _kp_snapshot_rows(cfg)
            picks[name] = pick
        for name in list(picks.keys()):
            if name not in submitted_names:
                del picks[name]
        quote_repo.update(quotation.quotation_id, config_l6_picks=picks)
        for cfg in normalized_configs:
            for row in cfg.get("kp_rows") or []:
                row.setdefault("category", "Key Parts")
                row.pop("final_price", None)
                row.pop("profit_margin", None)
        # 幂等同步：成本表→报价单每次全量替换 KP 行（先删旧再插入），
        # 避免同一批 komponent 多次同步时缺失 item_id 而累积重复行。
        quote_repo.patch_items(quotation.quotation_id, normalized_configs, delete_missing=True)

        return quotation.quotation_id
    finally:
        quote_repo.close()


class BomSchemeDraftBody(BaseModel):
    scheme_id: Optional[int] = None
    flow_card_id: Optional[int] = None
    name: str
    configs: List[dict] = []
    config_relation: str = "compose"  # compose=组合拆分 / alternative=方案备选对比
    primary_config: str = ""


class CostSheetDraftBody(BaseModel):
    sheet_id: Optional[int] = None
    flow_card_id: Optional[int] = None
    name: str
    configs: List[dict] = []
    bom_scheme_id: Optional[int] = None
    quotation_id: Optional[str] = None


@router.get("/api/portal/opp/{opp_id}/bom-schemes")
def list_bom_schemes(opp_id: str, user: dict = Depends(get_current_user)):
    _svc(opp_id, user)
    if not field_visible(user, "field.flow.bom"):
        return {"bom_schemes": []}
    flow_repo = FlowRepository()
    try:
        return {"bom_schemes": flow_repo.list_bom_schemes(opp_id)}
    finally:
        flow_repo.close()


@router.post("/api/portal/opp/{opp_id}/bom-schemes/draft")
def save_bom_scheme_draft(opp_id: str, body: BomSchemeDraftBody,
                          user: dict = Depends(get_current_user)):
    """新建或更新一个 BOM 方案草稿。一个方案可含多个内部配置页签。"""
    _svc(opp_id, user)
    if not field_visible(user, "field.flow.bom"):
        raise HTTPException(status_code=403, detail="当前角色无权编辑方案配置")
    if not body.configs:
        raise HTTPException(status_code=400, detail="方案内至少保留一个配置页签")

    flow_repo = FlowRepository()
    try:
        scheme = flow_repo.save_bom_scheme_draft(
            opp_id, body.scheme_id, body.name, body.configs, user.get("name") or "",
            body.config_relation, body.primary_config,
        )
        _attach_entity_card(
            opp_id,
            "bom",
            scheme["id"],
            origin_node="boming",
            current_node="boming",
            flow_status="processing" if body.flow_card_id else "draft",
            created_by=user.get("name") or "",
            card_id=body.flow_card_id,
            visible_upstream=body.flow_card_id is not None,
        )
        return {"scheme": scheme, "bom_schemes": flow_repo.list_bom_schemes(opp_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        flow_repo.close()


@router.post("/api/portal/opp/{opp_id}/bom-schemes/{scheme_id}/submit")
def submit_bom_scheme(opp_id: str, scheme_id: int,
                      body: SubmitAssigneeBody = None,
                      user: dict = Depends(get_current_user)):
    """提交一个 BOM 方案：转为 current，其他方案保留/归档，并推进到成本核算。"""
    _svc(opp_id, user)
    if not field_visible(user, "field.flow.bom"):
        raise HTTPException(status_code=403, detail="当前角色无权提交方案配置")

    flow_repo = FlowRepository()
    try:
        _ensure_downstream_assignee(flow_repo, opp_id, "costing",
                                    (body.assignee_name if body else "") or "")
        scheme = flow_repo.submit_bom_scheme(opp_id, scheme_id, user.get("name") or "")
        _assign_if_unset(flow_repo, opp_id, "costing",
                         (body.assignee_name if body else "") or "", user.get("name") or "")
        flow = flow_repo.get_flow(opp_id) or {}
        nodes = flow_repo.list_nodes(flow.get("flow_id") or "")
        _attach_entity_card(
            opp_id,
            "bom",
            scheme["id"],
            origin_node="boming",
            current_node="costing",
            flow_status="submitted",
            created_by=user.get("name") or "",
            visible_upstream=False,
        )
        return {
            "scheme": scheme,
            "bom_schemes": flow_repo.list_bom_schemes(opp_id),
            "flow": flow,
            "nodes": nodes,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        flow_repo.close()


@router.delete("/api/portal/opp/{opp_id}/bom-schemes/{scheme_id}")
def delete_bom_scheme(opp_id: str, scheme_id: int,
                      user: dict = Depends(get_current_user)):
    """删除 BOM 方案；当前/归档方案在满足未进入下游且无成本引用时允许删除。"""
    _svc(opp_id, user)
    if not field_visible(user, "field.flow.bom"):
        raise HTTPException(status_code=403, detail="当前角色无权删除方案配置")

    flow_repo = FlowRepository()
    try:
        flow_repo.delete_bom_scheme(opp_id, scheme_id)
        _unlink_entity_card(opp_id, "bom", scheme_id)
        return {"ok": True, "bom_schemes": flow_repo.list_bom_schemes(opp_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        flow_repo.close()


@router.get("/api/portal/opp/{opp_id}/cost-sheets")
def list_cost_sheets(opp_id: str, user: dict = Depends(get_current_user)):
    _svc(opp_id, user)
    if not field_visible(user, "field.flow.cost"):
        return {"cost_sheets": []}
    flow_repo = FlowRepository()
    try:
        return {"cost_sheets": flow_repo.list_cost_sheets(opp_id)}
    finally:
        flow_repo.close()


def _decode_filename(filename: str) -> str:
    """Best-effort fix for Windows multipart form encoding of Chinese filenames."""
    try:
        if not filename.isascii():
            return filename
        for encoding in ("utf-8", "gbk", "gb2312", "latin1"):
            try:
                decoded = filename.encode("latin1").decode(encoding)
                if decoded != filename and any("一" <= c <= "鿿" for c in decoded):
                    return decoded
            except Exception:
                continue
    except Exception:
        pass
    return filename


def _cost_sheet_name_from_filename(filename: str) -> str:
    stem = Path(filename).stem or "成本表"
    return f"成本-{stem}"


def _parse_result_to_cost_configs(result_configs: dict) -> list:
    """把上传解析结果映射为成本核算表 configs（L6/KP 分离，含成本价）。"""
    configs = []
    for cfg_name, cfg_data in result_configs.items():
        meta = cfg_data.get("meta") or {}
        server_model = str(meta.get("server_model") or "").strip()
        description = str(meta.get("description") or "").strip()
        try:
            qty = int(meta.get("model_qty") or 1)
        except (TypeError, ValueError):
            qty = 1
        items = cfg_data.get("items") or []
        l6_rows = []
        kp_rows = []
        l6_cost = 0.0
        for it in items:
            cat = it.get("category") or ""
            row = {
                "category": cat,
                "item_id": it.get("item_id"),
                "part_category": it.get("part_category") or "",
                "catalogue": it.get("catalogue") or "",
                "description": it.get("description") or "",
                "qty": it.get("qty") or 1,
                "base_price": it.get("base_price") or 0,
                "final_price": it.get("final_price") or 0,
                "profit_margin": it.get("profit_margin") or 0,
                "currency": it.get("currency") or "RMB",
                "note": it.get("note") or "",
            }
            if cat == "L6":
                l6_rows.append(row)
                l6_cost += float(it.get("final_price") or 0) * int(it.get("qty") or 1)
            else:
                kp_rows.append(row)
        # upload 解析的 items 不含 L6（L6 参考快照在 bom_excel_rows），合并进来，
        # 避免成本表丢失 L6 配置；若参考行带价则计入 l6_cost。
        seen_l6 = {(str(r.get("catalogue") or ""), str(r.get("description") or ""), int(r.get("qty") or 1)) for r in l6_rows}
        for ref in (cfg_data.get("bom_excel_rows") or []):
            if (ref.get("category") or "").lower() != "l6":
                continue
            brow = {
                "category": "L6",
                "item_id": ref.get("item_id"),
                "part_category": ref.get("part_category") or "",
                "catalogue": ref.get("catalogue") or "",
                "description": ref.get("description") or "",
                "qty": ref.get("qty") or 1,
                "base_price": ref.get("base_price") or 0,
                "final_price": ref.get("final_price") or 0,
                "profit_margin": ref.get("profit_margin") or 0,
                "currency": ref.get("currency") or "RMB",
                "note": ref.get("note") or "",
            }
            bkey = (str(brow["catalogue"]), str(brow["description"]), int(brow["qty"] or 1))
            if bkey in seen_l6:
                continue
            seen_l6.add(bkey)
            l6_rows.append(brow)
            l6_cost += float(brow["final_price"] or brow["base_price"] or 0) * int(brow["qty"] or 1)
        configs.append({
            "name": cfg_name,
            "server_model": server_model,
            "description": description,
            "qty": qty if qty > 0 else 1,
            "l6_cost": round(l6_cost, 2),
            "l6_margin": 0,
            "l6_rows": l6_rows,
            "kp_rows": kp_rows,
            "totals": {},
        })
    return configs


@router.post("/api/portal/opp/{opp_id}/cost-sheets/upload")
async def upload_cost_sheet(
    opp_id: str,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """上传成本表：解析 Excel 并生成成本核算草稿表（不生成报价单）。"""
    opp, flow = _svc(opp_id, user)
    if not field_visible(user, "field.flow.cost"):
        raise HTTPException(status_code=403, detail="当前角色无权上传成本表")

    filename = _decode_filename(file.filename or "")
    if not filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="只支持 .xlsx / .xls 文件")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件过大，最大允许 50MB")

    service = QuoteService()
    flow_repo = FlowRepository()
    feed_repo = FeedRepository()
    storage = get_storage()
    storage_key = None
    sheet_id = None
    try:
        result = service.process_upload(content, filename)
        if result.get("status") == "error":
            raw = result.get("message", "") or "未知错误"
            raise HTTPException(status_code=422, detail=f"成本表解析失败：{raw}")
        configs = _parse_result_to_cost_configs(result.get("configs") or {})
        if not configs:
            raise HTTPException(status_code=422, detail="未识别到有效配置：请检查成本表格式")
        name = _cost_sheet_name_from_filename(filename)
        try:
            sheet = flow_repo.save_cost_sheet_draft(
                opp_id, None, name, configs, bom_scheme_id=None,
                quotation_id="", created_by=user.get("name") or "",
            )
            sheet_id = sheet["id"]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        card = _attach_entity_card(
            opp_id,
            "cost",
            sheet["id"],
            origin_node="costing",
            current_node="costing",
            flow_status="draft",
            created_by=user.get("name") or "",
            card_id=None,
            visible_upstream=False,
        )

        ext = Path(filename).suffix.lower()
        try:
            storage_key = storage.save_bytes(
                opp_id,
                build_object_id(filename),
                content,
                ext,
                customer_name=opp.get("customer_name") or "",
                subfolder="成本核算",
            )
        except StorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        mime = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if ext == ".xlsx"
            else "application/vnd.ms-excel"
        )
        att = feed_repo.add_attachment(
            opportunity_id=opp_id,
            uploader_user_id=user["user_id"],
            original_filename=filename,
            storage_key=storage_key,
            file_size=len(content),
            mime_type=mime,
            kind="upload",
            quotation_id="",
            category="requirement",
            flow_card_id=card["id"],
        )
        await hub.broadcast(opp_id, {"type": "attachment", "attachment": att})
        return {
            "sheet": sheet,
            "attachment": att,
            "cost_sheets": flow_repo.list_cost_sheets(opp_id),
        }
    except Exception:
        if storage_key:
            try:
                storage.delete(storage_key)
            except Exception:
                pass
        if sheet_id is not None:
            try:
                flow_repo.delete_cost_sheet_draft(opp_id, sheet_id)
                _unlink_entity_card(opp_id, "cost", sheet_id)
            except Exception:
                pass
        raise
    finally:
        service.close()
        flow_repo.close()
        feed_repo.close()


@router.post("/api/portal/opp/{opp_id}/cost-sheets/draft")
def save_cost_sheet_draft(opp_id: str, body: CostSheetDraftBody,
                          user: dict = Depends(get_current_user)):
    """新建或更新一张成本核算草稿/当前表（由已提交 BOM 方案生成）。"""
    opp, _ = _svc(opp_id, user)
    if not field_visible(user, "field.flow.cost"):
        raise HTTPException(status_code=403, detail="当前角色无权编辑成本核算")
    if not body.configs:
        raise HTTPException(status_code=400, detail="成本表内至少保留一个配置页签")

    flow_repo = FlowRepository()
    try:
        linked_quotation_id = body.quotation_id or ""
        existing_status = None
        if body.sheet_id:
            existing = flow_repo.get_cost_sheet(opp_id, body.sheet_id)
            linked_quotation_id = linked_quotation_id or (existing or {}).get("quotation_id") or ""
            existing_status = (existing or {}).get("status")
        if linked_quotation_id:
            quote_repo = QuotationRepository()
            try:
                linked_quote = quote_repo.get_raw_by_id(linked_quotation_id)
                if not linked_quote:
                    raise HTTPException(status_code=404, detail="关联报价单不存在或不属于该商机")
                if linked_quote.opportunity_id != opp.get("opportunity_id"):
                    raise HTTPException(status_code=404, detail="关联报价单不存在或不属于该商机")
                if linked_quote.status != "active":
                    raise HTTPException(status_code=409, detail="对应报价单已删除，该成本表只能删除")
                if linked_quote.exported_at:
                    raise HTTPException(status_code=409, detail="关联报价单已导出或定稿，成本表不可再修改")
            finally:
                quote_repo.close()
        sheet = flow_repo.save_cost_sheet_draft(
            opp_id,
            body.sheet_id,
            body.name,
            body.configs,
            body.bom_scheme_id,
            body.quotation_id or "",
            user.get("name") or "",
        )
        card_id = body.flow_card_id
        if not card_id and body.bom_scheme_id:
            card_repo = FlowCardRepository()
            try:
                parent = card_repo.get_card_for_entity(opp_id, "bom", body.bom_scheme_id)
                card_id = parent["id"] if parent else None
            finally:
                card_repo.close()
        if existing_status == "current":
            card_repo = FlowCardRepository()
            try:
                cost_card = card_repo.get_card_for_entity(opp_id, "cost", sheet["id"])
                if cost_card:
                    card_repo.link_entity(cost_card["id"], "cost", sheet["id"], opportunity_id=opp_id)
                elif card_id:
                    card_repo.link_entity(card_id, "cost", sheet["id"], opportunity_id=opp_id)
                else:
                    card = card_repo.ensure_card(
                        opp_id,
                        origin_node="costing",
                        current_node="costing",
                        created_by=user.get("name") or "",
                        visible_upstream=False,
                        flow_status="processing",
                    )
                    card_repo.link_entity(card["id"], "cost", sheet["id"], opportunity_id=opp_id)
            finally:
                card_repo.close()
        else:
            _attach_entity_card(
                opp_id,
                "cost",
                sheet["id"],
                origin_node="costing",
                current_node="costing",
                flow_status="processing" if card_id else "draft",
                created_by=user.get("name") or "",
                card_id=card_id,
                visible_upstream=card_id is not None,
            )
        if linked_quotation_id:
            _sync_sheet_to_quotation(
                opp, linked_quotation_id, body.configs, body.name
            )
        return {"sheet": sheet, "cost_sheets": flow_repo.list_cost_sheets(opp_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        flow_repo.close()

@router.post("/api/portal/opp/{opp_id}/cost-sheets/{sheet_id}/submit")
def submit_cost_sheet(opp_id: str, sheet_id: int,
                      body: SubmitAssigneeBody = None,
                      user: dict = Depends(get_current_user)):
    """提交成本表：同步生成报价单草稿，并把流程推进到报价单节点。"""
    opp, flow = _svc(opp_id, user)
    if not field_visible(user, "field.flow.cost"):
        raise HTTPException(status_code=403, detail="当前角色无权提交成本核算")

    flow_repo = FlowRepository()
    try:
        _ensure_downstream_assignee(flow_repo, opp_id, "quoting",
                                    (body.assignee_name if body else "") or "")
        sheet = flow_repo.get_cost_sheet(opp_id, sheet_id)
        if not sheet or sheet.get("status") != "draft":
            raise HTTPException(status_code=400, detail="仅草稿成本表可提交")
        reuse_quotation_id = sheet.get("quotation_id") or None
        if reuse_quotation_id:
            quote_repo = QuotationRepository()
            try:
                raw_quote = quote_repo.get_raw_by_id(reuse_quotation_id)
            finally:
                quote_repo.close()
            # 报价单不存在/已删除/已定稿均不复用，提交时新建独立工作底表报价单草稿
            if not raw_quote or raw_quote.status != "active" or raw_quote.exported_at:
                reuse_quotation_id = None
        quotation_id = _sync_sheet_to_quotation(
            opp, reuse_quotation_id, sheet.get("configs") or [], sheet.get("name") or ""
        )
        submitted = flow_repo.submit_cost_sheet(
            opp_id, sheet_id, quotation_id, user.get("name") or ""
        )
        _assign_if_unset(flow_repo, opp_id, "quoting",
                         (body.assignee_name if body else "") or "", user.get("name") or "")
        flow = flow_repo.get_flow(opp_id) or flow
        nodes = flow_repo.list_nodes(flow["flow_id"])
        card_id = None
        card_repo = FlowCardRepository()
        try:
            card = card_repo.get_card_for_entity(opp_id, "cost", sheet_id)
            card_id = card["id"] if card else None
            if card_id:
                card_repo.link_entity(card_id, "quote", quotation_id, opportunity_id=opp_id)
                card_repo.update_card(card_id, current_node="quoting", flow_status="submitted")
        finally:
            card_repo.close()
        if not card_id:
            card_id = (_attach_entity_card(
                opp_id,
                "cost",
                sheet_id,
                origin_node="costing",
                current_node="quoting",
                flow_status="submitted",
                created_by=user.get("name") or "",
                visible_upstream=False,
            ) or {}).get("id")
            if card_id:
                _attach_entity_card(
                    opp_id,
                    "quote",
                    quotation_id,
                    origin_node="quoting",
                    current_node="quoting",
                    flow_status="submitted",
                    created_by=user.get("name") or "",
                    card_id=card_id,
                    visible_upstream=False,
                )
        return {
            "sheet": submitted,
            "cost_sheets": flow_repo.list_cost_sheets(opp_id),
            "flow": flow,
            "nodes": nodes,
            "quotation_id": quotation_id,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        flow_repo.close()


@router.delete("/api/portal/opp/{opp_id}/cost-sheets/{sheet_id}")
def delete_cost_sheet_draft(opp_id: str, sheet_id: int,
                            user: dict = Depends(get_current_user)):
    """删除成本核算表。已提交表仅在关联报价单已删除（孤儿）时才允许删除。"""
    _svc(opp_id, user)
    if not field_visible(user, "field.flow.cost"):
        raise HTTPException(status_code=403, detail="当前角色无权删除成本核算")

    flow_repo = FlowRepository()
    try:
        sheet = flow_repo.get_cost_sheet(opp_id, sheet_id)
        quotation_id = (sheet or {}).get("quotation_id") or ""
        if sheet and sheet.get("status") != "draft" and quotation_id:
            quote_repo = QuotationRepository()
            try:
                active_quote = quote_repo.get_by_id(quotation_id)
            finally:
                quote_repo.close()
            if active_quote:
                raise HTTPException(
                    status_code=409,
                    detail="成本表仍关联有效报价单，请先在报价单节点删除对应报价单再删除成本表",
                )
        ok = flow_repo.delete_cost_sheet_draft(opp_id, sheet_id)
        if ok:
            _unlink_entity_card(opp_id, "cost", sheet_id)
            if quotation_id:
                _unlink_entity_card(opp_id, "quote", quotation_id)
        return {"ok": ok, "cost_sheets": flow_repo.list_cost_sheets(opp_id)}
    finally:
        flow_repo.close()


class ConvertCostBody(BaseModel):
    quotation_id: str


@router.post("/api/portal/opp/{opp_id}/convert-to-quotation")
def convert_cost_to_quotation(opp_id: str, body: ConvertCostBody,
                              user: dict = Depends(get_current_user)):
    """成本核算提交后，由报价单节点将成本工作底表转为报价单草稿。

    注意：这里只生成草稿，不设置 flow.status=done；只有报价员正式发送后才算报价单已出。
    """
    _, flow = _svc(opp_id, user)

    quote_repo = QuotationRepository()
    try:
        quotation = quote_repo.get_by_id((body.quotation_id or "").strip())
        if not quotation or quotation.opportunity_id != opp_id:
            raise HTTPException(status_code=404, detail="工作底表不存在或不属于该商机")
        if quotation.source != "worktable":
            raise HTTPException(status_code=400, detail="该工作底表已转为报价单")
        quote_repo.update(quotation.quotation_id, source="manual")

        flow_repo = FlowRepository()
        try:
            flow_repo.advance_current_node_if_later(flow["flow_id"], "quoting", status="running")
            flow_repo.append_node(
                flow["flow_id"], "quoting", "draft",
                actor=user.get("name") or "",
                comment="成本表已转为报价单草稿",
                artifacts={"quotation_id": quotation.quotation_id, "version": quotation.version},
            )
        finally:
            flow_repo.close()
        return {"ok": True, "quotation_id": quotation.quotation_id}
    finally:
        quote_repo.close()


class SubmitQuoteBody(BaseModel):
    attachment_id: str
    comment: str = ""


@router.post("/api/portal/opp/{opp_id}/quotes/{quotation_id}/submit")
async def submit_quote(opp_id: str, quotation_id: str, body: SubmitQuoteBody,
                       user: dict = Depends(get_current_user)):
    """报价员正式发送已导出的 Excel 报价单。

    发送成功后：
    - 该报价单写入 submitted_at/submitted_by/submitted_attachment_id，并设为主推；
    - 商机流程状态置为 done（当前节点仍为 quoting，任务仍留在报价队列中）；
    - 在报价单审批节点下创建评论，并把指定 Excel 附件挂到该评论下。
    """
    if not user_has_permission(user, "action.flow.submit.quoting"):
        raise HTTPException(status_code=403, detail="无权限发送报价单")
    _, flow = _svc(opp_id, user)
    card_repo = FlowCardRepository()
    try:
        quote_card = card_repo.get_card_for_entity(opp_id, "quote", quotation_id)
    finally:
        card_repo.close()
    if quote_card:
        if quote_card.get("current_node") != "quoting" and quote_card.get("flow_status") != "completed":
            raise HTTPException(status_code=400, detail="该报价单尚未流转到报价节点")
    else:
        current_node = flow.get("current_node") or "requirement"
        if current_node == "assign":
            current_node = "requirement"
        if current_node != "quoting":
            raise HTTPException(status_code=400, detail="当前流程尚未进入报价单节点")

    attachment_id = (body.attachment_id or "").strip()
    if not attachment_id:
        raise HTTPException(status_code=400, detail="请选择要发送的 Excel 报价附件")

    quote_repo = QuotationRepository()
    feed_repo = FeedRepository()
    try:
        quotation = quote_repo.get_by_id(quotation_id)
        if not quotation or quotation.opportunity_id != opp_id:
            raise HTTPException(status_code=404, detail="报价单不存在或不属于该商机")
        if not quotation.exported_at:
            raise HTTPException(status_code=400, detail="报价单尚未导出，请先在报价工作台预览并下载 Excel")

        source_att = feed_repo.get_attachment(attachment_id)
        if (
            not source_att
            or source_att.get("opportunity_id") != opp_id
            or source_att.get("quotation_id") != quotation_id
            or source_att.get("kind") != "export"
            or source_att.get("category") != "sent_quote"
        ):
            raise HTTPException(status_code=400, detail="附件无效，请选择该报价单导出的 Excel 文件")

        now = datetime.now().isoformat()
        actor = user.get("name") or user.get("user_id") or "报价员"
        quote_repo.update(
            quotation_id,
            submitted_at=now,
            submitted_by=actor,
            submitted_attachment_id=attachment_id,
        )
        quote_repo.set_primary(quotation_id)

        flow_repo = FlowRepository()
        try:
            flow_repo.set_current_node(flow["flow_id"], "quoting", status="done")
            flow_repo.append_node(
                flow["flow_id"], "quoting", "complete",
                actor=actor,
                comment=(body.comment or "").strip() or "报价单已发送",
                artifacts={
                    "quotation_id": quotation_id,
                    "version": quotation.version,
                    "attachment_id": attachment_id,
                },
            )
        finally:
            flow_repo.close()

        card_repo = FlowCardRepository()
        try:
            card = card_repo.get_card_for_entity(opp_id, "quote", quotation_id)
            if card:
                card_repo.update_card(card["id"], current_node="quoting", flow_status="completed")
            else:
                card = card_repo.ensure_card(
                    opp_id,
                    origin_node="quoting",
                    current_node="quoting",
                    flow_status="completed",
                    created_by=actor,
                    visible_upstream=False,
                )
                card_repo.link_entity(card["id"], "quote", quotation_id, opportunity_id=opp_id)
        finally:
            card_repo.close()

        comment_text = (body.comment or "").strip() or f"报价单已发送：{source_att.get('original_filename') or '报价单.xlsx'}"
        msg = feed_repo.add_message(
            opportunity_id=opp_id,
            author_user_id=user.get("user_id") or "",
            body=comment_text,
            kind="comment",
            quotation_id=quotation_id,
            node_key="quoting",
        )
        copied = feed_repo.add_attachment(
            opportunity_id=opp_id,
            uploader_user_id=user.get("user_id") or "",
            original_filename=source_att.get("original_filename") or "报价单.xlsx",
            storage_key=source_att.get("storage_key") or "",
            file_size=int(source_att.get("file_size") or 0),
            mime_type=source_att.get("mime_type"),
            kind="quote_submission",
            message_id=msg.get("message_id"),
            quotation_id=quotation_id,
            category="sent_quote",
        )
        quote_repo.update(quotation_id, submitted_attachment_id=copied.get("attachment_id") or attachment_id)

        messages = feed_repo.list_messages(opp_id)
        created = next((m for m in messages if m.get("message_id") == msg.get("message_id")), msg)
        await hub.broadcast(opp_id, {"type": "message", "message": created})
        return {
            "ok": True,
            "quotation_id": quotation_id,
            "submitted_attachment_id": copied.get("attachment_id"),
            "message": created,
        }
    finally:
        quote_repo.close()
        feed_repo.close()


@router.get("/api/portal/opp/{opp_id}/requirements")
def list_requirements(opp_id: str, user: dict = Depends(get_current_user)):
    _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        reqs = flow_repo.list_requirements(opp_id)
    finally:
        flow_repo.close()
    return {"requirements": reqs, "current_version": next(
        (r["version"] for r in reqs if r["status"] == "current"), None)}


@router.get("/api/portal/opp/{opp_id}/requirements/{version}")
def get_requirement(opp_id: str, version: int, user: dict = Depends(get_current_user)):
    _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        req = flow_repo.get_requirement(opp_id, version)
    finally:
        flow_repo.close()
    if not req:
        raise HTTPException(status_code=404, detail="需求单版本不存在")
    return req


class RequirementBody(BaseModel):
    slots: dict = {}
    requirement_text: str = ""


class InitiateBody(BaseModel):
    opportunity: dict = {}
    slots: dict = {}
    requirement_text: str = ""
    assignee_name: str = ""


@router.post("/api/portal/opp/{opp_id}/initiate")
def initiate_opportunity(opp_id: str, body: InitiateBody,
                         user: dict = Depends(get_current_user)):
    # 业务发起一步到位：商机信息 + 需求 vN + 推进到 BOM。
    _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        _ensure_downstream_assignee(flow_repo, opp_id, "boming", body.assignee_name or "")
        req = flow_repo.initiate_requirement(
            opp_id,
            body.opportunity or {},
            body.slots,
            body.requirement_text,
            created_by=user.get("name") or "",
        )
        _assign_if_unset(flow_repo, opp_id, "boming",
                         body.assignee_name or "", user.get("name") or "")
    finally:
        flow_repo.close()
    if not req:
        raise HTTPException(status_code=404, detail="商机不存在")
    _attach_entity_card(
        opp_id,
        "requirement",
        req["version"],
        origin_node="requirement",
        current_node="boming",
        flow_status="submitted",
        created_by=user.get("name") or "",
    )
    return {"requirement": req}


@router.post("/api/portal/opp/{opp_id}/requirements")
def submit_requirement(opp_id: str, body: RequirementBody,
                       user: dict = Depends(get_current_user)):
    """更新需求再提交：存新版本 + 流程推进到 BOM 节点。"""
    _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        req = flow_repo.create_requirement(
            opp_id, body.slots, body.requirement_text,
            created_by=user.get("name") or "",
        )
    finally:
        flow_repo.close()
    _attach_entity_card(
        opp_id,
        "requirement",
        req["version"],
        origin_node="requirement",
        current_node="boming",
        flow_status="submitted",
        created_by=user.get("name") or "",
    )
    return {"requirement": req}


@router.post("/api/portal/opp/{opp_id}/requirements/draft")
def save_requirement_draft(opp_id: str, body: RequirementBody,
                           user: dict = Depends(get_current_user)):
    """新增/更新需求草稿：只保存，不推进流程，不影响当前版本。"""
    _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        req = flow_repo.create_or_update_requirement_draft(
            opp_id, body.slots, body.requirement_text,
            created_by=user.get("name") or "",
        )
    finally:
        flow_repo.close()
    _attach_entity_card(
        opp_id,
        "requirement",
        req["version"],
        origin_node="requirement",
        current_node="requirement",
        flow_status="draft",
        created_by=user.get("name") or "",
    )
    return {"requirement": req}


@router.post("/api/portal/opp/{opp_id}/requirements/{version}/submit")
def submit_requirement_draft(opp_id: str, version: int,
                             body: SubmitAssigneeBody = None,
                             user: dict = Depends(get_current_user)):
    """提交需求草稿：草稿转当前快照，旧当前归档，流程推进到 BOM。"""
    _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        _ensure_downstream_assignee(flow_repo, opp_id, "boming",
                                    (body.assignee_name if body else "") or "")
        req = flow_repo.submit_requirement_draft(opp_id, version)
        _assign_if_unset(flow_repo, opp_id, "boming",
                         (body.assignee_name if body else "") or "", user.get("name") or "")
    finally:
        flow_repo.close()
    if not req:
        raise HTTPException(status_code=404, detail="需求草稿不存在或已提交")
    _attach_entity_card(
        opp_id,
        "requirement",
        req["version"],
        origin_node="requirement",
        current_node="boming",
        flow_status="submitted",
        created_by=user.get("name") or "",
    )
    return {"requirement": req}


@router.delete("/api/portal/opp/{opp_id}/requirements/{version}")
def delete_requirement_draft(opp_id: str, version: int,
                             user: dict = Depends(get_current_user)):
    """删除需求草稿：仅允许删除 status=draft 的版本。"""
    _svc(opp_id, user)
    flow_repo = FlowRepository()
    try:
        ok = flow_repo.delete_requirement_draft(opp_id, version)
    finally:
        flow_repo.close()
    if not ok:
        raise HTTPException(status_code=404, detail="需求草稿不存在或已提交")
    _unlink_entity_card(opp_id, "requirement", version)
    return {"ok": True}


# ── 角色任务工作台 / 任务调度 ──

_NODE_PREV = {"boming": "requirement", "costing": "boming", "quoting": "costing"}
_NODE_LABEL = {"boming": "方案配置", "costing": "成本核算", "quoting": "报价单"}
_ASSIGN_ROLE_BY_NODE = {"boming": "te", "costing": "cost", "quoting": "quote"}


def _portal_is_admin(user: Optional[dict]) -> bool:
    return (user or {}).get("role") == "admin" or user_has_permission(user, "page.opportunities_all")


def _latest_prev_node(nodes: List[dict], prev: str) -> dict:
    matched = [n for n in nodes if n.get("node_key") == prev and n.get("action") in {"complete", "assign"}]
    return matched[-1] if matched else {}


def _task_item(flow_repo: FlowRepository, opp: dict, flow: dict,
               reqs: dict) -> dict:
    node = flow.get("current_node") or "requirement"
    if node == "assign":
        node = "requirement"
    req = reqs.get(opp.get("opportunity_id")) or {}
    slots = req.get("slots") or {}
    nodes = flow_repo.list_nodes(flow.get("flow_id") or "")
    prev_node = _NODE_PREV.get(node)
    latest = _latest_prev_node(nodes, prev_node) if prev_node else {}
    source_actor = opp.get("sales_person") or ""
    config_summary = ""
    amount_text = ""
    if prev_node:
        source_actor = latest.get("actor") or (flow.get("assignees") or {}).get(prev_node) or source_actor
        artifacts = latest.get("artifacts") or {}
        if isinstance(artifacts, str):
            try:
                artifacts = json.loads(artifacts)
            except Exception:
                artifacts = {}
        config_summary = artifacts.get("config_names") or artifacts.get("configs") or ""
        amount_text = artifacts.get("amount_text") or artifacts.get("total_amount") or ""
        if isinstance(config_summary, list):
            parts = []
            for x in config_summary:
                if isinstance(x, dict):
                    label = str(x.get("name") or "").strip()
                    model = str(x.get("server_model") or "").strip()
                    if model and model != label:
                        label = f"{label}·{model}" if label else model
                    if label:
                        parts.append(label)
                else:
                    parts.append(str(x))
            config_summary = " / ".join(parts)
        elif isinstance(config_summary, dict):
            label = str(config_summary.get("name") or "").strip()
            model = str(config_summary.get("server_model") or "").strip()
            if model and model != label:
                label = f"{label}·{model}" if label else model
            config_summary = label
        else:
            config_summary = str(config_summary or "")
    summary = " · ".join(str(x) for x in [
        slots.get("platform_type"),
        slots.get("chassis_form"),
        f"{slots.get('purchase_qty')}台" if slots.get("purchase_qty") else "",
    ] if x)
    return {
        "opportunity_id": opp.get("opportunity_id") or "",
        "customer_name": opp.get("customer_name") or "",
        "sales_person": opp.get("sales_person") or "",
        "source_actor": source_actor,
        "summary": summary,
        "config_summary": str(config_summary or ""),
        "amount_text": str(amount_text or ""),
        "current_node": node,
        "current_node_label": _NODE_LABEL.get(node, node),
        "flow_status": flow.get("status") or "running",
        "assignee": (flow.get("assignees") or {}).get(node) or "",
        "updated_at": flow.get("updated_at") or opp.get("updated_at") or "",
    }


@router.get("/api/portal/tasks")
def list_portal_tasks(node: str = "boming", scope: str = "mine",
                      page: int = 1, page_size: int = 20,
                      user: dict = Depends(get_current_user)):
    """角色任务队列：node=boming|costing|quoting；scope=mine|pool|all。"""
    if node not in _NODE_PREV:
        raise HTTPException(status_code=400, detail="不支持的流程节点")
    if scope not in {"mine", "pool", "all"}:
        raise HTTPException(status_code=400, detail="不支持的查询范围")
    is_admin = _portal_is_admin(user)
    if scope != "mine" and not is_admin:
        raise HTTPException(status_code=403, detail="无权查看该任务范围")

    flow_repo = FlowRepository()
    try:
        if scope == "mine":
            flows, total = flow_repo.list_task_flows(
                node, assignee_name=user.get("name") or "", page=page, page_size=page_size)
        elif scope == "pool":
            flows, total = flow_repo.list_task_flows(
                node, include_unassigned=True, page=page, page_size=page_size)
        else:
            flows, total = flow_repo.list_task_flows(
                node, page=page, page_size=page_size)

        if total > len(flows):
            if scope == "mine":
                all_flows, _ = flow_repo.list_task_flows(
                    node, assignee_name=user.get("name") or "", page=1, page_size=max(total, 1))
            elif scope == "pool":
                all_flows, _ = flow_repo.list_task_flows(
                    node, include_unassigned=True, page=1, page_size=max(total, 1))
            else:
                all_flows, _ = flow_repo.list_task_flows(
                    node, page=1, page_size=max(total, 1))
        else:
            all_flows = flows

        ids = [f.get("opportunity_id") for f in flows]
        opp_map = {}
        if ids:
            from app.models.opportunity import Opportunity
            rows = flow_repo.session.query(Opportunity).filter(
                Opportunity.opportunity_id.in_(ids)
            ).all()
            opp_map = {r.opportunity_id: r.to_dict() for r in rows}
        reqs = flow_repo.list_current_requirements_bulk(ids)
        items = [_task_item(flow_repo, opp_map.get(f.get("opportunity_id"), {}), f, reqs)
                 for f in flows]

        pool_total = flow_repo.list_task_flows(
            node, include_unassigned=True, page=1, page_size=1)[1]
        mine_total = flow_repo.list_task_flows(
            node, assignee_name=user.get("name") or "", page=1, page_size=1)[1]
        if is_admin and scope == "all":
            mine_total = total
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(1 for f in all_flows if (f.get("updated_at") or "").startswith(today))
        return {
            "items": items,
            "total": total,
            "summary": {
                "total": total,
                "today": today_count,
                "mine": mine_total,
                "pool": pool_total,
            },
        }
    finally:
        flow_repo.close()


@router.get("/api/portal/dispatch")
def portal_dispatch(admin: dict = Depends(require_admin)):
    """任务调度页数据：业务账号、默认分派规则、公共池统计、转交记录。"""
    flow_repo = FlowRepository()
    user_repo = FeedUserRepository()
    opp_repo = OpportunityRepository()
    try:
        users = user_repo.list_all()
        businesses = [
            {"user_id": u["user_id"], "name": u["name"]}
            for u in users
            if u.get("role") == "business" and u.get("is_active", True)
        ]
        businesses.sort(key=lambda x: x["name"])
        rules = flow_repo.get_assignment_rules()
        unassigned = {
            node: flow_repo.list_task_flows(node, include_unassigned=True, page=1, page_size=1)[1]
            for node in ("boming", "costing", "quoting")
        }

        transfers = []
        for e in flow_repo.list_assignment_events(30):
            flow = flow_repo.get_flow_by_id(e.get("flow_id") or "") or {}
            oid = flow.get("opportunity_id") or ""
            opp = opp_repo.get_opportunity(oid) if oid else None
            comment = e.get("comment") or ""
            m = re.match(r"由 (.*?) 转交给 (.*)", comment)
            transfers.append({
                "time": e.get("created_at") or "",
                "opportunity_id": oid,
                "customer_name": (opp or {}).get("customer_name") or "",
                "node_key": e.get("node_key") or "",
                "node_label": _NODE_LABEL.get(e.get("node_key"), e.get("node_key") or ""),
                "from_assignee": m.group(1) if m else "",
                "to_assignee": m.group(2) if m else "",
                "actor": e.get("actor") or "",
            })

        return {
            "businesses": businesses,
            "rules": rules,
            "unassigned": unassigned,
            "transfers": transfers,
        }
    finally:
        flow_repo.close()
        user_repo.close()
        opp_repo.close()


@router.get("/api/portal/assign-options")
def portal_assign_options(user: dict = Depends(get_current_user)):
    """转交/分派所需候选账号：业务 + 各节点处理人。"""
    if not user_has_permission(user, "page.opportunities"):
        raise HTTPException(status_code=403, detail="无权访问")
    user_repo = FeedUserRepository()
    try:
        users = user_repo.list_all()
        assignees = {}
        for node, role in _ASSIGN_ROLE_BY_NODE.items():
            items = sorted(
                [u["name"] for u in users if u.get("role") == role and u.get("is_active", True)]
            )
            assignees[node] = items
        businesses = []
        if _portal_is_admin(user):
            businesses = sorted(
                [{"user_id": u["user_id"], "name": u["name"]}
                 for u in users if u.get("role") == "business" and u.get("is_active", True)],
                key=lambda x: x["name"],
            )
        return {"businesses": businesses, "assignees": assignees}
    finally:
        user_repo.close()


@router.get("/api/portal/assignment-rules/{business_user_id}")
def portal_assignment_rules(business_user_id: str, user: dict = Depends(get_current_user)):
    """单业务默认分派规则：业务本人（自动填充商机字段）或管理员可读。"""
    if not (_portal_is_admin(user) or (user.get("user_id") and user.get("user_id") == business_user_id)):
        raise HTTPException(status_code=403, detail="无权查看该业务分派配置")
    flow_repo = FlowRepository()
    try:
        rules = flow_repo.get_assignment_rules(business_user_id)
    finally:
        flow_repo.close()
    return {"rules": rules}


class AssignmentRuleBody(BaseModel):
    business_user_id: str
    node_key: str
    assignee_name: str = ""


@router.put("/api/portal/assignment-rules")
def upsert_assignment_rule(body: AssignmentRuleBody,
                           admin: dict = Depends(require_admin)):
    if body.node_key not in _NODE_PREV:
        raise HTTPException(status_code=400, detail="不支持的流程节点")
    if not (body.business_user_id or "").strip() or not (body.assignee_name or "").strip():
        raise HTTPException(status_code=400, detail="业务账号和处理人不能为空")
    flow_repo = FlowRepository()
    try:
        rule = flow_repo.upsert_assignment_rule(
            body.business_user_id.strip(), body.node_key, body.assignee_name.strip()
        )
        return {"rule": rule}
    finally:
        flow_repo.close()


@router.delete("/api/portal/assignment-rules")
def delete_assignment_rule(body: AssignmentRuleBody,
                           admin: dict = Depends(require_admin)):
    if body.node_key not in _NODE_PREV:
        raise HTTPException(status_code=400, detail="不支持的流程节点")
    flow_repo = FlowRepository()
    try:
        ok = flow_repo.delete_assignment_rule(
            (body.business_user_id or "").strip(), body.node_key
        )
        return {"ok": ok}
    finally:
        flow_repo.close()


class PortalAssignBody(BaseModel):
    node_key: str
    assignee_name: str
    save_rule: bool = False


def _can_assign_portal_task(user: dict, flow: dict, node_key: str) -> bool:
    if _portal_is_admin(user):
        return True
    if (flow.get("current_node") or "") != node_key:
        return False
    assignee = (flow.get("assignees") or {}).get(node_key) or ""
    if assignee == user.get("name"):
        return True
    return not assignee and user.get("role") == _ASSIGN_ROLE_BY_NODE.get(node_key)


def _business_user_id_for_opp(opp: dict) -> str:
    if opp.get("owner_user_id"):
        return opp["owner_user_id"]
    sales_person = opp.get("sales_person") or ""
    if sales_person:
        repo = FeedUserRepository()
        try:
            for u in repo.list_all():
                if u.get("name") == sales_person and u.get("role") == "business":
                    return u.get("user_id") or ""
        finally:
            repo.close()
    return ""


@router.post("/api/portal/opp/{opp_id}/assign")
def assign_portal_task(opp_id: str, body: PortalAssignBody,
                       user: dict = Depends(get_current_user)):
    """单条任务指派/转交（管理员或当前处理人）。save_rule=true 时同步保存默认规则。"""
    if body.node_key not in _NODE_PREV:
        raise HTTPException(status_code=400, detail="不支持的流程节点")
    if not (body.assignee_name or "").strip():
        raise HTTPException(status_code=400, detail="处理人不能为空")
    opp, flow = _svc(opp_id, user)
    if not _can_assign_portal_task(user, flow, body.node_key):
        raise HTTPException(status_code=403, detail="无权指派该节点任务")

    flow_repo = FlowRepository()
    try:
        updated = flow_repo.assign_task(
            flow["flow_id"], body.node_key, body.assignee_name.strip(),
            actor=user.get("name") or "",
        )
        if body.save_rule and _portal_is_admin(user):
            business_user_id = _business_user_id_for_opp(opp)
            if business_user_id:
                flow_repo.upsert_assignment_rule(
                    business_user_id, body.node_key, body.assignee_name.strip()
                )
        return {"flow": updated, "nodes": flow_repo.list_nodes(flow["flow_id"])}
    finally:
        flow_repo.close()


@router.post("/api/portal/opp/{opp_id}/transfer")
def transfer_portal_task(opp_id: str, body: PortalAssignBody,
                         user: dict = Depends(get_current_user)):
    """转交给另一处理人；与 assign 共用权限/记录逻辑，不保存默认规则。"""
    body.save_rule = False
    return assign_portal_task(opp_id, body, user)
