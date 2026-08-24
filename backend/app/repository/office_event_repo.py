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

    def delete_memories_by_role(self, role_key: str) -> int:
        """Delete all persisted long-term memories for one role."""
        role_key = str(role_key or "").strip() or "unknown"
        with Rules_SessionLocal() as session:
            result = session.execute(
                OfficeEvent.__table__.delete().where(
                    OfficeEvent.role_key == role_key,
                    OfficeEvent.event_type == "memory",
                )
            )
            session.commit()
            return int(result.rowcount or 0)

    def prune_runtime_events(self, max_age_seconds: int = 90 * 24 * 3600) -> int:
        """清理普通办公室运行事件，保留 90 天内的可观测流水。

        长期记忆（event_type=memory）由 prune_memories 单独治理；治理审批历史
        由 OfficeGovernanceRepository.prune_resolved 单独治理。
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

    def prune_memories(self, role_key: str) -> int:
        """按上限清理员工长期记忆：自动情景记忆 TTL/数量、长期语义记忆总量。"""
        role_key = str(role_key or "").strip() or "unknown"
        max_auto = 200
        max_long = 500
        auto_ttl_seconds = 30 * 24 * 3600
        now = time.time()
        with Rules_SessionLocal() as session:
            rows = session.scalars(
                select(OfficeEvent)
                .where(
                    OfficeEvent.role_key == role_key,
                    OfficeEvent.event_type == "memory",
                )
                .order_by(OfficeEvent.id.desc())
            ).all()
            if not rows:
                return 0
            pinned: List[OfficeEvent] = []
            auto: List[OfficeEvent] = []
            long_term: List[OfficeEvent] = []
            for row in rows:
                payload = row.payload or {}
                if payload.get("pinned"):
                    pinned.append(row)
                elif str(payload.get("kind") or "") == "episodic" and str(row.source or "") != "manual":
                    auto.append(row)
                else:
                    long_term.append(row)

            delete_ids: List[int] = []
            for row in auto:
                ts = float(row.ts or 0)
                if ts and ts < now - auto_ttl_seconds:
                    delete_ids.append(row.id)

            keep_auto = [row for row in auto if row.id not in delete_ids][:max_auto]
            keep_auto_ids = {row.id for row in keep_auto}
            for row in auto:
                if row.id not in delete_ids and row.id not in keep_auto_ids:
                    delete_ids.append(row.id)

            allowed_long = max(0, max_long - len(pinned))
            keep_long_ids = {row.id for row in long_term[:allowed_long]}
            for row in long_term[allowed_long:]:
                delete_ids.append(row.id)

            if not delete_ids:
                return 0
            ids = list(dict.fromkeys(delete_ids))
            session.execute(OfficeEvent.__table__.delete().where(OfficeEvent.id.in_(ids)))
            session.commit()
            return len(ids)
