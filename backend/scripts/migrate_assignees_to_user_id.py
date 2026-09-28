"""一次性迁移：opportunity_flows.assignees 的姓名值 → user_id。

幂等可重跑。规则：
- 值已是 user_id（库里存在）→ 跳过
- 姓名在 feed_users 唯一命中 → 替换为 user_id
- 姓名无命中（自由填写的外部人名）→ 保留原值并报告
- 姓名多人重名 → 保留原值并报告（需人工拍板归属）

跑法：cd backend && ./.venv/Scripts/python.exe -X utf8 scripts/migrate_assignees_to_user_id.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.flow import OpportunityFlow
from app.models.base import Opportunity_SessionLocal
from app.repository.feed_user_repo import FeedUserRepository

repo = FeedUserRepository()
try:
    users = repo.list_all()
finally:
    repo.close()
by_uid = {u["user_id"]: u.get("name") or "" for u in users}
by_name: dict = {}
for u in users:
    by_name.setdefault(u.get("name") or "", []).append(u["user_id"])

s = Opportunity_SessionLocal()
migrated = skipped_uid = unmatched = conflicts = 0
report_unmatched, report_conflict = [], []
try:
    rows = s.query(OpportunityFlow).all()
    for flow in rows:
        original = flow.assignees or {}
        changed = False
        new_values = {}
        for node, value in original.items():
            if not value:
                new_values[node] = value
                continue
            if value in by_uid:
                skipped_uid += 1
                new_values[node] = value
                continue
            hits = by_name.get(value) or []
            if len(hits) == 1:
                new_values[node] = hits[0]
                migrated += 1
                changed = True
            elif not hits:
                unmatched += 1
                report_unmatched.append((flow.opportunity_id, node, value))
                new_values[node] = value
            else:
                conflicts += 1
                report_conflict.append((flow.opportunity_id, node, value, hits))
                new_values[node] = value
        if changed:
            flow.assignees = new_values
    s.commit()
finally:
    s.close()

print(f"流转总数处理完毕：迁移 {migrated} 项 | 已是 user_id {skipped_uid} 项 | "
      f"无命中 {unmatched} 项 | 重名冲突 {conflicts} 项")
if report_unmatched:
    print("\n-- 无命中（自由填写的外部姓名，原样保留，读写双格式兼容）--")
    for opp, node, v in report_unmatched[:30]:
        print(f"  {opp} [{node}] = {v}")
if report_conflict:
    print("\n-- 重名冲突（原样保留，请人工确认后改 user_id）--")
    for opp, node, v, uids in report_conflict[:30]:
        print(f"  {opp} [{node}] = {v} 候选 user_id: {uids}")
