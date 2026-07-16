"""L6 whole-machine price records model — maps l6_data.db:l6_records"""
from typing import Optional
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class L6Record(Base):
    __tablename__ = "l6_records"
    __table_args__ = {"schema": "l6"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chassis: Mapped[Optional[str]] = mapped_column(String, default=None)
    model: Mapped[Optional[str]] = mapped_column(String, default=None)
    motherboard: Mapped[Optional[str]] = mapped_column(String, default=None)
    backplane: Mapped[Optional[str]] = mapped_column(String, default=None)
    gpu_expansion: Mapped[Optional[str]] = mapped_column(String, default=None)
    psu: Mapped[Optional[str]] = mapped_column(String, default=None)
    drive_bays: Mapped[Optional[str]] = mapped_column(String, default=None)
    rail_kit: Mapped[Optional[str]] = mapped_column(String, default=None)
    power_cord: Mapped[Optional[str]] = mapped_column(String, default=None)
    price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    update_date: Mapped[Optional[str]] = mapped_column(String, default=None)
    note: Mapped[Optional[str]] = mapped_column(String, default=None)
    sort_order: Mapped[Optional[int]] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "chassis": self.chassis or "",
            "model": self.model or "",
            "motherboard": self.motherboard or "",
            "backplane": self.backplane or "",
            "gpu_expansion": self.gpu_expansion or "",
            "psu": self.psu or "",
            "drive_bays": self.drive_bays or "",
            "rail_kit": self.rail_kit or "",
            "power_cord": self.power_cord or "",
            "price": self.price or 0.0,
            "update_date": self.update_date or "",
            "note": self.note or "",
            "sort_order": self.sort_order or 0,
        }


class L6PriceHistory(Base):
    """L6 price/note change history — stored in l6_history schema"""
    __tablename__ = "l6_price_history"
    __table_args__ = {"schema": "l6_history"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    l6_record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[Optional[str]] = mapped_column(String, default=None)
    # Redundant fields to prevent history from being orphaned
    chassis: Mapped[Optional[str]] = mapped_column(String, default=None)
    model: Mapped[Optional[str]] = mapped_column(String, default=None)
    change_reason: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "l6_record_id": self.l6_record_id,
            "price": self.price or 0.0,
            "note": self.note or "",
            "chassis": self.chassis or "",
            "model": self.model or "",
            "change_reason": self.change_reason or "",
            "created_at": self.created_at,
        }
