# -*- coding: utf-8 -*-
"""agent_audit —— AI 工具写操作审计账本（P4 上安全带）。

一行 = 一次 AI 写语义工具的成功执行：谁（actor：哪个同事代理、代哪个用户）在哪个会话、
用什么工具、改了哪个实体、回读结果如何。字段命名对齐 OTel gen_ai.*（gen_ai.tool.name /
gen_ai.agent.id）——只取命名不引依赖（该规范仍 experimental）。
写入走 agent_audit.audit_write（fire-and-forget：失败仅日志，绝不挡业务）。
查询：GET /api/assistant/audit（ai.office.manage 权限）——办公室"运行与权限→审计"账本视图数据源。
建表：startup create_all（模型注册 metadata，同 artifact_share_tokens 模式）。
"""
from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class AgentAuditLog(Base):
    __tablename__ = "agent_audit_log"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    thread_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    agent_role_key: Mapped[str] = mapped_column(String(80), nullable=False, default="")   # gen_ai.agent.id
    user_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")          # gen_ai.end_user.id
    tool: Mapped[str] = mapped_column(String(80), nullable=False, default="")             # gen_ai.tool.name
    args_digest: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    result_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target_entity: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    readback: Mapped[str] = mapped_column(Text, nullable=False, default="")               # 回读事实（JSON）
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
