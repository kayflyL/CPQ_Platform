"""Assistant repository — threads + messages for the global AI assistant.

Mirrors the Feed pattern (懒 session, Opportunity_SessionLocal, now_iso) but is
fully separate from FeedMessage: assistant chats are a private user<->AI context,
not team activity.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid

from app.models.assistant import AssistantThread, AssistantMessage
from app.models.base import Opportunity_SessionLocal
from app.services.storage_adapter import now_iso


class AssistantRepository:
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

    # ── threads ──

    def create_thread(
        self,
        created_by: str,
        title: Optional[str] = None,
        opportunity_id: Optional[str] = None,
        quotation_id: Optional[str] = None,
    ) -> dict:
        now = now_iso()
        t = AssistantThread(
            thread_id=uuid.uuid4().hex,
            title=title or self._auto_title(opportunity_id, quotation_id),
            opportunity_id=opportunity_id,
            quotation_id=quotation_id,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.session.add(t)
        self.session.commit()
        self.session.refresh(t)
        return t.to_dict()

    def list_threads(self, created_by: str, limit: int = 50) -> List[dict]:
        rows = self.session.execute(
            select(AssistantThread)
            .where(
                AssistantThread.created_by == created_by,
                AssistantThread.deleted_at.is_(None),
            )
            .order_by(AssistantThread.updated_at.desc())
            .limit(limit)
        ).scalars().all()
        return [t.to_dict() for t in rows]

    def get_thread(self, thread_id: str) -> Optional[dict]:
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        return t.to_dict() if t else None

    def soft_delete_thread(self, thread_id: str) -> bool:
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        if not t:
            return False
        t.deleted_at = now_iso()
        self.session.commit()
        return True

    def update_thread_title(self, thread_id: str, title: str) -> Optional[dict]:
        """Overwrite a thread's title (used to auto-name it from the first user message)."""
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        if not t:
            return None
        t.title = title
        t.updated_at = now_iso()
        self.session.commit()
        self.session.refresh(t)
        return t.to_dict()

    # ── messages ──

    def list_messages(self, thread_id: str, limit: int = 200) -> List[dict]:
        rows = self.session.execute(
            select(AssistantMessage)
            .where(
                AssistantMessage.thread_id == thread_id,
                AssistantMessage.deleted_at.is_(None),
            )
            .order_by(AssistantMessage.created_at.asc())
            .limit(limit)
        ).scalars().all()
        return [m.to_dict() for m in rows]

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        opportunity_id: Optional[str] = None,
        quotation_id: Optional[str] = None,
    ) -> dict:
        m = AssistantMessage(
            message_id=uuid.uuid4().hex,
            thread_id=thread_id,
            role=role,
            content=content,
            opportunity_id=opportunity_id,
            quotation_id=quotation_id,
            created_at=now_iso(),
        )
        self.session.add(m)
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        if t:
            t.updated_at = now_iso()
        self.session.commit()
        self.session.refresh(m)
        return m.to_dict()

    @staticmethod
    def _auto_title(opportunity_id: Optional[str], quotation_id: Optional[str]) -> str:
        if opportunity_id and quotation_id:
            return f"商机 {opportunity_id} · 报价 {quotation_id}"
        if opportunity_id:
            return f"商机 {opportunity_id}"
        if quotation_id:
            return f"报价 {quotation_id}"
        return "新会话"
