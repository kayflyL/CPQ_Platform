"""办公室事件发布：用户消息原文不出会话线程（多用户看板是全局房间，2026-09-28 拍板截断 40 字）。"""
import asyncio

from app.services import office_events as oe


def _captured(monkeypatch):
    sent = []

    class FakeHub:
        async def update_and_broadcast(self, role_key, payload):
            sent.append(payload)

    class FakeMemory:
        async def record_event(self, role_key, payload):
            pass

    monkeypatch.setattr(oe, "office_hub", FakeHub())
    monkeypatch.setattr(oe, "office_memory", FakeMemory())
    return sent


def test_long_message_truncated_to_40_chars(monkeypatch):
    sent = _captured(monkeypatch)
    long_text = "客户" + "很长的需求" * 20
    asyncio.run(oe.publish_office_event(
        "support_engineer", "working", "接收新任务", message=long_text))
    assert len(sent) == 1
    msg = sent[0]["message"]
    assert msg.endswith("…") and len(msg) == 41  # 40 字 + 省略号
    assert msg[:40] == long_text[:40]


def test_short_message_passes_through(monkeypatch):
    sent = _captured(monkeypatch)
    asyncio.run(oe.publish_office_event(
        "support_engineer", "idle", "空闲", message="短消息"))
    assert sent[0]["message"] == "短消息"


def test_none_message_becomes_empty(monkeypatch):
    sent = _captured(monkeypatch)
    asyncio.run(oe.publish_office_event("assistant", "thinking", "思考"))
    assert sent[0]["message"] == ""
