"""Assistant models — global AI assistant chat (独立于 Feed 的人际协作).

Two tables under the opportunities schema:
- AssistantThread: one conversation; may anchor an opportunity/quotation context
- AssistantMessage: role-tagged turns (user / assistant / system)

LLM is not wired yet (骨架期走占位回复); tables are forward-compatible — add
tokens/model/trace columns later when a real model is plugged in.
"""
from typing import Optional
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class AssistantThread(Base):
    __tablename__ = "assistant_threads"
    __table_args__ = {"schema": "opportunities"}

    thread_id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[Optional[str]] = mapped_column(String, default=None)
    # Context anchor: a thread may be started against a specific opportunity/quotation
    opportunity_id: Mapped[Optional[str]] = mapped_column(String, default=None, index=True)
    quotation_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_by: Mapped[Optional[str]] = mapped_column(String, default=None, index=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    deleted_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "thread_id": self.thread_id,
            "title": self.title or "",
            "opportunity_id": self.opportunity_id or "",
            "quotation_id": self.quotation_id or "",
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"
    __table_args__ = {"schema": "opportunities"}

    message_id: Mapped[str] = mapped_column(String, primary_key=True)
    thread_id: Mapped[str] = mapped_column(String, index=True)
    role: Mapped[str] = mapped_column(String, default="user")  # user | assistant | system
    content: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # Snapshot of where the user was when this turn was sent (per-message, since
    # a thread can span pages). Used to reconstruct context for the LLM later.
    opportunity_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    quotation_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    deleted_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "thread_id": self.thread_id,
            "role": self.role or "user",
            "content": self.content or "",
            "opportunity_id": self.opportunity_id or "",
            "quotation_id": self.quotation_id or "",
            "created_at": self.created_at or "",
        }
