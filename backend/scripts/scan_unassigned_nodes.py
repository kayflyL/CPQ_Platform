"""扫描存量流程中「当前节点已到但无人指派」的商机（公共池已取消，只报告不自动改）。

跑法：cd backend && ./.venv/Scripts/python.exe -X utf8 scripts/scan_unassigned_nodes.py
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.flow import OpportunityFlow
from app.models.opportunity import Opportunity
from app.models.base import Opportunity_SessionLocal

s = Opportunity_SessionLocal()
try:
    excluded = {
        r[0] for r in s.query(Opportunity.opportunity_id).filter(
            Opportunity.status.in_(("ai_office", "deleted"))
        ).all()
    }
    rows = s.query(OpportunityFlow).all()
    findings = []
    for flow in rows:
        node = flow.current_node or ""
        if node not in ("boming", "costing", "quoting"):
            continue
        if flow.opportunity_id in excluded:
            continue
        if not (flow.assignees or {}).get(node):
            findings.append((flow.opportunity_id, node))
finally:
    s.close()

if not findings:
    print("无未指派节点，全部合规。")
else:
    print(f"发现 {len(findings)} 个未指派节点（需人工指派，任务队列已不含公共池）：")
    for opp_id, node in findings:
        print(f"  {opp_id} [{node}]")
