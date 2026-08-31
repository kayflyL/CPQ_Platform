"""Solution model — 解决方案（schema=rules）。

解决方案是「按场景沉淀的可复用服务器方案」：每个方案对应一个应用场景。
正文 content_md 为一段 Markdown（需求要点/配置思路等章节），详情页整段渲染；
适配平台 platforms 为结构化卡片 [{name, spec, link?}]，带 link 可跳转，均不带价格。
key 为稳定业务键（如 ai-infer），供前端路由 /strategies/solutions/:key 使用。
"""
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Solution(Base):
    __tablename__ = "solutions"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    scene_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    scene: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    sub: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    features: Mapped[Optional[str]] = mapped_column(Text, default=None)   # JSON list[str]
    intro: Mapped[Optional[str]] = mapped_column(Text, default=None)      # hero 首段（Markdown）
    content_md: Mapped[Optional[str]] = mapped_column(Text, default=None) # 正文（Markdown）
    platforms: Mapped[Optional[str]] = mapped_column(Text, default=None)  # JSON list[{name,spec,link?}]
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        import json
        j = lambda v: None if v is None else json.loads(v)
        return {
            "id": self.id,
            "key": self.key,
            "scene_key": self.scene_key,
            "scene": self.scene,
            "title": self.title,
            "sub": self.sub,
            "features": j(self.features),
            "intro": self.intro,
            "content_md": self.content_md,
            "platforms": j(self.platforms),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }# reload trigger
