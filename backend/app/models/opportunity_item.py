"""OpportunityItem model — quotation configuration items"""
from typing import Optional
from sqlalchemy import Integer, String, Float
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class OpportunityItem(Base):
    __tablename__ = "opportunity_items"

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quotation_id: Mapped[str] = mapped_column(String, index=True)
    config_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    category: Mapped[Optional[str]] = mapped_column(String, default=None)
    part_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    spec: Mapped[Optional[str]] = mapped_column(String, default=None)
    qty: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    confirmed_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    base_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    final_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    profit_margin: Mapped[Optional[float]] = mapped_column(Float, default=None)

    def to_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "quotation_id": self.quotation_id or "",
            "config_name": self.config_name or "",
            "category": self.category or "",
            "part_name": self.part_name or "",
            "spec": self.spec or "",
            "qty": self.qty or 1,
            "confirmed_price": self.confirmed_price or 0.0,
            "base_price": self.base_price or 0.0,
            "final_price": self.final_price or 0.0,
            "profit_margin": self.profit_margin or 0.0,
        }
