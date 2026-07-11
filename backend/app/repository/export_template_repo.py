"""Export template repository — CRUD for Excel export templates"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models.export_template import ExportTemplate
from app.models.base import Rules_SessionLocal
from datetime import datetime
import json


class ExportTemplateRepository:
    def __init__(self):
        self.db: Session = Rules_SessionLocal()

    def close(self):
        if self.db:
            self.db.close()

    def list(self) -> list[dict]:
        items = self.db.query(ExportTemplate).order_by(ExportTemplate.updated_at.desc()).all()
        return [t.to_dict(include_buffer=False) for t in items]

    def get_by_id(self, template_id: int) -> Optional[dict]:
        t = self.db.query(ExportTemplate).filter(ExportTemplate.id == template_id).first()
        return t.to_dict() if t else None

    def create(self, name: str, display_name: str, template_json: dict) -> dict:
        now = datetime.now().isoformat()
        t = ExportTemplate(
            name=name,
            display_name=display_name,
            is_default=False,
            template_json=json.dumps(template_json, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        self.db.add(t)
        self.db.commit()
        self.db.refresh(t)
        return t.to_dict()

    def update(self, template_id: int, data: dict) -> Optional[dict]:
        t = self.db.query(ExportTemplate).filter(ExportTemplate.id == template_id).first()
        if not t:
            return None
        if "display_name" in data:
            t.display_name = data["display_name"]
        if "template_json" in data:
            t.template_json = json.dumps(data["template_json"], ensure_ascii=False)
        t.updated_at = datetime.now().isoformat()
        self.db.commit()
        self.db.refresh(t)
        return t.to_dict()

    def delete(self, template_id: int) -> bool:
        t = self.db.query(ExportTemplate).filter(ExportTemplate.id == template_id).first()
        if not t:
            return False
        self.db.delete(t)
        self.db.commit()
        return True

    def set_default(self, template_id: int) -> bool:
        t = self.db.query(ExportTemplate).filter(ExportTemplate.id == template_id).first()
        if not t:
            return False
        # Clear all defaults first
        self.db.query(ExportTemplate).update({"is_default": False})
        t.is_default = True
        t.updated_at = datetime.now().isoformat()
        self.db.commit()
        return True
