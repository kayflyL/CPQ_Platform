"""OpportunityItem model — quotation configuration items"""
import json
from typing import Optional
from sqlalchemy import Integer, String, Float, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class OpportunityItem(Base):
    __tablename__ = "opportunity_items"
    __table_args__ = {"schema": "opportunities"}

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quotation_id: Mapped[str] = mapped_column(String, index=True)
    config_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    category: Mapped[Optional[str]] = mapped_column(String, default=None)
    part_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    spec: Mapped[Optional[str]] = mapped_column(String, default=None)
    qty: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    base_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    final_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    profit_margin: Mapped[Optional[float]] = mapped_column(Float, default=None)
    
    # 动态扩展字段（JSON 存储）
    extra_fields: Mapped[Optional[str]] = mapped_column(Text, default=None)
    
    # 多租户预留
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default")

    def to_dict(self) -> dict:
        result = {
            "item_id": self.item_id,
            "quotation_id": self.quotation_id or "",
            "config_name": self.config_name or "",
            "category": self.category or "",
            "part_name": self.part_name or "",
            "spec": self.spec or "",
            "qty": self.qty or 1,
            "base_price": self.base_price or 0.0,
            "final_price": self.final_price or 0.0,
            "profit_margin": self.profit_margin or 0.0,
        }
        
        # 展开 extra_fields 到顶层
        if self.extra_fields:
            try:
                extra = json.loads(self.extra_fields)
                result.update(extra)
            except (json.JSONDecodeError, TypeError):
                pass
        
        return result
