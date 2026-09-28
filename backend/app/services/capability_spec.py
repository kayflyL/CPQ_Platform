# -*- coding: utf-8 -*-
"""能力节点声明式元数据（Capability-as-Data）。

每个需求分析节点 = 一份 spec：
- `default_tools`：默认工具集（= 节点配置 enabled_tools 的初始值）；
- `mechanism_tools`：**节点机制必需的子集**——画布抽屉里锁定勾选、不可取消；
  运行时若 DB 配置漂移丢了它，保底补回并告警。

本模块是「节点 ↔ 工具」绑定的**唯一真源**。下面三处一律从这里派生，不再各写一份清单：
1. 空库播种 `skill_config_bootstrap`（enabled_tools 初值）；
2. 运行时保底 `skill_plan_runtime.effective_node_tools`（MECHANISM_TOOLS 投影）；
3. 前端抽屉 `GET /api/reasoning-flow/capabilities`（哪些工具可勾、哪些锁定）。

启动时 `validate_specs()` 校验工具均已注册，把「用了但没定义」这类运行时崩溃提前到启动期。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CapabilitySpec:
    key: str
    label: str
    kind: str
    default_tools: tuple[str, ...]
    serves_slot: bool = False
    mechanism_tools: tuple[str, ...] = ()
    # 机制锁因（抽屉 tooltip 用）：说明这些动词为什么不可摘（承载哪条协议）。
    mechanism_reason: str = ""

    def effective_tools(self) -> tuple[str, ...]:
        """节点实际可用工具 = default_tools ∪ mechanism_tools（去重保序）。"""
        return tuple(dict.fromkeys(self.default_tools + self.mechanism_tools))

    def as_dict(self) -> dict:
        """前端抽屉/接口视图：工具清单与锁定子集同源给出。"""
        return {
            "key": self.key,
            "label": self.label,
            "kind": self.kind,
            "serves_slot": self.serves_slot,
            "default_tools": list(self.default_tools),
            "mechanism_tools": list(self.mechanism_tools),
            "mechanism_reason": self.mechanism_reason,
        }


SPECS: dict[str, CapabilitySpec] = {
    "input": CapabilitySpec("input", "入口", "input", ()),
    # 通用智能体节点：workflow 型 skill 的自由大脑（趋势分析等），默认只读数据
    "agent": CapabilitySpec("agent", "通用智能体", "agent", ("query_data",)),
    "agent_fill": CapabilitySpec(
        "agent_fill", "智能对话填表 Agent", "agent_fill",
        # 目录接地改为提示词注入（catalog_options.catalog_whitelist），不再挂浏览工具（2026-08-29 步骤2 退役）
        (),
        serves_slot=True,
        mechanism_tools=("fill_requirement", "ask_user"),
        mechanism_reason="登记协议 + 缺口反问协议依赖：摘掉后节点无法登记、也无法把缺口升格成提问",
    ),
    "model_reason": CapabilitySpec(
        "model_reason", "机型选型", "model_reason",
        ("choose_model",), serves_slot=True,
        mechanism_tools=("choose_model",),
        mechanism_reason="落锁协议依赖：锁定唯一通道，摘掉后机型永远无法落定",
    ),
    "kp_reason": CapabilitySpec(
        "kp_reason", "配件选型", "kp_reason",
        # inspect_parts 是统一只读钻取/定向搜索（open/navigate/grep 收敛为一个 action 工具）：
        # 可勾选关闭，不影响三件套闭环，所以只进 default_tools、不进 mechanism_tools。
        ("query_parts", "inspect_parts", "select_parts"),
        serves_slot=True,
        mechanism_tools=("query_parts", "select_parts", "ask_user"),
        mechanism_reason="找料/落料/行反问协议依赖：摘掉后配件行无法召回、无法落地或无法向客户拍板",
    ),
    "compose": CapabilitySpec("compose", "BOM 组装", "compose", (), serves_slot=True),
    "output": CapabilitySpec("output", "输出", "output", ()),
}


def get_spec(key: str) -> CapabilitySpec:
    return SPECS[key]


def default_tools(key: str) -> tuple[str, ...]:
    return get_spec(key).default_tools


def mechanism_tools(key: str) -> tuple[str, ...]:
    return get_spec(key).mechanism_tools


def mechanism_tools_map() -> dict[str, list[str]]:
    """{节点: 机制必需工具}——skill_plan_runtime 的保底表由本函数派生（单一真源）。"""
    return {k: list(s.mechanism_tools) for k, s in SPECS.items() if s.mechanism_tools}


def capabilities_catalog() -> list[dict]:
    """节点能力目录（前端抽屉「工具层」的勾选/锁定依据）。"""
    return [s.as_dict() for s in SPECS.values()]


def validate_specs() -> list[str]:
    """启动自检：默认工具与机制工具均已注册。"""
    errors: list[str] = []
    from app.services.agent_tool_specs import registered_tool_ids
    known_tools = set(registered_tool_ids())
    for key, spec in SPECS.items():
        for tid in spec.effective_tools():
            if tid not in known_tools:
                errors.append(f"capability_spec[{key}] tool 未注册: {tid}")
    return errors
