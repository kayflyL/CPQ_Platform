"""Notification repository — 站内通知收件箱 CRUD。"""
import json
import uuid
from typing import Dict, List, Optional

from sqlalchemy import func, select

from app.models.base import Opportunity_SessionLocal
from app.models.notification import Notification
from app.services.storage_adapter import now_iso


def _now() -> str:
    return now_iso()


class NotificationRepository:
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

    def create(self, user_id: str, type: str, title: str, body: str = "",
               opportunity_id: str = "", payload: Optional[dict] = None) -> dict:
        row = Notification(
            notification_id=uuid.uuid4().hex,
            user_id=user_id,
            type=type,
            title=title,
            body=body or "",
            opportunity_id=opportunity_id or "",
            payload=json.dumps(payload, ensure_ascii=False) if payload else None,
            created_at=_now(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def list_for_user(self, user_id: str, page: int = 1, page_size: int = 20,
                      unread_only: bool = False, types: Optional[List[str]] = None) -> tuple[List[dict], int]:
        q = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            q = q.where(Notification.read_at.is_(None))
        if types:
            q = q.where(Notification.type.in_(types))
        rows = self.session.execute(
            q.order_by(Notification.created_at.desc())
        ).scalars().all()
        total = len(rows)
        start = (page - 1) * page_size
        return [r.to_dict() for r in rows[start:start + page_size]], total

    def unread_count(self, user_id: str) -> int:
        rows = self.session.execute(
            select(Notification.notification_id).where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        ).scalars().all()
        return len(rows)

    def unread_by_type(self, user_id: str) -> Dict[str, int]:
        rows = self.session.execute(
            select(Notification.type, func.count())
            .where(Notification.user_id == user_id,
                   Notification.read_at.is_(None))
            .group_by(Notification.type)
        ).all()
        return {t: n for t, n in rows}

    def mark_read(self, notification_id: str, user_id: str) -> bool:
        row = self.session.execute(
            select(Notification).where(
                Notification.notification_id == notification_id,
                Notification.user_id == user_id,
            )
        ).scalar_one_or_none()
        if not row or row.read_at:
            return bool(row)
        row.read_at = _now()
        self.session.commit()
        return True

    def mark_all_read(self, user_id: str) -> int:
        rows = self.session.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.read_at.is_(None),
            )
        ).scalars().all()
        now = _now()
        for r in rows:
            r.read_at = now
        self.session.commit()
        return len(rows)

    def delete(self, notification_id: str, user_id: str) -> bool:
        row = self.session.execute(
            select(Notification).where(
                Notification.notification_id == notification_id,
                Notification.user_id == user_id,
            )
        ).scalar_one_or_none()
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def delete_read(self, user_id: str) -> int:
        """清空已读（删除当前用户全部已读通知）。"""
        rows = self.session.execute(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.read_at.is_not(None),
            )
        ).scalars().all()
        for r in rows:
            self.session.delete(r)
        self.session.commit()
        return len(rows)
