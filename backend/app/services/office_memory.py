"""AI office memory service.

Process-local registry of recent office events, role relations, and role
facts for live visualization (3D office / observability feeds). Long-term
colleague memory now lives in rules.colleague_memories via
app.services.colleague_memory_service — this module no longer stores
chat snapshots.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any, Dict, List, Optional

from app.repository.office_event_repo import OfficeEventRepository


class OfficeMemory:
    """Recent events, relations, and facts keyed by colleague role_key."""

    def __init__(self, max_events_per_role: int = 50) -> None:
        self._max_events_per_role = max_events_per_role
        self._lock = asyncio.Lock()
        self._events: Dict[str, deque] = {}
        self._relations: Dict[str, Dict[str, Any]] = {}
        self._facts: Dict[str, Dict[str, Any]] = {}
        self._all_events: deque = deque(maxlen=300)
        self._persist_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._persist_count = 0
        self._persist_task: Optional[asyncio.Task] = None

    def _role(self, role_key: Optional[str]) -> str:
        return (role_key or "").strip() or "unknown"

    async def _ensure_persist_task(self) -> None:
        if self._persist_task is None or self._persist_task.done():
            self._persist_task = asyncio.create_task(self._persist_loop())

    async def _persist_loop(self) -> None:
        repo = OfficeEventRepository()
        while True:
            event = await self._persist_queue.get()
            try:
                await asyncio.to_thread(repo.create, event)
                self._persist_count += 1
                if self._persist_count % 100 == 0:
                    await asyncio.to_thread(repo.prune_runtime_events)
            except Exception:
                # Office history persistence must never break the live pipeline.
                pass
            finally:
                self._persist_queue.task_done()

    async def _enqueue_persist(self, event: Dict[str, Any]) -> None:
        await self._ensure_persist_task()
        try:
            self._persist_queue.put_nowait(event)
        except asyncio.QueueFull:
            try:
                self._persist_queue.get_nowait()
                self._persist_queue.task_done()
            except asyncio.QueueEmpty:
                pass
            try:
                self._persist_queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def record_event(self, role_key: Optional[str], event: Dict[str, Any]) -> None:
        role = self._role(role_key)
        record = {**event, "role_key": role}
        async with self._lock:
            if role not in self._events:
                self._events[role] = deque(maxlen=self._max_events_per_role)
            self._events[role].append(dict(record))
            if role not in self._facts:
                self._facts[role] = {}
            self._facts[role].update({
                "last_status": event.get("status"),
                "last_activity": event.get("activity"),
                "last_zone": event.get("zone"),
                "last_intent": event.get("intent"),
                "last_ts": event.get("ts"),
            })
            self._all_events.append(dict(record))

    async def update_relation(
        self,
        role_key: Optional[str],
        peer_role_key: str,
        note: str = "",
    ) -> None:
        role = self._role(role_key)
        async with self._lock:
            if role not in self._relations:
                self._relations[role] = {}
            relation = self._relations[role].setdefault(peer_role_key, {})
            relation["note"] = note
            relation["updated_ts"] = time.time()

    def recent_events(self, role_key: Optional[str], limit: int = 20) -> List[Dict[str, Any]]:
        role = self._role(role_key)
        events = list(self._events.get(role, []))[-max(1, min(limit, self._max_events_per_role)):]
        return [dict(event) for event in events]

    def recent_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        safe_limit = max(1, min(int(limit or 100), 300))
        events = list(self._all_events)[-safe_limit:]
        return [dict(event) for event in events]

    def snapshot(self, role_key: Optional[str]) -> Dict[str, Any]:
        role = self._role(role_key)
        return {
            "role_key": role,
            "recent_events": self.recent_events(role),
            "relations": {k: dict(v) for k, v in self._relations.get(role, {}).items()},
            "facts": dict(self._facts.get(role, {})),
        }

    async def clear(self, role_key: Optional[str] = None) -> None:
        async with self._lock:
            if role_key is None:
                self._events.clear()
                self._relations.clear()
                self._facts.clear()
                self._all_events.clear()
                return
            role = self._role(role_key)
            self._events.pop(role, None)
            self._relations.pop(role, None)
            self._facts.pop(role, None)


office_memory = OfficeMemory()
