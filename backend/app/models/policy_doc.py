"""PolicyDoc ORM —— 策略文档库独立表（rules.policy_docs）。

2026-08-04：文档从 rules.strategies（与定价/选型规则混表 + 自增数字 id）独立出来：
- 对外【无数字 id】，增删改查用「创建时间戳 (module, created_at)」定位；
- doc_key（UUID）仅是数据库必需的主键，前端/API 永不暴露、永不递增；
- created_at 不可变（创建时间），微秒精度，手动创建不会重复 → 稳定的业务定位键。
"""
import uuid
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class PolicyDoc(Base):
    __tablename__ = "policy_docs"
    __table_args__ = {"schema": "rules"}

    # 内部主键：UUID（非递增数字），任何接口都不返回它
    doc_key: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    module: Mapped[str] = mapped_column(String, nullable=False)          # pricing / selection / requirement
    name: Mapped[str] = mapped_column(String, nullable=False)            # 文档标题
    category: Mapped[str] = mapped_column(String, nullable=False, default="总览")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str] = mapped_column(String, nullable=False, default="system")
    updated_by: Mapped[str] = mapped_column(String, nullable=False, default="system")
