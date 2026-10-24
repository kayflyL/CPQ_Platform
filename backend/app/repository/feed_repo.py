"""Feed repository — messages + attachments for an opportunity's activity feed.

Replaces the old public.comments scan and the opportunity_files disk scan.
Listing is a query; author/uploader names are resolved in bulk per result set.
"""
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, update
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
        node_key: Optional[str] = None,
        flow_card_id: Optional[int] = None,
    ) -> dict:
        msg = FeedMessage(
            message_id=uuid.uuid4().hex,
            opportunity_id=opportunity_id,
            author_user_id=author_user_id,
            body=body,
            kind=kind,
            quotation_id=quotation_id,
            node_key=node_key,
            flow_card_id=flow_card_id,
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

    def get_message(self, message_id: str) -> Optional[dict]:
        m = self.session.execute(
            select(FeedMessage).where(FeedMessage.message_id == message_id)
        ).scalar_one_or_none()
        return m.to_dict() if m else None

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
        flow_card_id: Optional[int] = None,
        requirement_version: Optional[int] = None,
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
            flow_card_id=flow_card_id,
            requirement_version=requirement_version,
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

    def unbind_requirement_version(self, opportunity_id: str, version: int) -> int:
        """需求草稿删除时解绑其附件（requirement_version→NULL）。

        版本号按 max+1 分配、草稿删除后会被复用，不解绑会挂到未来同名草稿上；
        文件本身保留在 lead_requirement 归档，只散件化。返回解绑条数。
        """
        res = self.session.execute(
            update(FeedAttachment)
            .where(
                FeedAttachment.opportunity_id == opportunity_id,
                FeedAttachment.category == "lead_requirement",
                FeedAttachment.requirement_version == version,
                FeedAttachment.deleted_at.is_(None),
            )
            .values(requirement_version=None)
        )
        self.session.commit()
        return res.rowcount or 0

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

    # ── 会话暂存附件（聊天框直传；opportunity_id IS NULL）────────────────
    # 配额/过期是技术态不是业务事实：懒触发（上传时清本人的过期），无后台任务。

    STAGED_TTL_DAYS = 14
    STAGED_MAX_COUNT = 50
    STAGED_MAX_TOTAL_BYTES = 500 * 1024 * 1024

    def list_staged_attachments(self, uploader_user_id: str) -> List[dict]:
        """某用户的暂存附件（opportunity_id IS NULL、未删），created_at 倒序。"""
        rows = self.session.execute(
            select(FeedAttachment)
            .where(
                FeedAttachment.opportunity_id.is_(None),
                FeedAttachment.uploader_user_id == uploader_user_id,
                FeedAttachment.deleted_at.is_(None),
            )
            .order_by(FeedAttachment.created_at.desc())
        ).scalars().all()
        return [a.to_dict() for a in rows]

    def list_all_staged(self) -> List[dict]:
        """全部用户的暂存附件（opportunity_id IS NULL、未删），created_at 倒序
        （会话记录管理页的暂存清理入口）。"""
        rows = self.session.execute(
            select(FeedAttachment)
            .where(
                FeedAttachment.opportunity_id.is_(None),
                FeedAttachment.deleted_at.is_(None),
            )
            .order_by(FeedAttachment.created_at.desc())
        ).scalars().all()
        return [a.to_dict() for a in rows]

    def soft_delete_attachments(self, attachment_ids: List[str]) -> List[str]:
        """批量软删附件行，返回实际标记的 storage_key 供调用方尽力删盘。"""
        now = now_iso()
        keys: List[str] = []
        for aid in attachment_ids or []:
            row = self.session.execute(
                select(FeedAttachment).where(
                    FeedAttachment.attachment_id == str(aid),
                    FeedAttachment.deleted_at.is_(None),
                )
            ).scalars().first()
            if row:
                row.deleted_at = now
                keys.append(row.storage_key or "")
        self.session.commit()
        return [k for k in keys if k]

    def staged_quota(self, uploader_user_id: str) -> dict:
        """暂存配额现状：数量/字节 + 上限。"""
        rows = self.list_staged_attachments(uploader_user_id)
        return {
            "count": len(rows),
            "total_size": sum(r.get("file_size") or 0 for r in rows),
            "max_count": self.STAGED_MAX_COUNT,
            "max_total_size": self.STAGED_MAX_TOTAL_BYTES,
        }

    def purge_expired_staged(self, uploader_user_id: str,
                             ttl_days: Optional[int] = None) -> List[str]:
        """软删本人过期暂存行，返回应删的 storage_key（盘文件由调用方尽力删）。"""
        days = ttl_days if ttl_days is not None else self.STAGED_TTL_DAYS
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        rows = self.session.execute(
            select(FeedAttachment).where(
                FeedAttachment.opportunity_id.is_(None),
                FeedAttachment.uploader_user_id == uploader_user_id,
                FeedAttachment.deleted_at.is_(None),
                FeedAttachment.created_at < cutoff,
            )
        ).scalars().all()
        keys = [a.storage_key for a in rows]
        if rows:
            now = now_iso()
            for a in rows:
                a.deleted_at = now
            self.session.commit()
        return keys

    def bind_attachment(self, attachment_id: str, *, opportunity_id: Optional[str] = None,
                        message_id: Optional[str] = None, category: Optional[str] = None,
                        storage_key: Optional[str] = None) -> Optional[dict]:
        """业务绑定（暂存→商机桶 / 消息关联 / 归类 / 换存储键）：只更新给出的字段。"""
        a = self.session.execute(
            select(FeedAttachment).where(FeedAttachment.attachment_id == attachment_id)
        ).scalar_one_or_none()
        if not a:
            return None
        if opportunity_id is not None:
            a.opportunity_id = opportunity_id
        if message_id is not None:
            a.message_id = message_id
        if category is not None:
            a.category = category
        if storage_key is not None:
            a.storage_key = storage_key
        self.session.commit()
        self.session.refresh(a)
        return a.to_dict()

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
