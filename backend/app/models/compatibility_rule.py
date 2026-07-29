"""Compatibility rule models — 兼容性规则引擎（schema=rules）。

声明式 WHEN(条件)→THEN(动作) 规则，跨 KP 配件库 / 料号库 / 基准机箱 / 商机维度求值。
收敛原 Strategy.selection（X6 图）+ validateSelection + derivation_rules 三套零散实现。

type（大分类，驱动编辑器分 tab + 执行器路由）：
- require ：必配/依赖（选 GPU → 配 GPU 线缆）
- exclude ：互斥（同型号不混搭）
- derive  ：派生项+数量（每 8 个 SATA 盘 → 1 根线缆）
- filter  ：过滤候选（商机 Polaris → 只出 Polaris 机型）
- recommend：推荐标注

body = {when:{all/any:[{field,op,value}]}, then:{action,...}, desc}
hit_count 内联（高频读展示），不走日志表。
"""
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class CompatibilityRule(Base):
    __tablename__ = "compatibility_rules"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(20), nullable=False, default="selection", index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # require/exclude/derive/filter/recommend
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(Text, default=None)        # JSON 生效范围（series/platform_type）
    body: Mapped[str] = mapped_column(Text, nullable=False)                 # JSON: {when, then, desc}
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
