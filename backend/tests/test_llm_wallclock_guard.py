# -*- coding: utf-8 -*-
"""P2.5 稳健性回归：单轮模型调用必须有墙钟上限，超时/零产出必须如实收敛。

背景（实测事故）：间隔看门狗只约束「两次输出之间的空隙」，慢速持续吐 reasoning 的模型会把
看门狗无限重置 → 单轮静默空转 1605s，前端看板一直转圈、客户看不到任何东西。
四道闸（由内到外）：
  1) 通道级单轮墙钟上限（llm_client / anthropic_channel），到点抛 LLMError；
  2) 超时收口成 LLMError，不得误报成「通道不支持原生 tools」（否则白降级掉工具通道）；
  3) 编排壳每次尝试 = min(剩余预算, 单轮上限)，wait_for 兜最后一道；
  4) 整轮零产出 → 失败终态可见（不静默留 last_step、不弹零选项死卡）。
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import anthropic_channel, llm_client, skill_turn_engine  # noqa: E402


def _cfg(**kw) -> dict:
    base = {"enabled": True, "base_url": "http://x", "api_key": "k", "model": "qwen-plus",
            "temperature": 0.7, "max_tokens": 1000}
    base.update(kw)
    return base


def _reasoning_chunk(text: str):
    delta = SimpleNamespace(reasoning_content=text, content=None, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=None, delta=delta)])


def test_stream_agent_chat_cuts_endless_reasoning_by_wall_clock():
    """慢速无限吐 reasoning：间隔看门狗永不触发，单轮墙钟上限必须断开。"""
    async def _stream():
        for _ in range(100000):
            await asyncio.sleep(0.02)
            yield _reasoning_chunk("想")

    fake_client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=AsyncMock(return_value=_stream()))))

    async def scenario():
        with patch.object(llm_client, "_get_llm_config", return_value=_cfg()), \
                patch.object(llm_client, "_client", return_value=fake_client):
            out = []
            async for item in llm_client.stream_agent_chat(
                    [{"role": "user", "content": "hi"}], overall_timeout=0.2):
                out.append(item)
            return out

    try:
        asyncio.run(scenario())
        raise AssertionError("无限输出必须在墙钟上限处断开")
    except llm_client.LLMError as e:
        assert "整体超时" in str(e), f"超时原因要如实（区分于首字节/间隔超时）：{e}"


def test_anthropic_timeout_is_llm_error_not_native_unsupported():
    """Anthropic 通道超时 ≠ 不支持原生 tools：误报会让上层白白降级掉工具通道。"""
    async def _boom(messages, **kwargs):
        raise anthropic_channel.AnthropicTimeoutError("Anthropic 单轮生成整体超时：超过 1s 仍未收敛，已断开")
        yield  # pragma: no cover —— 让它成为 async generator

    tools = [{"type": "function", "function": {"name": "query_parts",
              "parameters": {"type": "object", "properties": {}}}}]

    async def scenario():
        with patch.object(llm_client, "_get_llm_config",
                          return_value=_cfg(upstream_format="anthropic")), \
                patch.object(anthropic_channel, "stream", _boom):
            async for _ in llm_client.stream_agent_chat(
                    [{"role": "user", "content": "hi"}], tools=tools):
                pass

    try:
        asyncio.run(scenario())
        raise AssertionError("应抛出 LLMError")
    except llm_client.LLMNativeToolsUnsupported as e:
        raise AssertionError(f"超时被误报成 unsupported（会白降级工具通道）：{e}")
    except llm_client.LLMError as e:
        assert "超时" in str(e)


def test_brain_attempt_wall_clock_caps_hung_round_and_reports_timeout():
    """内层挂死（run_stream_chat_loop 永不返回）：wait_for 兜最后一道，如实交 timeout。"""
    statuses: list = []
    calls = {"n": 0}

    async def hung_loop(msg, **kwargs):
        calls["n"] += 1
        await asyncio.sleep(30)
        return {"answer": "never"}

    async def settle(result):
        return {"action": "retry", "feedback": "bad"}

    async def emit_status(text):
        statuses.append(str(text))

    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", hung_loop):
            return await skill_turn_engine.run_brain_attempts(
                "客户消息", loop_kwargs={}, settle=settle, emit_status=emit_status,
                deadline_s=0.4, max_attempts=3)

    _result, action = asyncio.run(scenario())
    assert action == "timeout", "挂死必须收敛成 timeout，不能无限等"
    assert calls["n"] == 1, "到点不再发起新尝试"
    assert any("耗时较长" in s for s in statuses), "到点状态对客户可见（不静默）"


def test_brain_attempt_passes_tightened_round_timeout():
    """每次尝试的单轮上限 = min(剩余预算, 单轮上限)：内层通道照此收紧，不能放开。"""
    seen: list = []

    async def fake_loop(msg, **kwargs):
        seen.append(kwargs.get("llm_overall_timeout"))
        return {"answer": "好了", "tool_calls_log": []}

    async def settle(result):
        return {"action": "done"}

    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop):
            return await skill_turn_engine.run_brain_attempts(
                "客户消息", loop_kwargs={}, settle=settle,
                deadline_s=420.0, round_timeout_s=60.0)

    _result, action = asyncio.run(scenario())
    assert action == "done"
    assert seen == [60.0], "单轮上限必须下发到流式循环（否则内层仍可无限长跑）"


def test_brain_attempt_with_answer_skips_tool_rejection_retry():
    """大脑已产出收口正文时，日志里的历史工具拒绝不得触发整轮重开。

    探索型步骤（query_data 试错→自我纠正→写报告）的失败调用是常态；一律重开会把
    已完成的报告丢弃重生成（2026-09-16 趋势分析三份连体报告事故）。
    """
    calls = {"n": 0}

    async def loop_with_stale_rejection(msg, **kwargs):
        calls["n"] += 1
        return {"answer": "数据范围：2026.01.01 ~ 2026.09.12\n\n## 一、周数据",
                "tool_calls_log": [
                    {"name": "query_data", "args": {"sql": "bad"},
                     "result": {"ok": False, "error": "表不在白名单"}},
                    {"name": "query_data", "args": {"sql": "good"},
                     "result": {"ok": True, "rows": []}},
                ]}

    settles = []

    async def settle(result):
        settles.append(result)
        return {"action": "done"}

    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", loop_with_stale_rejection):
            return await skill_turn_engine.run_brain_attempts(
                "发起趋势分析", loop_kwargs={}, settle=settle,
                deadline_s=420.0, max_attempts=3)

    result, action = asyncio.run(scenario())
    assert action == "done"
    assert calls["n"] == 1, "已有正文的尝试不得因历史工具拒绝重开"
    assert len(settles) == 1, "收口判定必须执行（产物说了算）"
    assert "数据范围" in result["answer"]


def test_brain_attempt_without_answer_still_feeds_rejection_back():
    """没有收口正文 + 工具被拒：保持回喂重试（原行为，防丢掉纠错线索）。"""
    calls = {"n": 0}

    async def rejected_then_fixed(msg, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"answer": "", "tool_calls_log": [
                {"name": "query_data", "args": {"sql": "bad"},
                 "result": {"ok": False, "error": "表不在白名单"}}]}
        return {"answer": "补好了", "tool_calls_log": []}

    async def settle(result):
        return {"action": "done"}

    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", rejected_then_fixed):
            return await skill_turn_engine.run_brain_attempts(
                "客户消息", loop_kwargs={}, settle=settle,
                deadline_s=420.0, max_attempts=3)

    result, action = asyncio.run(scenario())
    assert action == "done"
    assert calls["n"] == 2, "无正文时工具拒绝仍要回喂重试一次"
    assert result["answer"] == "补好了"


def test_orphan_step_marks_visible_failure_instead_of_dead_card():
    """大脑整轮零产出 → 失败终态：不静默留 last_step，也不弹零选项死卡。"""
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    from app.services.skill_plan_runtime import engine_result_of
    from app.services.skill_chat import _failure_reply
    flow = ReasoningFlowRepository().get_active_flow("requirement_analysis")
    assert flow, "需求分析 active flow 未播种"
    events: list = []

    async def empty_loop(msg, **kwargs):
        return {}                       # 零正文、零工具：这一轮什么都没产出

    async def sink(payload):
        events.append(payload)

    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", empty_loop):
            return await skill_turn_engine.run_skill_agent_turn(
                thread_id="t_empty", role_key="tech", persona="测试人设",
                full_text="需要一台服务器", history=[], ext={}, mem={}, flow=flow,
                event_sink=sink, price_ok=True, opportunity_id="o_empty")

    engine = asyncio.run(scenario())
    assert engine.get("engine_result") == "failed", "零产出不得静默收工"
    fail = engine.get("engine_failure") or {}
    assert fail.get("reason_code") == "brain_no_output" and fail.get("step"), fail
    assert any(e.get("type") == "pipeline_paused" and e.get("failure") for e in events), \
        "失败要广播终态（看板不能一直空转）"
    er = engine_result_of(engine)
    assert er["status"] == "failed"
    reply = _failure_reply(er["failure"])
    assert "可采用的产出" in reply and "继续" in reply
    assert "编造" in reply


def test_brain_dead_is_pure_fact_judgement():
    """零产出判定是纯事实（无正文、无成功工具），与节点/话术无关。"""
    dead = skill_turn_engine._SkillTurnRuntime._brain_dead
    assert dead({}) is True
    assert dead(None) is True
    assert dead({"answer": "  "}) is True
    assert dead({"tool_calls_log": [{"result": {"ok": False, "error": "x"}}]}) is True
    assert dead({"answer": "已登记"}) is False
    assert dead({"tool_calls_log": [{"result": {"ok": True}}]}) is False


def test_abort_step_sets_structured_failure():
    """失败载荷只带结构化事实（节点 + 原因码 + 标签），不含话术模板。"""
    from app.services.skill_chat import _failure_reply
    rt = skill_turn_engine._SkillTurnRuntime(
        thread_id="t_abort", role_key="tech", persona="p", full_text="f",
        history=[], ext={}, mem={}, flow={})
    rt.engine = {"steps_done": set()}
    rt.narration = []
    rt.node_narration = {}
    rt._cur_step = {"key": "kp_reason", "label": "配件选型"}
    events: list = []

    async def sink(payload):
        events.append(payload)

    rt.event_sink = sink
    act = asyncio.run(rt._abort_step("kp_reason", "llm_timeout"))
    assert "生成超时" in _failure_reply({"reason_code": "llm_timeout", "label": "配件选型"})
    assert "生成超时" not in _failure_reply({"reason_code": "brain_no_output", "label": "配件选型"})
    assert act == "failed"
    assert rt.engine["engine_result"] == "failed"
    fail = rt.engine["engine_failure"]
    assert fail == {"step": "kp_reason", "reason_code": "llm_timeout", "label": "配件选型"}
    assert [e.get("type") for e in events] == ["pipeline_paused"]


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  OK {fn.__name__}"); passed += 1
        except Exception:
            print(f"  FAIL {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
