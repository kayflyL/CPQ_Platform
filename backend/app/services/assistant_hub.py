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
        """Send a JSON message to every socket in the thread room (best-effort)."""
        room = self._rooms.get(thread_id)
        if not room:
            return
        text = json.dumps(payload, ensure_ascii=False, default=str)
        dead: List[WebSocket] = []
        for ws in list(room):
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


assistant_hub = AssistantHub()
