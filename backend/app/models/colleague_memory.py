"""Colleague structured memory model (Claude Code 式分型记忆).

一条记忆 = 一句提炼过的事实/偏好/指引，按同事(role_key)隔离。与旧
office_events(event_type=memory) 的聊天快照流不同：这里只存 LLM 抽取或
人工维护的结构化条目，注入 prompt 与管理面板都直接消费它。
"""
from typing import Optional
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

# 记忆分型（前端 chip 与 prompt 分组共用）
MEMORY_TYPES = ("user_profile", "preference", "business_fact", "guide")
TYPE_LABELS = {
    "user_profile": "用户画像",
    "preference": "偏好反馈",
    "business_fact": "业务事实",
    "guide": "行为指引",
}


class ColleagueMemory(Base):
    __tablename__ = "colleague_memories"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role_key: Mapped[str] = mapped_column(String(120), index=True, default="unknown")
    type: Mapped[str] = mapped_column(String(32), index=True, default="business_fact")
    content: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="auto")  # auto | manual
    pinned: Mapped[Optional[bool]] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(120), default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String(32), default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role_key": self.role_key or "unknown",
            "type": self.type or "business_fact",
            "type_label": TYPE_LABELS.get(self.type or "", self.type),
            "content": self.content or "",
            "source": self.source or "auto",
            "pinned": bool(self.pinned),
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }
