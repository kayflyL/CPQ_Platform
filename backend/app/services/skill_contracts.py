# -*- coding: utf-8 -*-
"""需求分析 skill 的统一落地契约。

铁律（不 import agent_react / llm_client，只做确定性封装与校验）：
1. 事实必须真实存在于目录：料号/价格/规格来自工具返回，LLM 不编造。
2. 未命中白盒 unmatched，规格漂移白盒 spec_mismatch。
3. 替换/组合必须显式携带 reason + source，可审计、可回放。
4. 不允许“静默兜底选代表件”或“把放宽结果假装成精确匹配”。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

# 唯一大脑回合输出契约：后续 skill_chat / colleague_turn_service 都要收敛到这个形状。
@dataclass
class BrainTurnOutput:
    kind: str
    reply: str = ""
    skill_key: Optional[str] = None
    slots: dict = field(default_factory=dict)
    gaps: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)
    card_emitted: bool = False
    engine_ctx: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


# 确定性引擎结果契约：引擎只返回数据，不返回话术。
@dataclass
class EngineOutput:
    status: str
    artifact: Optional[dict] = None
    payload: dict = field(default_factory=dict)
    gaps: list = field(default_factory=list)
    assumptions: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


SKILL_SESSION_IDLE = "idle"
SKILL_SESSION_PROPOSING = "proposing"
SKILL_SESSION_ACTIVE = "active"
SKILL_SESSION_ENGINE_RUNNING = "engine_running"
SKILL_SESSION_AWAITING_INPUT = "awaiting_input"
SKILL_SESSION_DONE = "done"

SKILL_SESSION_PHASES = (
    SKILL_SESSION_IDLE,
    SKILL_SESSION_PROPOSING,
    SKILL_SESSION_ACTIVE,
    SKILL_SESSION_ENGINE_RUNNING,
    SKILL_SESSION_AWAITING_INPUT,
    SKILL_SESSION_DONE,
)

def grounding_envelope(parts: list) -> dict:
    """把 part_selector.select_parts 的扁平结果包成统一落地契约。"""
    matched: list = []
    unmatched: list = []
    spec_mismatch: list = []
    substitutions: list = []
    for p in (parts or []):
        if not isinstance(p, dict):
            continue
        if p.get("unmatched"):
            unmatched.append(p)
        elif p.get("spec_mismatch"):
            spec_mismatch.append(p)
        else:
            matched.append(p)
        sub = p.get("substitution")
        if isinstance(sub, dict) and sub.get("reason"):
            substitutions.append(sub)
    return {
        "matched": matched,
        "unmatched": unmatched,
        "spec_mismatch": spec_mismatch,
        "substitutions": substitutions,
        "count": len([p for p in (parts or []) if isinstance(p, dict)]),
    }


def validate_grounding(result: dict) -> list[str]:
    """契约校验：返回错误列表，空列表表示通过。"""
    errors: list[str] = []
    for part in (result.get("matched") or []):
        if not isinstance(part, dict) or not part.get("pn"):
            errors.append(f"matched 件缺料号: {part!r}")
    for part in (result.get("unmatched") or []):
        if not isinstance(part, dict) or not part.get("unmatched_reason"):
            errors.append(f"unmatched 件缺原因: {part!r}")
    for sub in (result.get("substitutions") or []):
        if not isinstance(sub, dict) or not sub.get("reason") or not sub.get("source"):
            errors.append(f"替换/组合缺 reason 或 source: {sub!r}")
    return errors
