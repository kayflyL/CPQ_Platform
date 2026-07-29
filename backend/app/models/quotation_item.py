"""QuotationItem model — quotation configuration items"""
import json
from typing import Optional
from sqlalchemy import Integer, String, Float, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class QuotationItem(Base):
    __tablename__ = "quotation_items"
    __table_args__ = {"schema": "opportunities"}

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quotation_id: Mapped[str] = mapped_column(String, index=True)
    config_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    category: Mapped[Optional[str]] = mapped_column(String, default=None)
    # 展示字段（跨 category 统一含义）：
    # catalogue = 渲染到 Catalogue 列的值（L6=零件名, KP=型号, Warranty=描述文本）
    # description = 渲染到 Description 列的值（L6=规格, KP/Warranty 通常空）
    # part_category = KP 的类别（CPU/Memory/GPU…），用于分组/分类；L6/Warranty 为 NULL
    catalogue: Mapped[Optional[str]] = mapped_column(String, default=None)
    description: Mapped[Optional[str]] = mapped_column(String, default=None)
    part_category: Mapped[Optional[str]] = mapped_column(String, default=None)
    qty: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    base_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    final_price: Mapped[Optional[float]] = mapped_column(Float, default=None)
    profit_margin: Mapped[Optional[float]] = mapped_column(Float, default=None)
    # 行级货币（RMB / USD / ...）；决定 final_price 是否走汇率+税。历史用 is_usd_cpu 布尔（已废弃，迁移时回填到本列）
    currency: Mapped[str] = mapped_column(String(10), default="RMB")

    # 动态扩展字段（JSON 存储）
    extra_fields: Mapped[Optional[str]] = mapped_column(Text, default=None)

    # 多租户预留
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default")

    @staticmethod
    def _sanitize(obj):
        """Replace NaN/Inf with None so json.dumps won't fail."""
        import math
        if isinstance(obj, float) and (obj != obj or obj == float('inf') or obj == float('-inf')):
            return None
        return obj

    def to_dict(self) -> dict:
        result = {
            "item_id": self.item_id,
            "quotation_id": self.quotation_id or "",
            "config_name": self.config_name or "",
            "category": self.category or "",
            "catalogue": self.catalogue or "",
            "description": self.description or "",
            "part_category": self.part_category or "",
            "qty": self.qty or 1,
            "base_price": self.base_price or 0.0,
            "final_price": self.final_price or 0.0,
            "profit_margin": self.profit_margin or 0.0,
            "currency": self.currency or "RMB",
        }

        # 展开 extra_fields 到顶层
        if self.extra_fields:
            try:
                extra = json.loads(self.extra_fields)
                extra = {k: self._sanitize(v) for k, v in extra.items()}
                result.update(extra)
            except (json.JSONDecodeError, TypeError):
                pass

        return result