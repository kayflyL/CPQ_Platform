"""Skill 注册表 —— 未来新增技能只在这里追加配置，不改核心运行时。"""
from __future__ import annotations

import copy
from typing import List


# 技能元数据主存储是 rules.skill_catalog（启动时由 SkillCatalogRepository.sync_defaults 补齐）。
# 这里保留默认种子：新增技能 = 追加一个 dict；绑定默认角色 = 追加 DEFAULT_SKILL_BINDINGS 项。
DEFAULT_SKILL_LIBRARY: List[dict] = [
    {
        "id": "requirement_analysis",
        "key": "requirement_analysis",
        "type": "workflow",
        "workflow_key": "requirement_analysis",
        "name": "需求分析",
        "description": "从自然语言中澄清服务器配置需求，必要时反问而不是直接进入选型。",
        "prompt": "先确认用户要解决什么业务问题，再提取服务器类型、形态、系列、数量、预算等关键信息；信息不足时一次只问一个最关键问题。",
        "tool_ids": [],
        "input_contract": "自然语言服务器配置需求",
        "output_contract": "需求摘要 + 候选方案 + BOM + 待确认项",
        "output_kind": "bom_scheme_draft",
    },
    {
        "id": "trend_analysis",
        "key": "trend_analysis",
        "type": "workflow",
        "workflow_key": "trend_analysis",
        "name": "趋势分析",
        "description": "识别用户对商机/配置数据的趋势、统计、排行等分析意图，并基于系统数据给出结论。",
        "prompt": "当用户需要趋势分析、周期统计、平台/机箱分布或销售排行时，调用趋势分析技能查询真实数据；没有明确周期时先按自然语义推断，不确定再向用户确认。",
        "tool_ids": [],
        "input_contract": "趋势/统计/排行等数据问题",
        "output_contract": "数据结论 + 口径说明",
        "output_kind": "data_answer",
    },
]


# 新库初始化时的默认技能绑定（仅作种子，后续由员工页配置，不覆盖已有绑定）。
DEFAULT_SKILL_BINDINGS: dict = {
    "assistant": ["requirement_analysis"],
    "support_engineer": ["requirement_analysis"],
    "data_analyst": ["trend_analysis"],
}


def default_skill_library() -> List[dict]:
    return copy.deepcopy(DEFAULT_SKILL_LIBRARY)


def default_skill_bindings() -> dict:
    return copy.deepcopy(DEFAULT_SKILL_BINDINGS)
