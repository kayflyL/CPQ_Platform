"""Office event persistence model.

Stored in the rules schema so office audit/history is independent from the
process-local OfficeHub/OfficeMemory caches.
"""
from typing import Optional
from sqlalchemy import JSON, Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class OfficeEvent(Base):
    __tablename__ = "office_events"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_key: Mapped[str] = mapped_column(String(120), index=True, default="unknown")
    event_type: Mapped[str] = mapped_column(String(64), index=True, default="colleague_status")
    status: Mapped[Optional[str]] = mapped_column(String(64), index=True, default=None)
    source: Mapped[Optional[str]] = mapped_column(String(64), index=True, default="system")
    activity: Mapped[Optional[str]] = mapped_column(Text, default=None)
    message: Mapped[Optional[str]] = mapped_column(Text, default=None)
    ts: Mapped[Optional[float]] = mapped_column(Float, index=True, default=None)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        data = dict(self.payload or {})
        data.setdefault("role_key", self.role_key or "unknown")
        data.setdefault("event_type", self.event_type or "colleague_status")
        data.setdefault("status", self.status)
        data.setdefault("source", self.source or "system")
        data.setdefault("activity", self.activity or "")
        data.setdefault("message", self.message or "")
        data["id"] = self.id
        data["ts"] = self.ts if self.ts is not None else data.get("ts")
        data["created_at"] = self.created_at or ""
        return data
