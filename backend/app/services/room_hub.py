"""Shared WebSocket room-hub primitives.

历史背景（2026-09-11 收敛）：assistant / feed / office 三个 hub 各自实现了一遍
「连接注册 + 广播」。其中「有界发送」这层保护当初只加在了 assistant_hub ——
`await ws.send_text` 对半死连接（页面重载 / 网络瞬断 / 客户端停止读取）可能因
TCP 背压永久阻塞，从而拖死整个回合任务（这是"流程卡在配件选型永远不出结果"的
实测根因之一）。feed_hub / office_hub 当时漏了这层保护，同一个 bug 在办公室与
商机动态链路上仍然存在。

本模块把"房间注册 + 有界广播"收敛到一处，三个 hub 共用：
- RoomHub：以 room_key（thread_id / opportunity_id）分房间的两个 hub 直接继承。
- send_bounded()：单连接有界发送，OfficeHub（全局单房间 + 角色过滤）直接调用。
超时即视为死连接并移除；历史消息已落库，客户端刷新后由 HTTP 对账补齐，
不影响消息可达性。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Set

from fastapi import WebSocket

#: 单连接发送超时（秒）。超时即判死连接，避免背压拖死调用方。
SEND_TIMEOUT_SECONDS = 5


async def send_bounded(ws: WebSocket, text: str, timeout: float = SEND_TIMEOUT_SECONDS) -> bool:
    """有界发送一帧文本。成功返回 True；超时或异常返回 False（调用方应判死连接）。"""
    try:
        await asyncio.wait_for(ws.send_text(text), timeout=timeout)
        return True
    except Exception:
        return False


class RoomHub:
    """Process-local registry: room_key -> set of websockets, with bounded broadcast.

    Single-node today. For multi-instance deployment, swap broadcast() to publish on
    Redis pub/sub and have each instance subscribe — the REST→hub call site stays
    unchanged.
    """

    send_timeout: float = SEND_TIMEOUT_SECONDS

    def __init__(self):
        self._rooms: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, room_key: str):
        await ws.accept()
        async with self._lock:
            self._rooms.setdefault(room_key, set()).add(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            for room in self._rooms.values():
                room.discard(ws)
            for key in [k for k, r in self._rooms.items() if not r]:
                self._rooms.pop(key, None)

    async def broadcast(self, room_key: str, payload: Dict[str, Any]):
        """Send a JSON message to every socket in the room (best-effort, bounded)."""
        room = self._rooms.get(room_key)
        if not room:
            return
        text = json.dumps(payload, ensure_ascii=False, default=str)
        dead: List[WebSocket] = []
        for ws in list(room):
            if not await send_bounded(ws, text, self.send_timeout):
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)
