"""AI office governance persistence model."""
from typing import Optional
from sqlalchemy import JSON, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class OfficeGovernanceItem(Base):
    __tablename__ = "office_governance_items"
    __table_args__ = {"schema": "rules"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    payload: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_ts: Mapped[Optional[float]] = mapped_column(Float, index=True, default=None)
    resolved_ts: Mapped[Optional[float]] = mapped_column(Float, default=None)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(120), default=None)
    resolution: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    reason: Mapped[Optional[str]] = mapped_column(Text, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status or "pending",
            "payload": self.payload or {},
            "created_ts": self.created_ts,
            "resolved_ts": self.resolved_ts,
            "resolved_by": self.resolved_by or "",
            "resolution": self.resolution or "",
            "reason": self.reason or "",
        }
