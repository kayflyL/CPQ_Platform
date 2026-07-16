"""System configuration model — stored in rules.db"""
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, rules_engine


class SystemConfig(Base):
    __tablename__ = "system_config"
    __table_args__ = {"schema": "rules"}

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(20), default='string')  # string/number/boolean/json
    description: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_by: Mapped[str] = mapped_column(String(50), default='system')

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "value": self.value,
            "type": self.type,
            "description": self.description,
            "updated_at": self.updated_at,
            "updated_by": self.updated_by,
        }
