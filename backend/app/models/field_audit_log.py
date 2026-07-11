"""Field audit log model — stored in kp_data.db"""
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, kp_engine


class FieldAuditLog(Base):
    __tablename__ = "field_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # create/update/delete
    changes: Mapped[Optional[str]] = mapped_column(Text, default=None)  # JSON: {"label": {"old": "A", "new": "B"}}
    operator: Mapped[str] = mapped_column(String, default='system')
    operated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "field_key": self.field_key,
            "action": self.action,
            "changes": self.changes,
            "operator": self.operator,
            "operated_at": self.operated_at,
        }
