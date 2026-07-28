"""Feed repository — messages + attachments for an opportunity's activity feed.

Replaces the old public.comments scan and the opportunity_files disk scan.
Listing is a query; author/uploader names are resolved in bulk per result set.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
import uuid

from app.models.feed_message import FeedMessage
from app.models.feed_attachment import FeedAttachment
from app.models.base import Opportunity_SessionLocal
from app.services.storage_adapter import now_iso


class FeedRepository:
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

    # ── messages ──

    def add_message(
        self,
        opportunity_id: str,
        author_user_id: str,
        body: Optional[str] = None,
        kind: str = "comment",
        quotation_id: Optional[str] = None,
    ) -> dict:
        msg = FeedMessage(
            message_id=uuid.uuid4().hex,
            opportunity_id=opportunity_id,
            author_user_id=author_user_id,
            body=body,
            kind=kind,
            quotation_id=quotation_id,
            created_at=now_iso(),
        )
        self.session.add(msg)
        self.session.commit()
        self.session.refresh(msg)
        return msg.to_dict()

    def list_messages(self, opportunity_id: str, limit: int = 200) -> List[dict]:
        msgs = self.session.execute(
            select(FeedMessage)
            .where(
                FeedMessage.opportunity_id == opportunity_id,
                FeedMessage.deleted_at.is_(None),
            )
            .order_by(FeedMessage.created_at.asc())
            .limit(limit)
        ).scalars().all()
        if not msgs:
            return []
        names = self._resolve_names([m.author_user_id for m in msgs])
        atts_by_msg = self._attachments_by_message([m.message_id for m in msgs])
        out = []
        for m in msgs:
            d = m.to_dict()
            d["author_name"] = names.get(m.author_user_id, "匿名")
            d["attachments"] = atts_by_msg.get(m.message_id, [])
            out.append(d)
        return out

    def soft_delete_message(self, message_id: str) -> Optional[str]:
        """Soft-delete a message; returns its opportunity_id (or None if missing)
        so callers can broadcast the deletion to the right room."""
        m = self.session.execute(
            select(FeedMessage).where(FeedMessage.message_id == message_id)
        ).scalar_one_or_none()
        if not m:
            return None
        opp = m.opportunity_id
        m.deleted_at = now_iso()
        self.session.commit()
        return opp

    # ── attachments ──

    def add_attachment(
        self,
        opportunity_id: str,
        uploader_user_id: str,
        original_filename: str,
        storage_key: str,
        file_size: int,
        mime_type: Optional[str] = None,
        kind: str = "upload",
        message_id: Optional[str] = None,
        quotation_id: Optional[str] = None,
        version: int = 1,
        version_group: Optional[str] = None,
        category: Optional[str] = None,
    ) -> dict:
        att = FeedAttachment(
            attachment_id=uuid.uuid4().hex,
            opportunity_id=opportunity_id,
            message_id=message_id,
            uploader_user_id=uploader_user_id,
            original_filename=original_filename,
            storage_key=storage_key,
            file_size=file_size,
            mime_type=mime_type,
            kind=kind,
            quotation_id=quotation_id,
            version=version,
            version_group=version_group or uuid.uuid4().hex,
            category=category,
            created_at=now_iso(),
        )
        self.session.add(att)
        self.session.commit()
        self.session.refresh(att)
        return att.to_dict()

    def get_attachment(self, attachment_id: str) -> Optional[dict]:
        a = self.session.execute(
            select(FeedAttachment).where(FeedAttachment.attachment_id == attachment_id)
        ).scalar_one_or_none()
        return a.to_dict() if a else None

    def list_attachments(self, opportunity_id: str) -> List[dict]:
        rows = self.session.execute(
            select(FeedAttachment)
            .where(
                FeedAttachment.opportunity_id == opportunity_id,
                FeedAttachment.deleted_at.is_(None),
            )
            .order_by(FeedAttachment.created_at.desc())
        ).scalars().all()
        if not rows:
            return []
        names = self._resolve_names([a.uploader_user_id for a in rows])
        out = []
        for a in rows:
            d = a.to_dict()
            d["uploader_name"] = names.get(a.uploader_user_id, "匿名")
            out.append(d)
        return out

    def update_attachment_category(self, attachment_id: str, category: Optional[str]) -> Optional[dict]:
        """Move an attachment between archive buckets (requirement/technical/sent_quote).

        category=None means 'uncategorized' (won't show in any archive column).
        Returns the updated dict or None if the row is missing.
        """
        a = self.session.execute(
            select(FeedAttachment).where(FeedAttachment.attachment_id == attachment_id)
        ).scalar_one_or_none()
        if not a:
            return None
        a.category = category
        self.session.commit()
        self.session.refresh(a)
        return a.to_dict()

    def soft_delete_attachment(self, attachment_id: str) -> Optional[str]:
        """Soft-delete an attachment and remove its physical file.
        Returns opportunity_id (or None if not found)."""
        a = self.session.execute(
            select(FeedAttachment).where(FeedAttachment.attachment_id == attachment_id)
        ).scalar_one_or_none()
        if not a:
            return None
        opp = a.opportunity_id
        storage_key = a.storage_key
        a.deleted_at = now_iso()
        self.session.commit()
        # 删除物理文件（失败不阻断，只记录日志）
        if storage_key:
            from app.services.storage_adapter import get_storage
            try:
                get_storage().delete(storage_key)
            except Exception:
                pass  # 物理删除失败不阻断业务
        return opp

    def soft_delete_attachments_by_quotation(self, quotation_id: str) -> List[str]:
        """Soft-delete all attachments linked to a quotation (sent_quote exports)
        and remove their physical files.
        Returns list of [opportunity_id, attachment_id, ...] for broadcasting."""
        rows = self.session.execute(
            select(FeedAttachment).where(
                FeedAttachment.quotation_id == quotation_id,
                FeedAttachment.deleted_at.is_(None),
            )
        ).scalars().all()
        if not rows:
            return []
        # Collect info before mutating
        opp_id = rows[0].opportunity_id
        attachment_ids = [a.attachment_id for a in rows]
        storage_keys = [(a.attachment_id, a.storage_key) for a in rows]
        # Soft-delete in DB
        for a in rows:
            a.deleted_at = now_iso()
        self.session.commit()
        # 删除物理文件（失败不阻断）
        from app.services.storage_adapter import get_storage
        storage = get_storage()
        for att_id, storage_key in storage_keys:
            if storage_key:
                try:
                    storage.delete(storage_key)
                except Exception:
                    pass  # 物理删除失败不阻断业务
        return [opp_id] + attachment_ids

    def update_storage_key_prefix(self, opportunity_id: str, old_prefix: str, new_prefix: str) -> int:
        """Update storage_key prefix when customer name changes.

        Args:
            opportunity_id: The opportunity whose attachments need updating
            old_prefix: Old folder prefix, e.g. "opportunities/华为_OPP-xxx"
            new_prefix: New folder prefix, e.g. "opportunities/华为科技_OPP-xxx"

        Returns:
            Number of rows updated
        """
        from sqlalchemy import update as sql_update
        # 获取该商机的所有附件
        attachments = self.session.execute(
            select(FeedAttachment).where(
                FeedAttachment.opportunity_id == opportunity_id,
                FeedAttachment.deleted_at.is_(None),
            )
        ).scalars().all()

        updated_count = 0
        for att in attachments:
            old_key = att.storage_key
            if old_key and old_key.startswith(old_prefix):
                new_key = old_key.replace(old_prefix, new_prefix, 1)
                att.storage_key = new_key
                updated_count += 1

        self.session.commit()
        return updated_count

    def list_versions(self, version_group: str) -> List[dict]:
        rows = self.session.execute(
            select(FeedAttachment)
            .where(
                FeedAttachment.version_group == version_group,
                FeedAttachment.deleted_at.is_(None),
            )
            .order_by(FeedAttachment.version.desc())
        ).scalars().all()
        return [a.to_dict() for a in rows]

    def latest_version(self, version_group: str) -> Optional[int]:
        row = self.session.execute(
            select(FeedAttachment.version)
            .where(FeedAttachment.version_group == version_group)
            .order_by(FeedAttachment.version.desc())
            .limit(1)
        ).first()
        return row[0] if row else None

    # ── internal helpers ──

    def _resolve_names(self, user_ids: List[str]) -> dict:
        """Bulk user_id -> display name, queried in this session."""
        from app.models.feed_user import FeedUser
        ids = [i for i in set(user_ids) if i]
        if not ids:
            return {}
        rows = self.session.execute(
            select(FeedUser.user_id, FeedUser.name).where(FeedUser.user_id.in_(ids))
        ).all()
        return {uid: (name or "匿名") for uid, name in rows}

    def _attachments_by_message(self, message_ids: List[str]) -> dict:
        ids = [i for i in message_ids if i]
        if not ids:
            return {}
        rows = self.session.execute(
            select(FeedAttachment).where(
                FeedAttachment.message_id.in_(ids),
                FeedAttachment.deleted_at.is_(None),
            )
        ).scalars().all()
        names = self._resolve_names([a.uploader_user_id for a in rows])
        out: dict = {}
        for a in rows:
            d = a.to_dict()
            d["uploader_name"] = names.get(a.uploader_user_id, "匿名")
            out.setdefault(a.message_id, []).append(d)
        return out
