# -*- coding: utf-8 -*-
"""LLM 调用审计 trace —— rules.llm_trace（P3：证明 LLM 节点价值，指标数据源）。

记录每次 LLM 节点调用：状态/耗时/合并/问题数/重试，
衡量 LLM 节点有效性与人工干预率。
"""
from typing import Optional
from sqlalchemy import Integer, String, Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class LLMTrace(Base):
    __tablename__ = "llm_trace"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    pipeline_id: Mapped[str] = mapped_column(String(40), default="")
    user_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    role_key: Mapped[str] = mapped_column(String(80), default="", index=True)
    tool_name: Mapped[str] = mapped_column(String(80), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="ok")   # ok / llm_error / validated_failed
    called: Mapped[bool] = mapped_column(Boolean, default=True)
    merged: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_chars: Mapped[int] = mapped_column(Integer, default=0)
    response_chars: Mapped[int] = mapped_column(Integer, default=0)
    thinking_chars: Mapped[int] = mapped_column(Integer, default=0)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit_tokens: Mapped[int] = mapped_column(Integer, default=0)
    plans_checked: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    retried: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True),
                                               nullable=False, server_default=func.now(), index=True)
