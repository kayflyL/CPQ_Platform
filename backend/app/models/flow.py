"""协作报价流程模型 — opportunities schema（审批流：需求→指派→配BOM→核价→报价）。

- OpportunityFlow：一商机一流程（current_node 推进 + 各节点指派人）。
- OpportunityFlowNode：时间线节点记录（需求版本提交/指派/完成/退回都追加一行）。
- OpportunityRequirement：需求单版本（RequirementSlots JSON，旧版 status=archived
  留档，业务改需求生成新版本流程重跑）。
"""
from typing import Optional
from sqlalchemy import String, Text, JSON, Integer, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base

# 流程节点顺序（时间线渲染顺序；current_node 取值域）
FLOW_NODE_KEYS = ["requirement", "assign", "boming", "costing", "quoting"]


class OpportunityFlow(Base):
    __tablename__ = "opportunity_flows"
    __table_args__ = {"schema": "opportunities"}

    flow_id: Mapped[str] = mapped_column(String, primary_key=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    # 当前节点：requirement / assign / boming / costing / quoting
    current_node: Mapped[str] = mapped_column(String, default="requirement")
    # running=流转中 done=报价定稿 returned=被退回（业务改需求后重提回 requirement）
    status: Mapped[str] = mapped_column(String, default="running")
    # 各节点指派人 {node_key: user_name}
    assignees: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "flow_id": self.flow_id,
            "opportunity_id": self.opportunity_id,
            "current_node": self.current_node or "requirement",
            "status": self.status or "running",
            "assignees": self.assignees or {},
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }


class FlowAssignmentRule(Base):
    """业务账号 × 流程节点的默认处理人规则（任务调度页维护）。"""
    __tablename__ = "flow_assignment_rules"
    __table_args__ = (
        UniqueConstraint("business_user_id", "node_key", name="uq_flow_assignment_rule_biz_node"),
        {"schema": "opportunities"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_user_id: Mapped[str] = mapped_column(String, index=True)
    node_key: Mapped[str] = mapped_column(String)  # boming / costing / quoting
    assignee_name: Mapped[str] = mapped_column(String)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "business_user_id": self.business_user_id,
            "node_key": self.node_key,
            "assignee_name": self.assignee_name or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }


class OpportunityFlowNode(Base):
    __tablename__ = "opportunity_flow_nodes"
    __table_args__ = {"schema": "opportunities"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_id: Mapped[str] = mapped_column(String, index=True)
    node_key: Mapped[str] = mapped_column(String)          # FLOW_NODE_KEYS 之一
    node_label: Mapped[Optional[str]] = mapped_column(String, default=None)
    version_tag: Mapped[Optional[str]] = mapped_column(String, default=None)  # 需求节点带 v1/v2…
    actor: Mapped[Optional[str]] = mapped_column(String, default=None)
    # submit=提交需求 / assign=指派 / complete=节点完成 / return=退回
    action: Mapped[str] = mapped_column(String, default="submit")
    comment: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # 节点交付物（BOM/成本/报价单引用；business 角色由 API 层按权限裁剪）
    artifacts: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "flow_id": self.flow_id,
            "node_key": self.node_key,
            "node_label": self.node_label or "",
            "version_tag": self.version_tag or "",
            "actor": self.actor or "",
            "action": self.action or "",
            "comment": self.comment or "",
            "artifacts": self.artifacts or {},
            "created_at": self.created_at or "",
        }


class OpportunityRequirement(Base):
    __tablename__ = "opportunity_requirements"
    __table_args__ = {"schema": "opportunities"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)          # v1/v2/v3…，商机内自增
    # RequirementSlots 契约 JSON（LLM_UNDERSTAND_SCHEMA 同构，后端可直接消费）
    slots: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    requirement_text: Mapped[Optional[str]] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String, default="current")  # draft / current / archived
    created_by: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "version": self.version,
            "slots": self.slots or {},
            "requirement_text": self.requirement_text or "",
            "status": self.status or "current",
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
        }


class OpportunityBomScheme(Base):
    """一个 BOM 方案 = 一张方案卡片。

    方案内部可以有多个配置页签（CFG1/CFG2…），页签不是方案。同一商机同一时刻最多
    一个 current 方案；其余为 draft（可继续编辑）或 archived（历史留档）。
    """
    __tablename__ = "opportunity_bom_schemes"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "name", name="uq_opportunity_bom_scheme_name"),
        {"schema": "opportunities"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft / current / archived
    configs: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    created_by: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "name": self.name or "",
            "status": self.status or "draft",
            "configs": self.configs or [],
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }


class OpportunityCostSheet(Base):
    """一张成本核算卡片，对应一个已提交的 BOM 方案。"""
    __tablename__ = "opportunity_cost_sheets"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "name", name="uq_opportunity_cost_sheet_name"),
        {"schema": "opportunities"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    bom_scheme_id: Mapped[Optional[int]] = mapped_column(Integer, default=None)
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="draft")  # draft / current / archived
    configs: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    quotation_id: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_by: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "bom_scheme_id": self.bom_scheme_id,
            "name": self.name or "",
            "status": self.status or "draft",
            "configs": self.configs or [],
            "quotation_id": self.quotation_id or "",
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }


class OpportunityFlowCard(Base):
    """卡片化流程路由：一张卡就是一条流转线，携带各节点业务实体映射。"""
    __tablename__ = "opportunity_flow_cards"
    __table_args__ = {"schema": "opportunities"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    origin_node: Mapped[str] = mapped_column(String, default="requirement")  # 卡在哪一个节点发起
    current_node: Mapped[str] = mapped_column(String, default="requirement")
    flow_status: Mapped[str] = mapped_column(String, default="draft")  # draft/submitted/processing/returned/completed/withdraw_requested/withdrawn
    assignee_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    visible_upstream: Mapped[Optional[bool]] = mapped_column(Boolean, default=True)
    withdraw_status: Mapped[Optional[str]] = mapped_column(String, default=None)
    withdraw_reason: Mapped[Optional[str]] = mapped_column(Text, default=None)
    withdraw_requested_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    returned_from_node: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_by: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "opportunity_id": self.opportunity_id,
            "origin_node": self.origin_node,
            "current_node": self.current_node,
            "flow_status": self.flow_status,
            "assignee_name": self.assignee_name or "",
            "visible_upstream": bool(self.visible_upstream),
            "withdraw_status": self.withdraw_status or "",
            "withdraw_reason": self.withdraw_reason or "",
            "withdraw_requested_at": self.withdraw_requested_at or "",
            "returned_from_node": self.returned_from_node or "",
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }


class OpportunityFlowCardLink(Base):
    """卡片与业务实体映射：requirement / bom / cost / quote 各自记录挂到同一张卡。"""
    __tablename__ = "opportunity_flow_card_links"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "entity_type", "entity_id", name="uq_opportunity_flow_card_entity"),
        {"schema": "opportunities"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_card_id: Mapped[int] = mapped_column(Integer, index=True)
    opportunity_id: Mapped[str] = mapped_column(String, index=True)
    entity_type: Mapped[str] = mapped_column(String)  # requirement / bom / cost / quote
    entity_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "flow_card_id": self.flow_card_id,
            "opportunity_id": self.opportunity_id,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "created_at": self.created_at or "",
        }
