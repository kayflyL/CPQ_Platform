"""AI office memory service.

Keeps a lightweight, process-local memory of recent office events and role
relations. Only long-term memories are persisted into the rules schema;
runtime status events stay process-local for live visualization.
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
        self._memories: Dict[str, deque] = {}
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
                if (event.get("event_type") or event.get("type")) == "memory":
                    await asyncio.to_thread(repo.prune_memories, event.get("role_key") or "unknown")
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

    async def remember(
        self,
        role_key: Optional[str],
        content: str,
        kind: str = "episodic",
        importance: float = 0.5,
        ttl_seconds: Optional[int] = None,
        pinned: bool = False,
        source: str = "assistant_chat",
    ) -> None:
        """记录一条员工长期记忆（情景/语义），进程内即时可见并异步持久化。"""
        role = self._role(role_key)
        text = (content or "").strip()
        if not text:
            return
        record = {
            "role_key": role,
            "event_type": "memory",
            "status": "remembered",
            "source": source,
            "activity": f"memory:{kind}",
            "message": text,
            "ts": time.time(),
            "payload": {
                "kind": kind,
                "importance": float(importance),
                "pinned": bool(pinned),
                "ttl_seconds": ttl_seconds,
                "expires_at": (time.time() + ttl_seconds) if ttl_seconds else None,
            },
        }
        async with self._lock:
            if role not in self._memories:
                self._memories[role] = deque(maxlen=100)
            self._memories[role].append(dict(record))
        await self._enqueue_persist(record)

    async def remember_manual(
        self,
        role_key: Optional[str],
        content: str,
        kind: str = "semantic",
        importance: float = 0.5,
        pinned: bool = False,
    ) -> dict:
        """手动创建长期记忆：同步写 DB 并立即进入进程内缓存。"""
        role = self._role(role_key)
        text = (content or "").strip()
        if not text:
            raise ValueError("记忆内容不能为空")
        record = {
            "role_key": role,
            "event_type": "memory",
            "status": "remembered",
            "source": "manual",
            "activity": f"memory:{kind}",
            "message": text,
            "ts": time.time(),
            "payload": {
                "kind": kind,
                "importance": float(importance),
                "pinned": bool(pinned),
                "ttl_seconds": None,
                "expires_at": None,
            },
        }
        async with self._lock:
            if role not in self._memories:
                self._memories[role] = deque(maxlen=100)
            self._memories[role].append(dict(record))
        repo = OfficeEventRepository()
        await asyncio.to_thread(repo.create, record)
        try:
            await asyncio.to_thread(repo.prune_memories, role)
        except Exception:
            # Memory pruning must not block manual memory creation.
            pass
        return dict(record)

    async def retrieve_memories(
        self,
        role_key: Optional[str],
        query: str = "",
        limit: int = 8,
    ) -> List[Dict[str, Any]]:
        """获取员工长期记忆：进程内近期记忆 + 数据库持久化记忆，按时间倒序去重。"""
        role = self._role(role_key)
        safe_limit = max(1, min(int(limit or 8), 20))
        in_memory = list(self._memories.get(role, []))[-safe_limit:]
        try:
            repo = OfficeEventRepository()
            persisted = await asyncio.to_thread(
                repo.query,
                page=1,
                page_size=200,
                role_key=role,
                event_type="memory",
            )
        except Exception:
            persisted = {"items": []}
        persisted_items = sorted(
            persisted.get("items") or [],
            key=lambda item: (
                -int(bool((item.get("payload") or {}).get("pinned"))),
                -float((item.get("payload") or {}).get("importance") or 0),
                -float(item.get("ts") or 0),
            ),
        )
        merged: List[Dict[str, Any]] = []
        seen: set = set()
        for item in list(reversed(in_memory)) + persisted_items:
            key = f"{item.get('ts') or ''}::{item.get('message') or ''}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        if query:
            lowered = str(query or "").lower()
            merged = [item for item in merged if lowered in str(item.get("message") or "").lower()]
        return merged[:safe_limit]

    async def memory_prompt(
        self,
        role_key: Optional[str],
        query: str = "",
        limit: int = 6,
    ) -> str:
        """把长期记忆整理成可注入 LLM 的短文本块。"""
        items = await self.retrieve_memories(role_key, query=query, limit=limit)
        if not items:
            return ""
        lines = []
        for item in items:
            kind = str((item.get("payload") or {}).get("kind") or "episodic")
            text = str(item.get("message") or "").strip()
            if text:
                lines.append(f"- [{kind}] {text}")
        return "员工长期记忆：\n" + "\n".join(lines[:limit])

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
                self._memories.clear()
                self._all_events.clear()
                return
            role = self._role(role_key)
            self._events.pop(role, None)
            self._relations.pop(role, None)
            self._facts.pop(role, None)
            self._memories.pop(role, None)


office_memory = OfficeMemory()
