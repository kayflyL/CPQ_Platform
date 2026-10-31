# -*- coding: utf-8 -*-
"""engine_wiring —— 组合根：宿主把能力注册进引擎端口（2026-11-01 融合区预解）。

引擎（ai_office）经 host_ports 取用宿主能力；本文件是唯一的接线处——
启动时 startup.py 调 wire_engine()，测试由 conftest 同样调用。
新增端口 = MODULE_ATTRS 加一个属性名 + 引擎侧把 import 换成 host_ports 代理。

注册的是**动态解析器**（每次调用 getattr 宿主属性），不是函数对象快照——
测试 monkeypatch 宿主函数、运行时热替换通道，引擎端口都看得见。
"""
from __future__ import annotations

import importlib

from ai_office import host_ports

# 端口表：宿主模块 -> 引擎取用的属性清单；端口名恒为 f"{模块}.{属性}"
# （引擎调用侧 host_ports 的端口名即此形状）。
# singleton = 该模块以「与模块同名的单例对象」暴露能力时，属性挂在单例上
# （如 assistant_hub.broadcast = 模块内单例的方法），仅此 4 例。
MODULE_ATTRS = {
    "assistant_hub": {"singleton": "assistant_hub", "attrs": ["broadcast"]},
    "office_governance": {"singleton": "office_governance", "attrs": ["enqueue"]},
    "office_hub": {"singleton": "office_hub", "attrs": ["update_and_broadcast"]},
    "office_memory": {"singleton": "office_memory", "attrs": ["record_event"]},
    "office_access": {"attrs": ["allowed_chat_role_keys"]},
    "office_mission": {"attrs": ["record_mission"]},
    "ai_colleague_service": {"attrs": ["colleague_tool_ids", "colleague_roster_digest",
                                       "get_ai_colleagues"]},
    "colleague_memory_service": {"attrs": ["memory_block"]},
    "capability_spec": {"attrs": ["default_tools", "mechanism_tools_map"]},
    "slot_contract": {"attrs": ["slot_spec", "canonical_key", "slot_label", "_missing_critical",
                                "unconfirmed_premise_fields", "apply_structured_slots",
                                "confirm_registration_on_bulk_click"]},
    "part_selector": {"attrs": ["pick_for_row", "pick_is_stale", "manual_signal_for_text",
                                "row_ref_meta", "kp_row_id", "kp_row_key",
                                "kp_registered_specified"]},
    "portal_flow_adapter": {"attrs": ["requirement_slots_from_ext", "seed_ext_from_requirement_draft",
                                      "persist_requirement_from_ctx", "persist_requirement_and_bom_from_ctx",
                                      "build_preview_bom_scheme", "save_scheme_progress_from_ctx",
                                      "build_requirement_text"]},
    "skill_phases": {"attrs": ["baseline_qty_cap", "prepare_model_step", "model_gap",
                               "phase_kp_reason", "kp_required_categories", "KP_MODE_OPTIONS"]},
    "capabilities": {"attrs": ["_apply_extracted_slots", "_compose_config", "_get_nested",
                               "_enrich_agent_semantic", "_slot_now_filled"]},
    "skill_tools_fill": {"attrs": ["requirement_prompt"]},
    "requirement_knowledge": {"attrs": ["knowledge_for_node"]},
    "data_range_follow": {"attrs": ["extract_report_data_range"]},
    "plan_builder": {"attrs": ["build_plan"]},
    "report_pdf": {"attrs": ["render_markdown_report_pdf", "report_meta_now", "save_office_report"]},
    "storage_adapter": {"attrs": ["build_object_id"]},
    "artifact_render": {"attrs": ["render_report_pdf"]},
    "agent_tool_specs": {"attrs": ["_TOOL_SPECS", "trace_note", "registered_tool_ids",
                                   "build_tool_registry"]},
    "skill_tools_select": {"attrs": ["search_candidates", "pick_fresh"]},
    "data_tools": {"attrs": ["part_recall", "lookup_parts_by_name"]},
}

_wired = False


def _iter_ports():
    """产出 (端口名, 宿主模块, 访问路径)。"""
    for mod_name, spec in MODULE_ATTRS.items():
        singleton = spec.get("singleton")
        for attr in spec["attrs"]:
            path = f"{singleton}.{attr}" if singleton else attr
            yield f"{mod_name}.{attr}", mod_name, path


def _resolver(mod, path: str):
    def _resolve():
        obj = mod
        for part in path.split("."):
            obj = getattr(obj, part)
        return obj
    return _resolve


def _has_path(obj, path: str) -> bool:
    try:
        for part in path.split("."):
            obj = getattr(obj, part)
        return True
    except AttributeError:
        return False


def wire_engine(force: bool = False) -> None:
    """把 MODULE_ATTRS 声明的宿主实现注册进引擎端口。幂等；缺属性当场报错
    （表与宿主代码漂移=接线失败，不静默跳过）。"""
    global _wired
    if _wired and not force:
        return
    missing = []
    for port_name, mod_name, path in _iter_ports():
        mod = importlib.import_module(f"app.services.{mod_name}")
        if not _has_path(mod, path):
            missing.append(f"{port_name} (app.services.{mod_name}.{path})")
            continue
        host_ports.register_port(port_name, _resolver(mod, path))
    if missing:
        raise RuntimeError("引擎端口接线失败（宿主缺属性，表与代码漂移）：" + repr(missing))
    _wired = True
