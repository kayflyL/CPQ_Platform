# -*- coding: utf-8 -*-
"""turn_breaker（P0-② 熔断阶梯）+ agent_react 重复调用守卫单测。

断路器默认 observe-only：只记观察不动作；supervise 的 hard_stop 语义必须与旧
asyncio.wait(timeout=900) 完全等价（skill_chat._run_task 依赖这一点走暂停分支）。
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

from app.services.turn_breaker import (
    CONSTRAINED, HEALTHY, STEERING, ToolRepeatGuard, TurnBreaker,
)


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, s):
        self.now += s


# ── ToolRepeatGuard ─────────────────────────────────────────────────


def test_repeat_guard_trips_at_limit():
    g = ToolRepeatGuard(limit=4)
    assert g.record("search", {"q": "cpu"}) is False
    assert g.record("search", {"q": "cpu"}) is False
    assert g.record("search", {"q": "cpu"}) is False
    assert g.record("search", {"q": "cpu"}) is True


def test_repeat_guard_resets_on_different_args():
    g = ToolRepeatGuard(limit=4)
    for _ in range(3):
        g.record("search", {"q": "cpu"})
    assert g.record("search", {"q": "mem"}) is False  # 换参数归零
    assert g.record("search", {"q": "cpu"}) is False  # 换回来也重新数


def test_repeat_guard_default_limit_is_six():
    g = ToolRepeatGuard()
    results = [g.record("t", {}) for _ in range(6)]
    assert results == [False] * 5 + [True]


# ── TurnBreaker.evaluate 档位 ────────────────────────────────────────


def test_level_ladder_by_wall_clock():
    clock = FakeClock()
    b = TurnBreaker(thread_id="t1", clock=clock, steer_after=180.0, constrain_after=360.0)
    assert b.level == HEALTHY
    assert b.evaluate() is False
    clock.advance(181.0)
    assert b.evaluate() is True and b.level == STEERING
    assert b.evaluate() is False  # 同档不重复升
    clock.advance(180.0)  # 361s
    assert b.evaluate() is True and b.level == CONSTRAINED


def test_no_progress_escalates_before_wall_clock():
    clock = FakeClock()
    b = TurnBreaker(thread_id="t1", clock=clock, steer_after=180.0,
                    constrain_after=360.0, no_progress_after=150.0)
    clock.advance(60.0)  # 墙钟未到 steer，但事件静默 60s？不够
    assert b.evaluate() is False
    clock.advance(100.0)  # 静默 160s ≥ 150 → 无进展升 steer
    assert b.evaluate() is True and b.level == STEERING
    kinds = [o["kind"] for o in b.observations]
    assert "no_progress" in kinds and "escalate" in kinds


def test_event_resets_no_progress_window():
    clock = FakeClock()
    # 墙钟阈值拉大，只验证「事件重置静默窗口」这一个变量
    b = TurnBreaker(thread_id="t1", clock=clock, steer_after=1000.0,
                    constrain_after=2000.0, no_progress_after=150.0)
    clock.advance(100.0)
    b.observe({"type": "chunk", "delta": "x"})  # 事件=有进展
    clock.advance(100.0)  # 距事件仅 100s < 150
    assert b.evaluate() is False


# ── TurnBreaker.observe 节点重入 ─────────────────────────────────────


def test_node_reentry_observed_at_third_entry():
    b = TurnBreaker(thread_id="t1", node_reentry_limit=3)
    for _ in range(2):
        b.observe({"type": "step_start", "step": "agent_fill"})
        assert not [o for o in b.observations if o["kind"] == "node_reentry"]
    b.observe({"type": "step_start", "step": "agent_fill"})
    hits = [o for o in b.observations if o["kind"] == "node_reentry"]
    assert len(hits) == 1 and hits[0]["step"] == "agent_fill" and hits[0]["count"] == 3


def test_node_trace_running_counts_as_entry():
    b = TurnBreaker(thread_id="t1", node_reentry_limit=3)
    b.observe({"type": "node_trace", "step": "kp_pick", "status": "running"})
    b.observe({"type": "node_trace", "step": "kp_pick", "status": "done"})  # done 不计
    b.observe({"type": "node_trace", "step": "kp_pick", "status": "running"})
    assert not [o for o in b.observations if o["kind"] == "node_reentry"]
    b.observe({"type": "node_trace", "step": "kp_pick", "status": "running"})
    assert [o for o in b.observations if o["kind"] == "node_reentry"]


def test_observe_never_raises_on_garbage():
    b = TurnBreaker(thread_id="t1")
    b.observe(None)
    b.observe("string")
    b.observe({"type": None, "step": 42})
    b.observe({"type": "step_start", "step": ["not", "str"]})


# ── wrap_sink ────────────────────────────────────────────────────────


def test_wrap_sink_observes_and_forwards():
    clock = FakeClock()
    seen = []
    b = TurnBreaker(thread_id="t1", clock=clock)

    async def sink(payload):
        seen.append(payload)

    wrapped = b.wrap_sink(sink)
    asyncio.run(wrapped({"type": "chunk", "delta": "hi"}))
    assert seen == [{"type": "chunk", "delta": "hi"}]
    clock.advance(50.0)
    assert b.evaluate() is False  # 事件喂过观察器，静默窗口从事件起算


def test_wrap_sink_works_without_underlying_sink():
    b = TurnBreaker(thread_id="t1")
    wrapped = b.wrap_sink(None)
    asyncio.run(wrapped({"type": "chunk"}))  # 不抛即过


# ── supervise ────────────────────────────────────────────────────────


def test_supervise_completed_task():
    b = TurnBreaker(thread_id="t1", poll_interval=0.05)

    async def quick():
        return 42

    async def run():
        task = asyncio.ensure_future(quick())
        return await b.supervise(task)

    done, pending, why = asyncio.run(run())
    assert why == "completed" and not pending and len(done) == 1


def test_supervise_hard_stop_matches_legacy_semantics():
    # 硬上限语义=旧 asyncio.wait(timeout=900)：到点返回 pending，由调用方 cancel+暂停
    b = TurnBreaker(thread_id="t1", poll_interval=0.05, hard_stop_after=0.12)

    async def hang():
        await asyncio.sleep(30)

    async def run():
        task = asyncio.ensure_future(hang())
        done, pending, why = await b.supervise(task)
        task.cancel()
        return done, pending, why

    done, pending, why = asyncio.run(run())
    assert why == "hard_stop" and not done and len(pending) == 1


def test_supervise_constrained_cancels_when_armed():
    b = TurnBreaker(thread_id="t1", poll_interval=0.02, steer_after=0.01,
                    constrain_after=0.05, hard_stop_after=60.0, armed=True)

    async def hang():
        await asyncio.sleep(30)

    async def run():
        task = asyncio.ensure_future(hang())
        return await b.supervise(task)

    done, pending, why = asyncio.run(run())
    assert why == "constrained" and not done and len(pending) == 1
    assert any(o["kind"] == "constrained_cancel" for o in b.observations)


def test_supervise_observe_only_never_cancels():
    # observe-only：constrain 档位升了也不动手，一路放到 hard_stop
    b = TurnBreaker(thread_id="t1", poll_interval=0.02, steer_after=0.01,
                    constrain_after=0.03, hard_stop_after=0.15, armed=False)

    async def hang():
        await asyncio.sleep(30)

    async def run():
        task = asyncio.ensure_future(hang())
        done, pending, why = await b.supervise(task)
        task.cancel()
        return done, pending, why

    done, pending, why = asyncio.run(run())
    assert why == "hard_stop" and len(pending) == 1
    assert b.level == CONSTRAINED
    assert not [o for o in b.observations if o["kind"] == "constrained_cancel"]


# ── agent_react 守卫接线 ─────────────────────────────────────────────


def _native_tool_call(name, args, call_id="call_1"):
    return {
        "message": {"role": "assistant", "content": None},
        "tool_calls": [{"id": call_id, "name": name, "arguments": args,
                        "arguments_raw": json.dumps(args, ensure_ascii=False)}],
    }


def test_react_loop_aborts_on_identical_repeat_calls():
    """同名同参连调 6 次 → 循环止损，error=repeat_tool:*（09-12 死循环家族防线）。"""
    from app.services import agent_react
    from app.services.agent_tool_registry import ToolRegistry
    reg = ToolRegistry()

    async def fake_h(args):
        return {"ok": True}

    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h)
    responses = [_native_tool_call("fake_tool", {"k": 1}, call_id=f"c{i}") for i in range(9)]
    with patch("app.services.agent_react.build_tool_registry", return_value=reg), \
            patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=responses)):
        out = asyncio.run(agent_react.run_react_loop(
            "req", {"enabled_tools": ["fake_tool"]}, max_iterations=9))
    assert out["ok"] is False
    assert str(out.get("error") or "").startswith("repeat_tool:fake_tool")
    assert len(out["tool_calls_log"]) == 5  # 第 6 次被拦，不执行


def test_react_loop_allows_varying_repeat_calls():
    """同工具不同参数的多次调用是合法检索 → 不触发守卫。"""
    from app.services import agent_react
    from app.services.agent_tool_registry import ToolRegistry
    reg = ToolRegistry()

    async def fake_h(args):
        return {"ok": True}

    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h)
    responses = [_native_tool_call("fake_tool", {"k": i}, call_id=f"c{i}") for i in range(5)]
    responses.append({"message": {"role": "assistant", "content": "done"}, "tool_calls": []})
    with patch("app.services.agent_react.build_tool_registry", return_value=reg), \
            patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=responses)):
        out = asyncio.run(agent_react.run_react_loop(
            "req", {"enabled_tools": ["fake_tool"]}, max_iterations=6))
    assert out["ok"] is True and out["answer"] == "done"
    assert len(out["tool_calls_log"]) == 5
