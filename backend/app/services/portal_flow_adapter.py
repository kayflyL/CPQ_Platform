# -*- coding: utf-8 -*-
"""商机真实流程适配层：让 Skill 的节点结果落到商机详情页四步对象。"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.repository.flow_card_repo import FlowCardRepository
from app.repository.flow_repo import FlowRepository

logger = logging.getLogger(__name__)


def _first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _readable_plan_description(plan: dict) -> str:
    """把 plan 的机型描述转成人可读文本，绝不把 product_content 整个 dict 字符串化。"""
    content = plan.get("product_content")
    if isinstance(content, dict):
        for key in ("overview", "tagline", "description", "summary"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        highlights = content.get("highlights") or []
        if isinstance(highlights, list) and highlights:
            first = highlights[0]
            if isinstance(first, dict):
                text = first.get("text") or first.get("title") or ""
                if str(text).strip():
                    return str(text).strip()
    for key in ("use", "selling_points"):
        value = plan.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(plan.get("model") or plan.get("name") or "AI方案").strip()


def _attach_entity_card(
    opportunity_id: str,
    entity_type: str,
    entity_id: Any,
    *,
    origin_node: str,
    current_node: str,
    created_by: str = "",
    flow_status: str = "draft",
    visible_upstream: bool = True,
) -> dict:
    repo = FlowCardRepository()
    try:
        card = repo.get_card_for_entity(opportunity_id, entity_type, entity_id)
        if card:
            repo.update_card(card["id"], current_node=current_node, flow_status=flow_status)
            card_id = card["id"]
        else:
            card = repo.ensure_card(
                opportunity_id,
                origin_node=origin_node,
                current_node=current_node,
                created_by=created_by,
                visible_upstream=visible_upstream,
                flow_status=flow_status,
            )
            card_id = card["id"]
        repo.link_entity(card_id, entity_type, entity_id, opportunity_id=opportunity_id)
        return repo.get_card(card_id) or card
    finally:
        repo.close()


def requirement_slots_from_ext(ext: Optional[dict]) -> dict:
    """线索登记表唯一视图：把 ext 收口为 RequirementSlots 契约。

    配置：server_type/platform_type/chassis_form/server_model/purchase_qty/warranty_years
    部件：kp_rows[{part_category, description, qty, catalogue, note}]
    登记表只有这一套：Catalogue(part_category) + Configuration Description(description) + qty。
    """
    from app.services.slot_contract import canonical_get
    ext = ext or {}
    slots: dict[str, Any] = {}
    for key in ("server_type", "platform_type", "chassis_form", "server_model"):
        v = canonical_get(ext, key)
        if v:
            slots[key] = str(v)
    purchase_qty = _first(ext.get("purchase_qty"), ext.get("server_qty"), ext.get("whole_qty"))
    if purchase_qty:
        slots["purchase_qty"] = _as_int(purchase_qty, 1) or 1
    if ext.get("warranty_years"):
        slots["warranty_years"] = str(ext["warranty_years"])
    kp = ext.get("kp_rows")
    if isinstance(kp, list):
        rows = []
        for r in kp:
            if not isinstance(r, dict):
                continue
            part_category = str(r.get("part_category") or r.get("category") or "").strip()
            if part_category:
                from app.services.part_selector import resolve_kp_category
                resolved = resolve_kp_category(part_category)
                if not resolved:
                    # 非 KP 大类（如「电源」属机箱）不入登记表 KP 行，保留在需求原文
                    continue
                part_category = resolved
            if not part_category:
                continue
            row: dict[str, Any] = {
                "part_category": part_category,
                "description": str(r.get("description") or "").strip(),
                "catalogue": str(r.get("catalogue") or "").strip(),
                "note": str(r.get("note") or "").strip(),
            }
            try:
                row["qty"] = int(float(r.get("qty", 1) or 1))
            except (TypeError, ValueError):
                row["qty"] = 1
            rows.append(row)
        if rows:
            slots["kp_rows"] = rows
    return slots


def merge_requirement_slots(base: Optional[dict], update: Optional[dict]) -> dict:
    out = dict(base or {})
    for key, value in (update or {}).items():
        if isinstance(value, dict) and key in ("cpu", "memory", "psu", "raid"):
            merged = dict(out.get(key) or {})
            merged.update(value)
            out[key] = merged
        elif isinstance(value, list) and key in ("storage", "gpu", "nic") and value:
            out[key] = value
        elif value not in (None, "", [], {}):
            out[key] = value
    return out


def load_requirement_draft(opportunity_id: str) -> Optional[dict]:
    if not opportunity_id:
        return None
    repo = FlowRepository()
    try:
        rows = repo.list_requirements(opportunity_id)
        return next((r for r in rows if r.get("status") == "draft"), None) or next(
            (r for r in rows if r.get("status") == "current"), None
        )
    except Exception:
        logger.exception("读取需求草稿失败 opp=%s", opportunity_id)
        return None
    finally:
        repo.close()


def build_requirement_text(opportunity_id: Optional[str], incoming_text: str, supplement_text: Optional[str] = None) -> str:
    base = ""
    if opportunity_id:
        draft = load_requirement_draft(opportunity_id)
        base = str((draft or {}).get("requirement_text") or "").strip()
    incoming = str(incoming_text or "").strip()
    supplement = str(supplement_text or "").strip()
    if supplement:
        return "\n".join(x for x in (base, supplement) if x)
    if incoming:
        if base and incoming != base:
            return "\n".join((base, incoming))
        return incoming
    return base


def save_requirement_draft(opportunity_id: str, slots: dict, requirement_text: str, created_by: str = "") -> Optional[dict]:
    if not opportunity_id:
        raise ValueError("缺少 opportunity_id，无法写入需求草稿")
    repo = FlowRepository()
    try:
        req = repo.create_or_update_requirement_draft(
            opportunity_id, slots or {}, requirement_text or "", created_by or ""
        )
    finally:
        repo.close()
    if req:
        _attach_entity_card(
            opportunity_id, "requirement", req["version"],
            origin_node="requirement", current_node="requirement",
            created_by=created_by or "", flow_status="draft", visible_upstream=True,
        )
    return req


def submit_requirement_draft(opportunity_id: str, version: int, created_by: str = "") -> Optional[dict]:
    repo = FlowRepository()
    try:
        req = repo.submit_requirement_draft(opportunity_id, version)
    finally:
        repo.close()
    if req:
        _attach_entity_card(
            opportunity_id, "requirement", req["version"],
            origin_node="requirement", current_node="boming",
            created_by=created_by or "", flow_status="submitted", visible_upstream=False,
        )
    return req


def _normalize_sheet_row(row: dict, category: str) -> dict:
    return {
        "category": category,
        "catalogue": str(row.get("catalogue") or row.get("name") or row.get("pn") or ""),
        "description": str(row.get("description") or ""),
        "part_category": str(row.get("part_category") or ""),
        "qty": _as_int(row.get("qty"), 1) or 1,
        "base_price": _as_float(row.get("base_price"), 0.0),
        "final_price": _as_float(row.get("final_price"), 0.0),
        "profit_margin": _as_float(row.get("profit_margin"), 0.0),
        "currency": str(row.get("currency") or "RMB"),
        "note": str(row.get("note") or ""),
    }


def plans_to_portal_configs(plans: list, slots: Optional[dict] = None) -> list[dict]:
    slots = slots or {}
    configs: list[dict] = []
    purchase_qty = _as_int(slots.get("purchase_qty"), 1) or 1
    for index, plan in enumerate(plans or [], start=1):
        if not isinstance(plan, dict):
            continue
        cfg = plan.get("cfg") if isinstance(plan.get("cfg"), dict) else {}
        rows = cfg.get("bom_excel_rows") or []
        l6_rows = [_normalize_sheet_row(r, "L6") for r in rows if str(r.get("category") or "") != "Key Parts"]
        kp_rows = [_normalize_sheet_row(r, "Key Parts") for r in rows if str(r.get("category") or "") == "Key Parts"]
        summary = plan.get("summary") if isinstance(plan.get("summary"), dict) else {}
        l6_cost = _as_float(summary.get("l6_cost"), _as_float(plan.get("l6_cost"), 0.0))
        kp_cost = _as_float(summary.get("kp_cost"), 0.0)
        total_cost = _as_float(summary.get("total_cost"), l6_cost + kp_cost)
        configs.append({
            "name": f"CFG{index}",
            "server_model": str(plan.get("model") or plan.get("name") or ""),
            "description": _readable_plan_description(plan),
            "qty": purchase_qty,
            "l6_cost": l6_cost,
            "l6_margin": 0.0,
            "l6_rows": l6_rows,
            "kp_rows": kp_rows,
            "totals": {"l6Cost": l6_cost, "kpCost": kp_cost, "totalCost": total_cost, "currency": summary.get("currency") or "RMB"},
        })
    return configs


def build_preview_bom_scheme(ctx: dict, config: Optional[dict] = None) -> Optional[dict]:
    """把 ctx.plans 转成不落库的 BOM 方案预览，供试运行/聊天终端复用只读 SchemeEditor。"""
    slots = requirement_slots_from_ext(ctx.get("ext") or {})
    configs = plans_to_portal_configs(ctx.get("plans") or [], slots)
    if not configs:
        return None
    name = (config or {}).get("name") if isinstance(config, dict) else None
    return {
        "id": f"preview-{ctx.get('opportunity_id') or 'test-run'}",
        "name": str(name or "").strip() or "试运行方案",
        "status": "draft",
        "configs": configs,
        "requirement_text": str(ctx.get("requirement_text") or ""),
        "slots": slots,
    }

def save_bom_scheme_draft(opportunity_id: str, configs: list, created_by: str = "", name: Optional[str] = None,
                          config_relation: str = "compose", primary_config: str = "") -> Optional[dict]:
    if not opportunity_id:
        raise ValueError("缺少 opportunity_id，无法写入 BOM 方案草稿")
    if not configs:
        raise ValueError("方案配置为空，无法写入 BOM 方案草稿")
    scheme_name = str(name or "").strip() or "AI方案"
    repo = FlowRepository()
    try:
        existing = next((scheme for scheme in repo.list_bom_schemes(opportunity_id) if scheme.get("name") == scheme_name and scheme.get("status") == "draft"), None)
        scheme_id = existing.get("id") if existing else None
        scheme = repo.save_bom_scheme_draft(
            opportunity_id, scheme_id, scheme_name, configs, created_by or "",
            config_relation, primary_config,
        )
    finally:
        repo.close()
    if scheme:
        _attach_entity_card(
            opportunity_id, "bom", scheme["id"],
            origin_node="boming", current_node="boming",
            created_by=created_by or "", flow_status="processing", visible_upstream=True,
        )
    return scheme


def _requirement_snapshot_slots(ctx: dict) -> dict:
    """线索登记表只以「需求分析节点冻结的需求快照」为准，禁止从下游可变 ext 重新推导。"""
    snap = ctx.get("requirement") if isinstance(ctx.get("requirement"), dict) else {}
    if snap:
        return requirement_slots_from_ext(snap)
    return requirement_slots_from_ext(ctx.get("ext") or {})


def _write_mode(ctx: dict) -> str:
    """落库写模式（2026-09-12 B1，去死判）：由入口显式决定，不看全仓从不写入的 business_mode。

    入口口径（colleague_turn_service）：试运行入口 → preview（不落库）；带商机 → draft；
    两者都没有 → none（不落库，出试运行预览）。历史 ctx 没有该字段时按「有商机才落草稿」兜底。
    """
    ctx = ctx or {}
    mode = str(ctx.get("write_mode") or "").strip().lower()
    if mode in ("preview", "draft", "none"):
        return mode
    return "draft" if str(ctx.get("opportunity_id") or "").strip() else "none"


def _can_persist_draft(ctx: dict) -> bool:
    """写模式 = draft 且确有商机时，才允许落库（preview / none 一律只出预览）。"""
    return (_write_mode(ctx) == "draft"
            and bool(str((ctx or {}).get("opportunity_id") or "").strip()))


def seed_ext_from_requirement_draft(ext: dict, opportunity_id: str) -> bool:
    """2026-09-12 B2 读回：把该商机的需求草稿（真相表）播种回本轮工作副本 ext。

    草稿里没有的键一律不动（不拿空表覆盖本轮现场）；草稿里有的以**库为准**——客户在
    商机详情页手改过线索登记表，对话下一轮就按改后的走。ext 仍是当轮工作副本。
    """
    if not isinstance(ext, dict) or not str(opportunity_id or "").strip():
        return False
    draft = load_requirement_draft(str(opportunity_id).strip())
    slots = draft.get("slots") if isinstance((draft or {}).get("slots"), dict) else {}
    if not slots:
        return False
    from app.services.slot_contract import canonical_set
    for key in ("server_type", "platform_type", "chassis_form", "server_model",
                "purchase_qty", "warranty_years"):
        value = slots.get(key)
        if value not in (None, "", [], {}):
            canonical_set(ext, key, value)
    rows = slots.get("kp_rows")
    if isinstance(rows, list) and rows:
        ext["kp_rows"] = [dict(r) for r in rows if isinstance(r, dict)]
    return True


def save_scheme_progress_from_ctx(ctx: dict, operator: str = "",
                                  name: Optional[str] = None) -> Optional[dict]:
    """2026-09-12 B3：模型/配件节点把**当前进度**原地写回该商机的方案配置草稿。

    机型已锁 → 用现成组装器组出 L6 段（未落地配件按既定口径不进 kp_rows）；配件已落 →
    同一份里带出 KP 段。走现成 save_bom_scheme_draft：同商机同名唯一、已有草稿原地更新
    （不新开版本），所以中途写与交付写落在同一张卡上。写模式非 draft 时只读不写。
    """
    if not _can_persist_draft(ctx):
        return None
    try:
        from app.services.skill_node_runtime import build_plans
        cfg = (ctx.get("flow_configs") or {}).get("compose")
        plans = build_plans(ctx, cfg if isinstance(cfg, dict) else {})
        slots = _requirement_snapshot_slots(ctx)
        configs = plans_to_portal_configs(plans, slots)
        if not configs:
            return None
        return save_bom_scheme_draft(
            str(ctx.get("opportunity_id") or "").strip(), configs, operator, name,
            slots.get("config_relation") or "compose", slots.get("primary_config") or "")
    except Exception:
        logger.exception("写方案配置草稿失败 opp=%s", (ctx or {}).get("opportunity_id"))
        return None


def persist_requirement_from_ctx(ctx: dict, operator: str = "") -> Optional[dict]:
    opportunity_id = str(ctx.get("opportunity_id") or "").strip()
    if not opportunity_id or not _can_persist_draft(ctx):
        return None
    try:
        slots = _requirement_snapshot_slots(ctx)
        text = str(ctx.get("requirement_text_snapshot") or ctx.get("requirement_text") or "")
        return save_requirement_draft(opportunity_id, slots, text, operator)
    except Exception:
        logger.exception("持久化需求草稿失败 opp=%s", opportunity_id)
        return None


def persist_requirement_and_bom_from_ctx(ctx: dict, operator: str = "", config: Optional[dict] = None) -> Optional[dict]:
    """AI Office / 商机流共用：先原地落线索登记表（需求单），再落方案配置（BOM 草稿）。

    2026-09-12 B4：交付 = 原地把对话期间那张需求草稿提交成 current（submit_requirement_draft），
    不再 initiate_requirement 新开一版——一商机一需求，对话期间与详情页看到的始终是同一条。
    """
    opportunity_id = str(ctx.get("opportunity_id") or "").strip()
    if not opportunity_id or not _can_persist_draft(ctx):
        return None
    try:
        slots = _requirement_snapshot_slots(ctx)
        _req_text = str(ctx.get("requirement_text_snapshot") or ctx.get("requirement_text") or "")
        # 先写回草稿（保证提交的就是本轮内容），再原地提交那张草稿。
        draft = save_requirement_draft(opportunity_id, slots, _req_text, operator)
        requirement = submit_requirement_draft(
            opportunity_id, int((draft or {}).get("version") or 0), operator) if draft else None
        if not requirement:
            logger.warning("需求草稿提交失败（无草稿可提交）opp=%s", opportunity_id)
        if requirement:
            _attach_entity_card(
                opportunity_id,
                "requirement",
                requirement["version"],
                origin_node="requirement",
                current_node="boming",
                created_by=operator,
                flow_status="submitted",
                visible_upstream=True,
            )

        configs = plans_to_portal_configs(ctx.get("plans") or [], slots)
        if not configs:
            return None
        name = (config or {}).get("name") if isinstance(config, dict) else None
        return save_bom_scheme_draft(opportunity_id, configs, operator, name,
                                     slots.get("config_relation") or "compose",
                                     slots.get("primary_config") or "")
    except Exception:
        logger.exception("持久化需求单/BOM 方案失败 opp=%s", opportunity_id)
        return None


def persist_bom_scheme_from_ctx(ctx: dict, operator: str = "", config: Optional[dict] = None) -> Optional[dict]:
    opportunity_id = str(ctx.get("opportunity_id") or "").strip()
    if not opportunity_id or not _can_persist_draft(ctx):
        return None
    try:
        slots = requirement_slots_from_ext(ctx.get("ext") or {})
        configs = plans_to_portal_configs(ctx.get("plans") or [], slots)
        if not configs:
            return None
        name = (config or {}).get("name") if isinstance(config, dict) else None
        return save_bom_scheme_draft(opportunity_id, configs, operator, name,
                                     slots.get("config_relation") or "compose",
                                     slots.get("primary_config") or "")
    except Exception:
        logger.exception("持久化 BOM 方案草稿失败 opp=%s", opportunity_id)
        return None
