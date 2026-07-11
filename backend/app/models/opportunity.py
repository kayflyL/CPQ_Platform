"""Opportunity model — represents a customer opportunity (商机线索)"""
from typing import Optional
from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Opportunity(Base):
    __tablename__ = "opportunities"

    opportunity_id: Mapped[str] = mapped_column(String, primary_key=True)
    folder_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    opportunity_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    customer_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    sales_person: Mapped[Optional[str]] = mapped_column(String, default=None)
    fae: Mapped[Optional[str]] = mapped_column(String, default=None)
    # 从 Quotation 迁移的商机级字段
    platform_type: Mapped[Optional[str]] = mapped_column(String, default=None)
    chassis_form: Mapped[Optional[str]] = mapped_column(String, default=None)
    total_qty: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    status: Mapped[Optional[str]] = mapped_column(String, default="active")

    def to_dict(self) -> dict:
        return {
            "opportunity_id": self.opportunity_id,
            "folder_name": self.folder_name or "",
            "opportunity_name": self.opportunity_name or "",
            "customer_name": self.customer_name or "",
            "sales_person": self.sales_person or "",
            "fae": self.fae or "",
            "platform_type": self.platform_type or "",
            "chassis_form": self.chassis_form or "",
            "total_qty": self.total_qty or 0,
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
            "status": self.status or "active",
        }
