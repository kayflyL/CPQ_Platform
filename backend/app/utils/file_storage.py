"""File storage utilities for opportunity files"""
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional


class FileStorageError(Exception):
    """Raised when a file storage operation violates security constraints."""
    pass


class FileStorage:
    """Handles file storage operations for opportunities"""
    
    def __init__(self, base_path: Optional[str] = None):
        """Initialize file storage
        
        Args:
            base_path: Base directory for file storage. Defaults to D:\CPQ_Platform_V1\storage
        """
        if base_path is None:
            # Default to opportunity root + storage
            base_path = Path(__file__).parent.parent.parent / "storage"
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Temporary directory for uploads before opportunity is saved
        self.temp_dir = self.base_path / "_temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def cleanup_temp(self, max_age_hours: int = 24) -> int:
        """Remove temporary files older than max_age_hours.

        Should be called periodically (e.g., on app startup) to prevent
        orphan files from accumulating in the _temp directory.

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
    
    def generate_opportunity_folder_name(self, opportunity_info: dict) -> str:
        """Generate opportunity folder name based on business rules
        
        Format: {时间}_{销售}_{机箱形态}_{平台类型}_{配置数}配置_{台数}台
        Example: 20260703_张三_2U_浪潮_3配置_10台
        
        Args:
            opportunity_info: Project information dict with keys like sales_person, 
                         chassis_form, platform_type, config_count, total_qty
        
        Returns:
            Formatted folder name
        """
        # 时间
        time_str = datetime.now().strftime("%Y%m%d")
        
        # 业务/销售
        sales = opportunity_info.get('sales_person', '') or '未知销售'
        # 清理特殊字符，替换下划线和空格
        sales = sales.replace('_', '').replace(' ', '').replace('/', '')
        
        # 机箱形态
        chassis = opportunity_info.get('chassis_form', '') or '未知机箱'
        chassis = chassis.replace('_', '').replace(' ', '')
        
        # 平台类型
        platform = opportunity_info.get('platform_type', '') or '未知平台'
        platform = platform.replace('_', '').replace(' ', '')
        
        # 配置数
        config_count = opportunity_info.get('config_count', 0) or 0
        
        # 台数
        total_qty = opportunity_info.get('purchase_qty', 0) or 0
        
        folder_name = f"{time_str}_{sales}_{chassis}_{platform}_{config_count}配置_{total_qty}台"
        return folder_name
    
    def create_opportunity_folder(self, folder_name: str) -> Path:
        """Create opportunity folder structure (uploads and exports subdirectories)
        
        Args:
            folder_name: Project folder name
        
        Returns:
            Path to opportunity directory
        """
        project_dir = self._get_project_dir(folder_name)
        project_dir.mkdir(parents=True, exist_ok=True)
        (project_dir / "uploads").mkdir(exist_ok=True)
        (project_dir / "exports").mkdir(exist_ok=True)
        return project_dir
    
    def _safe_join(self, *parts: str) -> Path:
        """Join path parts and verify the result stays within base_path.

        Defense-in-depth against path traversal (e.g., opportunity_id='..').
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

    def _get_project_dir(self, opportunity_id: str) -> Path:
        """Get opportunity directory path (does not create it)

        Note: opportunity_id here is actually the folder_name
        """
        return self._safe_join(opportunity_id)
    
    def _get_upload_dir(self, opportunity_id: str) -> Path:
        """Get upload directory for an opportunity (creates it)"""
        upload_dir = self._get_project_dir(opportunity_id) / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        return upload_dir
    
    def _get_export_dir(self, opportunity_id: str) -> Path:
        """Get export directory for an opportunity (creates it)"""
        export_dir = self._get_project_dir(opportunity_id) / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        return export_dir
    
    def _generate_filename(self, original_name: str, prefix: str = "") -> str:
        """Generate timestamped filename
        
        Args:
            original_name: Original filename
            prefix: Optional suffix tag (e.g., 'export')
        
        Returns:
            New filename with timestamp appended before extension
        """
        from pathlib import PurePath
        p = PurePath(original_name)
        stem = p.stem
        ext = p.suffix  # e.g. '.xlsx'
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if prefix:
            return f"{stem}_{prefix}_{timestamp}{ext}"
        return f"{stem}_{timestamp}{ext}"
    
    def save_upload_temp(self, file_content: bytes, original_name: str) -> dict:
        """Save uploaded file to temporary directory
        
        Args:
            file_content: File content as bytes
            original_name: Original filename
        
        Returns:
            dict with temp_path, file_size, created_at
        """
        stored_name = self._generate_filename(original_name)
        stored_path = self.temp_dir / stored_name
        
        # Write file
        with open(stored_path, "wb") as f:
            f.write(file_content)
        
        file_size = len(file_content)
        created_at = datetime.now().isoformat()
        
        return {
            "temp_path": str(stored_path),
            "file_size": file_size,
            "created_at": created_at,
        }
    
    def save_upload(self, opportunity_id: str, file_content: bytes, original_name: str) -> dict:
        """Save uploaded file to opportunity directory
        
        Args:
            opportunity_id: Project ID
            file_content: File content as bytes
            original_name: Original filename
        
        Returns:
            dict with stored_path, file_size, created_at
        """
        upload_dir = self._get_upload_dir(opportunity_id)
        stored_name = self._generate_filename(original_name)
        stored_path = upload_dir / stored_name
        
        # Write file
        with open(stored_path, "wb") as f:
            f.write(file_content)
        
        file_size = len(file_content)
        created_at = datetime.now().isoformat()
        
        return {
            "stored_path": f"uploads/{stored_name}",
            "file_size": file_size,
            "created_at": created_at,
        }
    
    def save_export(self, opportunity_id: str, file_content: bytes, original_name: str) -> dict:
        """Save exported file to opportunity directory
        
        Args:
            opportunity_id: Project ID
            file_content: File content as bytes
            original_name: Original filename
        
        Returns:
            dict with stored_path, file_size, created_at
        """
        export_dir = self._get_export_dir(opportunity_id)
        stored_name = self._generate_filename(original_name, prefix="export")
        stored_path = export_dir / stored_name
        
        # Write file
        with open(stored_path, "wb") as f:
            f.write(file_content)
        
        file_size = len(file_content)
        created_at = datetime.now().isoformat()
        
        return {
            "stored_path": f"exports/{stored_name}",
            "file_size": file_size,
            "created_at": created_at,
        }
    
    def move_temp_to_opportunity(self, temp_path: str, opportunity_id: str, original_name: str) -> dict:
        """Move file from temp directory to opportunity directory
        
        Args:
            temp_path: Path to temporary file
            opportunity_id: Project ID
            original_name: Original filename
        
        Returns:
            dict with stored_path, file_size, created_at
        """
        temp_file = Path(temp_path)
        if not temp_file.exists():
            raise FileNotFoundError(f"Temp file not found: {temp_path}")
        
        upload_dir = self._get_upload_dir(opportunity_id)
        stored_name = self._generate_filename(original_name)
        stored_path = upload_dir / stored_name
        
        # Move file
        shutil.move(str(temp_file), str(stored_path))
        
        file_size = stored_path.stat().st_size
        created_at = datetime.now().isoformat()
        
        return {
            "stored_path": f"uploads/{stored_name}",
            "file_size": file_size,
            "created_at": created_at,
        }
    
    def get_file_path(self, opportunity_id: str, stored_path: str) -> Path:
        """Get absolute file path."""
        return self._safe_join(opportunity_id, stored_path)

    def delete_opportunity_files(self, opportunity_id: str) -> bool:
        """Delete all files for an opportunity."""
        project_dir = self._get_project_dir(opportunity_id)
        if project_dir.exists():
            shutil.rmtree(project_dir)
            return True
        return False

    def get_project_file_count(self, opportunity_id: str) -> dict:
        """Get file count for an opportunity folder."""
        project_dir = self._get_project_dir(opportunity_id)
        counts = {"uploads": 0, "exports": 0}
        for subdir in ("uploads", "exports"):
            d = project_dir / subdir
            if d.exists():
                counts[subdir] = len([f for f in d.iterdir() if f.is_file()])
        return counts
