"""线索池仓库 — opportunities.opportunity_leads 的全部读写。

会话与 OpportunityRepository 同池（Opportunity_SessionLocal）；公开端点的目录读走
public_read_repo（受限只读连接），与本仓库互不交叉。
"""
import json
from datetime import datetime
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.base import Opportunity_SessionLocal
from app.models.lead import LEAD_OPEN_STATUSES, OpportunityLead, generate_lead_id
from app.repository.feed_user_repo import FeedUserRepository


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _dumps(v) -> Optional[str]:
    if v is None:
        return None
    return json.dumps(v, ensure_ascii=False)


class LeadRepository:
    def __init__(self):
        self._session: Optional[Session] = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Opportunity_SessionLocal()
        return self._session

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None

    # —— 写入 / 去重 ——

    def insert(self, lead: dict) -> str:
        row = OpportunityLead(
            lead_id=lead.get("lead_id") or generate_lead_id(),
            source=lead.get("source") or "catalog_general",
            status="new",
            company=(lead.get("company") or "").strip(),
            contact_name=(lead.get("contact_name") or "").strip(),
            contact_phone=(lead.get("contact_phone") or "").strip(),
            contact_email=(lead.get("contact_email") or "").strip(),
            delivery_region=(lead.get("delivery_region") or "").strip(),
            requirement_text=(lead.get("requirement_text") or "").strip(),
            config_slots=_dumps(lead.get("config_slots")),
            expected_delivery=(lead.get("expected_delivery") or "").strip(),
            attachments=_dumps(lead.get("attachments")),
            client_ip=(lead.get("client_ip") or "").strip(),
            user_agent=(lead.get("user_agent") or "").strip(),
            created_at=_now(),
            updated_at=_now(),
        )
        self.session.add(row)
        self.session.commit()
        return row.lead_id

    def find_open_by_phone(self, phone: str) -> Optional[dict]:
        row = (
            self.session.query(OpportunityLead)
            .filter(
                OpportunityLead.contact_phone == phone,
                OpportunityLead.status.in_(LEAD_OPEN_STATUSES),
            )
            .order_by(OpportunityLead.created_at.desc())
            .first()
        )
        return row.to_dict() if row else None

    def merge_submission(self, lead_id: str, requirement_text: str, attachments_append: Optional[list] = None,
                         config_slots: Optional[dict] = None, expected_delivery: str = "",
                         delivery_region: str = "") -> None:
        """同手机号重复提交并入：追加需求原文（capped）、并附件、补空槽位，dedup_count +1。"""
        row = self.session.query(OpportunityLead).filter(OpportunityLead.lead_id == lead_id).first()
        if row is None:
            return
        if requirement_text:
            existing = row.requirement_text or ""
            merged = (existing + "\n---\n" + requirement_text.strip())[:4000]
            row.requirement_text = merged
        if attachments_append:
            current = []
            if row.attachments:
                try:
                    current = json.loads(row.attachments)
                except (TypeError, ValueError):
                    current = []
            row.attachments = json.dumps((current + attachments_append)[:5], ensure_ascii=False)
        if config_slots and not row.config_slots:
            row.config_slots = _dumps(config_slots)
        if expected_delivery and not row.expected_delivery:
            row.expected_delivery = expected_delivery.strip()
        if delivery_region and not row.delivery_region:
            row.delivery_region = delivery_region.strip()
        row.dedup_count = (row.dedup_count or 1) + 1
        row.updated_at = _now()
        self.session.commit()

    # —— 读取 ——

    def get(self, lead_id: str) -> Optional[dict]:
        row = self.session.query(OpportunityLead).filter(OpportunityLead.lead_id == lead_id).first()
        return row.to_dict() if row else None

    def list_leads(self, status: str = "", search: str = "", page: int = 1, page_size: int = 20) -> dict:
        q = self.session.query(OpportunityLead)
        if status:
            q = q.filter(OpportunityLead.status == status)   # status='deleted' 即回收站视图
        else:
            q = q.filter(OpportunityLead.status != "deleted")  # 默认视图不含回收站
        if search:
            like = f"%{search.strip()}%"
            q = q.filter(or_(
                OpportunityLead.company.ilike(like),
                OpportunityLead.contact_name.ilike(like),
                OpportunityLead.contact_phone.ilike(like),
                OpportunityLead.requirement_text.ilike(like),
            ))
        total = q.count()
        rows = (
            q.order_by(OpportunityLead.created_at.desc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
            .all()
        )
        return {"items": [r.to_dict() for r in rows], "total": total, "page": page, "page_size": page_size}

    # —— 状态推进 ——

    def mark_confirmed(self, lead_id: str) -> Optional[str]:
        """new → confirmed（幂等：已 confirmed 直返）。返回最终状态，非法流转返回 None。"""
        row = self.session.query(OpportunityLead).filter(OpportunityLead.lead_id == lead_id).first()
        if row is None:
            return None
        if row.status == "confirmed":
            return row.status
        if row.status != "new":
            return None
        row.status = "confirmed"
        row.updated_at = _now()
        self.session.commit()
        return row.status

    def mark_rejected(self, lead_id: str, reason: str, note: str) -> bool:
        row = self.session.query(OpportunityLead).filter(OpportunityLead.lead_id == lead_id).first()
        if row is None or row.status not in ("new", "confirmed"):
            return False
        row.status = "rejected"
        row.reject_reason = reason
        row.reject_note = (note or "").strip()
        row.updated_at = _now()
        self.session.commit()
        return True

    def mark_deleted(self, lead_id: str) -> bool:
        """软删除（回收站语义）：仅未转化线索可删；已转化背着商机溯源，删了断链。"""
        row = self.session.query(OpportunityLead).filter(OpportunityLead.lead_id == lead_id).first()
        if row is None or row.status not in ("new", "confirmed", "rejected"):
            return False
        row.status = "deleted"
        row.updated_at = _now()
        self.session.commit()
        return True

    def restore_deleted(self, lead_id: str) -> bool:
        """从回收站恢复：回到待处理（new），重新进入专人筛选。"""
        row = self.session.query(OpportunityLead).filter(OpportunityLead.lead_id == lead_id).first()
        if row is None or row.status != "deleted":
            return False
        row.status = "new"
        row.updated_at = _now()
        self.session.commit()
        return True

    def try_mark_converting(self, lead_id: str) -> bool:
        """原子抢占（防并发转化）：仅 new/confirmed 可进入 converting。"""
        updated = (
            self.session.query(OpportunityLead)
            .filter(
                OpportunityLead.lead_id == lead_id,
                OpportunityLead.status.in_(LEAD_OPEN_STATUSES),
            )
            .update({"status": "converting", "updated_at": _now()}, synchronize_session=False)
        )
        self.session.commit()
        return updated == 1

    def finalize_converted(self, lead_id: str, opportunity_id: str, business_user_id: str) -> None:
        self.session.query(OpportunityLead).filter(OpportunityLead.lead_id == lead_id).update(
            {
                "status": "assigned",
                "converted_opportunity_id": opportunity_id,
                "assigned_business_user_id": business_user_id,
                "updated_at": _now(),
            },
            synchronize_session=False,
        )
        self.session.commit()

    def restore_from_converting(self, lead_id: str) -> None:
        """转化中途失败：converting → new（人工重新确认）。"""
        self.session.query(OpportunityLead).filter(
            OpportunityLead.lead_id == lead_id, OpportunityLead.status == "converting"
        ).update({"status": "new", "updated_at": _now()}, synchronize_session=False)
        self.session.commit()

    def get_raw(self, lead_id: str) -> Optional[OpportunityLead]:
        return self.session.query(OpportunityLead).filter(OpportunityLead.lead_id == lead_id).first()

    # —— 业务下拉 ——

    def business_options(self) -> List[dict]:
        """启用中的业务角色账号（与 POST /opportunities 的归属逻辑同一口径）。"""
        repo = FeedUserRepository()
        try:
            items = [
                {"user_id": u["user_id"], "name": u["name"]}
                for u in repo.list_all()
                if u.get("role") == "business" and u.get("is_active", True)
            ]
            items.sort(key=lambda x: x["name"])
            return items
        finally:
            repo.close()
