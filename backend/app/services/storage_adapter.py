"""Storage adapter — single chokepoint for all file I/O.

Interface is shaped for object storage (presigned URLs, opaque keys) so a
future S3/MinIO implementation only swaps this one file. Business code never
touches Path directly.

Key rule: storage_key is ``{sanitized_stem}_{shortuuid}{ext}`` under
``opportunities/{customer_name}_{opp_id}/`` — human-readable on disk while the
short UUID prevents same-name collisions. The stem is file metadata (the original
filename), NOT a business field like sales/chassis/platform, so editing
business fields still cannot orphan files.

Folder naming: {sanitized_customer_name}_{opp_id} — the customer name is a
one-time cosmetic prefix frozen at first save; customer renames do NOT touch
the filesystem or storage_keys (folder lookup matches on the immutable
opportunity_id, so drifted/legacy folder names keep resolving).
"""
from __future__ import annotations

import re
import uuid
import shutil
from pathlib import Path
from typing import Optional, Protocol
from datetime import datetime


class StorageAdapter(Protocol):
    base_path: Path

    def save_bytes(self, opportunity_id: str, object_id: str, content: bytes, ext: str, customer_name: str = "", subfolder: str = "") -> str:
        """Persist bytes; return the relative storage_key.

        subfolder is an optional single path segment for node/category grouping.
        """
        ...

    def save_scoped(self, rel_dir: str, object_id: str, content: bytes, ext: str) -> str:
        """Persist bytes under an opportunity-neutral bucket (e.g. office reports);
        return the relative storage_key. Downloads stay API-proxied + authenticated."""
        ...

    def read_bytes(self, storage_key: str) -> bytes: ...

    def resolve_local_path(self, storage_key: str) -> Optional[Path]:
        """Local filesystem path, or None if this adapter isn't local."""
        ...

    def delete(self, storage_key: str) -> bool: ...

    def delete_opportunity_folder(self, opportunity_id: str) -> int:
        """Physically remove the opportunity's on-disk folder(s); return count removed."""
        ...

    def presigned_url(self, storage_key: str, expires_in: int = 3600) -> Optional[str]:
        """Object-storage presigned URL, or None when downloads are API-proxied."""
        ...


class StorageError(Exception):
    pass


class LocalFileStorage:
    """Local-disk implementation. The only adapter shipped today."""

    def __init__(self, base_path: Optional[str] = None):
        if base_path is None:
            base_path = Path(__file__).parent.parent.parent / "storage"
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _safe_join(self, *parts: str) -> Path:
        joined = self.base_path.joinpath(*parts)
        resolved = joined.resolve()
        base_resolved = self.base_path.resolve()
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            raise StorageError(f"Path traversal detected: {parts}")
        return resolved

    @staticmethod
    def _sanitize(component: str) -> str:
        # object_id / opportunity_id must be a single, safe path segment
        return component.replace("/", "_").replace("\\", "_").replace("..", "_")

    @staticmethod
    def _sanitize_customer_name(name: str) -> str:
        """Sanitize customer name for use in folder path.
        Keep CJK / alnum / spaces / parentheses, replace others with underscore."""
        if not name:
            return "未命名"
        # Keep: letters, digits, CJK, spaces, parentheses, brackets, dash, underscore
        cleaned = re.sub(r"[^\w一-鿿\s()\[\]\-_]", "_", name)
        cleaned = re.sub(r"_+", "_", cleaned).strip("_ ")
        # Collapse multiple spaces to single
        cleaned = re.sub(r"\s+", " ", cleaned)
        # Limit length
        cleaned = cleaned[:50]
        return cleaned or "未命名"

    def _build_folder_name(self, opportunity_id: str, customer_name: str = "") -> str:
        """Build human-readable folder name: {customer_name}_{opp_id}"""
        sanitized_customer = self._sanitize_customer_name(customer_name)
        sanitized_opp_id = self._sanitize(opportunity_id)
        return f"{sanitized_customer}_{sanitized_opp_id}"

    def _find_opportunity_folders(self, opportunity_id: str) -> list:
        """Existing on-disk folders for this opportunity, matched by id.

        opportunity_id is globally unique, so matching on it (rather than a
        customer_name-prefixed path) is precise AND robust to folder-name drift
        — e.g. a legacy '未命名_OPP-…' folder created before customer_name was
        threaded through every save_bytes() call.
        """
        sanitized = self._sanitize(opportunity_id)
        if not sanitized:
            return []
        base = self._safe_join("opportunities")
        if not base.exists():
            return []
        return [d for d in base.iterdir() if d.is_dir() and sanitized in d.name]

    def save_bytes(self, opportunity_id: str, object_id: str, content: bytes, ext: str, customer_name: str = "", subfolder: str = "") -> str:
        """Save file under opportunities/{customer_name}_{opp_id}/{subfolder}/.

        Folder name is frozen at first save: existing folders for this
        opportunity_id are reused as-is, so a later customer rename never
        renames/moves anything on disk (lookup matches on the immutable id).
        """
        existing = self._find_opportunity_folders(opportunity_id)
        folder = existing[0].name if existing else self._build_folder_name(opportunity_id, customer_name)
        safe_subfolder = self._sanitize((subfolder or "").strip("/").strip("\\"))
        obj = self._sanitize(object_id)
        ext = ext if ext.startswith(".") else f".{ext}"
        base = f"opportunities/{folder}"
        if safe_subfolder:
            base = f"{base}/{safe_subfolder}"
        rel = f"{base}/{obj}{ext}"
        target = self._safe_join(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return rel

    def save_scoped(self, rel_dir: str, object_id: str, content: bytes, ext: str) -> str:
        """Save file under a neutral bucket outside the opportunities tree.

        rel_dir may contain "/" grouping (e.g. "office/reports"); each segment and
        object_id pass through _sanitize, and _safe_join guards traversal.
        """
        segs = [self._sanitize(p) for p in str(rel_dir or "").strip("/").strip("\\").split("/") if p]
        obj = self._sanitize(object_id)
        ext = ext if ext.startswith(".") else f".{ext}"
        rel = "/".join([*segs, f"{obj}{ext}"])
        target = self._safe_join(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return rel

    def read_bytes(self, storage_key: str) -> bytes:
        return self._safe_join(storage_key).read_bytes()

    def resolve_local_path(self, storage_key: str) -> Optional[Path]:
        p = self._safe_join(storage_key)
        return p if p.exists() else None

    def delete(self, storage_key: str) -> bool:
        p = self._safe_join(storage_key)
        if p.exists() and p.is_file():
            p.unlink()
            return True
        return False

    def delete_opportunity_folder(self, opportunity_id: str) -> int:
        """Physically remove this opportunity's folder(s) from disk.

        Returns the count removed. Matches by opportunity_id so a name-drifted
        folder (e.g. legacy '未命名_OPP-…') that a name-based lookup would miss
        is still purged.
        """
        removed = 0
        for folder in self._find_opportunity_folders(opportunity_id):
            shutil.rmtree(folder, ignore_errors=True)
            if not folder.exists():
                removed += 1
        return removed

    def presigned_url(self, storage_key: str, expires_in: int = 3600) -> Optional[str]:
        # Local adapter proxies downloads through the REST API; no presign.
        return None


_storage: Optional[LocalFileStorage] = None


def get_storage() -> LocalFileStorage:
    """Return the process-wide storage adapter.

    Swap point: when a deploy target is chosen, branch on a setting here and
    return an S3Storage — callers are already adapter-agnostic.
    """
    global _storage
    if _storage is None:
        _storage = LocalFileStorage()
    return _storage


def build_object_id(original_filename: str, short_uuid_len: int = 8) -> str:
    """Build a disk-friendly object_id from an original filename.

    Shape: ``{sanitized_stem}_{shortuuid}`` — keeps CJK / alnum / ``()[]-_``
    from the original stem so the file is recognizable on disk, suffixed with
    a short UUID so same-name uploads never collide. Caller passes the result
    as ``object_id`` into ``save_bytes``.
    """
    stem = Path(original_filename).stem
    cleaned = re.sub(r"[^\w一-鿿()\[\]\-]", "_", stem)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    cleaned = cleaned[:40]
    if not cleaned:
        cleaned = "file"
    return f"{cleaned}_{uuid.uuid4().hex[:short_uuid_len]}"


def now_iso() -> str:
    return datetime.now().isoformat()
