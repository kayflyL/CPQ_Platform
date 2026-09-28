"""站内通知模型 — 门户铃铛/审批提醒的数据源。

Table: opportunities.notifications
每个用户一条收件箱（user_id 索引），opportunity_id 用于点击跳转商机详情。
type: task_assigned | stage_advanced | card_returned | withdraw_requested |
      withdraw_decided | pricing_approval_requested | pricing_approval_decided
"""
from typing import Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = {"schema": "opportunities"}

    notification_id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, index=True)
    type: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    body: Mapped[str] = mapped_column(String, default="")
    opportunity_id: Mapped[str] = mapped_column(String, default="")
    payload: Mapped[Optional[str]] = mapped_column(String, default=None)  # JSON 字符串
    read_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[str] = mapped_column(String)

    def to_dict(self) -> dict:
        import json
        payload = None
        if self.payload:
            try:
                payload = json.loads(self.payload)
            except Exception:
                payload = None
        return {
            "notification_id": self.notification_id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "body": self.body or "",
            "opportunity_id": self.opportunity_id or "",
            "payload": payload,
            "read_at": self.read_at,
            "created_at": self.created_at or "",
        }
