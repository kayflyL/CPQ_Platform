# -*- coding: utf-8 -*-
"""agent_tools —— LLM 工具统一门面。保留模块名兼容旧引用；实现已拆分为 registry/handlers/specs。"""
from app.services.agent_tool_registry import ToolRegistry, _truncate
from app.services.agent_tool_handlers import _search_cases_handler, _tool_build_plan, _tool_cost_breakdown, _tool_get_server_model, _tool_list_kp_categories, _tool_list_server_models, _tool_list_server_types, _tool_query_cpq_data, _tool_quote_draft, _tool_select_models, _tool_select_parts, _tool_update_server_model, _tool_update_server_type
from app.services.agent_tool_specs import _TOOL_SPECS, ALL_TOOL_NAMES, build_tool_registry, registered_tool_ids, tool_catalog, tool_required_data_sources, tool_requires_approval
__all__ = ["ToolRegistry", "build_tool_registry", "registered_tool_ids", "tool_catalog", "tool_required_data_sources", "tool_requires_approval"]
