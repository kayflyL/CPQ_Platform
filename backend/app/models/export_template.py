"""Export template model — stores Excel template configs (cover + config sheet)"""
from typing import Optional
from sqlalchemy import Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class ExportTemplate(Base):
    __tablename__ = "export_templates"

    id: Mapped[int] = mapped_column("rowid", Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    display_name: Mapped[str] = mapped_column(String)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    template_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self, include_buffer: bool = True) -> dict:
        import json
        template_json = json.loads(self.template_json) if self.template_json else {}
        if not include_buffer:
            # Strip large base64 fileBuffers — list views don't need them
            for key in ('cover', 'config_sheet'):
                part = template_json.get(key)
                if isinstance(part, dict):
                    part.pop('fileBuffer', None)
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "is_default": self.is_default,
            "template_json": template_json,
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }
