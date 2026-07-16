"""Dynamic source fields model — stored in rules.db"""
from typing import Optional
from sqlalchemy import Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class DynamicSourceField(Base):
    __tablename__ = "dynamic_source_fields"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String, nullable=False)  # l6_details / kp_details / warranty_details / config_summary
    field_key: Mapped[str] = mapped_column(String, nullable=False)
    field_label: Mapped[str] = mapped_column(String, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_key": self.source_key,
            "field_key": self.field_key,
            "field_label": self.field_label,
            "sort_order": self.sort_order,
            "enabled": self.enabled,
        }
