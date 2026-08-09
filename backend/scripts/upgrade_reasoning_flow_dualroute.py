# -*- coding: utf-8 -*-
"""一次性升级 active reasoning_flow 到 v9 双路线拓扑。

不挂 startup（避免 v9 教训：每次启动重复迁移堆 active）。手动跑：

    cd backend
    python -X utf8 scripts/upgrade_reasoning_flow_dualroute.py

幂等：当前 active 已含 route_fork 节点则跳过。回退：调 activate 切回旧 v8 flow id
（旧 v8 flow 的 graph 未被改动，完整保留作回退锚点），例如：

    python -X utf8 scripts/upgrade_reasoning_flow_dualroute.py --rollback <旧v8_flow_id>
"""
import sys
from pathlib import Path

# 脚本在 backend/scripts/，把 backend 根加入 sys.path 以 import app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.reasoning_flow_repo import ReasoningFlowRepository  # noqa: E402


def main():
    repo = ReasoningFlowRepository()
    try:
        # --rollback <id>：切回指定 flow（回退用）
        if len(sys.argv) >= 3 and sys.argv[1] == "--rollback":
            old_id = int(sys.argv[2])
            r = repo.activate(old_id, operator="rollback-v9")
            print(f"✅ 已切回 flow id={old_id} name={r.get('name') if r else '?'}")
            return
        result = repo.upgrade_to_dual_route(operator="upgrade-v9-script")
        if result is None:
            print("⚠️ 当前 active flow 已是 v9 双路线（含 route_fork），跳过。")
            return
        nodes = (result.get("graph") or {}).get("nodes") or []
        print(f"✅ 已升级到 v9 双路线并激活：id={result.get('id')} name={result.get('name')}")
        print(f"   graph 节点数={len(nodes)}（含 route_fork / llm_extract / cond_audit）")
        print("   回退：python -X utf8 scripts/upgrade_reasoning_flow_dualroute.py --rollback <旧v8_id>")
    finally:
        repo.session.close()


if __name__ == "__main__":
    main()
