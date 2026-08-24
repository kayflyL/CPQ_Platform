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

    def save_model_image(
        self, file_content: bytes, original_name: str,
        model_key: Optional[str] = None, img_type: Optional[str] = None,
    ) -> dict:
        """Save a server model image to storage/model-images/ — 内容寻址平铺池。

        文件名 = 原始名净化 + 内容 sha256 前 16 位：同一张图无论传几次、给哪个机型/用途，
        都落到同一个文件（幂等写入，天然去重）；URL 跨机型通用。
        历史 {机型}/{type}/、portal-banner/ 子目录存量继续可读，不再新增。
        model_key/img_type 参数仅为调用方兼容保留，不再影响落盘路径。
        Returns {stored_path, filename, file_size}；filename 为相对 model-images 的路径。
        """
        import hashlib
        from pathlib import PurePath
        p = PurePath(original_name)
        ext = p.suffix.lower()
        stem = ''.join(c for c in p.stem if c.isalnum() or c in '-_')[:32] or 'img'
        digest = hashlib.sha256(file_content).hexdigest()[:16]
        stored_name = f"{stem}_{digest}{ext}"
        img_dir = self._safe_join("model-images")
        img_dir.mkdir(parents=True, exist_ok=True)
        stored_path = img_dir / stored_name
        if not stored_path.exists():   # 已有同内容文件则跳过，保留首次上传时间
            with open(stored_path, "wb") as f:
                f.write(file_content)
        return {
            "stored_path": stored_name,
            "filename": stored_name,
            "file_size": len(file_content),
        }

    def delete_model_image(self, rel_path: str) -> bool:
        """按相对路径删除 model-images 下的文件（仅本地上传池；防路径穿越）。

        rel_path 来自站点 URL（/api/server-catalog/model-image/ 之后的部分，可含历史子目录）。
        Returns 是否真的删除了文件。
        """
        parts = [p for p in rel_path.replace("\\", "/").split("/") if p and p not in ("..", ".")]
        if not parts:
            return False
        p = self._safe_join("model-images", *parts)
        if p.is_file():
            p.unlink()
            return True
        return False

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
        """Save 3D showcase GLB model to storage/showcase-models/ — 内容寻址。

        同一模型文件重传幂等（不产生副本）。Returns {stored_path, filename, file_size, url}.
        """
        import hashlib
        from pathlib import PurePath

        ext = PurePath(original_name).suffix.lower()
        if ext not in {'.glb', '.gltf'}:
            raise FileStorageError(f"Unsupported format: {ext}, only .glb/.gltf allowed")

        # Sanitize stem: keep alphanumeric, dash, underscore
        stem = ''.join(c for c in PurePath(original_name).stem if c.isalnum() or c in '-_')[:32] or 'model'
        digest = hashlib.sha256(file_content).hexdigest()[:16]
        stored_name = f"{stem}_{digest}{ext}"

        model_dir = self._safe_join("showcase-models")
        model_dir.mkdir(parents=True, exist_ok=True)
        stored_path = model_dir / stored_name

        if not stored_path.exists():
            with open(stored_path, "wb") as f:
                f.write(file_content)

        return {
            "stored_path": f"showcase-models/{stored_name}",
            "filename": stored_name,
            "file_size": len(file_content),
            "url": f"/api/server-catalog/showcase-models/{stored_name}",
        }

    def save_drawing_svg(self, file_content: bytes, original_name: str,
                           model_id: Optional[int] = None) -> dict:
        """Save a sanitized server drawing SVG to storage/drawing-svgs/[model_id]/ (timestamped).

        model_id 非空时按机型子目录归档（同一机型图纸集中存放，便于排查/清理）；
        URL 带机型段：/api/server-catalog/drawing-svg/{model_id}/{stored_name}。
        Returns {stored_path, filename, file_size, url}.
        """
        import uuid
        from pathlib import PurePath

        ext = PurePath(original_name).suffix.lower()
        if ext != ".svg":
            raise FileStorageError("Unsupported format: only .svg allowed")

        stem = ''.join(c for c in PurePath(original_name).stem if c.isalnum() or c in '-_')[:32] or 'drawing'
        short_uid = uuid.uuid4().hex[:8]
        stored_name = f"{stem}_{short_uid}{ext}"

        parts = ["drawing-svgs"]
        if model_id is not None:
            parts.append(str(model_id))
        parts.append(stored_name)
        drawing_dir = self._safe_join(*parts[:-1])
        drawing_dir.mkdir(parents=True, exist_ok=True)
        stored_path = drawing_dir / stored_name

        with open(stored_path, "wb") as f:
            f.write(file_content)

        rel = "/".join(parts)
        url = f"/api/server-catalog/drawing-svg/{model_id}/{stored_name}" if model_id is not None \
            else f"/api/server-catalog/drawing-svg/{stored_name}"
        return {
            "stored_path": rel,
            "filename": stored_name,
            "file_size": len(file_content),
            "url": url,
        }
