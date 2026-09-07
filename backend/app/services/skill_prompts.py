# -*- coding: utf-8 -*-
"""需求分析 Skill 的提示词配置源（前端可见/可编辑，DB 唯一权威）。

只从 rules.skill_prompt_template（DB）读取，缺失/空即返回空；不再有任何种子文件或运行时兜底。
前端「提示词」面板读写的就是这张表（list / upsert 单行落库）。
"""
from __future__ import annotations

DEFAULT_SKILL_KEY = "requirement_analysis"


def load_skill_prompts(skill_key: str = DEFAULT_SKILL_KEY) -> dict:
    """返回提示词模板与规则片段 dict（仅 DB skill_prompt_template，无种子兜底）。"""
    from app.models.base import Rules_SessionLocal
    from app.models.skill_config import SkillPromptTemplate
    s = Rules_SessionLocal()
    out: dict = {}
    try:
        rows = s.query(SkillPromptTemplate).filter(
            SkillPromptTemplate.skill_key == skill_key,
            SkillPromptTemplate.enabled == True,
        ).order_by(SkillPromptTemplate.sort_order).all()
        for r in rows:
            out[r.slot_key] = r.template or ""
    finally:
        s.close()
    return out


def list_prompt_templates(skill_key: str = DEFAULT_SKILL_KEY) -> list:
    """返回该 Skill 的全部提示词行（含未启用），按 sort_order 排序。"""
    from app.models.base import Rules_SessionLocal
    from app.models.skill_config import SkillPromptTemplate
    s = Rules_SessionLocal()
    try:
        rows = s.query(SkillPromptTemplate).filter(
            SkillPromptTemplate.skill_key == skill_key
        ).order_by(SkillPromptTemplate.sort_order, SkillPromptTemplate.id).all()
        return [r.to_dict() for r in rows]
    finally:
        s.close()


def upsert_prompt_template(
    slot_key: str,
    template: str,
    name: str | None = None,
    enabled: bool | None = None,
    skill_key: str = DEFAULT_SKILL_KEY,
    operator: str = "system",
) -> dict:
    """单行 upsert 到 rules.skill_prompt_template（前端修改直接落库；version 自增）。"""
    from datetime import datetime
    from app.models.base import Rules_SessionLocal
    from app.models.skill_config import SkillPromptTemplate
    s = Rules_SessionLocal()
    try:
        now = datetime.now().isoformat()
        row = s.query(SkillPromptTemplate).filter(
            SkillPromptTemplate.skill_key == skill_key,
            SkillPromptTemplate.slot_key == slot_key,
        ).first()
        if row is None:
            row = SkillPromptTemplate(
                skill_key=skill_key,
                slot_key=slot_key,
                name=name or slot_key,
                template=template or "",
                enabled=True if enabled is None else bool(enabled),
                sort_order=0,
                version=1,
                updated_at=now,
                updated_by=operator,
            )
            s.add(row)
        else:
            if template is not None:
                row.template = template
            if name is not None:
                row.name = name
            if enabled is not None:
                row.enabled = bool(enabled)
            row.version = (row.version or 1) + 1
            row.updated_at = now
            row.updated_by = operator
        s.commit()
        s.refresh(row)
        return row.to_dict()
    finally:
        s.close()


def get_role_prompt() -> str:
    return str(load_skill_prompts().get("role_prompt") or "")


def get_gap_ask_prompt() -> str:
    return str(load_skill_prompts().get("gap_ask_prompt") or "")


def get_extract_contract() -> str:
    return str(load_skill_prompts().get("extract_contract") or "")


def get_stream_chat_contract() -> str:
    return str(load_skill_prompts().get("stream_chat_contract") or "")
