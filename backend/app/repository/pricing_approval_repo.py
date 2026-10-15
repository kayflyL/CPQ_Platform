"""OpportunityPricingApproval repository — 报价外发审批单 CRUD。"""
import json
from datetime import datetime
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
               threshold: float, requested_by: str, trigger_reason: str = "outbound",
               content_hash: str = "", assigned_to: str = "", assigned_name: str = "",
               route_snapshot: str = "", request_note: str = "") -> dict:
        row = OpportunityPricingApproval(
            opportunity_id=opportunity_id,
            quotation_id=quotation_id,
            margin_pct=margin_pct,
            threshold=threshold,
            status="pending",
            requested_by=requested_by,
            trigger_reason=trigger_reason,
            content_hash=content_hash,
            assigned_to=assigned_to,
            assigned_name=assigned_name,
            route_snapshot=route_snapshot,
            request_note=request_note,
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

    def list_recent(self, limit: int = 50) -> List[dict]:
        """跨商机审批单（调度页待审批队列）：pending 在前、组内新的在前。"""
        rows = self.session.execute(
            select(OpportunityPricingApproval)
            .order_by(OpportunityPricingApproval.id.desc())
            .limit(200)
        ).scalars().all()
        items = [r.to_dict() for r in rows]
        pending = [a for a in items if a.get("status") == "pending"]
        done = [a for a in items if a.get("status") != "pending"]
        return (pending + done)[:limit]

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

    def reassign(self, approval_id: int, to_uid: str, to_name: str,
                 by_name: str, reason: str = "") -> Optional[dict]:
        """转交责任总监：改写 assigned_to 并追加转交链（审计），不改内容指纹。"""
        row = self.session.execute(
            select(OpportunityPricingApproval).where(
                OpportunityPricingApproval.id == approval_id)
        ).scalar_one_or_none()
        if not row or row.status != "pending":
            return None
        try:
            chain = json.loads(row.transfers or "[]")
        except (json.JSONDecodeError, TypeError):
            chain = []
        chain.append({
            "at": now_iso(),
            "from_name": row.assigned_name or "",
            "to_name": to_name,
            "by": by_name,
            "reason": reason or "",
        })
        row.assigned_to = to_uid
        row.assigned_name = to_name
        row.transfers = json.dumps(chain, ensure_ascii=False)
        row.escalated_at = None  # 责任人变了，超时提醒重新计时
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def mark_escalated(self, approval_id: int) -> None:
        row = self.session.execute(
            select(OpportunityPricingApproval).where(
                OpportunityPricingApproval.id == approval_id)
        ).scalar_one_or_none()
        if row:
            row.escalated_at = now_iso()
            self.session.commit()

    def mark_reminded(self, approval_id: int) -> None:
        row = self.session.execute(
            select(OpportunityPricingApproval).where(
                OpportunityPricingApproval.id == approval_id)
        ).scalar_one_or_none()
        if row:
            row.reminded_at = now_iso()
            self.session.commit()


def waited_hours(created_at: str) -> float:
    """审批单已等待小时数（ISO 文本容错）。"""
    try:
        start = datetime.fromisoformat((created_at or "").replace("Z", ""))
        return max(0.0, (datetime.now() - start).total_seconds() / 3600)
    except (ValueError, TypeError):
        return 0.0
