"""一次性把现有需求/BOM/成本/报价数据回填为卡片路由。

老数据没有来源需求字段，因此 BOM/成本/报价各自成卡；已有成本表会优先挂到对应 BOM 卡，
已有报价单会优先挂到对应成本卡。新流程不会再依赖本脚本。
"""
from datetime import datetime

from app.models.base import Opportunity_SessionLocal
from app.models.flow import (
    OpportunityFlowCard,
    OpportunityFlowCardLink,
    OpportunityRequirement,
    OpportunityBomScheme,
    OpportunityCostSheet,
)
from app.models.quotation import Quotation


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    db = Opportunity_SessionLocal()
    try:
        cards_by_entity = {}

        def existing_card_id(entity_type, entity_id, opportunity_id):
            link = db.query(OpportunityFlowCardLink).filter(
                OpportunityFlowCardLink.opportunity_id == opportunity_id,
                OpportunityFlowCardLink.entity_type == entity_type,
                OpportunityFlowCardLink.entity_id == str(entity_id),
            ).first()
            return link.flow_card_id if link else None

        reqs = db.query(OpportunityRequirement).order_by(OpportunityRequirement.version.asc()).all()
        for req in reqs:
            req_card_id = existing_card_id("requirement", req.version, req.opportunity_id)
            if req_card_id:
                cards_by_entity[("requirement", req.version)] = req_card_id
                continue
            card = OpportunityFlowCard(
                opportunity_id=req.opportunity_id,
                origin_node="requirement",
                current_node="boming" if req.status == "current" else "requirement",
                flow_status="submitted" if req.status == "current" else "draft",
                assignee_name=None,
                visible_upstream=True,
                created_by=req.created_by or "",
                created_at=req.created_at or now(),
                updated_at=now(),
            )
            db.add(card)
            db.flush()
            db.add(OpportunityFlowCardLink(flow_card_id=card.id, opportunity_id=req.opportunity_id, entity_type="requirement", entity_id=str(req.version), created_at=now()))
            cards_by_entity[("requirement", req.version)] = card.id

        boms = db.query(OpportunityBomScheme).order_by(OpportunityBomScheme.id.asc()).all()
        for bom in boms:
            bom_card_id = existing_card_id("bom", bom.id, bom.opportunity_id)
            if bom_card_id:
                cards_by_entity[("bom", bom.id)] = bom_card_id
                continue
            card = OpportunityFlowCard(
                opportunity_id=bom.opportunity_id,
                origin_node="boming",
                current_node="costing" if bom.status == "current" else "boming",
                flow_status="submitted" if bom.status == "current" else "draft",
                assignee_name=None,
                visible_upstream=False,
                created_by=bom.created_by or "",
                created_at=bom.created_at or now(),
                updated_at=now(),
            )
            db.add(card)
            db.flush()
            db.add(OpportunityFlowCardLink(flow_card_id=card.id, opportunity_id=bom.opportunity_id, entity_type="bom", entity_id=str(bom.id), created_at=now()))
            cards_by_entity[("bom", bom.id)] = card.id

        costs = db.query(OpportunityCostSheet).order_by(OpportunityCostSheet.id.asc()).all()
        for cost in costs:
            cost_card_id = existing_card_id("cost", cost.id, cost.opportunity_id)
            if cost_card_id:
                cards_by_entity[("cost", cost.id)] = cost_card_id
                continue
            card_id = cards_by_entity.get(("bom", cost.bom_scheme_id)) if cost.bom_scheme_id else None
            if not card_id:
                card = OpportunityFlowCard(
                    opportunity_id=cost.opportunity_id,
                    origin_node="costing",
                    current_node="quoting" if cost.status == "current" else "costing",
                    flow_status="submitted" if cost.status == "current" else "draft",
                    assignee_name=None,
                    visible_upstream=False,
                    created_by=cost.created_by or "",
                    created_at=cost.created_at or now(),
                    updated_at=now(),
                )
                db.add(card)
                db.flush()
                card_id = card.id
            db.add(OpportunityFlowCardLink(flow_card_id=card_id, opportunity_id=cost.opportunity_id, entity_type="cost", entity_id=str(cost.id), created_at=now()))
            cards_by_entity[("cost", cost.id)] = card_id

        quotes = db.query(Quotation).order_by(Quotation.created_at.asc()).all()
        for quote in quotes:
            quote_card_id = existing_card_id("quote", quote.quotation_id, quote.opportunity_id)
            if quote_card_id:
                continue
            linked_cost = db.query(OpportunityCostSheet).filter(
                OpportunityCostSheet.quotation_id == quote.quotation_id
            ).first()
            card_id = cards_by_entity.get(("cost", linked_cost.id)) if linked_cost else None
            if not card_id:
                card = OpportunityFlowCard(
                    opportunity_id=quote.opportunity_id,
                    origin_node="quoting",
                    current_node="quoting",
                    flow_status="completed" if quote.submitted_at else "draft",
                    assignee_name=None,
                    visible_upstream=False,
                    created_by=quote.submitted_by or "",
                    created_at=quote.created_at or now(),
                    updated_at=now(),
                )
                db.add(card)
                db.flush()
                card_id = card.id
            db.add(OpportunityFlowCardLink(flow_card_id=card_id, opportunity_id=quote.opportunity_id, entity_type="quote", entity_id=quote.quotation_id, created_at=now()))

        db.commit()
        print("backfill complete")
    finally:
        db.close()


if __name__ == "__main__":
    main()
