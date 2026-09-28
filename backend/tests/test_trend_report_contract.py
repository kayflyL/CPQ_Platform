# -*- coding: utf-8 -*-
"""趋势报告结构契约 + data_report 产物 builder 的注册表单测（2026-09-16）。

覆盖：document 契约格式化（章节渲染/分发）、BUILDERS data_report 产物、
resolve_kind 认抽屉声明的 slot、done_summary 字数摘要。
"""
from app.services.skill_node_artifacts import BUILDERS, done_summary, resolve_kind
from app.services.skill_target_contract import format_contract, format_document_contract

DOC_ART = {
    "kind": "document",
    "slot": "data_report",
    "name": "商机趋势分析报告",
    "sections": [
        {"key": "weekly", "title": "周数据", "requires": "本周新增商机数、平台分布"},
        {"key": "monthly", "title": "月数据", "requires": "本月新增；对比上月"},
        {"key": "insights", "title": "关键洞察", "requires": "3-5 条"},
    ],
}


def test_format_document_contract_renders_sections():
    text = format_document_contract(DOC_ART)
    assert "《商机趋势分析报告》" in text
    assert "数据范围" in text
    assert "一、周数据" in text and "二、月数据" in text and "三、关键洞察" in text
    assert "本周新增商机数、平台分布" in text
    assert "Markdown 表格" in text


def test_format_document_contract_configured_range():
    art = dict(DOC_ART, data_range={"mode": "half_year"})
    text = format_document_contract(art)
    assert "近半年" in text and "配置指定" in text and "各节统计范围即此窗口" in text
    # 禁令措辞不进共享代码（职责分离：行为纪律只住 manual_rules）
    assert "禁止" not in text and "不得" not in text
    # 窗口是后端确定性计算的日期文本（YYYY.MM.DD ~ YYYY.MM.DD），不是模板占位
    import re
    assert re.search(r"\d{4}\.\d{2}\.\d{2} ~ \d{4}\.\d{2}\.\d{2}", text)
    # custom 带起止
    custom = format_document_contract(dict(DOC_ART, data_range={"mode": "custom", "start": "2026-03-01", "end": "2026-09-01"}))
    assert "2026.03.01 ~ 2026.09.01" in custom and "自定义区间" in custom
    # auto/缺 start/end 的 custom → 按数据边界口径
    assert "实际数据边界" in format_document_contract(dict(DOC_ART, data_range={"mode": "custom"}))


def test_format_contract_dispatches_by_kind_document():
    # slot=data_report 未注册格式化器 → 按 kind=document 命中
    text = format_contract(dict(DOC_ART))
    assert "一、周数据" in text


def test_data_report_builder_reads_agent_result():
    builder = BUILDERS["data_report"]
    engine = {"agent_result": {"answer": "# 报告\n正文"}, "flow_configs": {}}
    output, artifact = builder(engine, DOC_ART)
    assert artifact["kind"] == "document"
    assert artifact["title"] == "商机趋势分析报告"
    assert artifact["data"]["markdown"] == "# 报告\n正文"
    assert output == {"answer_chars": 7}


def test_data_report_builder_empty_answer():
    output, artifact = BUILDERS["data_report"]({}, DOC_ART)
    assert artifact["data"]["markdown"] == ""
    assert output == {}


def test_resolve_kind_honors_declared_slot():
    engine = {"flow_configs": {"agent": {"target": {"artifacts": [DOC_ART]}}}}
    assert resolve_kind(engine, "agent") == "data_report"
    # 未声明 slot 的节点产物为空（白盒不装懂）
    assert resolve_kind({"flow_configs": {"agent": {}}}, "agent") == ""


def test_done_summary_document_char_count():
    art = {"kind": "document", "title": "商机趋势分析报告", "data": {"markdown": "x" * 123}}
    summary = done_summary({}, "agent", art)
    assert "123 字" in summary
    empty = done_summary({}, "agent", {"kind": "document", "title": "商机趋势分析报告", "data": {}})
    assert "产物为空" in empty


# ── data_answer 终检：配置数据范围物理核对（防大脑复读历史报告的自算窗口） ──

def _gate_ctx(answer: str, data_range=None) -> dict:
    art = dict(DOC_ART)
    if data_range is not None:
        art = dict(art, data_range=data_range)
    return {"agent_result": {"answer": answer},
            "flow_configs": {"agent": {"target": {"artifacts": [art]}}}}


def test_data_answer_gate_window_mismatch_reopens_node():
    from app.services.skill_plan_runtime import _data_answer_gate
    ctx = _gate_ctx("数据范围：2026.03.06 ~ 2026.09.15（真实商机 168 条）\n\n## 一、周数据",
                    {"mode": "custom", "start": "2026-01-01", "end": "2026-09-12"})
    g = _data_answer_gate(ctx)
    assert not g["ok"] and g["reopen"] == "agent"
    assert "2026.01.01 ~ 2026.09.12" in g["hint"]


def test_data_answer_gate_window_match_passes():
    from app.services.skill_plan_runtime import _data_answer_gate
    ctx = _gate_ctx("数据范围：2026.01.01 ~ 2026.09.12（自定义区间，配置指定）\n\n## 一、周数据",
                    {"mode": "custom", "start": "2026-01-01", "end": "2026-09-12"})
    assert _data_answer_gate(ctx)["ok"] is True


def test_data_answer_gate_auto_range_skips_window_check():
    from app.services.skill_plan_runtime import _data_answer_gate
    ctx = _gate_ctx("数据范围：2026.03.06 ~ 2026.09.15（按实际数据边界）\n\n正文")
    assert _data_answer_gate(ctx)["ok"] is True


def test_data_answer_gate_empty_answer_still_blocks():
    from app.services.skill_plan_runtime import _data_answer_gate
    g = _data_answer_gate({"agent_result": {"answer": ""}, "flow_configs": {}})
    assert not g["ok"] and g["hint"] == "分析尚未产出数据结论"
