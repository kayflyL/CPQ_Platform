"""WebSocket hub for the assistant — realtime streaming of LLM tokens to a thread room.

One room per thread_id. _stream_llm_reply calls broadcast() per token chunk; the WS
endpoint relays to every connected client viewing the thread.

房间注册与「有界广播」统一由 RoomHub 提供（见 room_hub.py：超时保护此前只加在本
hub，feed/office 漏了同一个 bug，2026-09-11 已收敛）。

FIPA-lite 信封（2026-09-13 ChatSessionRuntime）：broadcast 在每帧注入 thread_id
（FIPA ACL 的 conversation_id 位），客户端运行时按会话线程校验，迟帧/错帧直接丢弃，
永不写进别的会话。显式带了 thread_id 的载荷以调用方为准。
"""
from __future__ import annotations

from typing import Any, Dict

from app.services.room_hub import RoomHub


class AssistantHub(RoomHub):
    """Process-local connection registry, one room per thread_id. Single-node."""

    async def broadcast(self, room_key: str, payload: Dict[str, Any]):
        payload.setdefault("thread_id", room_key)
        await super().broadcast(room_key, payload)


assistant_hub = AssistantHub()
