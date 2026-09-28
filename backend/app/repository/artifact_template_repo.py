# -*- coding: utf-8 -*-
"""ArtifactTemplateRepo —— rules.artifact_template CRUD。"""
from typing import Optional

from sqlalchemy import func, select

from ..models.artifact_template import ArtifactTemplate
from ..models.base import Rules_SessionLocal


def _now() -> str:
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


class ArtifactTemplateRepo:
    def __init__(self):
        self.session = Rules_SessionLocal()

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass

    def list(self, include_deleted: bool = False) -> list[dict]:
        stmt = select(ArtifactTemplate)
        if not include_deleted:
            stmt = stmt.where(ArtifactTemplate.is_deleted.is_(False))
        rows = self.session.execute(stmt.order_by(ArtifactTemplate.id)).scalars().all()
        return [r.to_dict() for r in rows]

    def get(self, template_id: int) -> Optional[dict]:
        row = self.session.get(ArtifactTemplate, template_id)
        if row is None or row.is_deleted:
            return None
        return row.to_dict()

    def get_by_key(self, key: str) -> Optional[dict]:
        stmt = select(ArtifactTemplate).where(
            ArtifactTemplate.key == key, ArtifactTemplate.is_deleted.is_(False)
        )
        row = self.session.execute(stmt).scalars().first()
        return row.to_dict() if row else None

    def key_exists(self, key: str, exclude_id: Optional[int] = None) -> bool:
        stmt = select(func.count(ArtifactTemplate.id)).where(ArtifactTemplate.key == key)
        if exclude_id is not None:
            stmt = stmt.where(ArtifactTemplate.id != exclude_id)
        return int(self.session.execute(stmt).scalar() or 0) > 0

    def create(self, data: dict, operator: str = "system") -> dict:
        import json as _json
        row = ArtifactTemplate(
            key=data["key"],
            name=data.get("name") or data["key"],
            format=(data.get("format") or "pdf").lower(),
            description=data.get("description") or "",
            blocks=_json.dumps(data.get("blocks") or [], ensure_ascii=False),
            created_at=_now(),
            updated_at=_now(),
            created_by=operator,
            updated_by=operator,
        )
        self.session.add(row)
        self.session.commit()
        return row.to_dict()

    def update(self, template_id: int, data: dict, operator: str = "system") -> Optional[dict]:
        import json as _json
        row = self.session.get(ArtifactTemplate, template_id)
        if row is None or row.is_deleted:
            return None
        if "name" in data:
            row.name = data["name"] or row.key
        if "description" in data:
            row.description = data["description"] or ""
        if "format" in data and data["format"]:
            row.format = str(data["format"]).lower()
        if "blocks" in data and isinstance(data["blocks"], list):
            row.blocks = _json.dumps(data["blocks"], ensure_ascii=False)
            row.version = int(row.version or 1) + 1
        row.updated_at = _now()
        row.updated_by = operator
        self.session.commit()
        return row.to_dict()

    def soft_delete(self, template_id: int) -> bool:
        row = self.session.get(ArtifactTemplate, template_id)
        if row is None or row.is_deleted:
            return False
        row.is_deleted = True
        row.updated_at = _now()
        self.session.commit()
        return True

    def count(self) -> int:
        return int(
            self.session.execute(
                select(func.count(ArtifactTemplate.id)).where(ArtifactTemplate.is_deleted.is_(False))
            ).scalar() or 0
        )

    def seed_if_empty(self, seeds) -> None:
        if self.count() > 0:
            return
        for s in seeds:
            if self.key_exists(s["key"]):
                continue
            self.create(s, operator="system")
