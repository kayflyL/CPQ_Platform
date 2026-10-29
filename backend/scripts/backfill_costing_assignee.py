# -*- coding: utf-8 -*-
"""存量核价归属回填：把有核价历史的活流程 assignees['costing'] 写给成本核算岗（冯桃红）。

背景：2026-10 前核价工作全部由 admin 直传成本表完成，流程 assignees 从未落过 cost 岗指派，
桃红的工作台「经手商机」台账为空。本脚本一次性补齐归属，只动 costing 键。

口径：
- 目标集 = opportunity_flow_nodes 有 costing 事件 × 商机活（非 deleted/ai_office）
- assignees['costing'] 为空或非本人 → 写 uid；已是本人（uid 或 legacy 姓名串）→ 跳过
- 不改 updated_at（回填是簿记修正，不应扰动商机线索页按更新时间的排序）
- 不走 assign_task API（避免逐条"转交"审计事件刷屏调度台转交记录）

用法：
    python -X utf8 scripts/backfill_costing_assignee.py            # dry-run，只打印计划
    python -X utf8 scripts/backfill_costing_assignee.py --execute  # 先备份再单事务执行

备份/清单落 D:\\CPQ_Archive\\backfill_costing_<时间戳>\\（仓库外，见 CLAUDE.md 备份规矩）。
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text

from app.models.base import engine

# 备份/清单落仓库外：Windows 开发机走 D:\\CPQ_Archive，服务器跑本脚本时用 CPQ_ARCHIVE_ROOT 覆盖
if sys.platform.startswith("win"):
    ARCHIVE_ROOT = Path(os.environ.get("CPQ_ARCHIVE_ROOT", r"D:\CPQ_Archive"))
else:
    ARCHIVE_ROOT = Path(os.environ.get("CPQ_ARCHIVE_ROOT", Path.home() / "cpq_archive"))
TARGET_NAME = "冯桃红"


def resolve_target_uid() -> str:
    from app.repository.feed_user_repo import FeedUserRepository
    repo = FeedUserRepository()
    try:
        u = next((x for x in repo.list_all() if x.get("name") == TARGET_NAME), None)
    finally:
        repo.close()
    if not u or u.get("role") != "cost":
        raise SystemExit(f"未找到 cost 角色用户 {TARGET_NAME}，拒绝执行")
    return u["user_id"]


def fetch_targets(conn) -> list[dict]:
    rows = conn.execute(text(
        "SELECT DISTINCT ON (f.flow_id) f.flow_id, f.opportunity_id, f.assignees, o.customer_name "
        "FROM opportunities.opportunity_flow_nodes n "
        "JOIN opportunities.opportunity_flows f ON f.flow_id = n.flow_id "
        "JOIN opportunities.opportunities o ON o.opportunity_id = f.opportunity_id "
        "WHERE n.node_key = 'costing' "
        "AND o.status NOT IN ('deleted', 'ai_office') "
        "ORDER BY f.flow_id"
    )).mappings().fetchall()
    return [dict(r) for r in rows]


def plan_row(assignees, uid: str, name: str) -> tuple[str, str]:
    """返回 (动作, 旧值)：skip=已是本人 / write=需写入。"""
    data = assignees if isinstance(assignees, dict) else {}
    cur = data.get("costing")
    if isinstance(cur, list):
        return ("skip", "写") if uid in cur or name in cur else ("append", json.dumps(cur, ensure_ascii=False))
    if cur in (uid, name):
        return "skip", cur or ""
    return "write", cur or ""


def main() -> None:
    execute = "--execute" in sys.argv
    uid = resolve_target_uid()
    with engine.connect() as conn:
        targets = fetch_targets(conn)
    actions = []
    for t in targets:
        act, old = plan_row(t["assignees"], uid, TARGET_NAME)
        if act != "skip":
            actions.append({**t, "action": act, "old": old})
    print(f"目标流程 {len(targets)} 条，需写入 {len(actions)} 条，跳过 {len(targets) - len(actions)} 条")

    if not execute:
        for a in actions[:10]:
            print(f"  [dry] {a['opportunity_id']} {a['customer_name']}: {a['old']!r} -> {uid}")
        if len(actions) > 10:
            print(f"  ... 其余 {len(actions) - 10} 条略")
        print("dry-run 结束，加 --execute 执行")
        return

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = ARCHIVE_ROOT / f"backfill_costing_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # 备份先于任何写入：目标行全量 JSON（含未改动行，便于整体回滚核对）
    backup = {
        "executed_at": datetime.now().isoformat(),
        "target": {"user_id": uid, "name": TARGET_NAME},
        "flows_before": [
            {"flow_id": t["flow_id"], "opportunity_id": t["opportunity_id"],
             "customer_name": t["customer_name"], "assignees": t["assignees"]}
            for t in targets
        ],
    }
    backup_path = out_dir / "flows_backup.json"
    backup_path.write_text(json.dumps(backup, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已备份 {len(targets)} 行 -> {backup_path}")

    changed = []
    with engine.begin() as conn:
        for a in actions:
            data = dict(a["assignees"]) if isinstance(a["assignees"], dict) else {}
            cur = data.get("costing")
            if a["action"] == "append":
                data["costing"] = (cur if isinstance(cur, list) else [cur]) + [uid]
            else:
                data["costing"] = uid
            conn.execute(text(
                "UPDATE opportunities.opportunity_flows SET assignees = CAST(:j AS json) "
                "WHERE flow_id = :fid"),
                {"j": json.dumps(data, ensure_ascii=False), "fid": a["flow_id"]})
            changed.append({"flow_id": a["flow_id"], "opportunity_id": a["opportunity_id"],
                            "customer_name": a["customer_name"], "old": a["old"], "new": data["costing"]})
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(
        {"executed_at": backup["executed_at"], "changed_count": len(changed), "changed": changed},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已回填 {len(changed)} 条，清单 -> {manifest_path}")


if __name__ == "__main__":
    main()
