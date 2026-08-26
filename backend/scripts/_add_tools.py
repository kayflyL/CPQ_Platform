# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "agent_tools.py")

helpers = r'''def _as_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _part_family(category: str, family_kw: dict) -> str:
    """按规则库部件家族关键词归类类目（数据驱动，不写死词表）。"""
    cat = str(category or "").strip()
    up = cat.upper()
    for fam, kws in (family_kw or {}).items():
        hits = kws or {}
        if any(up.startswith(str(h).upper()) for h in hits.get("cat_upper") or []):
            return fam
        if any(str(h).upper() in up for h in hits.get("cat") or []):
            return fam
        if any(up.endswith(str(h).upper()) for h in hits.get("name_upper") or []):
            return fam
    return ""


def _cap_check(label: str, qty: int, cap, message: str, violations: list, warnings: list) -> None:
    if qty is None:
        return
    if cap is None or cap <= 0:
        return
    if qty > cap:
        violations.append({"code": f"{label}_over_capacity", "severity": "critical", "message": message.format(qty=qty, cap=cap)})
    elif qty == cap:
        warnings.append({"severity": "info", "message": message.format(qty=qty, cap=cap) + "（已满配）"})


'''

handler3 = r'''async def _tool_load_requirement_rules(args: dict) -> Any:
    """load_requirement_rules → 读需求规则目录（别名/系列/形态/RAID/功耗等），供 AI 规范化需求，不背规则。"""
    rule_types = args.get("rule_types") or [
        "category_alias", "platform_series_map", "type_alias",
        "gpu_form_map", "raid_level_map", "cpu_mem_generation", "workload_map",
    ]
    if not isinstance(rule_types, list):
        rule_types = [rule_types]
    from app.services import requirement_rule_catalog as _rc
    out = {}
    for rt in rule_types:
        body = _rc.active_bodies(str(rt))
        if body:
            out[str(rt)] = body
    return {"count": int(sum(len(v) for v in out.values())), "rules": out}


async def _tool_validate_compat(args: dict) -> Any:
    """validate_compat → 校验机型基准与配件兼容（读目录/规则库；AI 不背兼容表）。

    baseline: select_models 返回的候选机型（含 form/bays/max_cpu/max_dimm/base_config）。
    parts:    select_parts 返回的配件清单。
    requirement: 需求槽位（可选，用于 GPU 形态跨检）。
    """
    baseline = args.get("baseline")
    parts = args.get("parts") or []
    requirement = args.get("requirement") or {}
    if not isinstance(baseline, dict):
        return {"error": "缺 baseline 机型对象（请先调 select_models）"}
    if not isinstance(parts, list):
        return {"error": "缺 parts 配件清单（请先调 select_parts）"}

    from app.services import requirement_rule_catalog as _rc
    family_kw = _rc.part_family_keywords()
    bc = baseline.get("base_config") if isinstance(baseline.get("base_config"), dict) else {}

    def _cap(v=None, default=None):
        return _as_int(v if v is not None else default, None)

    capacity = {
        "form": str(baseline.get("form") or bc.get("form") or ""),
        "max_cpu": _cap(baseline.get("max_cpu"), bc.get("max_cpu")),
        "max_dimm": _cap(baseline.get("max_dimm"), bc.get("max_dimm")),
        "bays": _cap(baseline.get("bays"), bc.get("bays")),
        "gpu_slots": _cap(bc.get("gpu_slots")),
        "psu_bays": _cap(bc.get("psu_bays")),
    }
    fam_qty: dict[str, int] = {}
    unmatched: list = []
    for p in parts:
        qty = _as_int(p.get("qty"), 1) or 1
        fam = _part_family(str(p.get("category") or str(p.get("name") or "")), family_kw)
        fam_qty[fam] = fam_qty.get(fam, 0) + qty
        if p.get("unmatched"):
            unmatched.append(str(p.get("name") or p.get("pn") or "未匹配件"))

    violations: list = []
    warnings: list = []
    _cap_check("CPU", fam_qty.get("cpu"), capacity["max_cpu"], "需求 CPU {qty} 颗超出机箱上限 {cap}", violations, warnings)
    _cap_check("内存条数", fam_qty.get("memory"), capacity["max_dimm"], "需求内存 {qty} 条超出机箱上限 {cap}", violations, warnings)
    _cap_check("整机盘位", (fam_qty.get("disk") or 0) + (fam_qty.get("sata") or 0) + (fam_qty.get("sas") or 0),
               capacity["bays"], "需求硬盘 {qty} 块超出机箱盘位 {cap}", violations, warnings)
    gpu = fam_qty.get("gpu") or 0
    if gpu and capacity["gpu_slots"] is not None and gpu > capacity["gpu_slots"]:
        violations.append({"code": "gpu_over_slots", "severity": "critical",
                          "message": f"需求 {gpu} 卡超出机箱 GPU 槽位 {capacity['gpu_slots']}"})
    if gpu and not capacity["gpu_slots"]:
        warnings.append({"severity": "info", "message": "机箱 GPU 槽位未配置，跳过 GPU 槽位校验"})

    # GPU 形态跨检：需求缺省形态与规则期望不一致时提醒（不阻断）。
    req_form = str(requirement.get("form") or requirement.get("chassis_form") or "").strip()
    if gpu > 0 and req_form and capacity["form"] and req_form != capacity["form"]:
        expected = None
        for r in _rc.gpu_form_map():
            lo = _as_int(r.get("gpu_count_min"), 0)
            hi = _as_int(r.get("gpu_count_max"), 1 << 31)
            if lo <= gpu <= hi:
                expected = r.get("form")
                break
        if expected and capacity["form"] != expected:
            warnings.append({"severity": "warn", "message": f"需求 {gpu} 卡通常需 {expected} 机箱，当前为 {capacity['form']}"})

    if unmatched:
        warnings.append({"severity": "info", "message": "存在未精确匹配配件：" + "、".join(_truncate(u, 40) for u in unmatched[:8])})
    return {
        "ok": len(violations) == 0,
        "violations": violations,
        "warnings": warnings,
        "capacity": capacity,
        "family_qty": fam_qty,
    }


async def _tool_compute_price(args: dict) -> Any:
    """compute_price → 整机成本（读目录/配件库真实价格；AI 不背价格）。"""
    baseline = args.get("baseline")
    parts = args.get("parts") or []
    if not isinstance(baseline, dict):
        return {"error": "缺 baseline 机型对象"}
    if not isinstance(parts, list) or not parts:
        return {"error": "缺 parts 配件清单"}
    from app.api.candidate_search import build_plan
    plan = build_plan(baseline, parts)
    summary = plan.get("summary") or {}
    return {
        "model": plan.get("model") or "",
        "name": plan.get("name") or "",
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


'''

specs = r'''    "load_requirement_rules": {
        "category": "rule",
        "data_sources": ["requirement_rule_catalog"],
        "default_enabled": True,
        "description": ("读需求规则目录（品类别名/平台系列映射/形态规则/RAID 等级/CPU-内存代际等），"
                        "用于把客户话术规范化成结构化需求槽位。不携带价格/兼容硬编码。"),
        "parameters": {
            "type": "object",
            "properties": {
                "rule_types": {"type": "array", "items": {"type": "string"},
                               "description": "要读取的规则类型名，如 category_alias/platform_series_map/gpu_form_map"},
            },
        },
        "handler": _tool_load_requirement_rules,
    },
    "validate_compat": {
        "category": "selection",
        "data_sources": ["server_catalog", "requirement_rule_catalog", "kp_price"],
        "default_enabled": True,
        "description": ("校验候选机型与已选配件是否兼容（CPU/内存/盘位/GPU 槽位/形态规则），"
                        "返回 violations/warnings。选完机型与配件后调用，用结果决定是否调整配置。"),
        "parameters": {
            "type": "object",
            "properties": {
                "baseline": {"type": "object", "description": "select_models 返回的候选机型对象"},
                "parts": {"type": "array", "items": {"type": "object"}, "description": "select_parts 返回的配件清单"},
                "requirement": {"type": "object", "description": "需求槽位对象（用于 GPU 形态跨检）"},
            },
            "required": ["baseline", "parts"],
        },
        "handler": _tool_validate_compat,
    },
    "compute_price": {
        "category": "cost",
        "data_sources": ["server_catalog", "kp_price"],
        "default_enabled": True,
        "description": ("按目录真实价格计算整机成本（L6 底盘 + KP 关键件 + 总成本），"
                        "返回含税 RMB 成本结构。回答价格/成本时调用，AI 不估价格。"),
        "parameters": {
            "type": "object",
            "properties": {
                "baseline": {"type": "object", "description": "select_models 返回的候选机型对象"},
                "parts": {"type": "array", "items": {"type": "object"}, "description": "select_parts 返回的配件清单"},
            },
            "required": ["baseline", "parts"],
        },
        "handler": _tool_compute_price,
    },
'''

text = io.open(path, encoding="utf-8").read()

# 1) 插入 helpers + handlers，放在 _tool_build_plan 定义之前
anchor1 = "async def _tool_build_plan(args: dict) -> Any:"
assert anchor1 in text, "anchor1 missing"
text = text.replace(anchor1, helpers + handler3 + anchor1, 1)

# 2) 注册 specs，放在 "cost_breakdown": { 之前
anchor2 = '    "cost_breakdown": {'
assert anchor2 in text, "anchor2 missing"
text = text.replace(anchor2, specs + anchor2, 1)

io.open(path, "w", encoding="utf-8").write(text)
print("agent_tools.py patched OK", len(text))
