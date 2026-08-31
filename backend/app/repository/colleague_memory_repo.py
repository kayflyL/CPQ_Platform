"""Repository for colleague structured memories (rules.colleague_memories)."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_, select

from app.models.base import Rules_SessionLocal
from app.models.colleague_memory import MEMORY_TYPES, ColleagueMemory

MAX_PER_ROLE = 100


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ColleagueMemoryRepository:
    """Small synchronous repository; async callers use asyncio.to_thread."""

    def _norm_type(self, value: Any) -> str:
        t = str(value or "").strip()
        return t if t in MEMORY_TYPES else "business_fact"

    def list_by_role(self, role_key: str, keyword: str = "", limit: int = 500) -> List[dict]:
        role_key = str(role_key or "").strip()
        if not role_key:
            return []
        conditions = [ColleagueMemory.role_key == role_key]
        kw = str(keyword or "").strip()
        if kw:
            term = f"%{kw}%"
            conditions.append(or_(
                ColleagueMemory.content.ilike(term),
                ColleagueMemory.type.ilike(term),
            ))
        with Rules_SessionLocal() as session:
            rows = session.scalars(
                select(ColleagueMemory)
                .where(*conditions)
                .order_by(ColleagueMemory.pinned.desc(), ColleagueMemory.id.desc())
                .limit(max(1, min(int(limit or 500), 1000)))
            ).all()
            return [row.to_dict() for row in rows]

    def get(self, memory_id: int) -> Optional[dict]:
        with Rules_SessionLocal() as session:
            row = session.get(ColleagueMemory, int(memory_id))
            return row.to_dict() if row else None

    def add(self, role_key: str, type_: str, content: str, *,
            source: str = "manual", pinned: bool = False,
            created_by: str = "") -> Optional[dict]:
        role_key = str(role_key or "").strip()
        text = str(content or "").strip()
        if not role_key or not text:
            return None
        now = _now()
        with Rules_SessionLocal() as session:
            row = ColleagueMemory(
                role_key=role_key[:120],
                type=self._norm_type(type_),
                content=text[:1000],
                source="manual" if str(source) == "manual" else "auto",
                pinned=bool(pinned),
                created_by=str(created_by or "")[:120] or None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.to_dict()

    def update(self, memory_id: int, patch: Dict[str, Any]) -> Optional[dict]:
        if not isinstance(patch, dict):
            return self.get(memory_id)
        with Rules_SessionLocal() as session:
            row = session.get(ColleagueMemory, int(memory_id))
            if not row:
                return None
            if patch.get("type") is not None:
                row.type = self._norm_type(patch.get("type"))
            if patch.get("content") is not None:
                text = str(patch.get("content")).strip()
                if not text:
                    return row.to_dict()
                row.content = text[:1000]
            if patch.get("pinned") is not None:
                row.pinned = bool(patch.get("pinned"))
            row.updated_at = _now()
            session.commit()
            session.refresh(row)
            return row.to_dict()

    def delete(self, memory_id: int) -> bool:
        with Rules_SessionLocal() as session:
            row = session.get(ColleagueMemory, int(memory_id))
            if not row:
                return False
            session.delete(row)
            session.commit()
            return True

    def delete_by_role(self, role_key: str) -> int:
        role_key = str(role_key or "").strip()
        if not role_key:
            return 0
        with Rules_SessionLocal() as session:
            result = session.execute(
                ColleagueMemory.__table__.delete().where(ColleagueMemory.role_key == role_key)
            )
            session.commit()
            return int(result.rowcount or 0)

    def count_by_role(self, role_key: str) -> int:
        role_key = str(role_key or "").strip()
        if not role_key:
            return 0
        with Rules_SessionLocal() as session:
            return int(session.scalar(
                select(func.count(ColleagueMemory.id)).where(ColleagueMemory.role_key == role_key)
            ) or 0)

    def enforce_cap(self, role_key: str, cap: int = MAX_PER_ROLE) -> int:
        """超限淘汰最旧的非置顶条目，返回删除数。"""
        role_key = str(role_key or "").strip()
        if not role_key:
            return 0
        with Rules_SessionLocal() as session:
            rows = session.scalars(
                select(ColleagueMemory)
                .where(ColleagueMemory.role_key == role_key)
                .order_by(ColleagueMemory.pinned.desc(), ColleagueMemory.id.desc())
            ).all()
            if len(rows) <= cap:
                return 0
            victims = [r.id for r in rows[cap:] if not r.pinned]
            if victims:
                session.execute(ColleagueMemory.__table__.delete().where(ColleagueMemory.id.in_(victims)))
                session.commit()
            return len(victims)
