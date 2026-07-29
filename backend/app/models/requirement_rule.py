"""Requirement rule models — 需求分析规则库（schema=rules）。

照 strategy.py 模式，聚焦需求分析三类规则：
- clarity：需求明确度判定（命中条件 → explicit / partial / unclear）
- rebuttal：反问话术（缺某字段时引导用户补齐）
- budget：预算区间 → 配件选配策略映射（min_price/max_price）

hit_count 内联（高频读展示），不走日志表（后加）。
RequirementSample 关联规则，存历史需求样本 + 反哺标注，为未来 LLM 喂语料。
"""
from typing import Optional
from sqlalchemy import Integer, String, Text, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class RequirementRule(Base):
    __tablename__ = "requirement_rules"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(20), nullable=False, default="requirement", index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # clarity/rebuttal/budget
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(Text, default=None)        # JSON 生效条件
    body: Mapped[str] = mapped_column(Text, nullable=False)                 # JSON 规则体
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)              # 内联命中计数（越跑越聪明）
    last_hit_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    change_reason: Mapped[Optional[str]] = mapped_column(Text, default=None)
    description: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_by: Mapped[str] = mapped_column(String, default="system")
    updated_by: Mapped[str] = mapped_column(String, default="system")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "domain": self.domain,
            "type": self.type,
            "name": self.name,
            "scope": json.loads(self.scope) if self.scope else None,
            "body": json.loads(self.body) if self.body else None,
            "status": self.status,
            "version": self.version,
            "hit_count": self.hit_count or 0,
            "last_hit_at": self.last_hit_at,
            "change_reason": self.change_reason,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }


class RequirementSample(Base):
    """需求样本 —— 关联规则，存历史需求片段 + 标注预期输出。反哺 + 未来 LLM 语料。"""
    __tablename__ = "requirement_samples"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rule_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sample_text: Mapped[Optional[str]] = mapped_column(Text, default=None)
    expected_result: Mapped[Optional[str]] = mapped_column(Text, default=None)  # JSON
    source: Mapped[str] = mapped_column(String(40), default="manual")  # manual/replayed/llm_feedback
    tags: Mapped[Optional[str]] = mapped_column(Text, default=None)     # JSON array
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_by: Mapped[str] = mapped_column(String, default="system")
    updated_by: Mapped[str] = mapped_column(String, default="system")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "sample_text": self.sample_text,
            "expected_result": json.loads(self.expected_result) if self.expected_result else None,
            "source": self.source,
            "tags": json.loads(self.tags) if self.tags else None,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }
