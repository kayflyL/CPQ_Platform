"""Assistant repository — threads + messages for the global AI assistant.

Mirrors the Feed pattern (懒 session, Opportunity_SessionLocal, now_iso) but is
fully separate from FeedMessage: assistant chats are a private user<->AI context,
not team activity.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
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
        thread_kind: str = "assistant",
        colleague_role_key: Optional[str] = None,
        entry_point: Optional[str] = None,
    ) -> dict:
        now = now_iso()
        t = AssistantThread(
            thread_id=uuid.uuid4().hex,
            title=title or self._auto_title(opportunity_id, quotation_id),
            thread_kind=thread_kind,
            colleague_role_key=colleague_role_key,
            opportunity_id=opportunity_id,
            quotation_id=quotation_id,
            entry_point=entry_point,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self.session.add(t)
        self.session.commit()
        self.session.refresh(t)
        return t.to_dict()

    def update_thread_entry_point(self, thread_id: str, entry_point: str) -> Optional[dict]:
        """Update the latest entry source for a thread (portal/floating_assistant/ai_office)."""
        entry_point = (entry_point or "").strip() or None
        if not entry_point:
            return self.get_thread(thread_id)
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        if not t:
            return None
        t.entry_point = entry_point
        t.updated_at = now_iso()
        self.session.commit()
        self.session.refresh(t)
        return t.to_dict()

    def update_thread_opportunity_id(self, thread_id: str, opportunity_id: str) -> Optional[dict]:
        """Bind an AI Office thread to an internal opportunity so later turns reuse it."""
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        if not t:
            return None
        t.opportunity_id = opportunity_id or None
        t.updated_at = now_iso()
        self.session.commit()
        self.session.refresh(t)
        return t.to_dict()

    def list_threads(
        self,
        created_by: str,
        limit: int = 50,
        thread_kind: str = "assistant",
        colleague_role_key: Optional[str] = None,
        include_deleted: bool = False,
        with_meta: bool = False,
        include_preview: bool = False,
    ) -> List[dict]:
        conditions = [
            AssistantThread.created_by == created_by,
            AssistantThread.thread_kind == thread_kind,
        ]
        if not include_deleted:
            conditions.append(AssistantThread.deleted_at.is_(None))
        if not include_preview:
            conditions.append(AssistantThread.entry_point != "skill_studio_preview")
        if colleague_role_key:
            conditions.append(AssistantThread.colleague_role_key == colleague_role_key)
        rows = self.session.execute(
            select(AssistantThread)
            .where(*conditions)
            .order_by(AssistantThread.updated_at.desc())
            .limit(limit)
        ).scalars().all()
        if not with_meta:
            return [t.to_dict() for t in rows]
        message_meta = self.threads_message_meta([t.thread_id for t in rows])
        out: List[dict] = []
        for t in rows:
            d = t.to_dict()
            meta = message_meta.get(t.thread_id, {})
            d["deleted_at"] = t.deleted_at or ""
            d["msg_count"] = meta.get("msg_count", 0)
            d["first_message"] = meta.get("first_message", "")
            d["last_message"] = meta.get("last_message", "")
            d["role_counts"] = meta.get("role_counts", {})
            out.append(d)
        return out

    def get_thread(self, thread_id: str) -> Optional[dict]:
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        return t.to_dict() if t else None

    def list_all_threads(
        self,
        limit: int = 500,
        thread_kind: Optional[str] = None,
        colleague_role_key: Optional[str] = None,
        created_by: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[dict]:
        """管理员：列出全部会话（含回收站），带消息数/状态，按最后活跃倒序。"""
        conditions = []
        if thread_kind:
            conditions.append(AssistantThread.thread_kind == thread_kind)
        if colleague_role_key:
            conditions.append(AssistantThread.colleague_role_key == colleague_role_key)
        if created_by:
            conditions.append(AssistantThread.created_by == created_by)
        if keyword:
            term = f"%{str(keyword).strip()}%"
            conditions.append(or_(AssistantThread.title.ilike(term), AssistantThread.thread_id.ilike(term)))
        rows = self.session.execute(
            select(AssistantThread)
            .where(*conditions)
            .order_by(AssistantThread.updated_at.desc())
            .limit(limit)
        ).scalars().all()
        message_meta = self.threads_message_meta([t.thread_id for t in rows])
        out: List[dict] = []
        for t in rows:
            d = t.to_dict()
            meta = message_meta.get(t.thread_id, {})
            d["deleted_at"] = t.deleted_at or ""
            d["msg_count"] = meta.get("msg_count", 0)
            d["first_message"] = meta.get("first_message", "")
            d["last_message"] = meta.get("last_message", "")
            d["role_counts"] = meta.get("role_counts", {})
            out.append(d)
        return out

    def threads_message_meta(self, thread_ids: List[str]) -> dict:
        """批量返回会话消息元信息：总数、首条/末条预览、role 计数。"""
        ids = [str(i) for i in thread_ids if i]
        if not ids:
            return {}
        rows = self.session.execute(
            select(AssistantMessage)
            .where(
                AssistantMessage.thread_id.in_(ids),
                AssistantMessage.deleted_at.is_(None),
            )
            .order_by(AssistantMessage.created_at.asc())
        ).scalars().all()
        grouped: dict = {}
        for tid in ids:
            grouped[tid] = {"items": [], "role_counts": {}}
        for m in rows:
            grouped.setdefault(m.thread_id, {"items": [], "role_counts": {}})
            grouped[m.thread_id]["items"].append(m)
        out: dict = {}
        for tid, data in grouped.items():
            items = data["items"]
            counts = dict(data["role_counts"])
            for m in items:
                role = m.role or "unknown"
                counts[role] = int(counts.get(role, 0)) + 1
            out[tid] = {
                "msg_count": len(items),
                "first_message": (items[0].content or "")[:120] if items else "",
                "last_message": (items[-1].content or "")[:120] if items else "",
                "role_counts": counts,
            }
        return out

    def soft_delete_thread(self, thread_id: str, created_by: Optional[str] = None) -> bool:
        query = select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        if created_by:
            query = query.where(AssistantThread.created_by == created_by)
        t = self.session.execute(query).scalar_one_or_none()
        if not t:
            return False
        t.deleted_at = now_iso()
        self.session.commit()
        return True

    def restore_thread(self, thread_id: str, created_by: Optional[str] = None) -> bool:
        """回收站恢复：清空 deleted_at（会话回到正常）。"""
        query = select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        if created_by:
            query = query.where(AssistantThread.created_by == created_by)
        t = self.session.execute(query).scalar_one_or_none()
        if not t:
            return False
        t.deleted_at = None
        self.session.commit()
        return True

    def hard_delete_thread(self, thread_id: str, created_by: Optional[str] = None) -> bool:
        """彻底删除：物理清掉该会话全部消息 + 线程行（含 reasoning_state）。"""
        query = select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        if created_by:
            query = query.where(AssistantThread.created_by == created_by)
        t = self.session.execute(query).scalar_one_or_none()
        if not t:
            return False
        self.session.execute(
            AssistantMessage.__table__.delete().where(AssistantMessage.thread_id == thread_id)
        )
        self.session.delete(t)
        self.session.commit()
        return True

    def update_thread_title(self, thread_id: str, title: str, created_by: Optional[str] = None) -> Optional[dict]:
        """Overwrite a thread's title (used to auto-name it from the first user message)."""
        query = select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        if created_by:
            query = query.where(AssistantThread.created_by == created_by)
        t = self.session.execute(query).scalar_one_or_none()
        if not t:
            return None
        t.title = title
        t.updated_at = now_iso()
        self.session.commit()
        self.session.refresh(t)
        return t.to_dict()


    # ── reasoning state（方案助手通道的需求分析会话状态，JSON 存 reasoning_state 列）──

    def get_reasoning_state(self, thread_id: str) -> Optional[str]:
        """读会话的需求分析状态（原始 JSON 文本；无则 None）。"""
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        return t.reasoning_state if t else None

    def update_reasoning_state(self, thread_id: str, patch: dict) -> None:
        """合并写会话需求分析状态（read-modify-write，幂等）。"""
        import json
        t = self.session.execute(
            select(AssistantThread).where(AssistantThread.thread_id == thread_id)
        ).scalar_one_or_none()
        if not t:
            return
        current = {}
        if t.reasoning_state:
            try:
                parsed = json.loads(t.reasoning_state)
                if isinstance(parsed, dict):
                    current = parsed
            except Exception:
                current = {}
        current.update(patch or {})
        t.reasoning_state = json.dumps(current, ensure_ascii=False)
        t.updated_at = now_iso()
        self.session.commit()

    # ── 历史数据清理（rules 表走 Rules_SessionLocal，遵守 schema 隔离）──

    def hard_delete_empty_threads(self) -> int:
        """一键清理空会话：物理删除所有 0 消息（无有效消息）的线程。返回删除数。"""
        from sqlalchemy import func
        rows = self.session.execute(select(AssistantThread)).scalars().all()
        deleted = 0
        for t in rows:
            cnt = self.session.execute(
                select(func.count()).select_from(AssistantMessage).where(
                    AssistantMessage.thread_id == t.thread_id,
                    AssistantMessage.deleted_at.is_(None),
                )
            ).scalar() or 0
            if cnt == 0:
                self.session.delete(t)
                deleted += 1
        self.session.commit()
        return deleted

    def purge_llm_trace(self, keep_days: int) -> int:
        """LLM 调用痕迹：只保留最近 keep_days 天，删除更早。keep_days<=0 → 全清。"""
        from datetime import datetime, timedelta, timezone
        from app.models.base import Rules_SessionLocal
        from app.models.llm_trace import LLMTrace
        if keep_days < 0:
            keep_days = 0
        session = Rules_SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
            q = LLMTrace.__table__.delete()
            if keep_days > 0:
                q = q.where(LLMTrace.created_at < cutoff)
            res = session.execute(q)
            session.commit()
            return res.rowcount or 0
        finally:
            session.close()

    def prune_requirement_samples(self, keep_n: int) -> int:
        """需求反馈样本：保留最近 keep_n 条（按 id 倒序），删除其余；keep_n=0 → 全清。"""
        from app.models.base import Rules_SessionLocal
        from app.models.requirement_rule import RequirementSample
        if keep_n < 0:
            keep_n = 0
        session = Rules_SessionLocal()
        try:
            if keep_n == 0:
                res = session.execute(RequirementSample.__table__.delete())
            else:
                keep_ids = session.execute(
                    select(RequirementSample.id).order_by(RequirementSample.id.desc()).limit(keep_n)
                ).scalars().all()
                if keep_ids:
                    res = session.execute(
                        RequirementSample.__table__.delete().where(RequirementSample.id.not_in(keep_ids))
                    )
                else:
                    res = None
            session.commit()
            return res.rowcount if res is not None else 0
        finally:
            session.close()

    # ── messages ──

    def list_messages(self, thread_id: str, limit: int = 50) -> List[dict]:
        safe_limit = max(1, min(int(limit or 50), 500))
        rows = self.session.execute(
            select(AssistantMessage)
            .where(
                AssistantMessage.thread_id == thread_id,
                AssistantMessage.deleted_at.is_(None),
            )
            .order_by(AssistantMessage.created_at.desc())
            .limit(safe_limit)
        ).scalars().all()
        return [m.to_dict() for m in reversed(rows)]

    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        opportunity_id: Optional[str] = None,
        quotation_id: Optional[str] = None,
        kind: str = "text",
        data: Optional[str] = None,
        colleague_role_key: Optional[str] = None,
    ) -> dict:
        m = AssistantMessage(
            message_id=uuid.uuid4().hex,
            thread_id=thread_id,
            role=role,
            content=content,
            kind=kind,
            data=data,
            colleague_role_key=colleague_role_key,
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
