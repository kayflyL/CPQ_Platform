# -*- coding: utf-8 -*-
"""BOM案例库 ORM —— rules.bom_cases（选型配置 · BOM案例库）。

2026-08-04：原「方案库」更名「BOM案例库」，挂在选型配置模块。
- case_key 是对外业务键（时间戳型，如 BC-20260804-093012-123456），被 golden 用例引用；
- kp_lines 用 JSONB 存 [{part_id, qty}]，只引用 kp_parts（单一真源），不复制型号文本；
- version 每次编辑 +1，供 golden 版本指纹校验（防"方案改了回归还全绿"）；
- 无自增数字 id（用户偏好：讨厌编号，时间戳定位）。
"""
import uuid
from typing import Optional
from sqlalchemy import String, Text, Integer, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class BomCase(Base):
    __tablename__ = "bom_cases"
    __table_args__ = {"schema": "rules"}

    # 对外业务键：时间戳型（BC-YYYYMMDD-HHMMSS-ffffff），可读且唯一；被 golden.expect_case_key 引用
    case_key: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    scenario_tags: Mapped[Optional[list]] = mapped_column(JSONB, default=list)   # ["ai","2U","Orion","推理"] 场景标签
    model_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)     # → l6.server_models
    base_config_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bom_template_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chassis_signals: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict) # {psu_wattage,psu_qty,bp_type}
    kp_lines: Mapped[Optional[list]] = mapped_column(JSONB, default=list)        # [{part_id, qty}] 引用 kp_parts
    l6_rows: Mapped[Optional[list]] = mapped_column(JSONB, default=list)        # L6 配置单快照 [{catalogue,description,qty}]（保存时固化，案例自包含）
    price_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, default=dict)  # {cost,sales,marginPct} 快照
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)                # 说明
    requirement: Mapped[Optional[str]] = mapped_column(Text, nullable=True)            # 原始需求（原始需求 → BOM单）
    l6_config_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)         # 技术员报价单 L6 Configuration Description 原文（机箱能力声明，重放/校验用）
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)    # 编辑 +1，golden 指纹引用
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    created_by: Mapped[str] = mapped_column(String, nullable=False, default="system")
    updated_by: Mapped[str] = mapped_column(String, nullable=False, default="system")
