# -*- coding: utf-8 -*-
"""技能提示词 & 推理节点默认配置模型（schema=rules，DB 唯一权威）。

取代旧 system_config.skill_prompts / reasoning_node_defaults 两把 JSON blob：
- skill_prompt_template：一行一个提示词模板，前端「提示词」面板逐行读写落库。
- reasoning_node_default：一行一个推理节点默认契约（作者基准），Skill Studio 节点抽屉读取。
运行时只读这两张表；新建 flow 只存增量，生效值 = 默认 + 增量。
"""
from typing import Optional
from sqlalchemy import Integer, String, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class SkillPromptTemplate(Base):
    __tablename__ = "skill_prompt_template"
    __table_args__ = (
        UniqueConstraint("skill_key", "slot_key", name="uq_skill_prompt_slot"),
        {"schema": "rules"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    skill_key: Mapped[str] = mapped_column(String(80), nullable=False, default="requirement_analysis", index=True)
    slot_key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    template: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_by: Mapped[str] = mapped_column(String(50), default="system")

    def to_dict(self) -> dict:
        return {
            "id": self.id, "skill_key": self.skill_key, "slot_key": self.slot_key,
            "name": self.name, "template": self.template, "enabled": self.enabled,
            "sort_order": self.sort_order, "version": self.version,
            "updated_at": self.updated_at, "updated_by": self.updated_by,
        }


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
