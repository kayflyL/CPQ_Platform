"""Feed user model — lightweight identity (seed of future auth).

Table: opportunities.feed_users
UUID PK generated app-side (no pgcrypto dependency). No password yet —
upgrades to JWT/login replace this table's columns, not the feed FKs that
reference it, so author_user_id stays stable across the auth migration.
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
    role: Mapped[str] = mapped_column(String, default="member")
    created_at: Mapped[str] = mapped_column(String)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "email": self.email or "",
            "role": self.role or "member",
            "created_at": self.created_at or "",
        }
