# -*- coding: utf-8 -*-
"""trend_analysis（data_answer 型 workflow）交付链测试（2026-09-15 修复回归）。

审计实锤 trend_analysis 四层断裂后修复：skill_key 穿透 + agent_result 接线 +
终检/收尾按 output_kind 分派。本文件锁三件事：
1. delivery_gate 注册表：data_answer 两态；未登记 kind 回落 final_gate（需求分析语义不变）
2. 引擎离线端到端：trend 形状 flow + 假大脑 → done + agent_result 落位 + output_payload.answer
3. 需求分析回归护栏：同引擎路径下无机型锁的 requirement 形状流仍被 final_gate 拦截
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ANSWER = "SSD 价格 9 月环比涨 3%，建议关注 1.92T 企业级"


def test_delivery_gate_data_answer_two_states():
    from app.services.skill_plan_runtime import delivery_gate
    gate = delivery_gate({"agent_result": {"answer": ANSWER}}, "data_answer")
    assert gate["ok"] is True
    gate = delivery_gate({"agent_result": {"answer": "   "}}, "data_answer")
    assert gate["ok"] is False
    assert "数据结论" in gate["hint"]
    gate = delivery_gate({}, "data_answer")
    assert gate["ok"] is False


def test_delivery_gate_unregistered_kind_falls_back_to_final_gate():
    from app.services.skill_plan_runtime import delivery_gate, final_gate
    ctx = {"ext": {}, "_locked_baseline": {}}  # 无机型锁
    assert delivery_gate(ctx, "")["ok"] is False
    assert delivery_gate(ctx, "bom_scheme_draft")["ok"] is False
    # 与旧 final_gate 同语义同文案（需求分析路径不串）
    assert delivery_gate(ctx, "")["hint"] == final_gate(ctx)["hint"]
    assert "机型" in delivery_gate(ctx, "")["hint"]


def _trend_flow() -> dict:
    return {
        "id": 126, "name": "trend_analysis", "skill_key": "trend_analysis",
        "graph": {
            "nodes": [
                {"id": "input", "type": "input", "label": "输入"},
                {"id": "agent", "type": "agent", "label": "趋势分析", "position": {"x": 1, "y": 1}},
                {"id": "output", "type": "output", "label": "输出·数据结论", "position": {"x": 2, "y": 1}},
            ],
            "edges": [
                {"id": "e1", "source": "input", "target": "agent"},
                {"id": "e2", "source": "agent", "target": "output"},
            ],
        },
        "node_configs": {
            "input": {},
            "agent": {"enabled_tools": ["query_data"], "max_iterations": 6,
                      "system_prompt": "", "rule_types": []},
            "output": {"output_kind": "data_answer",
                       "payload_map": {"answer": "ctx.agent_result.answer"},
                       "target": "conversation_reply", "actions": []},
        },
    }


def test_trend_engine_offline_e2e(monkeypatch):
    """trend 形状流 + 假大脑（零 LLM/零 DB）：过 data_answer 终检 → 交付带结论。"""
    import app.services.skill_turn_engine as ste

    async def fake_brain(user_msg, *, loop_kwargs, settle, emit_status=None,
                         findings_out=None, **kw):
        result = {"answer": ANSWER, "tool_calls_log": []}
        verdict = await settle(result)
        return result, str((verdict or {}).get("action") or "done")

    monkeypatch.setattr(ste, "run_brain_attempts", fake_brain)
    events: list[dict] = []

    async def sink(ev: dict) -> None:
        events.append(ev)

    rt = ste._SkillTurnRuntime(
        thread_id="t-test-trend", role_key="data_analyst", persona="测试人设",
        full_text="看下 SSD 价格趋势", history=[], ext={}, mem={},
        flow=_trend_flow(), event_sink=sink)
    engine = asyncio.run(rt.run())
    assert engine["engine_result"] == "done"
    assert "agent" in engine["steps_done"]
    assert engine["agent_result"]["answer"] == ANSWER
    assert engine["output_kind"] == "data_answer"
    # 挂真实 sink 广播不抛异常，output_payload 必须是映射后的真 payload（回归：
    # 曾被 finalize_output 的 handoff 信封返回值覆盖，answer 被嵌进 .payload 丢一层）
    assert engine["output_payload"]["answer"] == ANSWER


def test_requirement_engine_still_gated_without_model(monkeypatch):
    """回归护栏：requirement 形状流（output_kind=bom_scheme_draft 缺省 seed）无机型锁
    → 仍被 final_gate 拦截成 gaps，data_answer 分派不串到需求分析路径。"""
    import app.services.skill_turn_engine as ste

    async def fake_brain(user_msg, *, loop_kwargs, settle, emit_status=None,
                         findings_out=None, **kw):
        # 大脑只产出了对话答复（没选机型）——需求分析语义下这不算交付
        result = {"answer": "好的我来看看", "tool_calls_log": []}
        verdict = await settle(result)
        return result, str((verdict or {}).get("action") or "done")

    monkeypatch.setattr(ste, "run_brain_attempts", fake_brain)
    flow = {
        "id": 41, "name": "requirement_analysis", "skill_key": "requirement_analysis",
        "graph": {
            "nodes": [
                {"id": "input", "type": "input", "label": "输入"},
                {"id": "agent_fill", "type": "agent_fill", "label": "登记"},
                {"id": "output", "type": "output", "label": "输出·BOM方案草稿"},
            ],
            "edges": [
                {"id": "e1", "source": "input", "target": "agent_fill"},
                {"id": "e2", "source": "agent_fill", "target": "output"},
            ],
        },
        "node_configs": {
            "input": {},
            "agent_fill": {"enabled_tools": []},  # 机制保底 fill_requirement/ask_user 仍在
            "output": {"output_kind": "bom_scheme_draft",
                       "payload_map": {"ext": "ctx.ext", "plans": "ctx.plans"},
                       "actions": []},
        },
    }
    rt = ste._SkillTurnRuntime(
        thread_id="t-test-req", role_key="sales", persona="测试人设",
        full_text="我要一台服务器", history=[], ext={}, mem={}, flow=flow)
    engine = asyncio.run(rt.run())
    assert engine["engine_result"] != "done"
    assert engine.get("awaiting_input") is True


def test_document_node_history_drops_stale_reports(monkeypatch):
    """document 产物节点的输入卫生：历史里「报告形状」的 assistant 消息（数据范围：指纹）
    在组上下文时确定性剔除——锚定复读的毒源在入口移除，出口闸门只作保险丝（2026-09-16）。"""
    import app.services.skill_turn_engine as ste

    captured = {}

    async def fake_brain(user_msg, *, loop_kwargs, settle, emit_status=None,
                         findings_out=None, **kw):
        captured["history"] = loop_kwargs.get("history")
        result = {"answer": ANSWER, "tool_calls_log": []}
        verdict = await settle(result)
        return result, str((verdict or {}).get("action") or "done")

    async def sink(ev):
        pass

    monkeypatch.setattr(ste, "run_brain_attempts", fake_brain)
    flow = _trend_flow()
    flow["node_configs"]["agent"]["target"] = {"artifacts": [
        {"kind": "document", "slot": "data_report", "name": "商机趋势分析报告",
         "sections": [{"key": "weekly", "title": "周数据", "requires": "本周新增"}]}]}
    history = [
        {"role": "user", "content": "请开始趋势分析"},
        {"role": "assistant",
         "content": "数据范围：2026.03.06 ~ 2026.09.15（按实际数据边界）\n\n## 一、周数据"},
        {"role": "user", "content": "重新按配置窗口出"},
        {"role": "assistant", "content": "好的，这次按配置窗口统计"},
    ]
    rt = ste._SkillTurnRuntime(
        thread_id="t-hist-doc", role_key="data_analyst", persona="测试人设",
        full_text="再来一次", history=history, ext={}, mem={},
        flow=flow, event_sink=sink)
    engine = asyncio.run(rt.run())
    assert engine["engine_result"] == "done"
    kept = captured["history"]
    assistants = [m for m in kept if m.get("role") == "assistant"]
    assert assistants and all("数据范围：" not in str(m.get("content") or "") for m in assistants),         "旧报告（assistant+数据范围指纹）必须被剔除"
    assert any("配置窗口" in str(m.get("content") or "") for m in assistants),         "非报告 assistant 消息保留（对话连续性不受影响）"
    assert any(m.get("role") == "user" and "趋势分析" in str(m.get("content") or "") for m in kept)


def test_nondocument_node_keeps_history_verbatim(monkeypatch):
    """无 document 产物的步骤历史原样进循环：输入卫生只归 document 产物节点，需求分析路径零接触。"""
    import app.services.skill_turn_engine as ste

    captured = {}

    async def fake_brain(user_msg, *, loop_kwargs, settle, emit_status=None,
                         findings_out=None, **kw):
        captured["history"] = loop_kwargs.get("history")
        result = {"answer": ANSWER, "tool_calls_log": []}
        verdict = await settle(result)
        return result, str((verdict or {}).get("action") or "done")

    async def sink(ev):
        pass

    monkeypatch.setattr(ste, "run_brain_attempts", fake_brain)
    history = [
        {"role": "user", "content": "请开始"},
        {"role": "assistant", "content": "数据范围：2026.03.06 ~ 2026.09.15\n## 一、周数据"},
    ]
    rt = ste._SkillTurnRuntime(
        thread_id="t-hist-keep", role_key="data_analyst", persona="测试人设",
        full_text="继续", history=history, ext={}, mem={},
        flow=_trend_flow(), event_sink=sink)
    asyncio.run(rt.run())
    assert captured["history"] == history, "非 document 节点不得动历史"
