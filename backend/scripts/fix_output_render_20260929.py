# -*- coding: utf-8 -*-
"""呈现配置搬家：目标层文档卡 render → 输出节点 config.render（2026-09-29，一次性幂等迁移）。

架构定调（原型 _prototypes/output-artifact-selector.html）：内容（报告名/章节/数据范围）
归目标层文档卡，呈现方式（是否出文件/格式/模板）归输出节点——输出节点统一「呈现方式」
区，默认「随流程呈现」（不写 render = 不出文件），选 PDF 才写 render。
运行时 skill_turn_engine._deliver 组装 document_target 时两处合并。

运行：cd backend && python -X utf8 scripts/fix_output_render_20260929.py [--apply]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.reasoning_flow_repo import ReasoningFlowRepository  # noqa: E402

OPERATOR = "fix_output_render_20260929"


def migrate(repo: ReasoningFlowRepository, flow: dict, apply: bool) -> None:
    flow_id = int(flow["id"])
    cfgs = flow.get("node_configs") or {}
    doc_node, doc_art = "", None
    for k, c in cfgs.items():
        tgt = c.get("target") if isinstance(c, dict) else None
        for a in (tgt.get("artifacts") or []) if isinstance(tgt, dict) else []:
            if isinstance(a, dict) and a.get("kind") == "document":
                doc_node, doc_art = k, a
                break
        if doc_art is not None:
            break
    old_render = doc_art.get("render") if isinstance(doc_art, dict) else None
    out_render = (cfgs.get("output") or {}).get("render")
    if not old_render and not isinstance(out_render, dict):
        print(f"flow {flow_id}（{flow.get('skill_key')}）：目标卡无 render 且输出节点无 render（幂等通过）")
        return
    print(f"flow {flow_id}（{flow.get('skill_key')}）: {doc_node}.render {json.dumps(old_render, ensure_ascii=False)}"
          f" → output.render；agent 卡删 render 子对象")
    if not apply:
        print("（dry-run，未写库；加 --apply 执行）")
        return
    if doc_art is not None:
        new_doc_cfg = dict(cfgs.get(doc_node) or {})
        arts = [({k: v for k, v in a.items() if k != "render"} if a is doc_art else a)
                for a in (new_doc_cfg.get("target") or {}).get("artifacts") or []]
        new_doc_cfg["target"] = {**(new_doc_cfg.get("target") or {}), "artifacts": arts}
        repo.upsert_node_config(flow_id, doc_node, new_doc_cfg, operator=OPERATOR)
    if isinstance(old_render, dict):
        out_cfg = dict(cfgs.get("output") or {})
        out_cfg["render"] = old_render
        repo.upsert_node_config(flow_id, "output", out_cfg, operator=OPERATOR)
    print(f"flow {flow_id} 迁移完成")


if __name__ == "__main__":
    do_apply = "--apply" in sys.argv
    repo = ReasoningFlowRepository()
    try:
        rows = repo.list_flows() if hasattr(repo, "list_flows") else []
        if not rows:
            # 兜底：直接取两个已知 skill 的 active flow
            rows = [r for r in (repo.get_active_flow(k) for k in ("trend_analysis", "requirement_analysis")) if r]
        for fl in rows:
            migrate(repo, fl, do_apply)
    finally:
        repo.close()
