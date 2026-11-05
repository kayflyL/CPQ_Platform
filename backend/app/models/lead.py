"""线索池模型 — 公开渠道汇聚的线索（规格 = docs/prototypes/线索池工作台-原型.html）。

Table: opportunities.opportunity_leads
状态机：new → confirmed → (converting 瞬态) → assigned；确认前可 → rejected。
config_slots 与商机线索登记表 RequirementSlots 同构，转化时原样生成需求草稿。
ai_* 字段为二期 AI 初筛预留（llm_client 结构化评分），一期不读写。
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

LEAD_OPEN_STATUSES = ("new", "confirmed")  # 未结：可被同手机号新提交并入


def generate_lead_id() -> str:
    return f"LEAD-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"


class OpportunityLead(Base):
    __tablename__ = "opportunity_leads"
    __table_args__ = {"schema": "opportunities"}

    lead_id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, default="catalog_general")  # catalog_model / catalog_general
    status: Mapped[str] = mapped_column(String, default="new")

    company: Mapped[str] = mapped_column(String, default="")
    contact_name: Mapped[str] = mapped_column(String, default="")
    contact_phone: Mapped[str] = mapped_column(String, default="")
    contact_email: Mapped[str] = mapped_column(String, default="")
    # 交付地区（中转列，与商机权威字段 opportunities.extra_fields.delivery_region 同名同义；
    # 转化时原样写入商机，统计口径不分裂。取值形如 国内-广东 / 海外-日本 / 海外-不在列表中）
    delivery_region: Mapped[str] = mapped_column(String, default="")

    requirement_text: Mapped[str] = mapped_column(Text, default="")
    # RequirementSlots 同构（configs[]/config_relation/purchase_qty/…）； None=客户没填配置区
    config_slots: Mapped[Optional[dict]] = mapped_column(Text, default=None)
    expected_delivery: Mapped[str] = mapped_column(String, default="")
    attachments: Mapped[Optional[str]] = mapped_column(Text, default=None)  # JSON [{storage_key,name,size}]

    # —— 二期 AI 初筛预留（一期不读写）——
    ai_grade: Mapped[Optional[str]] = mapped_column(String, default=None)
    ai_scores: Mapped[Optional[str]] = mapped_column(Text, default=None)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text, default=None)
    ai_flags: Mapped[Optional[str]] = mapped_column(Text, default=None)
    ai_screened_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    dedup_count: Mapped[int] = mapped_column(Integer, default=1)
    reject_reason: Mapped[str] = mapped_column(String, default="")
    reject_note: Mapped[str] = mapped_column(String, default="")
    converted_opportunity_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    assigned_business_user_id: Mapped[Optional[str]] = mapped_column(String, default=None)

    client_ip: Mapped[str] = mapped_column(String, default="")
    user_agent: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[str] = mapped_column(String)
    updated_at: Mapped[str] = mapped_column(String)

    def to_dict(self) -> dict:
        import json
        def _loads(v):
            if v is None or v == "":
                return None
            try:
                return json.loads(v)
            except (TypeError, ValueError):
                return None
        return {
            "lead_id": self.lead_id,
            "source": self.source or "",
            "status": self.status or "",
            "company": self.company or "",
            "contact_name": self.contact_name or "",
            "contact_phone": self.contact_phone or "",
            "contact_email": self.contact_email or "",
            "delivery_region": self.delivery_region or "",
            "requirement_text": self.requirement_text or "",
            "config_slots": _loads(self.config_slots),
            "expected_delivery": self.expected_delivery or "",
            "attachments": _loads(self.attachments) or [],
            "ai_grade": self.ai_grade,
            "dedup_count": self.dedup_count or 1,
            "reject_reason": self.reject_reason or "",
            "reject_note": self.reject_note or "",
            "converted_opportunity_id": self.converted_opportunity_id or "",
            "assigned_business_user_id": self.assigned_business_user_id or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }
