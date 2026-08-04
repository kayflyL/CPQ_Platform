# -*- coding: utf-8 -*-
"""LLM 调用审计 trace —— rules.llm_trace（P3：证明 LLM 节点价值，指标数据源）。

记录每次 LLM 节点调用（llm_understand / llm_audit）：状态/耗时/合并/问题数/重试，
配合 requirement_samples（llm_feedback）算「采纳率/修订率」。
"""
from typing import Optional
from sqlalchemy import Integer, String, Boolean, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class LLMTrace(Base):
    __tablename__ = "llm_trace"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # llm_understand / llm_audit
    opportunity_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    pipeline_id: Mapped[str] = mapped_column(String(40), default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(20), default="ok")   # ok / llm_error / validated_failed
    called: Mapped[bool] = mapped_column(Boolean, default=True)
    merged: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    prompt_chars: Mapped[int] = mapped_column(Integer, default=0)
    response_chars: Mapped[int] = mapped_column(Integer, default=0)
    plans_checked: Mapped[int] = mapped_column(Integer, default=0)
    issue_count: Mapped[int] = mapped_column(Integer, default=0)
    retried: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True),
                                               nullable=False, server_default=func.now(), index=True)
