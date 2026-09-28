# -*- coding: utf-8 -*-
"""Artifact template ORM —— 产出物模板（rules.artifact_template）。

模板 = 产出格式契约：blocks（区块序列）+ 示例说明；AI 只填内容（answer/payload），
渲染走确定性管线（blocks+数据 → HTML → Playwright PDF）。图表区块引用图表资产
（chart_assets 注册表，与商机线索页同源口径），模板不自建图表定义。

blocks 为不透明 JSON blob：前端可加块级字段自动往返，后端只校验形状
（type ∈ title/text/kpi/chart/table），未知字段透传不解释。
"""
import json
from typing import Optional

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ArtifactTemplate(Base):
    __tablename__ = "artifact_template"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    format: Mapped[str] = mapped_column(String(16), nullable=False, default="pdf")  # P0 仅 pdf；xlsx/pptx 走文件模板路线（下期）
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    blocks: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list（不透明 blob）
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False, default="system")
    updated_by: Mapped[str] = mapped_column(String, nullable=False, default="system")

    def to_dict(self) -> dict:
        try:
            blocks = json.loads(self.blocks) if self.blocks else []
        except Exception:
            blocks = []
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "format": str(self.format or "pdf"),
            "description": self.description or "",
            "blocks": blocks if isinstance(blocks, list) else [],
            "version": int(self.version or 1),
            "is_deleted": bool(self.is_deleted),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }
