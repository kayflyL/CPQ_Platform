"""WebSocket hub for requirement-intel pipeline — realtime streaming of reasoning
steps to an opportunity room.

Mirrors AssistantHub (one room per opportunity_id). run_pipeline() in
requirement_intel_service calls broadcast() per step; the WS endpoint relays to
every connected client viewing the opportunity's reasoning panel. Kept separate
from assistant_hub so reasoning steps never pollute the chat token stream.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Set

from fastapi import WebSocket


class ReasoningHub:
    """Process-local connection registry, one room per opportunity_id. Single-node."""

    def __init__(self):
        self._rooms: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, opportunity_id: str):
        await ws.accept()
        async with self._lock:
            self._rooms.setdefault(opportunity_id, set()).add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            for room in self._rooms.values():
                room.discard(ws)
            empty = [oid for oid, r in self._rooms.items() if not r]
            for oid in empty:
                self._rooms.pop(oid, None)

    async def broadcast(self, opportunity_id: str, payload: Dict[str, Any]):
        """Send a JSON message to every socket in the opportunity room (best-effort)."""
        room = self._rooms.get(opportunity_id)
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


reasoning_hub = ReasoningHub()
