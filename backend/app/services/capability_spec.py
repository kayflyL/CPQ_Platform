# -*- coding: utf-8 -*-
"""能力节点声明式元数据（Capability-as-Data）。

每个需求分析节点 = 一份 spec：默认工具集（default_tools）、是否服务线索登记表
（serves_slot）。执行器（capabilities.py）从本模块取默认工具；启动时
validate_capability_specs() 校验默认工具均已注册，把「用了但没定义」这类运行时
崩溃提前到启动期暴露。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilitySpec:
    key: str
    label: str
    kind: str
    default_tools: tuple[str, ...]
    serves_slot: bool = False


SPECS: dict[str, CapabilitySpec] = {
    "input": CapabilitySpec("input", "入口", "input", ()),
    "agent_fill": CapabilitySpec(
        "agent_fill", "智能对话填表 Agent", "agent_fill",
        # 目录接地改为提示词注入（_catalog_whitelist），不再挂浏览工具（2026-08-29 步骤2 退役）
        (),
        serves_slot=True,
    ),
    "model_reason": CapabilitySpec(
        "model_reason", "机型选型", "model_reason",
        ("select_models",), serves_slot=True,
    ),
    "kp_reason": CapabilitySpec(
        "kp_reason", "配件选型", "kp_reason",
        ("list_kp_categories", "select_parts", "resolve_part_alias", "compose_memory"), serves_slot=True,
    ),
    "compose": CapabilitySpec("compose", "BOM 组装", "compose", (), serves_slot=True),
    "output": CapabilitySpec("output", "输出", "output", ()),
}


def get_spec(key: str) -> CapabilitySpec:
    return SPECS[key]


def default_tools(key: str) -> tuple[str, ...]:
    return get_spec(key).default_tools


def validate_specs() -> list[str]:
    """启动自检：默认工具均已注册。"""
    errors: list[str] = []
    from app.services.agent_tool_specs import registered_tool_ids
    known_tools = set(registered_tool_ids())
    for key, spec in SPECS.items():
        for tid in spec.default_tools:
            if tid not in known_tools:
                errors.append(f"capability_spec[{key}] tool 未注册: {tid}")
    return errors
