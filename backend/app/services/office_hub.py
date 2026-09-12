"""WebSocket hub for the AI office — a single global room for office status events.

Clients are stored with an optional allowed-role-key filter so non-admin users
only receive events from rooms they are allowed to see.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket

from app.services.room_hub import send_bounded


class OfficeHub:
    """Process-local connection registry + latest colleague status map."""

    def __init__(self):
        self._clients: Dict[WebSocket, Optional[Set[str]]] = {}
        self._lock = asyncio.Lock()
        self._latest: Dict[str, Any] = {}

    async def connect(self, ws: WebSocket, allowed_role_keys: Optional[List[str]] = None):
        await ws.accept()
        allowed = set(allowed_role_keys) if allowed_role_keys is not None else None
        async with self._lock:
            self._clients[ws] = allowed

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            self._clients.pop(ws, None)

    async def broadcast(self, payload: Dict[str, Any]):
        """Send a JSON message to clients allowed to see its role_key (best-effort)."""
        async with self._lock:
            clients = list(self._clients.items())
        if not clients:
            return
        role_key = str(payload.get("role_key") or "unknown")
        text = json.dumps(payload, ensure_ascii=False, default=str)
        dead = []
        for ws, allowed in clients:
            if allowed is not None and role_key not in allowed and role_key != "unknown":
                continue
            # 有界发送：半死连接（页面重载/网络瞬断/客户端停止读取）会因 TCP 背压永久
            # 阻塞，进而拖死整个回合任务。与 assistant/feed 链路同一处修复（room_hub）。
            if not await send_bounded(ws, text):
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)

    async def update_and_broadcast(self, role_key: str, payload: Dict[str, Any]):
        """Merge the latest per-colleague state, then broadcast the event."""
        role_key = (role_key or "").strip() or "unknown"
        previous = self._latest.get(role_key, {}) or {}
        revision = int(previous.get("revision") or 0) + 1
        event = {
            "type": "colleague_status",
            "role_key": role_key,
            "revision": revision,
            "status": payload.get("status") or "idle",
            "activity": payload.get("activity") or "",
            "message": payload.get("message") or "",
            "tool": payload.get("tool"),
            "thread_id": payload.get("thread_id"),
            "opportunity_id": payload.get("opportunity_id"),
            "zone": payload.get("zone"),
            "intent": payload.get("intent"),
            "participants": payload.get("participants"),
            "conversation_id": payload.get("conversation_id"),
            "task_id": payload.get("task_id"),
            "mission_id": payload.get("mission_id"),
            "assignment_id": payload.get("assignment_id"),
            "assignment_status": payload.get("assignment_status"),
            "step_id": payload.get("step_id"),
            "result_summary": payload.get("result_summary"),
            "approval_required": payload.get("approval_required"),
            "priority": payload.get("priority"),
            "summary": payload.get("summary"),
            "assignments": payload.get("assignments"),
            "conclusion": payload.get("conclusion"),
            # 暂停载荷对象（P4-1）：结构化事实原样带给看板，不靠话术字段还原中断点
            "pause": payload.get("pause"),
            "actor": payload.get("actor"),
            "source": payload.get("source") or "system",
            "ts": payload.get("ts"),
        }
        self._latest[role_key] = {**previous, **event}
        await self.broadcast(event)

    def snapshot(self, allowed_role_keys: Optional[List[str]] = None) -> Dict[str, Any]:
        """Return a stable copy of the latest status map, optionally role-scoped."""
        data = {k: dict(v) for k, v in self._latest.items()}
        if allowed_role_keys is not None:
            allowed = set(allowed_role_keys)
            data = {
                k: v for k, v in data.items()
                if k in allowed or k == "unknown"
            }
        return data


office_hub = OfficeHub()
