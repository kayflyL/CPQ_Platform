"""Repository for colleague structured memories (rules.colleague_memories)."""
import json
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

    def list_by_role(self, role_key: str, keyword: str = "", limit: int = 500,
                     include_retired: bool = False,
                     visible_to: Optional[str] = None,
                     public_only: bool = False) -> List[dict]:
        """域过滤（多用户隔离）：visible_to=某用户 → 公共 ∪ 该用户私有；
        public_only → 仅公共域（治理面默认）；两者都不给 → 全量。"""
        role_key = str(role_key or "").strip()
        if not role_key:
            return []
        conditions = [ColleagueMemory.role_key == role_key]
        if not include_retired:
            conditions.append(ColleagueMemory.retired_at.is_(None))
        if public_only:
            conditions.append(ColleagueMemory.user_id.is_(None))
        elif str(visible_to or "").strip():
            conditions.append(or_(ColleagueMemory.user_id.is_(None),
                                  ColleagueMemory.user_id == str(visible_to).strip()[:120]))
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
            created_by: str = "", provenance: Optional[dict] = None,
            user_id: Optional[str] = None) -> Optional[dict]:
        role_key = str(role_key or "").strip()
        text = str(content or "").strip()
        if not role_key or not text:
            return None
        now = _now()
        prov_json = ""
        if isinstance(provenance, dict) and provenance:
            try:
                prov_json = json.dumps(provenance, ensure_ascii=False)[:2000]
            except Exception:
                prov_json = ""
        with Rules_SessionLocal() as session:
            row = ColleagueMemory(
                role_key=role_key[:120],
                type=self._norm_type(type_),
                content=text[:1000],
                source="manual" if str(source) == "manual" else "auto",
                pinned=bool(pinned),
                created_by=str(created_by or "")[:120] or None,
                valid_from=now,
                provenance=prov_json or None,
                user_id=str(user_id or "").strip()[:120] or None,
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

    def retire(self, memory_id: int, superseded_by: Optional[int] = None,
               force: bool = False) -> Optional[dict]:
        """失效打戳（双时间轴）：默认拒绝钉死集（置顶/手工）条目，force 供管理面强制。"""
        with Rules_SessionLocal() as session:
            row = session.get(ColleagueMemory, int(memory_id))
            if not row or row.retired_at:
                return row.to_dict() if row else None
            if not force and (row.pinned or str(row.source or "") == "manual"):
                return None
            row.retired_at = _now()
            row.updated_at = row.retired_at
            if superseded_by is not None:
                row.superseded_by = int(superseded_by)
            session.commit()
            session.refresh(row)
            return row.to_dict()

    def touch_access(self, memory_ids: List[int]) -> int:
        """注入命中的条目刷新 last_accessed_at（供老化排序与治理面参考）。"""
        ids = [int(i) for i in (memory_ids or []) if int(i) > 0]
        if not ids:
            return 0
        now = _now()
        with Rules_SessionLocal() as session:
            result = session.execute(
                ColleagueMemory.__table__.update()
                .where(ColleagueMemory.id.in_(ids), ColleagueMemory.retired_at.is_(None))
                .values(last_accessed_at=now)
            )
            session.commit()
            return int(result.rowcount or 0)

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
                select(func.count(ColleagueMemory.id)).where(
                    ColleagueMemory.role_key == role_key,
                    ColleagueMemory.retired_at.is_(None),
                )
            ) or 0)

    def enforce_cap(self, role_key: str, cap: int = MAX_PER_ROLE,
                    user_id: Optional[str] = None) -> int:
        """超限打戳淘汰最旧的非置顶条目（不物理删，双时间轴），返回失效数。
        user_id 分域计数：None=公共域，非空=该用户私有域（互不挤占）。"""
        role_key = str(role_key or "").strip()
        if not role_key:
            return 0
        domain = str(user_id or "").strip()[:120] or None
        with Rules_SessionLocal() as session:
            conditions = [ColleagueMemory.role_key == role_key,
                          ColleagueMemory.retired_at.is_(None),
                          ColleagueMemory.user_id.is_(None) if domain is None
                          else ColleagueMemory.user_id == domain]
            rows = session.scalars(
                select(ColleagueMemory)
                .where(*conditions)
                .order_by(ColleagueMemory.pinned.desc(), ColleagueMemory.id.desc())
            ).all()
            if len(rows) <= cap:
                return 0
            now = _now()
            victims = rows[cap:]
            for r in victims:
                if r.pinned:
                    continue
                r.retired_at = now
                r.updated_at = now
            session.commit()
            return len([r for r in victims if not r.pinned])
