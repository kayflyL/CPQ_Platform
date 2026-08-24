"""Skill catalog repository —— rules.skill_catalog 主存储访问。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models.base import Rules_SessionLocal
from ..models.skill import SkillCatalog


def _json_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


class SkillCatalogRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    def list(self, include_deleted: bool = False) -> list:
        query = self.session.query(SkillCatalog)
        if not include_deleted:
            query = query.filter(SkillCatalog.is_deleted == False)  # noqa: E712
        return [row.to_dict() for row in query.order_by(SkillCatalog.id.asc()).all()]

    def get(self, key: str, include_deleted: bool = False) -> Optional[dict]:
        query = self.session.query(SkillCatalog).filter(SkillCatalog.key == key)
        if not include_deleted:
            query = query.filter(SkillCatalog.is_deleted == False)  # noqa: E712
        row = query.first()
        return row.to_dict() if row else None

    def upsert(self, payload: dict, operator: str = "system") -> dict:
        key = str(payload.get("key") or "").strip()
        row = self.session.query(SkillCatalog).filter(SkillCatalog.key == key).first()
        now = datetime.now().isoformat()
        tool_ids = payload.get("tool_ids")
        if not isinstance(tool_ids, list):
            tool_ids = []
        tool_ids = [str(t) for t in tool_ids if str(t)]
        values = {
            "key": key,
            "name": str(payload.get("name") or key).strip() or key,
            "type": str(payload.get("type") or "tool_prompt").strip() or "tool_prompt",
            "workflow_key": str(payload.get("workflow_key") or "").strip() or None,
            "description": str(payload.get("description") or "").strip(),
            "prompt": str(payload.get("prompt") or "").strip(),
            "tool_ids": json.dumps(tool_ids, ensure_ascii=False),
            "input_contract": str(payload.get("input_contract") or "").strip(),
            "output_contract": str(payload.get("output_contract") or "").strip(),
            "output_kind": str(payload.get("output_kind") or "").strip() or None,
            "updated_at": now,
            "updated_by": operator,
        }
        if row:
            for field, value in values.items():
                setattr(row, field, value)
            row.is_deleted = False
        else:
            row = SkillCatalog(**values, created_at=now, created_by=operator, is_deleted=False)
            self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def increment_hit(self, key: str) -> int:
        row = self.session.query(SkillCatalog).filter(SkillCatalog.key == key).first()
        if not row:
            return 0
        row.hit_count = int(row.hit_count or 0) + 1
        row.updated_at = datetime.now().isoformat()
        self.session.commit()
        return int(row.hit_count)

    def soft_delete(self, key: str, operator: str = "system") -> bool:
        row = self.session.query(SkillCatalog).filter(SkillCatalog.key == key).first()
        if not row or row.is_deleted:
            return False
        row.is_deleted = True
        row.updated_at = datetime.now().isoformat()
        row.updated_by = operator
        self.session.commit()
        return True

    def sync_defaults(self, defaults: list) -> int:
        """把代码默认技能补进表（只补缺失 key，不覆盖已编辑数据）。"""
        changed = 0
        for item in defaults or []:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            if self.get(str(item["key"]).strip(), include_deleted=True):
                continue
            self.upsert(dict(item), operator="seed")
            changed += 1
        return changed

    def normalize_workflow_tools(self) -> int:
        """清理旧工作流工具引用：workflow Skill 不再通过 ReAct 工具执行。"""
        removed_tools = {"run_requirement_analysis", "run_skill_workflow"}
        changed = 0
        for row in self.session.query(SkillCatalog).all():
            if str(row.type or "").strip() == "workflow":
                cleaned = []
            else:
                cleaned = [t for t in _json_list(row.tool_ids) if str(t) not in removed_tools]
            old = _json_list(row.tool_ids)
            if [str(t) for t in old] != [str(t) for t in cleaned]:
                row.tool_ids = json.dumps(cleaned, ensure_ascii=False)
                row.updated_at = datetime.now().isoformat()
                changed += 1
        if changed:
            self.session.commit()
        return changed

    def close(self):
        self.session.close()
