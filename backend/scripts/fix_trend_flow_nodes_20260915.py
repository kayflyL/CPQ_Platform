# -*- coding: utf-8 -*-
"""修复 trend_analysis flow 的节点配置（2026-09-15，一次性幂等迁移）。

审计实锤：DB flow 126（趋势分析）的 agent 节点没有配置行（只有孤儿 agent_fill 行），
output 行缺 target —— 引擎零大脑步 + 交付收尾错位。本脚本：
  1. 取 skill_key='trend_analysis' 的 active flow（没有则按现行种子建）
  2. 删除 graph 节点 id 之外的孤儿 ReasoningNodeConfig 行（清 agent_fill）
  3. upsert agent 行：query_data 工具 + 6 轮迭代上限
  4. 补齐 output 行的 output_kind=data_answer / payload_map / target=conversation_reply
幂等：已正确则零改动。运行：cd backend && python -X utf8 scripts/fix_trend_flow_nodes_20260915.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models.reasoning_flow import ReasoningNodeConfig  # noqa: E402
from app.repository.reasoning_flow_repo import ReasoningFlowRepository  # noqa: E402

SKILL_KEY = "trend_analysis"

AGENT_CONFIG = {
    "enabled_tools": ["query_data"],
    "max_iterations": 6,
    "system_prompt": "",
    "rule_types": [],
}

OUTPUT_ENSURE = {
    "output_kind": "data_answer",
    "payload_map": {"answer": "ctx.agent_result.answer"},
    "target": "conversation_reply",
}


def main() -> int:
    repo = ReasoningFlowRepository()
    try:
        flow = repo.get_active_flow(SKILL_KEY) or repo.ensure_skill_flow(SKILL_KEY)
        if not flow:
            print("FAIL: trend_analysis 流不存在且无法种子化")
            return 1
        flow_id = int(flow["id"])
        graph_nodes = {str(n.get("id") or "") for n in (flow.get("graph") or {}).get("nodes") or []
                       if isinstance(n, dict)}
        if not graph_nodes:
            print(f"FAIL: flow {flow_id} graph 无节点，中止（别误删全部配置行）")
            return 1
        changes: list[str] = []

        # 1) 清孤儿配置行（节点已不在图上的历史残留）
        orphans = repo.session.query(ReasoningNodeConfig).filter(
            ReasoningNodeConfig.flow_id == flow_id,
            ~ReasoningNodeConfig.node_key.in_(graph_nodes),
        ).all()
        for n in orphans:
            changes.append(f"删孤儿配置行 node_key={n.node_key}")
            repo.session.delete(n)
        if orphans:
            repo.session.commit()

        # 2) agent 行对齐种子（逐键合并，保留用户后加的未知键）
        agent_now = (flow.get("node_configs") or {}).get("agent")
        merged = dict(agent_now) if isinstance(agent_now, dict) else {}
        if merged != {**merged, **AGENT_CONFIG}:
            merged.update(AGENT_CONFIG)
            repo.upsert_node_config(flow_id, "agent", merged, operator="fix_trend_20260915")
            changes.append(f"upsert agent 行 -> {json.dumps(merged, ensure_ascii=False)}")

        # 3) output 行补齐交付声明（只补缺失键，不动既有 template/schema/actions）
        out_now = (flow.get("node_configs") or {}).get("output")
        out_merged = dict(out_now) if isinstance(out_now, dict) else {}
        for k, v in OUTPUT_ENSURE.items():
            if out_merged.get(k) != v:
                out_merged[k] = v
                repo.upsert_node_config(flow_id, "output", out_merged, operator="fix_trend_20260915")
                changes.append(f"output.{k} -> {json.dumps(v, ensure_ascii=False)}")

        if changes:
            print(f"flow {flow_id}（{SKILL_KEY}）修复 {len(changes)} 处：")
            for c in changes:
                print("  -", c)
        else:
            print(f"flow {flow_id}（{SKILL_KEY}）配置已正确，零改动（幂等通过）")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
