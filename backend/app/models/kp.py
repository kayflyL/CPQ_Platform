"""KP (Key Parts) price records model — maps kp_data.db:kp_records"""
from typing import Optional
from sqlalchemy import Integer, String, Float
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class KPRecord(Base):
    __tablename__ = "kp_records"
    __table_args__ = {"schema": "kp"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[Optional[str]] = mapped_column(String, default=None)
    model: Mapped[Optional[str]] = mapped_column(String, default=None)
    price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    currency: Mapped[Optional[str]] = mapped_column(String, default="RMB")
    date: Mapped[Optional[str]] = mapped_column(String, default=None)
    note: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "category": self.category or "",
            "model": self.model or "",
            "price": self.price or 0.0,
            "currency": self.currency or "RMB",
            "date": self.date or "",
            "note": self.note or "",
        }
