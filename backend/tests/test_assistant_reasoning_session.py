# -*- coding: utf-8 -*-
"""方案助手需求分析通道：会话状态（thread reasoning_state）+ run_pipeline 会话化。

覆盖 2026-08-05 的会话抽象：
- ReasoningSession('thread') 读写 assistant_threads.reasoning_state（与商机 extra_fields 平行）；
- run_pipeline 绑定 thread 会话 + 自定义 hub 时，clarify/目录状态落在会话上，
  pipeline 事件经 collector 收集（candidates_ready 可落库重放）。
跑法（backend 目录）：python -X utf8 -m pytest tests/test_assistant_reasoning_session.py -q
"""
import asyncio
import pytest

from app.repository.assistant_repo import AssistantRepository
from app.services.reasoning_session import ReasoningSession


def _make_thread(title="会话状态测试"):
    repo = AssistantRepository()
    try:
        t = repo.create_thread(created_by="test_user", title=title)
        return t["thread_id"]
    finally:
        repo.close()


def test_reasoning_session_thread_roundtrip():
    tid = _make_thread()
    sess = ReasoningSession(tid, "thread")
    assert sess.get_extra() == {}
    sess.update_meta({"requirement_clarity_round": 3, "requirement_clarity_base": "2U 服务器"})
    extra = sess.get_extra()
    assert extra.get("requirement_clarity_round") == 3
    assert extra.get("requirement_clarity_base") == "2U 服务器"
    # 合并写：不覆盖已有键
    sess.update_meta({"requirement_clarity_defaults": ["scene"]})
    extra = sess.get_extra()
    assert extra["requirement_clarity_round"] == 3
    assert extra["requirement_clarity_defaults"] == ["scene"]


class FakeHub:
    """内存广播 hub：收 pipeline 事件（替代 assistant_hub/ reasoning_hub）。"""
    def __init__(self):
        self.events: list = []

    async def broadcast(self, room_id: str, payload: dict):
        self.events.append(payload)


def test_run_pipeline_thread_session_linear_fallback(monkeypatch):
    """无 active flow（回退线性 5 步，不调 LLM）时，pipeline 绑定 thread 会话：
    状态落 assistant_threads.reasoning_state，事件经 collector 收集。"""

    async def _run():
        tid = _make_thread()
        hub = FakeHub()
        collected: list = []

        # 强制走线性 fallback：get_active_flow 返回 None（避免图执行器里的 LLM 节点拖慢/依赖外网）
        from app.repository import reasoning_flow_repo as rfr
        monkeypatch.setattr(rfr.ReasoningFlowRepository, "get_active_flow", lambda self: None)

        from app.services.requirement_intel_service import run_pipeline
        await run_pipeline(
            tid,
            "2U 服务器，AMD 9654 双路，8条32G内存，2块960G SATA SSD，预算10万",
            supplement=None,
            force_complete=True,
            session=ReasoningSession(tid, "thread"),
            hub=hub,
            collector=collected.append,
        )
        return tid, hub, collected

    tid, hub, collected = asyncio.run(_run())

    types = [e.get("type") for e in hub.events]
    assert "pipeline_start" in types
    assert types[-1] in ("pipeline_done", "pipeline_paused", "error")
    # 会话状态已落到 thread（反问轮次/需求原文被持久化）
    sess = ReasoningSession(tid, "thread")
    extra = sess.get_extra()
    assert extra.get("requirement_clarity_base") == "2U 服务器，AMD 9654 双路，8条32G内存，2块960G SATA SSD，预算10万"
    assert "requirement_clarity_round" in extra
    # collector 拿到 candidates_ready（有基准配置库时）或至少收到全部事件
    assert len(collected) == len(hub.events)
    if any(e.get("type") == "candidates_ready" for e in collected):
        plans = next(e for e in collected if e.get("type") == "candidates_ready").get("plans") or []
        assert len(plans) >= 1
