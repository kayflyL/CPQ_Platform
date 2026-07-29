"""Feed user repository — lightweight identity (no password).

get_or_create by display name is the whole "sign-in" flow today. The
author_user_id FK on messages/attachments references these rows, so a later
JWT/login migration only touches this table, not the feed schema.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid

from app.models.feed_user import FeedUser
from app.models.base import Opportunity_SessionLocal
from app.services.storage_adapter import now_iso


class FeedUserRepository:
    def __init__(self):
        self._session: Optional[Session] = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Opportunity_SessionLocal()
        return self._session

    def close(self):
        if self._session:
            self._session.close()

    def get_or_create(self, name: str, email: Optional[str] = None) -> dict:
        name = (name or "").strip() or "匿名"
        existing = self.session.execute(
            select(FeedUser).where(FeedUser.name == name)
        ).scalar_one_or_none()
        if existing:
            return existing.to_dict()
        user = FeedUser(
            user_id=uuid.uuid4().hex,
            name=name,
            email=email,
            role="member",
            created_at=now_iso(),
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user.to_dict()

    def get(self, user_id: str) -> Optional[dict]:
        u = self.session.execute(
            select(FeedUser).where(FeedUser.user_id == user_id)
        ).scalar_one_or_none()
        return u.to_dict() if u else None

    def name_map(self, user_ids: List[str]) -> dict:
        """Bulk resolve user_id -> display name."""
        ids = [i for i in set(user_ids) if i]
        if not ids:
            return {}
        rows = self.session.execute(
            select(FeedUser.user_id, FeedUser.name).where(FeedUser.user_id.in_(ids))
        ).all()
        return {uid: (name or "匿名") for uid, name in rows}

    def list_all(self) -> List[dict]:
        rows = self.session.execute(
            select(FeedUser).order_by(FeedUser.name.asc())
        ).scalars().all()
        return [u.to_dict() for u in rows]
