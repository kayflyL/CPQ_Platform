"""卡片化流程路由仓库：一张卡一条流转线，卡片状态与业务实体解耦。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import or_

from app.models.base import Opportunity_SessionLocal
from app.models.flow import (
    OpportunityFlowCard,
    OpportunityFlowCardLink,
    OpportunityBomScheme,
    OpportunityCostSheet,
)
from app.models.feed_message import FeedMessage
from app.models.feed_attachment import FeedAttachment


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FlowCardRepository:
    def __init__(self):
        self._session = None

    @property
    def session(self):
        if self._session is None:
            self._session = Opportunity_SessionLocal()
        return self._session

    def close(self):
        if self._session:
            self._session.close()

    def list_cards(self, opportunity_id: str) -> list[dict]:
        rows = (
            self.session.query(OpportunityFlowCard)
            .filter(OpportunityFlowCard.opportunity_id == opportunity_id)
            .order_by(OpportunityFlowCard.id.desc())
            .all()
        )
        cards = []
        for row in rows:
            d = row.to_dict()
            d["entities"] = self._entities_for_card(row.id)
            cards.append(d)
        return cards

    def get_card(self, card_id: int) -> Optional[dict]:
        row = self.session.query(OpportunityFlowCard).filter(OpportunityFlowCard.id == card_id).first()
        if not row:
            return None
        d = row.to_dict()
        d["entities"] = self._entities_for_card(row.id)
        return d

    def get_card_for_entity(self, opportunity_id: str, entity_type: str, entity_id) -> Optional[dict]:
        link = self.session.query(OpportunityFlowCardLink).filter(
            OpportunityFlowCardLink.opportunity_id == opportunity_id,
            OpportunityFlowCardLink.entity_type == entity_type,
            OpportunityFlowCardLink.entity_id == str(entity_id),
        ).first()
        if not link:
            return None
        return self.get_card(link.flow_card_id)

    def ensure_card(self, opportunity_id: str, origin_node: str, current_node: str,
                    created_by: str = "", assignee_name: str = None,
                    visible_upstream: bool = True, flow_status: str = "draft") -> dict:
        row = OpportunityFlowCard(
            opportunity_id=opportunity_id,
            origin_node=origin_node,
            current_node=current_node,
            flow_status=flow_status,
            assignee_name=assignee_name,
            visible_upstream=visible_upstream,
            created_by=created_by,
            created_at=_now(),
            updated_at=_now(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def link_entity(self, card_id: int, entity_type: str, entity_id,
                    opportunity_id: Optional[str] = None) -> dict:
        entity_id = str(entity_id)
        link = self.session.query(OpportunityFlowCardLink).filter(
            OpportunityFlowCardLink.opportunity_id == opportunity_id,
            OpportunityFlowCardLink.entity_type == entity_type,
            OpportunityFlowCardLink.entity_id == entity_id,
        ).first()
        if link:
            if link.flow_card_id != card_id:
                raise ValueError("该业务记录已挂到其他流转卡")
            return link.to_dict()
        link = OpportunityFlowCardLink(
            flow_card_id=card_id,
            opportunity_id=opportunity_id or "",
            entity_type=entity_type,
            entity_id=entity_id,
            created_at=_now(),
        )
        self.session.add(link)
        self.session.commit()
        self.session.refresh(link)
        return link.to_dict()

    def unlink_entity(self, card_id: int, entity_type: str, entity_id,
                      opportunity_id: Optional[str] = None) -> bool:
        link = self.session.query(OpportunityFlowCardLink).filter(
            OpportunityFlowCardLink.flow_card_id == card_id,
            OpportunityFlowCardLink.opportunity_id == opportunity_id,
            OpportunityFlowCardLink.entity_type == entity_type,
            OpportunityFlowCardLink.entity_id == str(entity_id),
        ).first()
        if not link:
            return False
        self.session.delete(link)
        self.session.commit()
        return True

    def delete_card_if_empty(self, card_id: int) -> bool:
        remaining = self.session.query(OpportunityFlowCardLink).filter(
            OpportunityFlowCardLink.flow_card_id == card_id
        ).count()
        if remaining:
            return False
        row = self.session.query(OpportunityFlowCard).filter(OpportunityFlowCard.id == card_id).first()
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def update_card(self, card_id: int, **fields) -> Optional[dict]:
        row = self.session.query(OpportunityFlowCard).filter(OpportunityFlowCard.id == card_id).first()
        if not row:
            return None
        for key, value in fields.items():
            if hasattr(row, key):
                setattr(row, key, value)
        row.updated_at = _now()
        self.session.commit()
        self.session.refresh(row)
        d = row.to_dict()
        d["entities"] = self._entities_for_card(row.id)
        return d

    def return_card(self, card_id: int, target_node: str,
                    actor: str = "", reason: str = "") -> Optional[dict]:
        card = self.get_card(card_id)
        if not card:
            return None
        return self.update_card(
            card_id,
            current_node=target_node,
            flow_status="returned",
            returned_from_node=card.get("current_node"),
            withdraw_status=None,
            withdraw_reason=(reason or "").strip() or None,
        )

    def revert_card_deliverables(self, card_id: int, from_node: str) -> None:
        """退回/撤回时把已生成的下游交付物回退到可编辑状态。"""
        links = self.session.query(OpportunityFlowCardLink).filter(
            OpportunityFlowCardLink.flow_card_id == card_id
        ).all()
        bom_ids = [int(l.entity_id) for l in links if l.entity_type == "bom"]
        cost_ids = [int(l.entity_id) for l in links if l.entity_type == "cost"]

        if from_node == "boming":
            for bom_id in bom_ids:
                row = self.session.query(OpportunityBomScheme).filter(OpportunityBomScheme.id == bom_id).first()
                if row:
                    row.status = "archived"
                    row.updated_at = _now()
        elif from_node == "costing":
            for bom_id in bom_ids:
                row = self.session.query(OpportunityBomScheme).filter(OpportunityBomScheme.id == bom_id).first()
                if row:
                    row.status = "draft"
                    row.updated_at = _now()
            for cost_id in cost_ids:
                row = self.session.query(OpportunityCostSheet).filter(OpportunityCostSheet.id == cost_id).first()
                if row:
                    row.status = "archived"
                    row.updated_at = _now()
        elif from_node == "quoting":
            for cost_id in cost_ids:
                row = self.session.query(OpportunityCostSheet).filter(OpportunityCostSheet.id == cost_id).first()
                if row:
                    row.status = "draft"
                    row.updated_at = _now()

        self.session.commit()

    def claim_card(self, card_id: int, assignee_name: str) -> Optional[dict]:
        affected = (
            self.session.query(OpportunityFlowCard)
            .filter(
                OpportunityFlowCard.id == card_id,
                or_(
                    OpportunityFlowCard.assignee_name.is_(None),
                    OpportunityFlowCard.assignee_name == "",
                    OpportunityFlowCard.assignee_name == assignee_name,
                ),
            )
            .update(
                {
                    OpportunityFlowCard.assignee_name: assignee_name,
                    OpportunityFlowCard.flow_status: "processing",
                    OpportunityFlowCard.updated_at: _now(),
                },
                synchronize_session=False,
            )
        )
        if not affected:
            card = self.get_card(card_id)
            if not card:
                return None
            if card.get("assignee_name") and card.get("assignee_name") != assignee_name:
                raise ValueError("该卡已指定其他处理人")
            raise ValueError("认领失败，请刷新后重试")
        self.session.commit()
        self.session.expire_all()
        return self.get_card(card_id)

    def request_withdraw(self, card_id: int, reason: str = "") -> Optional[dict]:
        card = self.get_card(card_id)
        if not card:
            return None
        if card.get("flow_status") != "submitted":
            raise ValueError("仅已提交到下游的卡可申请撤回")
        downstream_entity = {
            "requirement": "bom",
            "boming": "cost",
            "costing": "quote",
        }.get(card.get("current_node") or "")
        if downstream_entity:
            downstream_link = self.session.query(OpportunityFlowCardLink).filter(
                OpportunityFlowCardLink.flow_card_id == card_id,
                OpportunityFlowCardLink.entity_type == downstream_entity,
            ).first()
            if downstream_link:
                raise ValueError("下游已保存或处理该卡，无法撤回")
        comment_count = self.session.query(FeedMessage).filter(
            FeedMessage.flow_card_id == card_id,
            FeedMessage.kind == "comment",
            FeedMessage.deleted_at.is_(None),
        ).count()
        attachment_count = self.session.query(FeedAttachment).filter(
            FeedAttachment.flow_card_id == card_id,
            FeedAttachment.deleted_at.is_(None),
        ).count()
        if comment_count or attachment_count:
            raise ValueError("下游已评论或上传附件，无法撤回")
        return self.update_card(
            card_id,
            withdraw_status="requested",
            withdraw_reason=(reason or "").strip() or None,
            withdraw_requested_at=_now(),
        )

    def approve_withdraw(self, card_id: int, target_node: str) -> Optional[dict]:
        card = self.get_card(card_id)
        if not card:
            return None
        if card.get("withdraw_status") != "requested":
            raise ValueError("该卡没有待处理的撤回申请")
        return self.update_card(
            card_id,
            current_node=target_node,
            flow_status="withdrawn",
            withdraw_status="approved",
            returned_from_node=card.get("current_node"),
        )

    def reject_withdraw(self, card_id: int, reason: str = "") -> Optional[dict]:
        card = self.get_card(card_id)
        if not card:
            return None
        if card.get("withdraw_status") != "requested":
            raise ValueError("该卡没有待处理的撤回申请")
        return self.update_card(
            card_id,
            withdraw_status="rejected",
            withdraw_reason=(reason or "").strip() or card.get("withdraw_reason") or "",
        )

    def _entities_for_card(self, card_id: int) -> list[dict]:
        links = self.session.query(OpportunityFlowCardLink).filter(
            OpportunityFlowCardLink.flow_card_id == card_id
        ).order_by(OpportunityFlowCardLink.id.asc()).all()
        return [link.to_dict() for link in links]
