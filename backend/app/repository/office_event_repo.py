"""Repository for persisted AI office events."""
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.base import Rules_SessionLocal
from app.models.office_event import OfficeEvent


class OfficeEventRepository:
    """Small synchronous repository; callers use asyncio.to_thread when async."""

    def create(self, payload: Dict[str, Any]) -> Optional[int]:
        if not isinstance(payload, dict):
            return None
        event = OfficeEvent(
            role_key=str(payload.get("role_key") or "unknown")[:120],
            event_type=str(payload.get("event_type") or payload.get("type") or "colleague_status")[:64],
            status=(str(payload["status"])[:64] if payload.get("status") is not None else None),
            source=(str(payload["source"])[:64] if payload.get("source") else "system"),
            activity=payload.get("activity"),
            message=payload.get("message"),
            ts=payload.get("ts"),
            payload=payload,
            created_at=str(payload.get("created_at") or ""),
        )
        with Rules_SessionLocal() as session:
            session.add(event)
            session.commit()
            session.refresh(event)
            return event.id

    def query(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        role_key: Optional[str] = None,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        source: Optional[str] = None,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        keyword: Optional[str] = None,
        allowed_role_keys: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        safe_page = max(1, int(page or 1))
        safe_size = max(1, min(int(page_size or 100), 500))
        conditions = []

        if role_key:
            conditions.append(OfficeEvent.role_key == role_key)
        if event_type:
            conditions.append(OfficeEvent.event_type == event_type)
        if status:
            conditions.append(OfficeEvent.status == status)
        if source:
            conditions.append(OfficeEvent.source == source)
        if start_ts is not None:
            conditions.append(OfficeEvent.ts >= float(start_ts))
        if end_ts is not None:
            conditions.append(OfficeEvent.ts <= float(end_ts))
        if allowed_role_keys is not None:
            allowed = [str(key) for key in allowed_role_keys if key]
            if allowed:
                conditions.append(OfficeEvent.role_key.in_(allowed))
            else:
                conditions.append(OfficeEvent.role_key.in_(["__no_office_role__"]))
        if keyword:
            term = f"%{str(keyword).strip()}%"
            conditions.append(or_(
                OfficeEvent.role_key.ilike(term),
                OfficeEvent.activity.ilike(term),
                OfficeEvent.message.ilike(term),
                OfficeEvent.source.ilike(term),
            ))

        with Rules_SessionLocal() as session:
            total = int(session.scalar(select(func.count(OfficeEvent.id)).where(*conditions)) or 0)
            rows = session.scalars(
                select(OfficeEvent)
                .where(*conditions)
                .order_by(OfficeEvent.id.desc())
                .offset((safe_page - 1) * safe_size)
                .limit(safe_size)
            ).all()

        return {
            "items": [row.to_dict() for row in rows],
            "total": total,
            "page": safe_page,
            "page_size": safe_size,
        }

    def get(self, event_id: int) -> Optional[dict]:
        with Rules_SessionLocal() as session:
            row = session.get(OfficeEvent, int(event_id))
            return row.to_dict() if row else None

    def update(self, event_id: int, patch: Dict[str, Any]) -> Optional[dict]:
        if not isinstance(patch, dict):
            return self.get(event_id)
        with Rules_SessionLocal() as session:
            row = session.get(OfficeEvent, int(event_id))
            if not row:
                return None
            if patch.get("message") is not None:
                row.message = str(patch.get("message"))[:4000]
            if patch.get("activity") is not None:
                row.activity = patch.get("activity")
            if isinstance(patch.get("payload"), dict):
                merged = dict(row.payload or {})
                merged.update(patch["payload"])
                row.payload = merged
            session.commit()
            session.refresh(row)
            return row.to_dict()

    def delete(self, event_id: int) -> bool:
        with Rules_SessionLocal() as session:
            row = session.get(OfficeEvent, int(event_id))
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True

    def prune_runtime_events(self, max_age_seconds: int = 90 * 24 * 3600) -> int:
        """清理普通办公室运行事件，保留 90 天内的可观测流水。

        治理审批历史由 OfficeGovernanceRepository.prune_resolved 单独治理；
        员工长期记忆已迁 rules.colleague_memories（上限治理在
        ColleagueMemoryRepository.enforce_cap）。
        """
        cutoff = time.time() - int(max_age_seconds)
        with Rules_SessionLocal() as session:
            result = session.execute(
                OfficeEvent.__table__.delete().where(
                    OfficeEvent.event_type == "colleague_status",
                    OfficeEvent.ts < cutoff,
                )
            )
            session.commit()
            return int(result.rowcount or 0)
