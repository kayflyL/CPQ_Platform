"""Skill 类型语义统一入口。

能力包(skill) 与 任务流(workflow) 是两套概念：
- skill：静默增强，模型按 description 判断调用，无任务 UI；
- workflow：可见多步编排，显式发起（用户点「+」或模型建议+确认）。
旧值 tool_prompt 一律归一为 skill，存量数据无需刷库即可在新语义下工作。
"""
from __future__ import annotations
from typing import Any

TYPE_WORKFLOW = "workflow"
TYPE_SKILL = "skill"
TYPE_LEGACY_TOOL_PROMPT = "tool_prompt"


def normalize_skill_type(value: Any) -> str:
    """把任意合法输入归一到两种规范值（skill / workflow）。"""
    t = str(value or "").strip()
    if t == TYPE_LEGACY_TOOL_PROMPT:
        return TYPE_SKILL
    return t or TYPE_SKILL


def is_capability_skill(skill: dict) -> bool:
    """能力包：静默注入，不上任务编排 UI。"""
    return normalize_skill_type((skill or {}).get("type")) == TYPE_SKILL


def is_workflow_skill(skill: dict) -> bool:
    """任务流：可见多步编排，显式发起。"""
    return str((skill or {}).get("type") or "").strip() == TYPE_WORKFLOW
