# -*- coding: utf-8 -*-
"""数据范围跟随用户输入（data_range_follow）+ 全链路接线的单测（2026-10-22）。

覆盖：跟随闸门（auto+有话才解析）、LLM 抽取结果收口、with_data_range 合并、
steps_payload 契约改写、_data_answer_gate 覆盖窗口核对、章节槽加粗残留清理、
封面兜底文案。LLM 一律打桩（零网络、零 DB）。
"""
import asyncio

from app.services import data_range_follow as drf
from app.services.data_range_follow import (
    extract_report_data_range, follow_wants, parse_range_reply)
from app.services.skill_node_runtime import split_answer_sections
from app.services.skill_target_contract import (
    USER_RANGE_LABEL, _report_window, format_document_contract, with_data_range)

import datetime as _dt

TODAY = _dt.date(2026, 10, 22)

DOC_ART = {
    "kind": "document", "slot": "data_report", "name": "商机趋势分析报告",
    "sections": [{"key": "weekly", "title": "周数据", "requires": "本周新增商机数"}],
    "data_range": {"mode": "auto"},
}


def _flow(data_range=None) -> dict:
    art = dict(DOC_ART)
    if data_range is not None:
        art = dict(art, data_range=data_range)
    return {
        "graph": {"nodes": [{"id": "agent", "type": "agent", "label": "趋势分析"}],
                  "edges": []},
        "node_configs": {"agent": {"enabled_tools": ["query_data"],
                                   "target": {"artifacts": [art]}}},
    }


OVERRIDE = {"mode": "custom", "start": "2026-01-01", "end": "2026-10-22",
            "label": USER_RANGE_LABEL}


# ── 跟随闸门：auto + 用户有话才解析 ──

def test_follow_wants_auto_with_text():
    assert follow_wants(_flow(), "给我从年初到现在的趋势报告") is True


def test_follow_wants_skips_explicit_config():
    assert follow_wants(_flow({"mode": "half_year"}), "从年初到现在") is False


def test_follow_wants_skips_without_doc_card_or_text():
    assert follow_wants({"node_configs": {"agent": {}}}, "从年初到现在") is False
    assert follow_wants(_flow(), "   ") is False


# ── LLM 抽取结果收口（确定性校验，不做日期正则） ──

def test_parse_range_reply_valid():
    got = parse_range_reply({"start": "2026-01-01", "end": "2026-10-22"}, TODAY)
    assert got == OVERRIDE


def test_parse_range_reply_swaps_reversed_dates():
    got = parse_range_reply({"start": "2026-10-22", "end": "2026-01-01"}, TODAY)
    assert got["start"] == "2026-01-01" and got["end"] == "2026-10-22"


def test_parse_range_reply_clamps_future_end():
    got = parse_range_reply({"start": "2026-01-01", "end": "2027-05-01"}, TODAY)
    assert got["end"] == "2026-10-23"  # 明天（含今天全天）


def test_parse_range_reply_unspecified_or_invalid():
    assert parse_range_reply({"start": None, "end": None}, TODAY) is None
    assert parse_range_reply({"start": "今年", "end": "x"}, TODAY) is None
    assert parse_range_reply("今年", TODAY) is None
    assert parse_range_reply(None, TODAY) is None


# ── extract：打桩 chat_json，验证闸门与降级 ──

def test_extract_skips_llm_when_not_following(monkeypatch):
    called = []

    async def fake_chat_json(*a, **kw):
        called.append(1)
        return {"start": None, "end": None}

    import app.services.llm_client as lc
    monkeypatch.setattr(lc, "chat_json", fake_chat_json)
    assert asyncio.run(extract_report_data_range(_flow({"mode": "half_year"}), "从年初到现在", TODAY)) is None
    assert asyncio.run(extract_report_data_range(_flow(), "  ", TODAY)) is None
    assert called == []


def test_extract_follows_user_window(monkeypatch):
    async def fake_chat_json(*a, **kw):
        return {"start": "2026-01-01", "end": "2026-10-22"}

    import app.services.llm_client as lc
    monkeypatch.setattr(lc, "chat_json", fake_chat_json)
    got = asyncio.run(extract_report_data_range(_flow(), "给我从年初到现在的商机趋势分析报告", TODAY))
    assert got == OVERRIDE


def test_extract_falls_back_on_llm_failure(monkeypatch):
    async def fake_chat_json(*a, **kw):
        raise RuntimeError("llm down")

    import app.services.llm_client as lc
    monkeypatch.setattr(lc, "chat_json", fake_chat_json)
    assert asyncio.run(extract_report_data_range(_flow(), "从年初到现在", TODAY)) is None


# ── with_data_range：只合报告卡，浅拷贝不改原配置 ──

def test_with_data_range_merges_doc_card_only():
    cfg = _flow()["node_configs"]["agent"]
    merged = with_data_range(cfg, OVERRIDE)
    art = merged["target"]["artifacts"][0]
    assert art["data_range"] == OVERRIDE
    # 原配置不被改动
    assert cfg["target"]["artifacts"][0]["data_range"] == {"mode": "auto"}


def test_with_data_range_noop_without_override():
    cfg = {"enabled_tools": ["query_data"]}
    assert with_data_range(cfg, None) is cfg
    assert with_data_range(cfg, {}) is cfg


def test_with_data_range_ignores_non_document_card():
    cfg = {"target": {"artifacts": [{"kind": "table", "columns": []}]}}
    assert with_data_range(cfg, OVERRIDE) == cfg


# ── 契约与窗口：覆盖后的契约/封面文案 ──

def test_report_window_custom_label_from_override():
    window, label = _report_window({"data_range": OVERRIDE})
    assert window == "2026.01.01 ~ 2026.10.22" and label == USER_RANGE_LABEL
    # 无 label 的 custom 维持原标签
    window2, label2 = _report_window({"data_range": {"mode": "custom", "start": "2026-01-01", "end": "2026-02-01"}})
    assert label2 == "自定义区间"


def test_document_contract_carries_user_window():
    art = with_data_range({"target": {"artifacts": [dict(DOC_ART)]}}, OVERRIDE)["target"]["artifacts"][0]
    text = format_document_contract(art)
    assert "数据范围：2026.01.01 ~ 2026.10.22（客户指定）" in text
    # auto（未覆盖）维持按实际数据边界口径
    assert "实际数据边界" in format_document_contract(DOC_ART)


def test_steps_payload_rewrites_contract_line():
    from app.services.skill_plan_runtime import steps_payload
    flow = _flow()
    steps_auto = steps_payload(flow)
    assert "实际数据边界" in steps_auto[0]["artifact"]
    steps_user = steps_payload(flow, data_range=OVERRIDE)
    assert "数据范围：2026.01.01 ~ 2026.10.22（客户指定）" in steps_user[0]["artifact"]


# ── 终检：覆盖窗口物理核对（用户要的窗口大脑没照抄 → 打回） ──

def test_data_answer_gate_checks_override_window():
    from app.services.skill_plan_runtime import _data_answer_gate
    ok_ctx = {"agent_result": {"answer": "数据范围：2026.01.01 ~ 2026.10.22（客户指定）\n\n一、周数据"},
              "flow_configs": _flow()["node_configs"], "data_range_override": OVERRIDE}
    assert _data_answer_gate(ok_ctx)["ok"] is True
    bad_ctx = {"agent_result": {"answer": "数据范围：2026.08.01 ~ 2026.10.22（近90天）\n\n一、周数据"},
               "flow_configs": _flow()["node_configs"], "data_range_override": OVERRIDE}
    g = _data_answer_gate(bad_ctx)
    assert not g["ok"] and g["reopen"] == "agent" and "2026.01.01 ~ 2026.10.22" in g["hint"]


def test_data_answer_gate_without_override_still_skips_auto():
    from app.services.skill_plan_runtime import _data_answer_gate
    ctx = {"agent_result": {"answer": "数据范围：2026.03.06 ~ 2026.10.21（按实际数据边界）"},
           "flow_configs": _flow()["node_configs"]}
    assert _data_answer_gate(ctx)["ok"] is True


# ── 章节槽加粗残留清理 ──

def test_split_strips_bold_leftovers():
    answer = ("数据范围：2026.01.01 ~ 2026.10.22\n"
              "一、周数据（10.09 ~ 10.15）**\n"
              "本周新增商机数 0。\n"
              "**\n"
              "二、月数据\n"
              "**\n累计商机 196 个。\n"
              "三、关键洞察\n"
              "**加粗**保持不动，行内正常。")
    slots = split_answer_sections(answer, DOC_ART_WITH_SECTIONS)
    assert slots["weekly"] == "（10.09 ~ 10.15）\n本周新增商机数 0。"
    assert slots["monthly"] == "累计商机 196 个。"
    # 正常加粗（** 成对）原样保留，失衡尾巴才剥
    assert slots["insights"] == "**加粗**保持不动，行内正常。"


DOC_ART_WITH_SECTIONS = [
    {"key": "weekly", "title": "周数据"},
    {"key": "monthly", "title": "月数据"},
    {"key": "insights", "title": "关键洞察"},
]


# ── 封面兜底文案：auto 且未跟随时不再谎报「近 8 周」 ──

def test_default_payload_fallback_label_is_honest():
    from app.services.artifact_render import _default_payload
    meta = _default_payload({}, "模板")["meta"]
    assert "近 8 周" not in meta["period_label"]
    assert "全部数据" in meta["period_label"]


# ── 引擎离线 e2e：回合开始抽取 → 覆盖进契约与 document_target（零 LLM/零 DB） ──

def _report_flow() -> dict:
    return {
        "graph": {"nodes": [
                {"id": "input", "type": "input", "label": "输入"},
                {"id": "agent", "type": "agent", "label": "趋势分析"},
                {"id": "output", "type": "output", "label": "输出"}],
            "edges": [{"id": "e1", "source": "input", "target": "agent"},
                      {"id": "e2", "source": "agent", "target": "output"}]},
        "node_configs": {
            "input": {},
            "agent": {"enabled_tools": ["query_data"],
                      "target": {"artifacts": [dict(DOC_ART)]}},
            "output": {"output_kind": "data_answer",
                       "payload_map": {"answer": "ctx.agent_result.answer"}},
        },
    }


def test_engine_run_backfills_override_end_to_end(monkeypatch):
    import app.services.llm_client as lc
    import app.services.skill_turn_engine as ste

    async def fake_chat_json(*a, **kw):
        return {"start": "2026-01-01", "end": "2026-10-22"}

    async def fake_brain(user_msg, *, loop_kwargs, settle, emit_status=None,
                         findings_out=None, **kw):
        result = {"answer": "数据范围：2026.01.01 ~ 2026.10.22（客户指定）\n\n一、周数据\n本周新增 0。",
                  "tool_calls_log": []}
        return result, str((await settle(result) or {}).get("action") or "done")

    monkeypatch.setattr(lc, "chat_json", fake_chat_json)
    monkeypatch.setattr(ste, "run_brain_attempts", fake_brain)

    rt = ste._SkillTurnRuntime(
        thread_id="t-dr-follow", role_key="data_analyst", persona="测试人设",
        full_text="给我从年初到现在的商机趋势分析报告", history=[], ext={}, mem={},
        flow=_report_flow())
    engine = asyncio.run(rt.run())
    assert engine["engine_result"] == "done"
    assert engine["data_range_override"] == OVERRIDE
    assert engine["document_target"]["data_range"] == OVERRIDE
