"""低毛利报价审批单模型 — 毛利审批门（P2）的持久层。

Table: opportunities.opportunity_pricing_approvals
发送报价单时综合毛利率低于审批红线 → 自动建单，director/admin 审批。
每次发送最多一张 pending 单；rejected 后再发送会新建单（不复用，审计留痕）。
"""
from typing import Optional
from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class OpportunityPricingApproval(Base):
    __tablename__ = "opportunity_pricing_approvals"
    __table_args__ = {"schema": "opportunities"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    quotation_id: Mapped[str] = mapped_column(String, index=True)
    margin_pct: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|approved|rejected
    requested_by: Mapped[str] = mapped_column(String, default="")
    decided_by: Mapped[Optional[str]] = mapped_column(String, default=None)
    decided_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    comment: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[str] = mapped_column(String)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "quotation_id": self.quotation_id,
            "margin_pct": self.margin_pct,
            "threshold": self.threshold,
            "status": self.status,
            "requested_by": self.requested_by,
            "decided_by": self.decided_by or "",
            "decided_at": self.decided_at or "",
            "comment": self.comment or "",
            "created_at": self.created_at or "",
        }
