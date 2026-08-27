"""Reasoning flow models — 推理流可视化配置（schema=rules）。

把需求分析推理流参数化（AI-first 单路能力链：
input→agent_fill→model_reason→kp_reason→compose→output）：ReasoningFlow 存图结构（节点+边），ReasoningNodeConfig 存每步可配参数。
run_ai_skill_plan 读 active flow 的 config 驱动执行；DB 异常或无 active 回退模块常量（三层兜底）。

语义独立于 Strategy（Strategy=业务规则，Flow=执行图），但照搬其 to_dict / JSON 序列化模式。
"""
from typing import Optional
from sqlalchemy import Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class ReasoningFlow(Base):
    """推理流图定义。全局通常一个 active；多版本用于切版回退。"""
    __tablename__ = "reasoning_flow"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    skill_key: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)  # draft/active
    graph: Mapped[str] = mapped_column(Text, nullable=False)  # JSON {nodes:[{key,label}], edges:[{from,to}]}
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_by: Mapped[str] = mapped_column(String, default="system")
    updated_by: Mapped[str] = mapped_column(String, default="system")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id, "name": self.name, "skill_key": self.skill_key, "version": self.version,
            "status": self.status,
            "graph": json.loads(self.graph) if self.graph else {"nodes": [], "edges": []},
            "is_active": self.is_active, "description": self.description,
            "created_at": self.created_at, "updated_at": self.updated_at,
            "created_by": self.created_by, "updated_by": self.updated_by,
        }


class ReasoningNodeConfig(Base):
    """推理流每步节点的可配参数（按 node_key 索引，config 是参数 JSON 体）。"""
    __tablename__ = "reasoning_node_config"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 关联 reasoning_flow.id
    node_key: Mapped[str] = mapped_column(String(40), nullable=False)  # input/agent_fill/model_reason/kp_reason/compose/output…
    config: Mapped[str] = mapped_column(Text, nullable=False)  # JSON 参数体
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_by: Mapped[str] = mapped_column(String, default="system")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id, "flow_id": self.flow_id, "node_key": self.node_key,
            "config": json.loads(self.config) if self.config else {},
            "version": self.version, "updated_at": self.updated_at, "updated_by": self.updated_by,
        }
