"""Opportunity model — represents a customer opportunity (商机线索)"""
from typing import Optional
from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = {"schema": "opportunities"}

    opportunity_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    sales_person: Mapped[Optional[str]] = mapped_column(String, default=None)
    fae: Mapped[Optional[str]] = mapped_column(String, default=None)
    quotation_person: Mapped[Optional[str]] = mapped_column(String, default=None)
    # 从 Quotation 迁移的商机级字段
    platform_type: Mapped[Optional[str]] = mapped_column(String, default=None)
    chassis_form: Mapped[Optional[str]] = mapped_column(String, default=None)
    # D1 商机结果与复盘（蓝图 A1-A2）— 解锁 M4 丢标复盘 / P2 直销渠道双基线 / M1 行业打法
    industry: Mapped[Optional[str]] = mapped_column(String, default=None)        # 行业（教育/政府/金融/制造…）
    customer_type: Mapped[Optional[str]] = mapped_column(String, default=None)   # 客户类型（直销/渠道/集成商/最终用户）
    result: Mapped[str] = mapped_column(String, default="pending")               # 业务结果：pending / won / lost（与 status 正交）
    purchase_qty: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    status: Mapped[Optional[str]] = mapped_column(String, default="active")
    extra_fields: Mapped[Optional[str]] = mapped_column(Text, default=None)  # JSON
    tenant_id: Mapped[Optional[str]] = mapped_column(String, default="default")

    def to_dict(self) -> dict:
        import json
        result = {
            "opportunity_id": self.opportunity_id,
            "customer_name": self.customer_name or "",
            "sales_person": self.sales_person or "",
            "fae": self.fae or "",
            "quotation_person": self.quotation_person or "",
            "platform_type": self.platform_type or "",
            "chassis_form": self.chassis_form or "",
            "industry": self.industry or "",
            "customer_type": self.customer_type or "",
            "result": self.result or "pending",
            "purchase_qty": self.purchase_qty or 0,
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
            "status": self.status or "active",
            "tenant_id": self.tenant_id or "default",
        }
        # 展开 extra_fields JSON 到顶层
        if self.extra_fields:
            try:
                extra = json.loads(self.extra_fields)
                result.update(extra)
            except (json.JSONDecodeError, TypeError):
                pass
        return result
