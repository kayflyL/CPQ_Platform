"""OpportunityPricingApproval repository — 低毛利报价审批单 CRUD。"""
from typing import List, Optional

from sqlalchemy import select

from app.models.base import Opportunity_SessionLocal
from app.models.pricing_approval import OpportunityPricingApproval
from app.services.storage_adapter import now_iso


class PricingApprovalRepository:
    def __init__(self):
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = Opportunity_SessionLocal()
        return self._session

    def close(self):
        if self._session:
            self._session.close()

    def create(self, opportunity_id: str, quotation_id: str, margin_pct: float,
               threshold: float, requested_by: str) -> dict:
        row = OpportunityPricingApproval(
            opportunity_id=opportunity_id,
            quotation_id=quotation_id,
            margin_pct=margin_pct,
            threshold=threshold,
            status="pending",
            requested_by=requested_by,
            created_at=now_iso(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def latest_for_quotation(self, quotation_id: str) -> Optional[dict]:
        # 驳回后重发会为同一报价单建多张审批单（审计留痕），取最新一张
        row = self.session.execute(
            select(OpportunityPricingApproval)
            .where(OpportunityPricingApproval.quotation_id == quotation_id)
            .order_by(OpportunityPricingApproval.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        return row.to_dict() if row else None

    def list_for_opportunity(self, opportunity_id: str) -> List[dict]:
        rows = self.session.execute(
            select(OpportunityPricingApproval)
            .where(OpportunityPricingApproval.opportunity_id == opportunity_id)
            .order_by(OpportunityPricingApproval.id.desc())
        ).scalars().all()
        return [r.to_dict() for r in rows]

    def get(self, approval_id: int) -> Optional[dict]:
        row = self.session.execute(
            select(OpportunityPricingApproval).where(
                OpportunityPricingApproval.id == approval_id)
        ).scalar_one_or_none()
        return row.to_dict() if row else None

    def decide(self, approval_id: int, status: str, decided_by: str,
               comment: str = "") -> Optional[dict]:
        row = self.session.execute(
            select(OpportunityPricingApproval).where(
                OpportunityPricingApproval.id == approval_id)
        ).scalar_one_or_none()
        if not row or row.status != "pending":
            return None
        row.status = status
        row.decided_by = decided_by
        row.decided_at = now_iso()
        row.comment = comment or ""
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()
