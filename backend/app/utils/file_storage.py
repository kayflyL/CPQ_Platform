"""File storage for global assets (model images, branding) + _temp scratch dir.

Opportunity file archiving is handled by StorageAdapter (storage_adapter.py),
which writes opportunities/{opp_id}/{stem}_{shortuuid}{ext} via build_object_id.
"""
from pathlib import Path
from datetime import datetime
from typing import Optional


class FileStorageError(Exception):
    """Raised when a file storage operation violates security constraints."""
    pass


class FileStorage:
    """Temp uploads + global assets (model images, branding logo)."""

    def __init__(self, base_path: Optional[str] = None):
        if base_path is None:
            base_path = Path(__file__).parent.parent.parent / "storage"
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.temp_dir = self.base_path / "_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_temp(self, max_age_hours: int = 24) -> int:
        """Remove temporary files older than max_age_hours.

        Called on app startup to prevent orphan files accumulating in _temp.
        Returns the number of files removed.
        """
        if not self.temp_dir.exists():
            return 0
        now = datetime.now().timestamp()
        removed = 0
        for f in self.temp_dir.iterdir():
            try:
                if f.is_file() and (now - f.stat().st_mtime) > max_age_hours * 3600:
                    f.unlink()
                    removed += 1
            except Exception:
                pass
        return removed

    def _safe_join(self, *parts: str) -> Path:
        """Join path parts and verify the result stays within base_path.

        Defense-in-depth against path traversal (e.g., '..' segments).
        """
        joined = self.base_path.joinpath(*parts)
        resolved = joined.resolve()
        base_resolved = self.base_path.resolve()
        try:
            resolved.relative_to(base_resolved)
        except ValueError:
            raise FileStorageError(
                f"Path traversal detected: {parts} resolves outside base_path"
            )
        return resolved

    def save_model_image(self, file_content: bytes, original_name: str) -> dict:
        """Save a server model product image to storage/model-images/ (timestamped).

        Returns {stored_path, filename, file_size}.
        """
        from pathlib import PurePath
        p = PurePath(original_name)
        ext = p.suffix.lower()
        stem = ''.join(c for c in p.stem if c.isalnum() or c in '-_')[:32] or 'model'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stored_name = f"{stem}_{timestamp}{ext}"
        img_dir = self._safe_join("model-images")
        img_dir.mkdir(parents=True, exist_ok=True)
        stored_path = img_dir / stored_name
        with open(stored_path, "wb") as f:
            f.write(file_content)
        return {
            "stored_path": f"model-images/{stored_name}",
            "filename": stored_name,
            "file_size": len(file_content),
        }

    def save_branding_logo(self, file_content: bytes, original_name: str) -> dict:
        """Save branding logo to a global branding/ dir (overwrite, no timestamp).

        Re-upload replaces the previous logo so the URL stays stable.
        Returns {stored_path, file_size, created_at}.
        """
        from pathlib import PurePath
        ext = PurePath(original_name).suffix.lower()
        stored_name = f"logo{ext}"
        logo_dir = self._safe_join("branding")
        logo_dir.mkdir(parents=True, exist_ok=True)
        stored_path = logo_dir / stored_name
        with open(stored_path, "wb") as f:
            f.write(file_content)
        return {
            "stored_path": f"branding/{stored_name}",
            "file_size": len(file_content),
            "created_at": datetime.now().isoformat(),
        }

    def save_showcase_model(self, file_content: bytes, original_name: str) -> dict:
        """Save 3D showcase GLB model to storage/showcase-models/.

        Returns {stored_path, filename, file_size, url}.
        """
        import uuid
        from pathlib import PurePath

        ext = PurePath(original_name).suffix.lower()
        if ext not in {'.glb', '.gltf'}:
            raise FileStorageError(f"Unsupported format: {ext}, only .glb/.gltf allowed")

        # Sanitize stem: keep alphanumeric, dash, underscore
        stem = ''.join(c for c in PurePath(original_name).stem if c.isalnum() or c in '-_')[:32] or 'model'

        # Add short UUID to avoid collision
        short_uid = uuid.uuid4().hex[:8]
        stored_name = f"{stem}_{short_uid}{ext}"

        model_dir = self._safe_join("showcase-models")
        model_dir.mkdir(parents=True, exist_ok=True)
        stored_path = model_dir / stored_name

        with open(stored_path, "wb") as f:
            f.write(file_content)

        return {
            "stored_path": f"showcase-models/{stored_name}",
            "filename": stored_name,
            "file_size": len(file_content),
            "url": f"/api/server-catalog/showcase-models/{stored_name}",
        }
