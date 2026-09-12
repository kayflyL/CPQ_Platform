# -*- coding: utf-8 -*-
"""推理节点默认配置模型（schema=rules，DB 唯一权威）。

取代旧 system_config.reasoning_node_defaults 那把 JSON blob：
- reasoning_node_default：一行一个推理节点默认契约（作者基准），Skill Studio 节点抽屉读取。
运行时只读这张表；新建 flow 只存增量，生效值 = 默认 + 增量。
"""
from typing import Optional
from sqlalchemy import Integer, String, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class ReasoningNodeDefault(Base):
    __tablename__ = "reasoning_node_default"
    __table_args__ = (
        UniqueConstraint("skill_key", "node_key", name="uq_reasoning_node_default"),
        {"schema": "rules"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_key: Mapped[str] = mapped_column(String(80), nullable=False, default="requirement_analysis", index=True)
    node_key: Mapped[str] = mapped_column(String(40), nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON 参数体
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_by: Mapped[str] = mapped_column(String(50), default="system")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id, "skill_key": self.skill_key, "node_key": self.node_key,
            "config": json.loads(self.config) if self.config else {},
            "version": self.version, "updated_at": self.updated_at, "updated_by": self.updated_by,
        }
