"""一次性迁移：把需求分析 / 趋势分析两个内置 Skill 落进 rules.skill_catalog。

唯一权威源 = rules.skill_catalog；代码不再持有 DEFAULT_SKILL_LIBRARY 种子。
本脚本幂等：按 key 判存在，已存在不覆盖（保留线上编辑），空库时灌入默认定义。
用法：python -X utf8 backend/scripts/seed_skill_catalog.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.models.base import Rules_SessionLocal
from app.models.skill import SkillCatalog

# Skill 初始定义（仅空库需要；已存在行不覆盖，以 rules.skill_catalog 为权威源）
BUILTIN_SKILLS: list[dict] = [
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
        "output_kind": "plans",
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


def seed() -> int:
    """按 key 幂等执行；返回新建行数。"""
    s = Rules_SessionLocal()
    created = 0
    try:
        for item in BUILTIN_SKILLS:
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            exists = s.query(SkillCatalog).filter(SkillCatalog.key == key).first()
            if exists:
                continue
            s.add(SkillCatalog(
                key=key,
                name=str(item.get("name") or key).strip() or key,
                type=str(item.get("type") or "tool_prompt").strip() or "tool_prompt",
                workflow_key=str(item.get("workflow_key") or "").strip() or None,
                description=str(item.get("description") or "").strip(),
                prompt=str(item.get("prompt") or "").strip(),
                tool_ids="[]",
                input_contract=str(item.get("input_contract") or "").strip(),
                output_contract=str(item.get("output_contract") or "").strip(),
                output_kind=str(item.get("output_kind") or "").strip() or None,
                is_deleted=False,
                created_at=None,
                updated_at=None,
                created_by="seed",
                updated_by="seed",
            ))
            created += 1
        if created:
            s.commit()
    finally:
        s.close()
    return created


if __name__ == "__main__":
    n = seed()
    print(f"Seed skill_catalog: {n} new, existing untouched")
