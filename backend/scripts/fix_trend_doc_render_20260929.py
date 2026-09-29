# -*- coding: utf-8 -*-
"""趋势分析文件产物配置迁往目标层文档卡（2026-09-29，一次性幂等迁移）。

架构收敛：报告的内容（章节/数据范围/报告名）与呈现（生成 PDF+模板）唯一权威 =
agent 节点目标层文档卡（target.artifacts[0] + render 子对象）；输出节点不再持有
文件产物配置（config.artifacts 删除）。模板卸内容职责：weekly_opportunity_report
blocks 槽位化——text 块绑章节 key（weekly/monthly/half_year/platform/chassis/
top_sales/insights），days 参数清空（运行时由目标层数据范围单源驱动）。

运行：cd backend && python -X utf8 scripts/fix_trend_doc_render_20260929.py [--apply]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.reasoning_flow_repo import ReasoningFlowRepository  # noqa: E402
from app.repository.artifact_template_repo import ArtifactTemplateRepo  # noqa: E402

SKILL_KEY = "trend_analysis"
TEMPLATE_KEY = "weekly_opportunity_report"
OPERATOR = "fix_trend_doc_render_20260929"

# 槽位版区块：文本槽 key = 目标层章节 key（一对一）；图表/明细由资产取数；
# days 参数一律不写（目标层数据范围 → 运行时 asset_params 覆盖）
BLOCKS = [
    {"type": "title"},
    {"type": "kpi", "asset": "cockpit.kpi", "title": "核心指标"},
    {"type": "text", "source": "payload", "key": "weekly", "title": "周数据"},
    {"type": "chart", "asset": "cockpit.trend", "title": "商机趋势（分平台）", "height": 320},
    {"type": "text", "source": "payload", "key": "monthly", "title": "月数据"},
    {"type": "text", "source": "payload", "key": "half_year", "title": "半年度商机趋势"},
    {"type": "text", "source": "payload", "key": "platform", "title": "平台格局"},
    {"type": "chart", "asset": "cockpit.dist", "title": "平台结构分布", "height": 240},
    {"type": "text", "source": "payload", "key": "chassis", "title": "机箱形态"},
    {"type": "chart", "asset": "cockpit.chassis_dist", "title": "机箱形态分布", "height": 260},
    {"type": "text", "source": "payload", "key": "top_sales", "title": "半年业务 TOP3"},
    {"type": "table", "asset": "cockpit.top_opps", "title": "最新商机明细"},
    {"type": "text", "source": "payload", "key": "insights", "title": "关键洞察"},
]
DESCRIPTION = ("商机趋势报告 · 章节槽位版：文本槽对接目标层章节 key"
               "（weekly/monthly/half_year/platform/chassis/top_sales/insights），"
               "图表与明细由图表资产取数；统计口径由工作流目标层数据范围单源驱动。")
TEMPLATE_NAME = "商机趋势报告"


def migrate_flow(apply: bool) -> None:
    repo = ReasoningFlowRepository()
    try:
        flow = repo.get_active_flow(SKILL_KEY) or repo.ensure_skill_flow(SKILL_KEY)
        if not flow:
            print("FAIL: trend_analysis 流不存在且无法种子化")
            sys.exit(1)
        flow_id = int(flow["id"])
        cfgs = flow.get("node_configs") or {}
        out_cfg = dict(cfgs.get("output") or {})
        old_arts = out_cfg.get("artifacts") or []
        old_tpl = ""
        for a in old_arts:
            if isinstance(a, dict) and a.get("kind") == "document":
                old_tpl = str(a.get("template_key") or "")
        doc_node, doc_art = "", None
        for k, c in cfgs.items():
            tgt = c.get("target") if isinstance(c, dict) else None
            for a in (tgt.get("artifacts") or []) if isinstance(tgt, dict) else []:
                if isinstance(a, dict) and a.get("kind") == "document":
                    doc_node, doc_art = k, a
                    break
        if doc_art is None:
            print("FAIL: 全图找不到 document 目标层文档卡（agent.target.artifacts）")
            sys.exit(1)
        render = {"enabled": True, "format": "pdf",
                  **({"template_key": old_tpl or TEMPLATE_KEY} if (old_tpl or TEMPLATE_KEY) else {})}
        if doc_art.get("render") == render and not old_arts:
            print(f"flow {flow_id} agent.render 已正确且 output 无 artifacts（幂等通过）")
            return
        print(f"flow {flow_id}: {doc_node}.render <- {json.dumps(render, ensure_ascii=False)}")
        print(f"flow {flow_id}: output.artifacts 将删除（现值 {json.dumps(old_arts, ensure_ascii=False)}）")
        if not apply:
            print("（dry-run，未写库；加 --apply 执行）")
            return
        new_doc_cfg = dict(cfgs.get(doc_node) or {})
        new_doc_cfg["target"] = {**(new_doc_cfg.get("target") or {}),
                                 "artifacts": [{**doc_art, "render": render}]}
        repo.upsert_node_config(flow_id, doc_node, new_doc_cfg, operator=OPERATOR)
        out_cfg.pop("artifacts", None)
        repo.upsert_node_config(flow_id, "output", out_cfg, operator=OPERATOR)
        print(f"flow {flow_id} 迁移完成")
    finally:
        repo.close()


def migrate_template(apply: bool) -> None:
    repo = ArtifactTemplateRepo()
    try:
        tpl = repo.get_by_key(TEMPLATE_KEY)
        if not tpl:
            print(f"FAIL: 模板 {TEMPLATE_KEY} 不存在")
            sys.exit(1)
        if tpl.get("blocks") == BLOCKS and tpl.get("description") == DESCRIPTION and tpl.get("name") == TEMPLATE_NAME:
            print(f"模板 {TEMPLATE_KEY} 已槽位化（幂等通过）")
            return
        print(f"模板 {TEMPLATE_KEY}: name「{tpl.get('name')}」→「{TEMPLATE_NAME}」, blocks {len(tpl.get('blocks') or [])} -> {len(BLOCKS)} 区块（槽位化）")
        if not apply:
            print("（dry-run，未写库；加 --apply 执行）")
            return
        repo.update(tpl["id"], {"name": TEMPLATE_NAME, "blocks": BLOCKS, "description": DESCRIPTION}, operator=OPERATOR)
        print(f"模板 {TEMPLATE_KEY} 迁移完成")
    finally:
        repo.close()


if __name__ == "__main__":
    do_apply = "--apply" in sys.argv
    migrate_flow(do_apply)
    migrate_template(do_apply)
