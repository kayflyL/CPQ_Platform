# -*- coding: utf-8 -*-
"""思考流工具卡（2026-10-02）的 WS 广播契约：agent_react 工具事件带 phase，
event_sink 必须广播 {"type":"tool_trace","tool","phase"}——前端工具活动卡
「同一工具 start→done 原地翻状态」依赖这个形状。

真机链路是 LLM 流式循环；这里用假循环钓出真实 event_sink 闭包喂数据，
拦掉写库/办公事件两条旁路，只验证广播形状：
- tool + phase(start/done) → tool_trace 两条（时序保序）
- tool 无 phase（旧形状）→ 只走 chat_status 文案，不产生 tool_trace
- thinking 通道不受影响
"""
import asyncio


def test_tool_trace_broadcast_contract(monkeypatch):
    from app.services import colleague_turn_runners as runners

    broadcasts = []

    async def fake_broadcast(tid, payload):
        broadcasts.append((tid, dict(payload)))

    async def fake_publish(*a, **kw):
        pass

    async def fake_persist(*a, **kw):
        pass  # 落库路径与本契约无关，拦在仓库外

    monkeypatch.setattr(runners.assistant_hub, "broadcast", fake_broadcast)
    monkeypatch.setattr(runners, "publish_office_event", fake_publish)
    monkeypatch.setattr(runners, "_persist_and_broadcast", fake_persist)

    async def fake_loop(*args, **kwargs):
        sink = kwargs["event_sink"]
        await sink({"sub": {"kind": "thinking", "text": "推理中"}})
        await sink({"sub": {"kind": "tool", "text": "正在调用工具 query_data",
                            "tool": "query_data", "phase": "start"}})
        await sink({"sub": {"kind": "tool", "text": "工具 query_data 已完成",
                            "tool": "query_data", "phase": "done"}})
        await sink({"sub": {"kind": "tool", "text": "正在调用工具 catalog_search",
                            "tool": "catalog_search"}})  # 旧形状：无 phase
        return {"ok": True, "answer": "查到了"}

    monkeypatch.setattr(runners, "run_stream_chat_loop", fake_loop)

    asyncio.run(runners._run_tool_turn(
        "t-tool", "查一下在售机型", None, [],
        {"role_key": "assistant", "name": "方案助手"}, "",
        allowed_tool_ids=["query_data"], final_office_event=None, trace_sink=None,
    ))

    traces = [(p.get("tool"), p.get("phase"))
              for _, p in broadcasts if p.get("type") == "tool_trace"]
    assert traces == [("query_data", "start"), ("query_data", "done")]

    statuses = [p.get("text") for _, p in broadcasts if p.get("type") == "chat_status"]
    assert "正在调用工具 catalog_search" in statuses

    thinking = [p for _, p in broadcasts if p.get("type") == "thinking"]
    assert thinking == [{"type": "thinking", "text": "推理中"}]

    assert {tid for tid, _ in broadcasts} == {"t-tool"}
