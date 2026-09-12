"""WebSocket hub for the assistant — realtime streaming of LLM tokens to a thread room.

One room per thread_id. _stream_llm_reply calls broadcast() per token chunk; the WS
endpoint relays to every connected client viewing the thread.

房间注册与「有界广播」统一由 RoomHub 提供（见 room_hub.py：超时保护此前只加在本
hub，feed/office 漏了同一个 bug，2026-09-11 已收敛）。
"""
from __future__ import annotations

from app.services.room_hub import RoomHub


class AssistantHub(RoomHub):
    """Process-local connection registry, one room per thread_id. Single-node."""


assistant_hub = AssistantHub()
