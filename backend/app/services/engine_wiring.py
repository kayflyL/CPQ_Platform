# -*- coding: utf-8 -*-
"""engine_wiring —— 组合根：宿主把能力注册进引擎端口（2026-11-01 融合区预解）。

引擎（ai_office）经 host_ports 取用宿主能力；本文件是唯一的接线处——
启动时 startup.py 调 wire_engine()，测试由 conftest 同样调用。
新增端口 = PORT_TABLE 加一行 + 引擎侧把 import 换成 host_ports 代理。

注册的是**动态解析器**（每次调用 getattr 宿主模块属性），不是函数对象快照——
测试 monkeypatch 宿主函数、运行时热替换通道，引擎端口都看得见。
"""
from __future__ import annotations

import importlib

from ai_office import host_ports

# 端口表：端口名（引擎侧契约，host_ports 调用名）-> (宿主模块, 模块内访问路径)。
# 访问路径支持单例属性跳一层（如 assistant_hub.broadcast = 模块内单例的方法）。
PORT_TABLE = {
    # ── 广播与办公室运行时 ──
    "assistant_hub.broadcast": ("assistant_hub", "assistant_hub.broadcast"),
    "office_governance.enqueue": ("office_governance", "office_governance.enqueue"),
    "office_hub.update_and_broadcast": ("office_hub", "office_hub.update_and_broadcast"),
    "office_memory.record_event": ("office_memory", "office_memory.record_event"),
    "office_access.allowed_chat_role_keys": ("office_access", "allowed_chat_role_keys"),
    "office_mission.record_mission": ("office_mission", "record_mission"),
    # ── 同事配置与记忆 ──
    "ai_colleague_service.colleague_tool_ids": ("ai_colleague_service", "colleague_tool_ids"),
    "ai_colleague_service.colleague_roster_digest": ("ai_colleague_service", "colleague_roster_digest"),
    "ai_colleague_service.get_ai_colleagues": ("ai_colleague_service", "get_ai_colleagues"),
    "colleague_memory_service.memory_block": ("colleague_memory_service", "memory_block"),
    # ── 能力声明 ──
    "capability_spec.default_tools": ("capability_spec", "default_tools"),
    "capability_spec.mechanism_tools_map": ("capability_spec", "mechanism_tools_map"),
    # ── 登记表契约（slot_contract，宿主资产）──
    "slot_contract.slot_spec": ("slot_contract", "slot_spec"),
    "slot_contract.canonical_key": ("slot_contract", "canonical_key"),
    "slot_contract.slot_label": ("slot_contract", "slot_label"),
    "slot_contract._missing_critical": ("slot_contract", "_missing_critical"),
    "slot_contract.unconfirmed_premise_fields": ("slot_contract", "unconfirmed_premise_fields"),
    "slot_contract.apply_structured_slots": ("slot_contract", "apply_structured_slots"),
    "slot_contract.confirm_registration_on_bulk_click": ("slot_contract", "confirm_registration_on_bulk_click"),
    # ── 选型域 ──
    "part_selector.pick_for_row": ("part_selector", "pick_for_row"),
    "part_selector.pick_is_stale": ("part_selector", "pick_is_stale"),
    "part_selector.manual_signal_for_text": ("part_selector", "manual_signal_for_text"),
    "part_selector.row_ref_meta": ("part_selector", "row_ref_meta"),
    "part_selector.kp_row_id": ("part_selector", "kp_row_id"),
    "part_selector.kp_row_key": ("part_selector", "kp_row_key"),
    "part_selector.kp_registered_specified": ("part_selector", "kp_registered_specified"),
    # ── 门户流适配（进度持久化/需求文本）──
    "portal_flow_adapter.requirement_slots_from_ext": ("portal_flow_adapter", "requirement_slots_from_ext"),
    "portal_flow_adapter.seed_ext_from_requirement_draft": ("portal_flow_adapter", "seed_ext_from_requirement_draft"),
    "portal_flow_adapter.persist_requirement_from_ctx": ("portal_flow_adapter", "persist_requirement_from_ctx"),
    "portal_flow_adapter.persist_requirement_and_bom_from_ctx": ("portal_flow_adapter", "persist_requirement_and_bom_from_ctx"),
    "portal_flow_adapter.build_preview_bom_scheme": ("portal_flow_adapter", "build_preview_bom_scheme"),
    "portal_flow_adapter.save_scheme_progress_from_ctx": ("portal_flow_adapter", "save_scheme_progress_from_ctx"),
    "portal_flow_adapter.build_requirement_text": ("portal_flow_adapter", "build_requirement_text"),
    # ── 阶段族 ──
    "skill_phases.baseline_qty_cap": ("skill_phases", "baseline_qty_cap"),
    "skill_phases.prepare_model_step": ("skill_phases", "prepare_model_step"),
    "skill_phases.model_gap": ("skill_phases", "model_gap"),
    "skill_phases.phase_kp_reason": ("skill_phases", "phase_kp_reason"),
    "skill_phases.kp_required_categories": ("skill_phases", "kp_required_categories"),
    "skill_phases.KP_MODE_OPTIONS": ("skill_phases", "KP_MODE_OPTIONS"),
    # ── 能力回填 ──
    "capabilities._apply_extracted_slots": ("capabilities", "_apply_extracted_slots"),
    "capabilities._compose_config": ("capabilities", "_compose_config"),
    "capabilities._get_nested": ("capabilities", "_get_nested"),
    "capabilities._enrich_agent_semantic": ("capabilities", "_enrich_agent_semantic"),
    "capabilities._slot_now_filled": ("capabilities", "_slot_now_filled"),
    # ── 工具与知识 ──
    "skill_tools_fill.requirement_prompt": ("skill_tools_fill", "requirement_prompt"),
    "requirement_knowledge.knowledge_for_node": ("requirement_knowledge", "knowledge_for_node"),
    "data_range_follow.extract_report_data_range": ("data_range_follow", "extract_report_data_range"),
    "plan_builder.build_plan": ("plan_builder", "build_plan"),
    # ── 报告与存储 ──
    "report_pdf.render_markdown_report_pdf": ("report_pdf", "render_markdown_report_pdf"),
    "report_pdf.report_meta_now": ("report_pdf", "report_meta_now"),
    "report_pdf.save_office_report": ("report_pdf", "save_office_report"),
    "storage_adapter.build_object_id": ("storage_adapter", "build_object_id"),
    "artifact_render.render_report_pdf": ("artifact_render", "render_report_pdf"),
    # ── 工具声明面 ──
    "agent_tool_specs._TOOL_SPECS": ("agent_tool_specs", "_TOOL_SPECS"),
    "agent_tool_specs.trace_note": ("agent_tool_specs", "trace_note"),
    "agent_tool_specs.registered_tool_ids": ("agent_tool_specs", "registered_tool_ids"),
    "data_tools.part_recall": ("data_tools", "part_recall"),
    "data_tools.lookup_parts_by_name": ("data_tools", "lookup_parts_by_name"),
}

_wired = False


def _resolver(mod, path: str):
    def _resolve():
        obj = mod
        for part in path.split("."):
            obj = getattr(obj, part)
        return obj
    return _resolve


def wire_engine(force: bool = False) -> None:
    """把 PORT_TABLE 声明的宿主实现注册进引擎端口。幂等；缺属性当场报错
    （表与宿主代码漂移=接线失败，不静默跳过）。"""
    global _wired
    if _wired and not force:
        return
    missing = []
    for port_name, (mod_name, path) in PORT_TABLE.items():
        mod = importlib.import_module(f"app.services.{mod_name}")
        if not _has_path(mod, path):
            missing.append(f"{port_name} (app.services.{mod_name}.{path})")
            continue
        host_ports.register_port(port_name, _resolver(mod, path))
    if missing:
        raise RuntimeError("引擎端口接线失败（宿主缺属性，表与代码漂移）：" + repr(missing))
    _wired = True


def _has_path(obj, path: str) -> bool:
    try:
        for part in path.split("."):
            obj = getattr(obj, part)
        return True
    except AttributeError:
        return False
