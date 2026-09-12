"""WebSocket hub for the opportunity feed — realtime broadcast + presence.

One room per opportunity_id. REST handlers (feed.py) call broadcast() after
mutating state; the WS endpoint relays to every connected client in the room.
Presence is derived from the sockets currently subscribed to a room.

房间注册与「有界广播」由 RoomHub 提供（见 room_hub.py）；本类只额外负责
presence 元数据（谁在看这条商机）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import WebSocket

from app.services.room_hub import RoomHub

logger = logging.getLogger(__name__)


class FeedHub(RoomHub):
    """Process-local connection registry. Single-node today."""

    def __init__(self):
        super().__init__()
        # ws -> {opportunity_id, user_id, name}
        self._meta: Dict[WebSocket, Dict[str, str]] = {}

    async def connect(self, ws: WebSocket, opportunity_id: str, user_id: str, name: str):
        await ws.accept()
        async with self._lock:
            self._rooms.setdefault(opportunity_id, set()).add(ws)
            self._meta[ws] = {"opportunity_id": opportunity_id, "user_id": user_id, "name": name}
        await self._broadcast_presence(opportunity_id)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            meta = self._meta.pop(ws, None)
        await super().disconnect(ws)
        if meta:
            await self._broadcast_presence(meta["opportunity_id"])

    def online_users(self, opportunity_id: str) -> List[Dict[str, str]]:
        """Distinct users currently viewing this opportunity's feed."""
        room = self._rooms.get(opportunity_id)
        if not room:
            return []
        seen: Dict[str, str] = {}
        for ws in room:
            meta = self._meta.get(ws)
            if meta and meta["user_id"]:
                seen[meta["user_id"]] = meta["name"]
        return [{"user_id": uid, "name": name} for uid, name in seen.items()]

    async def _broadcast_presence(self, opportunity_id: str):
        await self.broadcast(opportunity_id, {
            "type": "presence",
            "online": self.online_users(opportunity_id),
        })


hub = FeedHub()
