"""Skill catalog ORM —— 技能元数据独立表（rules.skill_catalog）。

技能定义不再依赖 system_config.ai_colleagues.skill_library JSON：
- 技能元数据主存储在本表；
- 工作流图仍存 reasoning_flow / reasoning_node_config，通过 skill_key 关联；
- system_config JSON 保留兼容镜像，旧代码可回退读取。
"""
from typing import Optional
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class SkillCatalog(Base):
    __tablename__ = "skill_catalog"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    type: Mapped[str] = mapped_column(String(24), nullable=False, default="skill")  # skill / workflow
    workflow_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tool_ids: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON list
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    input_contract: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_contract: Mapped[str] = mapped_column(Text, nullable=False, default="")
    output_kind: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # plans / data_answer / generic
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    updated_at: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False, default="system")
    updated_by: Mapped[str] = mapped_column(String, nullable=False, default="system")

    def to_dict(self) -> dict:
        import json
        try:
            tool_ids = json.loads(self.tool_ids) if self.tool_ids else []
        except Exception:
            tool_ids = []
        return {
            "id": self.id,
            "key": self.key,
            "name": self.name,
            "type": "skill" if str(self.type or "").strip() == "tool_prompt" else str(self.type or "skill").strip(),
            "workflow_key": self.workflow_key,
            "description": self.description or "",
            "prompt": self.prompt or "",
            "tool_ids": tool_ids if isinstance(tool_ids, list) else [],
            "hit_count": int(self.hit_count or 0),
            "input_contract": self.input_contract or "",
            "output_contract": self.output_contract or "",
            "output_kind": self.output_kind,
            "is_deleted": bool(self.is_deleted),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }
