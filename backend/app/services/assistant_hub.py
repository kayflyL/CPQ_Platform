"""WebSocket hub for the assistant — realtime streaming of LLM tokens to a thread room.

Mirrors FeedHub (one room per thread_id). _stream_llm_reply calls broadcast()
per token chunk; the WS endpoint relays to every connected client viewing the thread.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Set

from fastapi import WebSocket


class AssistantHub:
    """Process-local connection registry, one room per thread_id. Single-node."""

    def __init__(self):
        self._rooms: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, thread_id: str):
        await ws.accept()
        async with self._lock:
            self._rooms.setdefault(thread_id, set()).add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            for room in self._rooms.values():
                room.discard(ws)
            empty = [tid for tid, r in self._rooms.items() if not r]
            for tid in empty:
                self._rooms.pop(tid, None)

    async def broadcast(self, thread_id: str, payload: Dict[str, Any]):
        """Send a JSON message to every socket in the thread room (best-effort).

        有界等待（2026-09-06）：`await ws.send_text` 对半死连接（页面重载/网络瞬断/
        客户端停止读取）可能因 TCP 背压永久阻塞，拖死整个回合任务——这是"流程卡在
        配件选型永远不出结果"的实测根因之一。每连接 5s 超时，超时即视为死连接移除；
        历史已落库，客户端刷新后由 HTTP 对账补齐，不影响消息可达性。"""
        room = self._rooms.get(thread_id)
        if not room:
            return
        text = json.dumps(payload, ensure_ascii=False, default=str)
        dead: List[WebSocket] = []
        for ws in list(room):
            try:
                await asyncio.wait_for(ws.send_text(text), timeout=5)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


assistant_hub = AssistantHub()
