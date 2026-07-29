"""Feed message model — one row per chat post in an opportunity's activity feed.

Table: opportunities.opportunity_messages
Replaces the old public.comments table (comments backfilled as kind='comment').
A message may carry 0..N attachments (see FeedAttachment.message_id).
"""
from typing import Optional
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class FeedMessage(Base):
    __tablename__ = "opportunity_messages"
    __table_args__ = {"schema": "opportunities"}

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    author_user_id: Mapped[str] = mapped_column(String)
    body: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # 'comment' = user chat post; 'system' = auto event (e.g. "导出了报价单X")
    kind: Mapped[str] = mapped_column(String, default="comment")
    quotation_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    deleted_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "opportunity_id": self.opportunity_id,
            "author_user_id": self.author_user_id,
            "author_name": "",
            "body": self.body or "",
            "kind": self.kind or "comment",
            "quotation_id": self.quotation_id or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
            "deleted_at": self.deleted_at or "",
        }
