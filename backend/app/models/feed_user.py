"""Feed user model — identity + auth.

Table: opportunities.feed_users
UUID PK generated app-side (no pgcrypto dependency). Auth columns
(password_hash / is_active / role) live on this table; the feed FKs that
reference user_id stay stable across the auth migration.
"""
from typing import Optional
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class FeedUser(Base):
    __tablename__ = "feed_users"
    __table_args__ = {"schema": "opportunities"}

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[Optional[str]] = mapped_column(String, default=None)
    role: Mapped[str] = mapped_column(String, default="member")  # 角色 key（RBAC 用，默认 member）
    password_hash: Mapped[Optional[str]] = mapped_column(String, default=None)  # bcrypt 哈希；空=旧身份未设密码
    is_active: Mapped[bool] = mapped_column(default=True)  # 禁用标记（登录/鉴权用）
    created_at: Mapped[str] = mapped_column(String)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email or "",
            "role": self.role or "member",
            "is_active": bool(self.is_active) if self.is_active is not None else True,
            "created_at": self.created_at or "",
        }
