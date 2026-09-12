"""Governance queue for AI office approval-required events.

Sensitive events marked `approval_required` are parked here instead of being
broadcast immediately. Items are persisted in the rules schema and mirrored in
memory for fast lookup.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from app.repository.office_governance_repo import OfficeGovernanceRepository
from app.services.office_hub import office_hub
from app.services.office_memory import office_memory


class OfficeGovernance:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._items: Dict[str, Dict[str, Any]] = {}
        self._sequence = 0
        self._loaded = False

    def _load_sync(self) -> None:
        if self._loaded:
            return
        try:
            for item in OfficeGovernanceRepository().list_items():
                self._items[item["id"]] = item
            self._loaded = True
        except Exception:
            pass

    async def _load(self) -> None:
        if self._loaded:
            return
        try:
            items = await asyncio.to_thread(OfficeGovernanceRepository().list_items)
        except Exception:
            return
        for item in items:
            self._items[item["id"]] = item
        self._loaded = True

    async def _save(self, item: Dict[str, Any]) -> None:
        try:
            await asyncio.to_thread(OfficeGovernanceRepository().save, dict(item))
        except Exception:
            pass

    async def enqueue(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self._load()
        async with self._lock:
            self._sequence += 1
            item_id = f"gov_{int(time.time() * 1000)}_{self._sequence}"
            item = {
                "id": item_id,
                "status": "pending",
                "payload": dict(payload or {}),
                "created_ts": time.time(),
                "resolved_ts": None,
                "resolved_by": None,
                "resolution": None,
                "reason": "",
            }
            self._items[item_id] = item
        await self._save(self._items[item_id])
        return dict(self._items[item_id])

    def list_items(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        self._load_sync()
        items = list(self._items.values())
        if status:
            items = [item for item in items if item.get("status") == status]
        items.sort(key=lambda item: item.get("created_ts") or 0, reverse=True)
        return [dict(item) for item in items]

    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        self._load_sync()
        item = self._items.get(item_id)
        return dict(item) if item else None

    async def approve(self, item_id: str, actor: str) -> Dict[str, Any]:
        await self._load()
        async with self._lock:
            item = self._items.get(item_id)
            if not item:
                raise KeyError("approval item not found")
            if item.get("status") != "pending":
                raise ValueError("approval item is not pending")
            item["status"] = "approved"
            item["resolved_ts"] = time.time()
            item["resolved_by"] = actor or "system"
            item["resolution"] = "approved"
            payload = dict(item.get("payload") or {})
            snapshot = dict(item)

        role_key = str(payload.get("role_key") or "unknown")
        await office_hub.update_and_broadcast(role_key, payload)
        await office_memory.record_event(role_key, payload)
        await self._save(snapshot)
        try:
            await asyncio.to_thread(OfficeGovernanceRepository().prune_resolved)
        except Exception:
            pass
        return dict(snapshot)

    async def reject(self, item_id: str, actor: str, reason: str = "") -> Dict[str, Any]:
        await self._load()
        async with self._lock:
            item = self._items.get(item_id)
            if not item:
                raise KeyError("approval item not found")
            if item.get("status") != "pending":
                raise ValueError("approval item is not pending")
            item["status"] = "rejected"
            item["resolved_ts"] = time.time()
            item["resolved_by"] = actor or "system"
            item["resolution"] = "rejected"
            item["reason"] = reason or ""
            snapshot = dict(item)
        await self._save(snapshot)
        try:
            await asyncio.to_thread(OfficeGovernanceRepository().prune_resolved)
        except Exception:
            pass
        return dict(snapshot)


office_governance = OfficeGovernance()
