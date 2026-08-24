"""Repository for persisted AI office governance items."""
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.base import Rules_SessionLocal
from app.models.office_governance import OfficeGovernanceItem


class OfficeGovernanceRepository:
    def save(self, item: Dict[str, Any]) -> None:
        if not isinstance(item, dict) or not item.get("id"):
            return
        with Rules_SessionLocal() as session:
            row = session.get(OfficeGovernanceItem, str(item["id"]))
            if not row:
                row = OfficeGovernanceItem(id=str(item["id"]))
                session.add(row)
            row.status = str(item.get("status") or "pending")
            row.payload = item.get("payload") or {}
            row.created_ts = item.get("created_ts")
            row.resolved_ts = item.get("resolved_ts")
            row.resolved_by = item.get("resolved_by")
            row.resolution = item.get("resolution")
            row.reason = item.get("reason")
            session.commit()

    def get(self, item_id: str) -> Optional[Dict[str, Any]]:
        with Rules_SessionLocal() as session:
            row = session.get(OfficeGovernanceItem, str(item_id))
            return row.to_dict() if row else None

    def prune_resolved(self, max_age_seconds: int = 180 * 24 * 3600) -> int:
        """清理已批准/已拒绝的治理历史，保留近期可追溯记录。"""
        cutoff = time.time() - int(max_age_seconds)
        with Rules_SessionLocal() as session:
            result = session.execute(
                OfficeGovernanceItem.__table__.delete().where(
                    OfficeGovernanceItem.status.in_(["approved", "rejected"]),
                    OfficeGovernanceItem.resolved_ts < cutoff,
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def list_items(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        statement = select(OfficeGovernanceItem)
        if status:
            statement = statement.where(OfficeGovernanceItem.status == status)
        statement = statement.order_by(OfficeGovernanceItem.created_ts.desc()).limit(500)
        with Rules_SessionLocal() as session:
            rows = session.scalars(statement).all()
            return [row.to_dict() for row in rows]
