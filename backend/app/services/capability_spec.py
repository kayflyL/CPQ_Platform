# -*- coding: utf-8 -*-
"""能力节点声明式元数据（Capability-as-Data）。

每个需求分析节点 = 一份 spec：提示词来源（prompt_node）、默认工具集（default_tools）、
是否服务线索登记表（serves_slot）。执行器（capabilities.py）从本模块取默认值，
不再手写字面量常量；启动时 validate_capability_specs() 校验所有引用，
把“用了但没定义”这类运行时崩溃提前到启动期暴露。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CapabilitySpec:
    key: str
    label: str
    kind: str
    prompt_node: Optional[str]
    default_tools: tuple[str, ...]
    serves_slot: bool = False


SPECS: dict[str, CapabilitySpec] = {
    "input": CapabilitySpec("input", "入口", "input", None, ()),
    "agent_fill": CapabilitySpec(
        "agent_fill", "智能对话填表 Agent", "agent_fill", "agent_fill",
        ("list_server_types",),
        serves_slot=True,
    ),
    "model_reason": CapabilitySpec(
        "model_reason", "机型选型", "model_reason", "model_reason",
        ("select_models",), serves_slot=True),
    "kp_reason": CapabilitySpec(
        "kp_reason", "配件选型", "kp_reason", "kp_reason",
        ("pick_kp_parts",), serves_slot=True),
    "compose": CapabilitySpec("compose", "BOM 组装", "compose", None, (), serves_slot=True),
    "output": CapabilitySpec("output", "输出", "output", None, ()),
}


def get_spec(key: str) -> CapabilitySpec:
    return SPECS[key]


def default_tools(key: str) -> tuple[str, ...]:
    return get_spec(key).default_tools


def validate_specs() -> list[str]:
    """启动自检：prompt 节点存在默认词、默认工具已在 agent_tools 注册表注册。"""
    errors: list[str] = []
    from app.services import agent_tools
    from app.services import prompt_store
    known_tools = set(agent_tools.registered_tool_ids())
    for key, spec in SPECS.items():
        if spec.prompt_node:
            d = prompt_store.get_prompt_defaults(spec.prompt_node)
            if not d:
                errors.append(f"capability_spec[{key}] prompts 无默认值: {spec.prompt_node}")
        for tid in spec.default_tools:
            if tid not in known_tools:
                errors.append(f"capability_spec[{key}] tool 未注册: {tid}")
    return errors
