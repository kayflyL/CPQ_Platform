"""Feed user repository — identity + auth (JWT).

get_or_create by display name is the legacy "sign-in" flow (feed picker);
auth methods (get_by_name / set_password / update_role / update_active /
create_user) serve the JWT login + admin user management.
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

    def get_by_name(self, name: str) -> Optional[dict]:
        """Look up a single user by display name (exact match, no password_hash)."""
        name = (name or "").strip()
        if not name:
            return None
        u = self.session.execute(
            select(FeedUser).where(FeedUser.name == name)
        ).scalar_one_or_none()
        return u.to_dict() if u else None

    def get_by_name_auth(self, name: str) -> Optional[dict]:
        """内部鉴权视图：按名取用户并带 password_hash（仅登录/引导用，禁止直接返回 API）。"""
        name = (name or "").strip()
        if not name:
            return None
        u = self.session.execute(
            select(FeedUser).where(FeedUser.name == name)
        ).scalar_one_or_none()
        if not u:
            return None
        d = u.to_dict()
        d["password_hash"] = u.password_hash
        return d

    def get_auth(self, user_id: str) -> Optional[dict]:
        """内部鉴权视图：按 id 取用户并带 password_hash（仅登录/改密用）。"""
        u = self.session.execute(
            select(FeedUser).where(FeedUser.user_id == user_id)
        ).scalar_one_or_none()
        if not u:
            return None
        d = u.to_dict()
        d["password_hash"] = u.password_hash
        return d
    def create_user(self, name: str, role: str = "member", password_hash: Optional[str] = None,
                    email: Optional[str] = None) -> dict:
        """Create a user with explicit role/password (admin user management / bootstrap)."""
        user = FeedUser(
            user_id=uuid.uuid4().hex,
            name=(name or "").strip() or "匿名",
            email=email,
            role=role or "member",
            password_hash=password_hash,
            is_active=True,
            created_at=now_iso(),
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user.to_dict()

    def set_password(self, user_id: str, password_hash: Optional[str]) -> bool:
        u = self.session.execute(
            select(FeedUser).where(FeedUser.user_id == user_id)
        ).scalar_one_or_none()
        if not u:
            return False
        u.password_hash = password_hash
        self.session.commit()
        return True

    def update_role(self, user_id: str, role: str) -> bool:
        u = self.session.execute(
            select(FeedUser).where(FeedUser.user_id == user_id)
        ).scalar_one_or_none()
        if not u:
            return False
        u.role = role or "member"
        self.session.commit()
        return True

    def update_active(self, user_id: str, is_active: bool) -> bool:
        u = self.session.execute(
            select(FeedUser).where(FeedUser.user_id == user_id)
        ).scalar_one_or_none()
        if not u:
            return False
        u.is_active = bool(is_active)
        self.session.commit()
        return True

    def update_name(self, user_id: str, name: str) -> bool:
        u = self.session.execute(
            select(FeedUser).where(FeedUser.user_id == user_id)
        ).scalar_one_or_none()
        if not u:
            return False
        u.name = (name or "").strip() or u.name
        self.session.commit()
        return True

    def list_all(self) -> List[dict]:
        rows = self.session.execute(
            select(FeedUser).order_by(FeedUser.name.asc())
        ).scalars().all()
        return [u.to_dict() for u in rows]
