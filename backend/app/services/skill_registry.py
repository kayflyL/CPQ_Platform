"""Skill 注册表 —— 技能元数据主存储是 DB（rules.skill_catalog + reasoning_flow），这里只读取/合成 manifest。

代码里不存技能提示词：skill.prompt 的唯一来源是配置层。
"""
from __future__ import annotations

import logging
from typing import Optional
from .skill_types import normalize_skill_type, is_capability_skill


logger = logging.getLogger(__name__)


def resolve_skill_manifest(skill_key: str) -> Optional[dict]:
    """按 skill_key 解析 Skill manifest；目录和流程都没有时返回 None。

    目录行是面向大脑的“能力说明”，流程行是面向引擎的“执行图”。
    两者分开读取，但在这里合成同一份标准 manifest。
    """
    key = str(skill_key or "").strip()
    if not key:
        return None

    from app.repository.skill_catalog_repo import SkillCatalogRepository
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository

    catalog: dict = {}
    try:
        repo = SkillCatalogRepository()
        try:
            row = repo.get(key)
        finally:
            repo.close()
        catalog = dict(row) if isinstance(row, dict) else {}
    except Exception:
        logger.exception("读取 skill_catalog 失败 skill_key=%s", key)

    flow: dict = {}
    try:
        repo = ReasoningFlowRepository()
        try:
            flow = repo.get_active_flow(key) or {}
        finally:
            repo.close()
    except Exception:
        logger.exception("读取 reasoning_flow 失败 skill_key=%s", key)

    if not catalog and not flow:
        return None

    return {
        "skill_key": key,
        "name": str(catalog.get("name") or flow.get("name") or key).strip() or key,
        "type": normalize_skill_type(catalog.get("type") or "workflow"),
        "workflow_key": str(catalog.get("workflow_key") or flow.get("skill_key") or key).strip() or key,
        "description": str(catalog.get("description") or "").strip(),
        "prompt": str(catalog.get("prompt") or "").strip(),
        "tool_ids": list(catalog.get("tool_ids") or []),
        "input_contract": str(catalog.get("input_contract") or "").strip(),
        "output_contract": str(catalog.get("output_contract") or "").strip(),
        "output_kind": str(catalog.get("output_kind") or "").strip() or None,
        "is_workflow": bool(flow) or str(catalog.get("type") or "").strip() == "workflow",
        "is_capability": is_capability_skill(catalog),
        "flow": flow,
        "node_configs": dict(flow.get("node_configs") or {}),
        "graph": flow.get("graph") or {"nodes": [], "edges": []},
    }
