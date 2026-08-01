"""Strategy models — 策略中心核心表（schema=rules）。

不塞进 rules.py 的 MatchingRule（那是 Excel 解析键值，会污染）；治理逻辑（审计/埋点）
照搬 BusinessField 那套模式但独立成表，语义清晰。

domain 五域：requirement(需求分析) / selection(选型配置) / pricing(报价毛利) / market(行业市场) / policy(策略文档)
type：域内类别，如 pricing.platform_baseline / selection.conflict / policy.document
scope：JSON 生效条件，起步单维 {platform_type:"Polaris"}（行业等数据积累后再扩）
body：JSON schema 化规则体（每类 type 各自定义结构）；policy.document 的 body = {category,sort_order,content_markdown}
status：draft/testing/active/archived 四态（只有 active 被业务引用）
"""
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class Strategy(Base):
    __tablename__ = "strategies"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[Optional[str]] = mapped_column(Text, default=None)        # JSON 生效条件
    body: Mapped[str] = mapped_column(Text, nullable=False)                 # JSON 规则体
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    change_reason: Mapped[Optional[str]] = mapped_column(Text, default=None)  # 异动原因留痕
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
            "change_reason": self.change_reason,
            "description": self.description,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }


class StrategyUsageLog(Base):
    """策略引用埋点 —— 谁在哪个商机/报价引用了哪条策略哪版。使用率统计的数据源。"""
    __tablename__ = "strategy_usage_log"
    __table_args__ = {"schema": "rules"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    strategy_version: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    ref_type: Mapped[Optional[str]] = mapped_column(String(20), default=None)  # opportunity/quotation/config
    ref_id: Mapped[Optional[str]] = mapped_column(String(60), default=None)
    operator: Mapped[str] = mapped_column(String, default="system")
    referenced_at: Mapped[Optional[str]] = mapped_column(String, default=None)
