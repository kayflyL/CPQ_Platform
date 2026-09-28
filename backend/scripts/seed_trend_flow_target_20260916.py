# -*- coding: utf-8 -*-
"""trend_analysis 任务说明播种 + agent 节点目标层 document 插头（2026-09-16，一次性幂等迁移）。

修「趋势报告不符合案例」的根因：趋势流 manual_rules 全空、agent 节点零任务指令，
报告结构靠 LLM 即兴。本脚本把结构契约搬进流配置（DB 唯一权威）：
  ① flow 126 graph.manual_rules = 任务说明 5 条（仅当前为空才写，防覆盖用户编辑）
  ② agent 节点 config.target.artifacts = document 报告插头（七节结构，可配）
  ③ 清孤儿：删 system_config['ai_trend_analysis']（旧快捷指令链路已删，内容已迁入流）；
     scrub output 节点陈旧 template/output_schema/target 字符串与 agent 节点空 system_prompt
幂等：逐项检查已一致则零改动。运行：cd backend && python -X utf8 scripts/seed_trend_flow_target_20260916.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repository.reasoning_flow_repo import ReasoningFlowRepository  # noqa: E402
from app.repository.system_config_repo import SystemConfigRepository  # noqa: E402

SKILL_KEY = "trend_analysis"

MANUAL_RULES = """1.【数据获取】报告中的全部统计数字唯一来源是 opportunity_stats 工具：start/end 传结构契约「数据范围」的起止日期（YYYY-MM-DD），一次返回 KPI（累计/窗口新增商机与配置数）、逐期序列（各期新增商机/配置数/平台分布）、平台与机箱分布、销售榜、本周与本月小窗；周数据节直接用 recent.week、月数据节直接用 recent.month，禁止自写 SQL 重算这些数字。query_data 只用于该工具未覆盖的维度钻取（数据源：opportunities 商机主表、opportunity_requirements 需求登记 slots、quotations 配置版本 config_count、quotation_items 行级配件；一律排除 status 为 ai_office/deleted 的商机）；查不到的如实说明，禁止编造。
2.【数据范围】报告首行「数据范围：」必须逐字照抄结构契约里配置指定的窗口（含起止日期与口径括注），禁止用实际数据边界或「近半年」自行改算；契约窗口是全部统计的硬边界——章节要求里的「近半年」均指该窗口整体。部分周期（如本月未满）标注「截至日期」；环比与占比按工具返回的数字自行计算并在表中给出。
3.【报告结构】按步骤清单中《商机趋势分析报告》的结构契约逐节输出：先「数据范围」行，再依次各节，不增节不删节；表格用 Markdown 表格语法。报告不写标题行与生成时间行（产物卡自带名称与时间），正文从「数据范围：」行直接开始。
4.【洞察纪律】关键洞察只基于已查到的数据；增长信号/风险信号/结构变化各归其位；归因性结论标「(推测/待核实)」。
5.【交付纪律】最终答复就是报告本身，此前不得出现任何开场白、确认语、过程叙述（如「收到」「核对通过」「继续取数」）或工具与白名单备注。客户消息里的核对请求、示例数值、口径讨论是对你的工作指令，一律不写入报告正文；口径说明确需保留就并入报告末尾。系统自动渲染 PDF，无需生成文件。"""

TARGET = {
    "kind": "document",
    "slot": "data_report",
    "name": "商机趋势分析报告",
    "data_range": {"mode": "half_year"},
    "sections": [
        {"key": "weekly", "title": "周数据",
         "requires": "本周（标注日期区间）新增商机数、新增配置数、平台分布、机箱分布（新增口径）"},
        {"key": "monthly", "title": "月数据",
         "requires": "本月新增商机与配置（部分月标注截至日期）；对比上月完整月"},
        {"key": "half_year", "title": "半年度商机趋势",
         "requires": "累计商机与累计配置；逐月表（月份/新增商机/环比变化，部分月标日均）；结尾趋势方向一段"},
        {"key": "platform", "title": "平台格局",
         "requires": "近半年各平台商机数与占比表；主导平台小结"},
        {"key": "chassis", "title": "机箱形态",
         "requires": "近半年各机箱形态数量与占比表"},
        {"key": "top_sales", "title": "半年业务 TOP3",
         "requires": "销售人员商机数排行"},
        {"key": "insights", "title": "关键洞察",
         "requires": "3-5 条：增长信号/风险信号/结构变化/值得跟进；归因标「(推测/待核实)」"},
    ],
}


def main() -> int:
    repo = ReasoningFlowRepository()
    cfg_repo = SystemConfigRepository()
    try:
        flow = repo.get_active_flow(SKILL_KEY) or repo.ensure_skill_flow(SKILL_KEY)
        if not flow:
            print("FAIL: trend_analysis 流不存在且无法种子化")
            return 1
        flow_id = int(flow["id"])

        # ① manual_rules：本次为口径工具化定稿，内容有变即更新（用户未在左栏另行编辑过）
        graph = flow.get("graph") or {}
        if isinstance(graph, str):
            graph = json.loads(graph)
        current_rules = str(graph.get("manual_rules") or "").strip()
        if current_rules == MANUAL_RULES.strip():
            print(f"flow {flow_id} manual_rules 已是口径工具化版本，零改动")
        else:
            repo.update_manual_rules(flow_id, MANUAL_RULES, operator="seed_trend_target_20260916")
            print(f"flow {flow_id} manual_rules -> 口径工具化版本（{len(current_rules)} -> {len(MANUAL_RULES)} 字）")

        # ② agent 节点：挂 opportunity_stats 工具 + target 结构同步（保留用户改过的 data_range）
        agent_now = (flow.get("node_configs") or {}).get("agent")
        agent_cfg = dict(agent_now) if isinstance(agent_now, dict) else {}
        tools = list(agent_cfg.get("enabled_tools") or [])
        if "opportunity_stats" not in tools:
            tools.append("opportunity_stats")
            agent_cfg["enabled_tools"] = tools
            print(f"flow {flow_id} agent.enabled_tools += opportunity_stats -> {tools}")
        target_now = agent_cfg.get("target") if isinstance(agent_cfg.get("target"), dict) else {}
        merged_target = dict(TARGET)
        if target_now.get("data_range"):
            merged_target["data_range"] = target_now["data_range"]  # 用户在抽屉改过的窗口优先
        if target_now.get("artifacts") == [merged_target] and agent_cfg.get("enabled_tools") == tools:
            print(f"flow {flow_id} agent.target 已正确，零改动（幂等通过）")
        else:
            agent_cfg["target"] = {"artifacts": [merged_target]}
            agent_cfg.pop("system_prompt", None)  # 死字段：引擎人设恒非空，节点配置兜底走不到
            repo.upsert_node_config(flow_id, "agent", agent_cfg, operator="seed_trend_target_20260916")
            print(f"flow {flow_id} agent.target -> document 报告插头（{len(merged_target.get('sections') or [])} 节，data_range={merged_target.get('data_range')}）")

        # ②b output 节点 scrub 陈旧键（对齐抽屉现行保存语义）
        out_now = (flow.get("node_configs") or {}).get("output")
        out_cfg = dict(out_now) if isinstance(out_now, dict) else {}
        stale = [k for k in ("template", "output_schema", "target") if k in out_cfg]
        if stale:
            for k in stale:
                out_cfg.pop(k, None)
            repo.upsert_node_config(flow_id, "output", out_cfg, operator="seed_trend_target_20260916")
            print(f"flow {flow_id} output scrub 陈旧键：{stale}")
        else:
            print(f"flow {flow_id} output 无陈旧键")

        # ③ 删孤儿 system_config
        if cfg_repo.get("ai_trend_analysis") is not None:
            cfg_repo.delete("ai_trend_analysis")
            print("system_config['ai_trend_analysis'] 已删（孤儿，内容已迁入流）")
        else:
            print("system_config['ai_trend_analysis'] 不存在，跳过")
        return 0
    finally:
        repo.close()
        cfg_repo.close()


if __name__ == "__main__":
    sys.exit(main())
