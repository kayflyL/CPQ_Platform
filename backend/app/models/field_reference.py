"""Field reference tracking model — stored in rules.db"""
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, rules_engine


class FieldReference(Base):
    __tablename__ = "field_references"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    ref_type: Mapped[str] = mapped_column(String, nullable=False)  # template/export/rule
    ref_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "field_key": self.field_key,
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "ref_name": self.ref_name,
            "created_at": self.created_at,
        }
