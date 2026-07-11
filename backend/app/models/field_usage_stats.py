"""Field usage statistics model — stored in kp_data.db"""
from typing import Optional
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, kp_engine


class FieldUsageStats(Base):
    __tablename__ = "field_usage_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    field_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "field_key": self.field_key,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at,
        }
