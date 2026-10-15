"""报价外发审批单模型 — 外发审批门（M1）的持久层。

Table: opportunities.opportunity_pricing_approvals
报价单外发（客户版导出冻结 / 平台内发送 / 规格书 PDF）须持有效审批：
批准 = 对 content_hash 对应内容的「外发许可」，之后改价 hash 失配自动失效重批。
责任总监由调度面板 approval 节点规则按业务路由（assigned_to）；规则未命中 = 广播降级。
每次外发最多一张 pending 单；rejected 后再发起会新建单（不复用，审计留痕）。
"""
from typing import Optional
from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base


class OpportunityPricingApproval(Base):
    __tablename__ = "opportunity_pricing_approvals"
    __table_args__ = {"schema": "opportunities"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    quotation_id: Mapped[str] = mapped_column(String, index=True)
    margin_pct: Mapped[float] = mapped_column(Float)
    threshold: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|approved|rejected
    requested_by: Mapped[str] = mapped_column(String, default="")
    decided_by: Mapped[Optional[str]] = mapped_column(String, default=None)
    decided_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    comment: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[str] = mapped_column(String)
    # ── M1 外发审批门扩展 ──
    # low_margin=低于红线 | outbound=常规外发（都须批，前者审批卡多一条警示）
    trigger_reason: Mapped[Optional[str]] = mapped_column(String, default="outbound")
    # 内容指纹（报价行+单头关键值 sha256 前 16 位）：批准绑定内容，改价即失效
    content_hash: Mapped[Optional[str]] = mapped_column(String, default=None)
    # 责任总监（调度面板 approval 规则路由结果；空=广播降级）
    assigned_to: Mapped[Optional[str]] = mapped_column(String, default=None)
    assigned_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    # 路由快照 JSON：命中规则/兜底/广播 + 当时依据
    route_snapshot: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # 发起人提交的审批说明
    request_note: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # 转交链 JSON：[{at, from_name, to_name, by, reason}]
    transfers: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # 系统超时提醒时间（超过 remind_hours 未批时推送一次）/ 提交人最近催办时间
    escalated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    reminded_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "quotation_id": self.quotation_id,
            "margin_pct": self.margin_pct,
            "threshold": self.threshold,
            "status": self.status,
            "requested_by": self.requested_by,
            "decided_by": self.decided_by or "",
            "decided_at": self.decided_at or "",
            "comment": self.comment or "",
            "created_at": self.created_at or "",
            "trigger_reason": self.trigger_reason or "outbound",
            "content_hash": self.content_hash or "",
            "assigned_to": self.assigned_to or "",
            "assigned_name": self.assigned_name or "",
            "route_snapshot": self.route_snapshot or "",
            "request_note": self.request_note or "",
            "transfers": self.transfers or "",
            "escalated_at": self.escalated_at or "",
            "reminded_at": self.reminded_at or "",
        }
