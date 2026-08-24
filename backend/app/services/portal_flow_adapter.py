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
    ext = ext or {}
    slots: dict[str, Any] = {}
    purchase_qty = _first(ext.get("purchase_qty"), ext.get("server_qty"), ext.get("whole_qty"))
    if purchase_qty:
        slots["purchase_qty"] = _as_int(purchase_qty, 1) or 1
    server_type = _first(ext.get("server_type_name"), ext.get("usage"))
    if server_type:
        slots["server_type"] = str(server_type)
    series = _first(ext.get("series"), ext.get("platform_type"))
    if series:
        slots["platform_type"] = str(series)
    form = _first(ext.get("form"), ext.get("chassis_form"))
    if form:
        slots["chassis_form"] = str(form).upper()

    cpu_signal = ext.get("cpu_signal") if isinstance(ext.get("cpu_signal"), dict) else {}
    if cpu_signal:
        cpu: dict[str, Any] = {}
        for key in ("model", "brand", "cores", "tdp_w"):
            if cpu_signal.get(key) is not None:
                cpu[key] = cpu_signal[key]
        qty_map = ext.get("qty_map") if isinstance(ext.get("qty_map"), dict) else {}
        qty = _first(qty_map.get("CPU"), cpu_signal.get("qty"))
        if qty is not None:
            cpu["qty"] = _as_int(qty, 0) or None
        cpu = {k: v for k, v in cpu.items() if v not in (None, "")}
        if cpu:
            slots["cpu"] = cpu

    mem_signal = ext.get("mem_signal") if isinstance(ext.get("mem_signal"), dict) else {}
    mem_groups = ext.get("mem_groups") if isinstance(ext.get("mem_groups"), list) else []
    if mem_signal or mem_groups:
        memory: dict[str, Any] = {}
        if mem_signal.get("per_stick_gb") is not None:
            memory["per_stick_gb"] = mem_signal["per_stick_gb"]
        if mem_signal.get("type"):
            memory["type"] = mem_signal["type"]
        if mem_signal.get("speed_mt") is not None:
            memory["speed_mt"] = mem_signal["speed_mt"]
        if mem_signal.get("brand"):
            memory["brand"] = mem_signal["brand"]
        per_stick = mem_signal.get("per_stick_gb")
        mem_qty = _first((mem_groups[0] or {}).get("qty") if mem_groups else None, mem_signal.get("qty"))
        if mem_qty is None and per_stick and mem_signal.get("total_gb"):
            try:
                total = int(mem_signal["total_gb"])
                per = int(per_stick)
                if per > 0 and total % per == 0:
                    mem_qty = total // per
            except (TypeError, ValueError):
                mem_qty = None
        if mem_qty is not None:
            memory["qty"] = _as_int(mem_qty, 0) or None
        memory = {k: v for k, v in memory.items() if v not in (None, "")}
        if memory:
            slots["memory"] = memory

    drives = []
    for group in ext.get("drive_groups") or []:
        if not isinstance(group, dict):
            continue
        term = group.get("term") or ""
        if not term:
            continue
        row = {"capacity": str(term), "qty": _as_int(group.get("qty"), 1) or 1}
        if group.get("kind"):
            row["interface"] = group["kind"]
        drives.append(row)
    if drives:
        slots["storage"] = drives

    gpus = []
    raw_gpu = (ext.get("llm_enhanced") or {}).get("gpu") if isinstance(ext.get("llm_enhanced"), dict) else None
    for group in raw_gpu or []:
        if not isinstance(group, dict):
            continue
        model = group.get("model") or ""
        qty = group.get("qty")
        if model or qty:
            gpus.append({"model": str(model), "qty": _as_int(qty, 1) or 1})
    if not gpus:
        for group in ext.get("gpu_groups") or []:
            if not isinstance(group, dict):
                continue
            tokens = group.get("tokens") or []
            qty = group.get("qty")
            if not tokens and not qty:
                continue
            model = " ".join(str(t) for t in tokens[:2]).strip()
            gpus.append({"model": model, "qty": _as_int(qty, 1) or 1})
    if gpus:
        slots["gpu"] = gpus

    nic_rows = []
    msf = ext.get("multi_spec_filters") if isinstance(ext.get("multi_spec_filters"), dict) else {}
    for line in msf.get("Network(NIC) requirement") or []:
        if not isinstance(line, dict):
            continue
        filters = line.get("filters") or []
        speed = None
        ports = None
        for item in filters:
            if not isinstance(item, dict):
                continue
            spec_key = str(item.get("spec_key") or "")
            value = str(item.get("value") or "")
            if spec_key == "Link Speed" and value:
                try:
                    speed = int(value.rstrip("G"))
                except ValueError:
                    speed = None
            elif spec_key == "Ports" and value:
                try:
                    ports = int(value)
                except ValueError:
                    ports = None
        names = line.get("name_contains") or []
        row: dict[str, Any] = {"model": str(names[0] if names else "") or None, "qty": _as_int(line.get("qty"), 1) or 1}
        if speed is not None:
            row["speed_g"] = speed
        if ports is not None:
            row["ports"] = ports
        row = {k: v for k, v in row.items() if v not in (None, "")}
        if row:
            nic_rows.append(row)
    if nic_rows:
        slots["nic"] = nic_rows

    psu_signal = ext.get("psu_signal") if isinstance(ext.get("psu_signal"), dict) else {}
    if psu_signal:
        psu = {k: v for k, v in psu_signal.items() if v not in (None, "")}
        if psu:
            slots["psu"] = psu

    raid_groups = ext.get("raid_groups") if isinstance(ext.get("raid_groups"), list) else []
    raid_rows = []
    for group in raid_groups:
        if not isinstance(group, dict):
            continue
        row = {k: v for k, v in group.items() if v not in (None, "")}
        if row.get("model") or row.get("raid_levels"):
            raid_rows.append(row)
    if not raid_rows:
        raid_signal = ext.get("raid_signal") if isinstance(ext.get("raid_signal"), dict) else {}
        raid = {k: v for k, v in raid_signal.items() if v not in (None, "")}
        if raid.get("model") or raid.get("raid_levels"):
            raid_rows.append(raid)
    if raid_rows:
        slots["raid"] = raid_rows

    if ext.get("budget") is not None:
        try:
            slots["budget"] = float(ext["budget"])
        except (TypeError, ValueError):
            pass
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

def save_bom_scheme_draft(opportunity_id: str, configs: list, created_by: str = "", name: Optional[str] = None) -> Optional[dict]:
    if not opportunity_id:
        raise ValueError("缺少 opportunity_id，无法写入 BOM 方案草稿")
    if not configs:
        raise ValueError("方案配置为空，无法写入 BOM 方案草稿")
    scheme_name = str(name or "").strip() or "AI方案"
    repo = FlowRepository()
    try:
        existing = next((scheme for scheme in repo.list_bom_schemes(opportunity_id) if scheme.get("name") == scheme_name and scheme.get("status") == "draft"), None)
        scheme_id = existing.get("id") if existing else None
        scheme = repo.save_bom_scheme_draft(opportunity_id, scheme_id, scheme_name, configs, created_by or "")
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


def persist_requirement_from_ctx(ctx: dict, operator: str = "") -> Optional[dict]:
    opportunity_id = str(ctx.get("opportunity_id") or "").strip()
    if not opportunity_id or ctx.get("business_mode") != "opportunity_flow":
        return None
    try:
        slots = _requirement_snapshot_slots(ctx)
        text = str(ctx.get("requirement_text_snapshot") or ctx.get("requirement_text") or "")
        return save_requirement_draft(opportunity_id, slots, text, operator)
    except Exception:
        logger.exception("持久化需求草稿失败 opp=%s", opportunity_id)
        return None


def persist_requirement_and_bom_from_ctx(ctx: dict, operator: str = "", config: Optional[dict] = None) -> Optional[dict]:
    """AI Office / 商机流共用：先落线索登记表（需求单），再落方案配置（BOM 草稿）。"""
    opportunity_id = str(ctx.get("opportunity_id") or "").strip()
    if not opportunity_id or ctx.get("business_mode") != "opportunity_flow":
        return None
    try:
        slots = _requirement_snapshot_slots(ctx)
        _req_text = str(ctx.get("requirement_text_snapshot") or ctx.get("requirement_text") or "")
        repo = FlowRepository()
        try:
            requirement = repo.initiate_requirement(
                opportunity_id,
                {},
                slots,
                _req_text,
                created_by=operator,
            )
        finally:
            repo.close()
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
        return save_bom_scheme_draft(opportunity_id, configs, operator, name)
    except Exception:
        logger.exception("持久化需求单/BOM 方案失败 opp=%s", opportunity_id)
        return None


def persist_bom_scheme_from_ctx(ctx: dict, operator: str = "", config: Optional[dict] = None) -> Optional[dict]:
    opportunity_id = str(ctx.get("opportunity_id") or "").strip()
    if not opportunity_id or ctx.get("business_mode") != "opportunity_flow":
        return None
    try:
        slots = requirement_slots_from_ext(ctx.get("ext") or {})
        configs = plans_to_portal_configs(ctx.get("plans") or [], slots)
        if not configs:
            return None
        name = (config or {}).get("name") if isinstance(config, dict) else None
        return save_bom_scheme_draft(opportunity_id, configs, operator, name)
    except Exception:
        logger.exception("持久化 BOM 方案草稿失败 opp=%s", opportunity_id)
        return None
