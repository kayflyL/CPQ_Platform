# -*- coding: utf-8 -*-
"""trend_analysis 输出节点开启 PDF 报告产物（2026-09-15，一次性幂等迁移）。

兑现「输出节点目标输出物多格式」：output 节点声明 artifacts 插槽，
finalize_output 在 data_answer 交付时确定性渲染 markdown→PDF 落 office 桶。
本脚本给 trend flow 的 output 行 upsert
  artifacts=[{"kind": "document", "format": "pdf", "title": "商机趋势分析报告"}]
幂等：已一致则零改动。运行：cd backend && python -X utf8 scripts/fix_trend_flow_artifacts_20260915.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.reasoning_flow_repo import ReasoningFlowRepository  # noqa: E402

SKILL_KEY = "trend_analysis"

ARTIFACTS = [{"kind": "document", "format": "pdf", "title": "商机趋势分析报告"}]


def main() -> int:
    repo = ReasoningFlowRepository()
    try:
        flow = repo.get_active_flow(SKILL_KEY) or repo.ensure_skill_flow(SKILL_KEY)
        if not flow:
            print("FAIL: trend_analysis 流不存在且无法种子化")
            return 1
        flow_id = int(flow["id"])
        out_now = (flow.get("node_configs") or {}).get("output")
        merged = dict(out_now) if isinstance(out_now, dict) else {}
        if merged.get("artifacts") == ARTIFACTS:
            print(f"flow {flow_id}（{SKILL_KEY}）output.artifacts 已正确，零改动（幂等通过）")
            return 0
        merged["artifacts"] = ARTIFACTS
        repo.upsert_node_config(flow_id, "output", merged, operator="fix_trend_artifacts_20260915")
        print(f"flow {flow_id}（{SKILL_KEY}）output.artifacts -> {json.dumps(ARTIFACTS, ensure_ascii=False)}")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
