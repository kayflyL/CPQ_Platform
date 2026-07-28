"""Storage adapter — single chokepoint for all file I/O.

Interface is shaped for object storage (presigned URLs, opaque keys) so a
future S3/MinIO implementation only swaps this one file. Business code never
touches Path directly.

Key rule: storage_key is ``{sanitized_stem}_{shortuuid}{ext}`` under
``opportunities/{customer_name}_{opp_id}/`` — human-readable on disk while the
short UUID prevents same-name collisions. The stem is file metadata (the original
filename), NOT a business field like sales/chassis/platform, so editing
business fields still cannot orphan files.

Folder naming: {sanitized_customer_name}_{opp_id} — includes customer name
for easy identification, suffixed with opp_id for uniqueness.
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

    def save_bytes(self, opportunity_id: str, object_id: str, content: bytes, ext: str, customer_name: str = "") -> str:
        """Persist bytes; return the relative storage_key."""
        ...

    def read_bytes(self, storage_key: str) -> bytes: ...

    def resolve_local_path(self, storage_key: str) -> Optional[Path]:
        """Local filesystem path, or None if this adapter isn't local."""
        ...

    def delete(self, storage_key: str) -> bool: ...

    def rename_opportunity_folder(self, opportunity_id: str, old_customer: str, new_customer: str) -> tuple[bool, dict]:
        """Rename opportunity folder when customer name changes.
        Returns (success, {old_key_prefix, new_key_prefix}) for DB updates."""
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

    def save_bytes(self, opportunity_id: str, object_id: str, content: bytes, ext: str, customer_name: str = "") -> str:
        """Save file under opportunities/{customer_name}_{opp_id}/"""
        folder = self._build_folder_name(opportunity_id, customer_name)
        obj = self._sanitize(object_id)
        ext = ext if ext.startswith(".") else f".{ext}"
        rel = f"opportunities/{folder}/{obj}{ext}"
        target = self._safe_join(rel)
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

    def rename_opportunity_folder(self, opportunity_id: str, old_customer: str, new_customer: str) -> tuple[bool, dict]:
        """Rename opportunity folder when customer name changes.

        Returns:
            (success, {old_prefix, new_prefix}) - prefix for updating storage_key in DB

        Example:
            Old folder: opportunities/华为_OPP-xxx/
            New folder: opportunities/华为科技_OPP-xxx/
            Returns: (True, {"old_prefix": "opportunities/华为_OPP-xxx",
                             "new_prefix": "opportunities/华为科技_OPP-xxx"})
        """
        old_folder = self._build_folder_name(opportunity_id, old_customer)
        new_folder = self._build_folder_name(opportunity_id, new_customer)

        old_path = self._safe_join("opportunities", old_folder)
        new_path = self._safe_join("opportunities", new_folder)

        # If old folder doesn't exist, nothing to do (might be a new opp)
        if not old_path.exists():
            # Ensure new folder exists for future uploads
            new_path.mkdir(parents=True, exist_ok=True)
            return True, {
                "old_prefix": f"opportunities/{old_folder}",
                "new_prefix": f"opportunities/{new_folder}",
            }

        # If new folder already exists (edge case), merge or skip
        if new_path.exists():
            # Move all files from old to new
            for f in old_path.iterdir():
                target = new_path / f.name
                if not target.exists():
                    shutil.move(str(f), str(target))
            # Remove empty old folder
            try:
                old_path.rmdir()
            except OSError:
                pass  # Folder not empty, keep it
        else:
            # Simple rename
            shutil.move(str(old_path), str(new_path))

        return True, {
            "old_prefix": f"opportunities/{old_folder}",
            "new_prefix": f"opportunities/{new_folder}",
        }

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
