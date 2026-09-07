"""协作流程 repository — opportunity_flows / opportunity_flow_nodes / opportunity_requirements。

会话绑 Opportunity_SessionLocal（opportunities schema，与商机/报价单同库）。
"""
from datetime import datetime
from typing import List, Optional
import uuid

from app.models.flow import (
    OpportunityFlow,
    OpportunityFlowNode,
    OpportunityRequirement,
    OpportunityBomScheme,
    OpportunityCostSheet,
    FlowAssignmentRule,
    FLOW_NODE_KEYS,
)
from app.models.base import Opportunity_SessionLocal

NODE_LABELS = {
    "requirement": "需求",
    "assign": "指派",
    "boming": "配 BOM",
    "costing": "核价",
    "quoting": "报价",
}

_FLOW_NODE_ORDER = {
    "requirement": 0,
    "assign": 1,
    "boming": 1,
    "costing": 2,
    "quoting": 3,
}


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class FlowRepository:
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

    # ── 流程 ──

    def get_or_create_flow(self, opportunity_id: str) -> OpportunityFlow:
        flow = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.opportunity_id == opportunity_id
        ).first()
        if not flow:
            flow = OpportunityFlow(
                flow_id=f"FLW-{uuid.uuid4().hex[:12]}",
                opportunity_id=opportunity_id,
                current_node="requirement",
                status="running",
                assignees={},
                created_at=_now(),
                updated_at=_now(),
            )
            self.session.add(flow)
            self.session.commit()
            self.session.refresh(flow)
        return flow

    def get_flow(self, opportunity_id: str) -> Optional[dict]:
        flow = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.opportunity_id == opportunity_id
        ).first()
        return flow.to_dict() if flow else None

    def _advance_after_requirement_submit(self, flow: OpportunityFlow) -> None:
        """需求提交后推进到 BOM；若流程已进入下游节点则不回退。"""
        current_node = (flow.current_node or "").strip()
        if current_node in {"requirement", "assign"} or not current_node:
            flow.current_node = "boming"
        flow.status = "running"
        flow.updated_at = _now()

    _OPPORTUNITY_CORE_COLUMNS = {
        "opportunity_id", "customer_name", "sales_person", "fae", "quotation_person",
        "industry", "order_type", "result",
        "created_at", "updated_at", "status", "extra_fields", "tenant_id",
    }

    def initiate_requirement(self, opportunity_id: str, opportunity_updates: dict,
                             slots: dict, requirement_text: str = "",
                             created_by: str = "") -> Optional[dict]:
        # 业务发起一步到位：商机信息 + 需求 vN 在同一事务提交；流程尚在需求/指派时推进到 BOM。
        from app.models.opportunity import Opportunity
        import json

        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if not opp:
            return None

        extra = {}
        if opp.extra_fields:
            try:
                extra = json.loads(opp.extra_fields)
            except (json.JSONDecodeError, TypeError):
                extra = {}

        for key, val in (opportunity_updates or {}).items():
            if key in self._OPPORTUNITY_CORE_COLUMNS:
                setattr(opp, key, val)
            else:
                extra[key] = val
        opp.extra_fields = json.dumps(extra, ensure_ascii=False) if extra else None
        opp.updated_at = _now()

        for old in self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.status == "current",
        ).all():
            old.status = "archived"

        latest = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id
        ).order_by(OpportunityRequirement.version.desc()).first()
        version = (latest.version + 1) if latest else 1

        row = OpportunityRequirement(
            opportunity_id=opportunity_id,
            version=version,
            slots=slots or {},
            requirement_text=requirement_text or "",
            status="current",
            created_by=created_by,
            created_at=_now(),
        )
        self.session.add(row)

        flow = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.opportunity_id == opportunity_id
        ).first()
        if not flow:
            flow = OpportunityFlow(
                flow_id=f"FLW-{uuid.uuid4().hex[:12]}",
                opportunity_id=opportunity_id,
                current_node="requirement",
                status="running",
                assignees={},
                created_at=_now(),
                updated_at=_now(),
            )
            self.session.add(flow)
        self._advance_after_requirement_submit(flow)

        self.session.commit()
        self.apply_default_assignments(flow.flow_id, opportunity_id)

        self.session.add(OpportunityFlowNode(
            flow_id=flow.flow_id,
            node_key="requirement",
            node_label=NODE_LABELS.get("requirement", "需求"),
            version_tag=f"v{version}",
            actor=created_by,
            action="submit",
            comment="",
            artifacts={"requirement_version": version},
            created_at=_now(),
        ))
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def list_task_flows(self, node_key: str, assignee_name: str = None,
                        include_unassigned: bool = False,
                        page: int = 1, page_size: int = 20) -> tuple[List[dict], int]:
        """当前节点任务流。按 assignees[node_key] 过滤；include_unassigned 时只取未指派。"""
        q = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.current_node == node_key
        )
        # 排除内部 AI 商机（status=ai_office）与软删商机（status=deleted）：不出现在工作台任务队列。
        from app.models.opportunity import Opportunity
        excluded_subq = self.session.query(Opportunity.opportunity_id).filter(
            Opportunity.status.in_(("ai_office", "deleted"))
        )
        q = q.filter(~OpportunityFlow.opportunity_id.in_(excluded_subq))
        rows = q.order_by(OpportunityFlow.updated_at.desc()).all()
        items = []
        for r in rows:
            d = r.to_dict()
            cur = (d.get("assignees") or {}).get(node_key) or ""
            if include_unassigned:
                if cur:
                    continue
            elif assignee_name and cur != assignee_name:
                continue
            items.append(d)
        total = len(items)
        start = (page - 1) * page_size
        return items[start:start + page_size], total

    def resolve_node_assignee(self, opportunity_id: str, node_key: str) -> str:
        """计算某节点默认处理人：商机角色字段优先（fae→boming、报价人→quoting），否则走业务默认规则。"""
        from app.models.opportunity import Opportunity
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if not opp:
            return ""
        business_user_id = opp.owner_user_id or ""
        prefer_field = {
            "boming": (opp.fae or "").strip(),
            "costing": "",
            "quoting": (opp.quotation_person or "").strip(),
        }.get(node_key, "")
        rule = ""
        if business_user_id:
            row = self.session.query(FlowAssignmentRule).filter(
                FlowAssignmentRule.business_user_id == business_user_id,
                FlowAssignmentRule.node_key == node_key,
            ).first()
            rule = (row.assignee_name if row else "") or ""
        return (prefer_field or rule or "").strip()

    def apply_default_assignments(self, flow_id: str, opportunity_id: str) -> None:
        """按业务账号默认规则补齐当前流程节点的 assignees（只补缺失，不覆盖手动转交）。"""
        flow = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.flow_id == flow_id
        ).first()
        if not flow:
            return
        current = flow.current_node
        target = self.resolve_node_assignee(opportunity_id, current)
        if not target:
            return
        assignees = {**(flow.assignees or {})}
        if not assignees.get(current):
            assignees[current] = target
            flow.assignees = assignees
            flow.updated_at = _now()
            self.session.commit()

    def get_assignment_rules(self, business_user_id: str = None) -> List[dict]:
        q = self.session.query(FlowAssignmentRule)
        if business_user_id:
            q = q.filter(FlowAssignmentRule.business_user_id == business_user_id)
        rows = q.order_by(FlowAssignmentRule.business_user_id.asc(), FlowAssignmentRule.node_key.asc()).all()
        return [r.to_dict() for r in rows]

    def upsert_assignment_rule(self, business_user_id: str, node_key: str,
                               assignee_name: str) -> dict:
        row = self.session.query(FlowAssignmentRule).filter(
            FlowAssignmentRule.business_user_id == business_user_id,
            FlowAssignmentRule.node_key == node_key,
        ).first()
        if row:
            row.assignee_name = assignee_name
            row.updated_at = _now()
        else:
            row = FlowAssignmentRule(
                business_user_id=business_user_id,
                node_key=node_key,
                assignee_name=assignee_name,
                created_at=_now(),
                updated_at=_now(),
            )
            self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def delete_assignment_rule(self, business_user_id: str, node_key: str) -> bool:
        row = self.session.query(FlowAssignmentRule).filter(
            FlowAssignmentRule.business_user_id == business_user_id,
            FlowAssignmentRule.node_key == node_key,
        ).first()
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def assign_task(self, flow_id: str, node_key: str, assignee_name: str,
                    actor: str = "") -> dict:
        flow = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.flow_id == flow_id
        ).first()
        old = ""
        if flow:
            old = (flow.assignees or {}).get(node_key) or ""
            flow.assignees = {**(flow.assignees or {}), node_key: assignee_name}
            flow.updated_at = _now()
            self.session.commit()
        comment = f"由 {old or '未指派'} 转交给 {assignee_name}"
        self.append_node(flow_id, node_key, "assign", actor=actor, comment=comment)
        return self.get_flow_by_id(flow_id) or {}

    def get_flow_by_id(self, flow_id: str) -> Optional[dict]:
        flow = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.flow_id == flow_id
        ).first()
        return flow.to_dict() if flow else None

    def list_assignment_events(self, limit: int = 50) -> List[dict]:
        rows = self.session.query(OpportunityFlowNode).filter(
            OpportunityFlowNode.action == "assign"
        ).order_by(OpportunityFlowNode.id.desc()).limit(limit * 3).all()
        out = []
        for r in rows:
            comment = r.comment or ""
            if "转交给" in comment or "指派给" in comment:
                out.append(r.to_dict())
                if len(out) >= limit:
                    break
        return out

    # ── 批量查询（门户卡片列表，避免逐商机 N+1）──

    def list_flows_bulk(self, opp_ids: List[str]) -> dict:
        if not opp_ids:
            return {}
        rows = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.opportunity_id.in_(opp_ids)
        ).all()
        return {r.opportunity_id: r.to_dict() for r in rows}

    def list_current_requirements_bulk(self, opp_ids: List[str]) -> dict:
        """各商机当前生效需求单。"""
        if not opp_ids:
            return {}
        rows = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id.in_(opp_ids),
            OpportunityRequirement.status == "current",
        ).all()
        return {r.opportunity_id: r.to_dict() for r in rows}

    def set_current_node(self, flow_id: str, node_key: str, status: Optional[str] = None) -> None:
        if node_key not in FLOW_NODE_KEYS:
            return
        flow = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.flow_id == flow_id
        ).first()
        if flow:
            flow.current_node = node_key
            if status:
                flow.status = status
            flow.updated_at = _now()
            self.session.commit()

    def advance_current_node_if_later(self, flow_id: str, node_key: str,
                                      status: Optional[str] = None) -> None:
        """仅允许把旧版全局流程节点向后推进，避免多卡片并发时回退。"""
        if node_key not in _FLOW_NODE_ORDER:
            return
        flow = self.session.query(OpportunityFlow).filter(
            OpportunityFlow.flow_id == flow_id
        ).first()
        if not flow:
            return
        current_node = (flow.current_node or "").strip() or "requirement"
        if _FLOW_NODE_ORDER.get(node_key, 0) < _FLOW_NODE_ORDER.get(current_node, 0):
            return
        flow.current_node = node_key
        if status and _FLOW_NODE_ORDER.get(node_key, 0) > _FLOW_NODE_ORDER.get(current_node, 0):
            flow.status = status
        flow.updated_at = _now()
        self.session.commit()

    # ── 时间线节点 ──

    def append_node(self, flow_id: str, node_key: str, action: str,
                    actor: str = "", comment: str = "",
                    version_tag: str = "", artifacts: Optional[dict] = None) -> OpportunityFlowNode:
        node = OpportunityFlowNode(
            flow_id=flow_id,
            node_key=node_key,
            node_label=NODE_LABELS.get(node_key, node_key),
            version_tag=version_tag,
            actor=actor,
            action=action,
            comment=comment,
            artifacts=artifacts or {},
            created_at=_now(),
        )
        self.session.add(node)
        self.session.commit()
        self.session.refresh(node)
        return node

    def list_nodes(self, flow_id: str) -> List[dict]:
        rows = self.session.query(OpportunityFlowNode).filter(
            OpportunityFlowNode.flow_id == flow_id
        ).order_by(OpportunityFlowNode.id.asc()).all()
        return [r.to_dict() for r in rows]

    # ── BOM 方案卡片 ──

    def list_bom_schemes(self, opportunity_id: str) -> List[dict]:
        rows = self.session.query(OpportunityBomScheme).filter(
            OpportunityBomScheme.opportunity_id == opportunity_id
        ).all()
        rank = {"current": 0, "draft": 1, "archived": 2}
        rows = sorted(rows, key=lambda r: (rank.get(r.status, 9), r.id))
        return [r.to_dict() for r in rows]

    def get_bom_scheme(self, opportunity_id: str, scheme_id: int) -> Optional[dict]:
        row = self.session.query(OpportunityBomScheme).filter(
            OpportunityBomScheme.opportunity_id == opportunity_id,
            OpportunityBomScheme.id == scheme_id,
        ).first()
        return row.to_dict() if row else None

    def save_bom_scheme_draft(self, opportunity_id: str, scheme_id: Optional[int],
                              name: str, configs: list, created_by: str = "",
                              config_relation: str = "compose",
                              primary_config: str = "") -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("方案名称不能为空")
        dup = self.session.query(OpportunityBomScheme).filter(
            OpportunityBomScheme.opportunity_id == opportunity_id,
            OpportunityBomScheme.name == name,
        )
        if scheme_id:
            dup = dup.filter(OpportunityBomScheme.id != scheme_id)
        if dup.first():
            raise ValueError("方案名称已存在")

        if scheme_id:
            row = self.session.query(OpportunityBomScheme).filter(
                OpportunityBomScheme.opportunity_id == opportunity_id,
                OpportunityBomScheme.id == scheme_id,
                OpportunityBomScheme.status == "draft",
            ).first()
            if not row:
                raise ValueError("仅草稿方案可编辑")
            row.name = name
            row.configs = configs or []
            row.config_relation = config_relation or "compose"
            row.primary_config = primary_config or ""
            row.created_by = created_by
            row.updated_at = _now()
        else:
            row = OpportunityBomScheme(
                opportunity_id=opportunity_id,
                name=name,
                status="draft",
                configs=configs or [],
                config_relation=config_relation or "compose",
                primary_config=primary_config or "",
                created_by=created_by,
                created_at=_now(),
                updated_at=_now(),
            )
            self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def delete_bom_scheme(self, opportunity_id: str, scheme_id: int) -> bool:
        row = self.session.query(OpportunityBomScheme).filter(
            OpportunityBomScheme.opportunity_id == opportunity_id,
            OpportunityBomScheme.id == scheme_id,
        ).first()
        if not row:
            raise ValueError("方案不存在")

        linked_cost = self.session.query(OpportunityCostSheet).filter(
            OpportunityCostSheet.opportunity_id == opportunity_id,
            OpportunityCostSheet.bom_scheme_id == scheme_id,
        ).first()
        if linked_cost:
            raise ValueError("该方案已被成本核算引用，请先删除对应成本表")

        self.session.delete(row)
        self.session.commit()
        return True

    def submit_bom_scheme(self, opportunity_id: str, scheme_id: int, actor: str = "") -> dict:
        row = self.session.query(OpportunityBomScheme).filter(
            OpportunityBomScheme.opportunity_id == opportunity_id,
            OpportunityBomScheme.id == scheme_id,
            OpportunityBomScheme.status == "draft",
        ).first()
        if not row:
            raise ValueError("草稿方案不存在或已提交")
        if not row.configs:
            raise ValueError("方案内容为空，无法提交")

        for old in self.session.query(OpportunityBomScheme).filter(
            OpportunityBomScheme.opportunity_id == opportunity_id,
            OpportunityBomScheme.status == "current",
        ).all():
            old.status = "archived"

        row.status = "current"
        row.updated_at = _now()
        flow = self.get_or_create_flow(opportunity_id)
        self.session.commit()
        self.advance_current_node_if_later(flow.flow_id, "costing", status="running")
        self.apply_default_assignments(flow.flow_id, opportunity_id)
        self.session.refresh(row)

        self.append_node(
            flow.flow_id,
            "boming",
            "complete",
            actor=actor or row.created_by or "",
            artifacts={"scheme_id": row.id, "scheme_name": row.name,
                       "config_names": [{"name": c.get("name") or "", "server_model": c.get("server_model") or ""} for c in row.configs or [] if isinstance(c, dict)]},
        )
        return row.to_dict()

    # ── 成本核算卡片 ──

    def list_cost_sheets(self, opportunity_id: str) -> List[dict]:
        rows = self.session.query(OpportunityCostSheet).filter(
            OpportunityCostSheet.opportunity_id == opportunity_id
        ).all()
        rank = {"current": 0, "draft": 1, "archived": 2}
        rows = sorted(rows, key=lambda r: (rank.get(r.status, 9), r.id))
        return [r.to_dict() for r in rows]

    def get_cost_sheet(self, opportunity_id: str, sheet_id: int) -> Optional[dict]:
        row = self.session.query(OpportunityCostSheet).filter(
            OpportunityCostSheet.opportunity_id == opportunity_id,
            OpportunityCostSheet.id == sheet_id,
        ).first()
        return row.to_dict() if row else None

    def save_cost_sheet_draft(self, opportunity_id: str, sheet_id: Optional[int],
                              name: str, configs: list, bom_scheme_id: Optional[int] = None,
                              quotation_id: str = "", created_by: str = "") -> dict:
        name = (name or "").strip()
        if not name:
            raise ValueError("成本表名称不能为空")
        dup = self.session.query(OpportunityCostSheet).filter(
            OpportunityCostSheet.opportunity_id == opportunity_id,
            OpportunityCostSheet.name == name,
        )
        if sheet_id:
            dup = dup.filter(OpportunityCostSheet.id != sheet_id)
        if dup.first():
            raise ValueError("成本表名称已存在")

        if sheet_id:
            row = self.session.query(OpportunityCostSheet).filter(
                OpportunityCostSheet.opportunity_id == opportunity_id,
                OpportunityCostSheet.id == sheet_id,
                OpportunityCostSheet.status.in_(("draft", "current")),
            ).first()
            if not row:
                raise ValueError("仅草稿或当前成本表可编辑")
            row.name = name
            row.configs = configs or []
            row.bom_scheme_id = bom_scheme_id
            row.quotation_id = quotation_id or row.quotation_id
            row.created_by = created_by
            row.updated_at = _now()
        else:
            row = OpportunityCostSheet(
                opportunity_id=opportunity_id,
                bom_scheme_id=bom_scheme_id,
                name=name,
                status="draft",
                configs=configs or [],
                quotation_id=quotation_id or None,
                created_by=created_by,
                created_at=_now(),
                updated_at=_now(),
            )
            self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def delete_cost_sheet_draft(self, opportunity_id: str, sheet_id: int) -> bool:
        row = self.session.query(OpportunityCostSheet).filter(
            OpportunityCostSheet.opportunity_id == opportunity_id,
            OpportunityCostSheet.id == sheet_id,
        ).first()
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def submit_cost_sheet(self, opportunity_id: str, sheet_id: int,
                          quotation_id: str = "", actor: str = "") -> dict:
        row = self.session.query(OpportunityCostSheet).filter(
            OpportunityCostSheet.opportunity_id == opportunity_id,
            OpportunityCostSheet.id == sheet_id,
            OpportunityCostSheet.status == "draft",
        ).first()
        if not row:
            raise ValueError("草稿成本表不存在或已提交")
        if not row.configs:
            raise ValueError("成本表内容为空，无法提交")

        row.status = "current"
        if quotation_id:
            row.quotation_id = quotation_id
        row.updated_at = _now()
        flow = self.get_or_create_flow(opportunity_id)
        self.session.commit()
        self.advance_current_node_if_later(flow.flow_id, "quoting", status="running")
        self.apply_default_assignments(flow.flow_id, opportunity_id)
        self.session.refresh(row)

        self.append_node(
            flow.flow_id,
            "costing",
            "complete",
            actor=actor or row.created_by or "",
            artifacts={
                "cost_sheet_id": row.id,
                "cost_sheet_name": row.name,
                "quotation_id": row.quotation_id or "",
                "config_names": [{"name": c.get("name") or "", "server_model": c.get("server_model") or ""} for c in row.configs or [] if isinstance(c, dict)],
            },
        )
        return row.to_dict()

    # ── 需求单版本 ──

    def list_requirements(self, opportunity_id: str) -> List[dict]:
        rows = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id
        ).order_by(OpportunityRequirement.version.desc()).all()
        return [r.to_dict() for r in rows]

    def get_requirement(self, opportunity_id: str, version: int) -> Optional[dict]:
        r = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.version == version,
        ).first()
        return r.to_dict() if r else None

    def create_requirement(self, opportunity_id: str, slots: dict,
                           requirement_text: str = "", created_by: str = "") -> dict:
        """提交需求单新版本：旧版全部 archived，新版 current；流程尚未进入下游时推进到 BOM。"""
        for old in self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.status == "current",
        ).all():
            old.status = "archived"
        latest = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id
        ).order_by(OpportunityRequirement.version.desc()).first()
        version = (latest.version + 1) if latest else 1
        row = OpportunityRequirement(
            opportunity_id=opportunity_id,
            version=version,
            slots=slots or {},
            requirement_text=requirement_text or "",
            status="current",
            created_by=created_by,
            created_at=_now(),
        )
        self.session.add(row)
        flow = self.get_or_create_flow(opportunity_id)
        self._advance_after_requirement_submit(flow)
        self.session.commit()
        self.apply_default_assignments(flow.flow_id, opportunity_id)
        self.session.refresh(row)
        # 时间线追加「需求 v{n} 提交」节点
        self.append_node(flow.flow_id, "requirement", "submit", actor=created_by,
                         version_tag=f"v{version}", artifacts={"requirement_version": version})
        return row.to_dict()

    def create_or_update_requirement_draft(self, opportunity_id: str, slots: dict,
                                           requirement_text: str = "", created_by: str = "") -> dict:
        """创建或更新一个需求草稿（不推进流程，不影响当前版本）。"""
        draft = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.status == "draft",
        ).first()
        if draft:
            draft.slots = slots or {}
            draft.requirement_text = requirement_text or ""
            draft.created_by = created_by
            self.session.commit()
            self.session.refresh(draft)
            return draft.to_dict()

        latest = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id
        ).order_by(OpportunityRequirement.version.desc()).first()
        version = (latest.version + 1) if latest else 1
        row = OpportunityRequirement(
            opportunity_id=opportunity_id,
            version=version,
            slots=slots or {},
            requirement_text=requirement_text or "",
            status="draft",
            created_by=created_by,
            created_at=_now(),
        )
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row.to_dict()

    def delete_requirement_draft(self, opportunity_id: str, version: int) -> bool:
        """删除需求草稿：仅允许删除 status=draft 的版本，不影响 current/archived。"""
        row = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.version == version,
            OpportunityRequirement.status == "draft",
        ).first()
        if not row:
            return False
        self.session.delete(row)
        self.session.commit()
        return True

    def submit_requirement_draft(self, opportunity_id: str, version: int) -> Optional[dict]:
        """提交需求草稿：草稿转 current，旧 current 归档；流程尚未进入下游时推进到 BOM。"""
        draft = self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.version == version,
            OpportunityRequirement.status == "draft",
        ).first()
        if not draft:
            return None

        for old in self.session.query(OpportunityRequirement).filter(
            OpportunityRequirement.opportunity_id == opportunity_id,
            OpportunityRequirement.status == "current",
        ).all():
            old.status = "archived"

        draft.status = "current"
        flow = self.get_or_create_flow(opportunity_id)
        self._advance_after_requirement_submit(flow)
        self.session.commit()
        self.apply_default_assignments(flow.flow_id, opportunity_id)
        self.session.refresh(draft)

        self.append_node(flow.flow_id, "requirement", "submit", actor=draft.created_by or "",
                         version_tag=f"v{draft.version}",
                         artifacts={"requirement_version": draft.version})
        return draft.to_dict()

