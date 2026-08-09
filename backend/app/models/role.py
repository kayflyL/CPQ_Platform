"""Role model — RBAC 角色（schema=rules）。

role_key 是稳定标识（feed_users.role 存的就是它）；name 是显示名（可改）；
permissions 是 JSON 数组（权限目录里的 key，目录本身存 system_config.auth.permissions）。
角色完全数据化：增删改查在「用户与权限」页，引擎只按 role_key 读权限。
"""
from typing import Optional
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = {"schema": "rules"}

    role_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    permissions: Mapped[str] = mapped_column(Text, default="[]")  # JSON 数组：权限 key
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        import json
        perms = []
        try:
            perms = json.loads(self.permissions or "[]")
        except (json.JSONDecodeError, TypeError):
            perms = []
        return {
            "role_key": self.role_key,
            "name": self.name,
            "description": self.description or "",
            "permissions": [p for p in perms if isinstance(p, str)],
            "updated_at": self.updated_at or "",
        }
