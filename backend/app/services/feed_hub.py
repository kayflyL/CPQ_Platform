"""WebSocket hub for the opportunity feed — realtime broadcast + presence.

One room per opportunity_id. REST handlers (feed.py) call broadcast() after
mutating state; the WS endpoint relays to every connected client in the room.
Presence is derived from the sockets currently subscribed to a room.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class FeedHub:
    """Process-local connection registry. Single-node today.

    For multi-instance deployment, swap broadcast() to publish on Redis pub/sub
    and have each instance subscribe — the REST→hub call site stays unchanged.
    """

    def __init__(self):
        # room (opportunity_id) -> set of websockets
        self._rooms: Dict[str, Set[WebSocket]] = {}
        # ws -> {opportunity_id, user_id, name}
        self._meta: Dict[WebSocket, Dict[str, str]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, opportunity_id: str, user_id: str, name: str):
        await ws.accept()
        async with self._lock:
            self._rooms.setdefault(opportunity_id, set()).add(ws)
            self._meta[ws] = {"opportunity_id": opportunity_id, "user_id": user_id, "name": name}
        await self._broadcast_presence(opportunity_id)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            meta = self._meta.pop(ws, None)
            if meta:
                opp = meta["opportunity_id"]
                room = self._rooms.get(opp)
                if room:
                    room.discard(ws)
                    if not room:
                        self._rooms.pop(opp, None)
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

    async def broadcast(self, opportunity_id: str, payload: Dict[str, Any]):
        """Send a JSON message to every socket in the room (best-effort)."""
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

    async def _broadcast_presence(self, opportunity_id: str):
        await self.broadcast(opportunity_id, {
            "type": "presence",
            "online": self.online_users(opportunity_id),
        })


hub = FeedHub()
