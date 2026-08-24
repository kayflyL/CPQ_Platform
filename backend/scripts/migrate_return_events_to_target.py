#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""一次性迁移：把历史退回事件从“发起退回的节点”迁到“被退回的需求节点”。

规则（幂等，默认 dry-run）：
- 仅处理 action=return 且 node_key != requirement 的流程事件。
- node_key 改为 requirement，node_label 改为 需求。
- 原 node_key 写入 artifacts.from_node，保留 requirement_version。

用法（backend 目录）：
  ./.venv/Scripts/python.exe -X utf8 scripts/migrate_return_events_to_target.py
  ./.venv/Scripts/python.exe -X utf8 scripts/migrate_return_events_to_target.py --commit
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

from app.models.base import Opportunity_SessionLocal
from app.models.flow import OpportunityFlowNode


TARGET_NODE = 'requirement'
TARGET_LABEL = '需求'


def _artifacts(node):
    if not node.artifacts:
        return {}
    try:
        value = json.loads(node.artifacts or '{}')
        return value if isinstance(value, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def migrate(session, commit):
    rows = (
        session.query(OpportunityFlowNode)
        .filter(OpportunityFlowNode.action == 'return')
        .order_by(OpportunityFlowNode.id.asc())
        .all()
    )
    print(f'待迁移退回事件: {len(rows)}')
    for node in rows:
        old_key = node.node_key
        artifacts = _artifacts(node)
        if old_key != TARGET_NODE:
            artifacts['from_node'] = old_key
        artifacts.setdefault('requirement_version', node.version_tag.lstrip('v') if node.version_tag else '')
        print(f'  id={node.id} flow={node.flow_id} {old_key} -> {TARGET_NODE} v={node.version_tag}')
        if commit:
            node.node_key = TARGET_NODE
            node.node_label = TARGET_LABEL
            node.artifacts = artifacts

    if commit and rows:
        session.commit()
        print('\n已写库。')
    elif not commit:
        print('\nDRY RUN：未写库。确认后加 --commit 执行。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--commit', action='store_true')
    args = parser.parse_args()

    session = Opportunity_SessionLocal()
    try:
        migrate(session, args.commit)
    finally:
        session.close()


if __name__ == '__main__':
    main()
