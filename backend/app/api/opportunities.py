import logging

logger = logging.getLogger(__name__)
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from app.services.quote_service import QuoteService
from app.utils.file_storage import FileStorage
from app.repository.opportunity_file_repo import OpportunityFileRepository
from app.repository.opportunity_repo import OpportunityRepository
import os
from pathlib import Path
from datetime import datetime
from pydantic import BaseModel

# === File upload security constants ===
_ALLOWED_UPLOAD_EXTENSIONS = {
    '.xlsx', '.xls', '.csv', '.pdf', '.docx', '.doc',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.txt', '.zip',
}
_BLOCKED_OPEN_EXTENSIONS = {
    '.exe', '.bat', '.cmd', '.ps1', '.vbs', '.sh', '.com',
    '.scr', '.msi', '.jar', '.py', '.rb', '.php', '.js',
}
_MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
from urllib.parse import quote

router = APIRouter(
    prefix="/api/opportunities",
    tags=["opportunities"]
)


class CreateOpportunityRequest(BaseModel):
    opportunity_name: str
    customer_name: str = ""
    notes: str = ""


class UpdateOpportunityRequest(BaseModel):
    opportunity_name: Optional[str] = None
    customer_name: Optional[str] = None
    purchase_qty: Optional[int] = None
    platform_type: Optional[str] = None
    chassis_form: Optional[str] = None
    sales_person: Optional[str] = None
    fae: Optional[str] = None
    quotation_person: Optional[str] = None
    
    class Config:
        extra = "allow"  # Allow dynamic fields from field system


@router.post("/")
def create_empty_opportunity(req: CreateOpportunityRequest):
    """Create an empty opportunity manually."""
    from app.utils.file_storage import FileStorage
    
    repo = OpportunityRepository()
    try:
        opportunity_id = f"PRJ-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 创建数据库记录
        repo.create_or_update_opportunity(opportunity_id, {
            "folder_name": opportunity_id,
            "opportunity_name": req.opportunity_name,
            "customer_name": req.customer_name,
        })
        
        # 创建物理文件夹
        file_storage = FileStorage()
        opportunity_info = {
            "opportunity_name": req.opportunity_name,
            "customer_name": req.customer_name,
        }
        folder_name = file_storage.generate_opportunity_folder_name(opportunity_info)
        file_storage.create_opportunity_folder(folder_name)
        
        # 更新数据库中的 folder_name
        repo.update_meta(opportunity_id, {"folder_name": folder_name})
        
        return {
            "status": "success",
            "opportunity_id": opportunity_id,
            "folder_name": folder_name,
            "message": "商机创建成功"
        }
    finally:
        repo.close()


@router.get("/list")
def list_opportunities(page: int = 1, page_size: int = 50, include_deleted: bool = False):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        items, total = repo.list_opportunities(include_deleted, page, page_size)
        return {"items": items, "total": total}
    finally:
        repo.close()


@router.put("/{opportunity_id}")
def update_opportunity(opportunity_id: str, req: UpdateOpportunityRequest):
    """Update opportunity basic info (supports dynamic fields)"""
    repo = OpportunityRepository()
    try:
        # Extract all fields from request (including dynamic ones)
        updates = req.dict(exclude_unset=True)
        
        if not updates:
            return {"status": "success", "message": "No fields to update"}
        
        success = repo.update_meta(opportunity_id, updates)
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return {"status": "success", "message": "Project updated"}
    finally:
        repo.close()


@router.get("/{opportunity_id}")
def get_opportunity(opportunity_id: str):
    service = QuoteService()
    try:
        result = service.get_opportunity_details(opportunity_id)
        if result.get("status") == "error":
            raise HTTPException(status_code=404, detail=result.get("message"))
        return result
    finally:
        service.close()


@router.post("/save")
def save_opportunity(data: dict):
    """Save opportunity and move temp files to opportunity folder"""
    service = QuoteService()
    try:
        opportunity_info = data.get("opportunity_info", {})
        configs = data.get("configs", {})
        config_quantities = data.get("config_quantities", {})
        temp_file = data.get("temp_file", None)  # Temp file info from upload
        
        # Save opportunity to database
        result = service.save_opportunity(opportunity_info, configs, config_quantities)
        
        # If save successful, always create folder and update folder_name
        if result.get("status") == "success":
            opportunity_id = result.get("opportunity_id")
            if opportunity_id:
                file_storage = FileStorage()
                file_repo = OpportunityFileRepository()
                opportunity_repo = OpportunityRepository()
                try:
                    # Generate folder name based on business rules
                    folder_name = file_storage.generate_opportunity_folder_name(opportunity_info)
                    
                    # Always create folder structure
                    file_storage.create_opportunity_folder(folder_name)
                    
                    if temp_file and temp_file.get('temp_path'):
                        # Move temp file to opportunity folder
                        file_info = file_storage.move_temp_to_opportunity(
                            temp_path=temp_file['temp_path'],
                            opportunity_id=folder_name,
                            original_name=temp_file['original_name']
                        )
                        
                        # Save file record to database
                        file_repo.add_file(
                            opportunity_id=folder_name,
                            file_type='upload',
                            original_name=temp_file['original_name'],
                            stored_path=file_info['stored_path'],
                            file_size=file_info['file_size']
                        )
                    
                    # Update database with folder_name
                    opportunity_repo.update_meta(opportunity_id, {"folder_name": folder_name})
                    
                    # Return folder_name in result for frontend reference
                    result['folder_name'] = folder_name
                finally:
                    file_repo.close()
                    opportunity_repo.close()
        
        return result
    except Exception as e:
        import traceback
        print(f"[ERROR save_opportunity] UNEXPECTED ERROR: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        service.close()


@router.get("/{opportunity_id}/files")
def get_opportunity_files(opportunity_id: str):
    """Scan opportunity uploads folder and return real-time file list.
    
    This reads the actual filesystem, so manually added/renamed/deleted
    files are immediately reflected — no DB sync lag.
    """
    from pathlib import Path
    
    # Get folder_name from database
    opportunity_repo = OpportunityRepository()
    try:
        opportunity_info = opportunity_repo.get_opportunity(opportunity_id)
        if not opportunity_info:
            raise HTTPException(status_code=404, detail="Project not found")
        folder_name = opportunity_info.get('folder_name')
    finally:
        opportunity_repo.close()
    
    if not folder_name:
        return {"files": [], "total": 0}
    
    # Scan actual filesystem - both uploads and exports
    file_storage = FileStorage()
    opportunity_dir = file_storage.base_path / folder_name
    upload_dir = opportunity_dir / "uploads"
    export_dir = opportunity_dir / "exports"
    
    files = []
    
    # Scan uploads folder
    if upload_dir.exists():
        for f in sorted(upload_dir.iterdir()):
            if f.is_file() and not f.name.startswith('.'):
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "upload",
                })
    
    # Scan exports folder
    if export_dir.exists():
        for f in sorted(export_dir.iterdir()):
            if f.is_file() and not f.name.startswith('.'):
                stat = f.stat()
                files.append({
                    "name": f.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "type": "export",
                })
    
    return {"files": files, "total": len(files)}


@router.get("/{opportunity_id}/files/download")
def download_opportunity_file(opportunity_id: str, filename: str):
    """Download a file by its actual filename from uploads or exports folder."""
    from pathlib import Path
    
    # Get folder_name from database
    opportunity_repo = OpportunityRepository()
    try:
        opportunity_info = opportunity_repo.get_opportunity(opportunity_id)
        if not opportunity_info:
            raise HTTPException(status_code=404, detail="Project not found")
        folder_name = opportunity_info.get('folder_name')
    finally:
        opportunity_repo.close()
    
    if not folder_name:
        raise HTTPException(status_code=404, detail="File storage not initialized")
    
    file_storage = FileStorage()
    opportunity_dir = file_storage.base_path / folder_name
    
    # Try uploads folder first, then exports
    file_path = None
    for subdir in ["uploads", "exports"]:
        candidate = opportunity_dir / subdir / filename
        if candidate.exists() and candidate.is_file():
            file_path = candidate
            break
    
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Security: prevent path traversal
    try:
        file_path.resolve().relative_to(opportunity_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid file path")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type='application/octet-stream'
    )


@router.put("/{opportunity_id}/files/rename")
def rename_opportunity_file(opportunity_id: str, old_name: str, new_name: str):
    """Rename a file in the opportunity uploads or exports folder."""
    # Get folder_name from database
    opportunity_repo = OpportunityRepository()
    try:
        opportunity_info = opportunity_repo.get_opportunity(opportunity_id)
        if not opportunity_info:
            raise HTTPException(status_code=404, detail="Project not found")
        folder_name = opportunity_info.get('folder_name')
    finally:
        opportunity_repo.close()
    
    if not folder_name:
        raise HTTPException(status_code=404, detail="File storage not initialized")
    
    file_storage = FileStorage()
    opportunity_dir = file_storage.base_path / folder_name
    
    # Try to find file in uploads or exports
    old_path = None
    subdir = None
    for d in ["uploads", "exports"]:
        candidate = opportunity_dir / d / old_name
        if candidate.exists():
            old_path = candidate
            subdir = d
            break
    
    if not old_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    new_path = opportunity_dir / subdir / new_name
    
    # Security: prevent path traversal
    try:
        old_path.resolve().relative_to(opportunity_dir.resolve())
        new_path.resolve().relative_to(opportunity_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid file path")
    
    if new_path.exists():
        raise HTTPException(status_code=400, detail="File with new name already exists")
    
    try:
        old_path.rename(new_path)
        return {"status": "success", "old_name": old_name, "new_name": new_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to rename file")


@router.delete("/{opportunity_id}/files")
def delete_opportunity_file(opportunity_id: str, filename: str):
    """Delete a file from the opportunity uploads or exports folder."""
    # Get folder_name from database
    opportunity_repo = OpportunityRepository()
    try:
        opportunity_info = opportunity_repo.get_opportunity(opportunity_id)
        if not opportunity_info:
            raise HTTPException(status_code=404, detail="Project not found")
        folder_name = opportunity_info.get('folder_name')
    finally:
        opportunity_repo.close()
    
    if not folder_name:
        raise HTTPException(status_code=404, detail="File storage not initialized")
    
    file_storage = FileStorage()
    opportunity_dir = file_storage.base_path / folder_name
    
    # Try to find file in uploads or exports
    file_path = None
    for d in ["uploads", "exports"]:
        candidate = opportunity_dir / d / filename
        if candidate.exists():
            file_path = candidate
            break
    
    if not file_path:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Security: prevent path traversal
    try:
        file_path.resolve().relative_to(opportunity_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid file path")
    
    try:
        file_path.unlink()
        return {"status": "success", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete file")


@router.post("/{opportunity_id}/files/upload")
async def upload_opportunity_file(opportunity_id: str, file: UploadFile = File(...)):
    """Upload a new file to the opportunity uploads folder."""
    # Get folder_name from database
    opportunity_repo = OpportunityRepository()
    try:
        opportunity_info = opportunity_repo.get_opportunity(opportunity_id)
        if not opportunity_info:
            raise HTTPException(status_code=404, detail="Project not found")
        folder_name = opportunity_info.get('folder_name')
    finally:
        opportunity_repo.close()
    
    if not folder_name:
        raise HTTPException(status_code=404, detail="File storage not initialized")
    
    file_storage = FileStorage()
    upload_dir = file_storage.base_path / folder_name / "uploads"

    # Ensure uploads directory exists
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Validate file type
    ext = Path(file.filename or '').suffix.lower()
    if ext not in _ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}（允许: {', '.join(sorted(_ALLOWED_UPLOAD_EXTENSIONS))}）")

    file_path = upload_dir / file.filename

    # Security: prevent path traversal
    try:
        file_path.resolve().relative_to((file_storage.base_path / folder_name).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid file path")

    try:
        content = await file.read()
        if len(content) > _MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail=f"文件过大，最大允许 {_MAX_UPLOAD_SIZE // (1024*1024)}MB")
        with open(file_path, 'wb') as f:
            f.write(content)
        
        return {
            "status": "success",
            "filename": file.filename,
            "size": len(content)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to upload file")


@router.get("/{opportunity_id}/folder-path")
def get_opportunity_folder_path(opportunity_id: str):
    """Get the absolute path of the opportunity folder (for opening in file explorer)."""
    # Get folder_name from database
    opportunity_repo = OpportunityRepository()
    try:
        opportunity_info = opportunity_repo.get_opportunity(opportunity_id)
        if not opportunity_info:
            raise HTTPException(status_code=404, detail="Project not found")
        folder_name = opportunity_info.get('folder_name')
    finally:
        opportunity_repo.close()
    
    if not folder_name:
        raise HTTPException(status_code=404, detail="File storage not initialized")
    
    file_storage = FileStorage()
    folder_path = file_storage.base_path / folder_name
    
    return {
        "folder_path": str(folder_path.resolve()),
        "uploads_path": str((folder_path / "uploads").resolve()),
        "exports_path": str((folder_path / "exports").resolve())
    }


@router.post("/{opportunity_id}/files/open")
def open_opportunity_file(opportunity_id: str, filename: str):
    """Open a file with the system default application (local deployment only)."""
    import platform
    import subprocess
    
    # Get folder_name from database
    opportunity_repo = OpportunityRepository()
    try:
        opportunity_info = opportunity_repo.get_opportunity(opportunity_id)
        if not opportunity_info:
            raise HTTPException(status_code=404, detail="Project not found")
        folder_name = opportunity_info.get('folder_name')
    finally:
        opportunity_repo.close()
    
    if not folder_name:
        raise HTTPException(status_code=404, detail="File storage not initialized")
    
    file_storage = FileStorage()
    file_path = file_storage.base_path / folder_name / "uploads" / filename

    # Security: prevent path traversal
    try:
        file_path.resolve().relative_to((file_storage.base_path / folder_name).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid file path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # Security: block executable file types to prevent RCE
    ext = Path(filename).suffix.lower()
    if ext in _BLOCKED_OPEN_EXTENSIONS:
        raise HTTPException(status_code=403, detail=f"出于安全考虑，不允许打开可执行文件类型: {ext}")
    
    try:
        system = platform.system()
        if system == 'Windows':
            os.startfile(str(file_path))
        elif system == 'Darwin':  # macOS
            subprocess.run(['open', str(file_path)], check=True)
        else:  # Linux
            subprocess.run(['xdg-open', str(file_path)], check=True)
        
        return {"status": "success", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to open file")


@router.post("/{opportunity_id}/trash")
def move_to_trash(opportunity_id: str):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        repo.move_to_trash(opportunity_id)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.post("/{opportunity_id}/restore")
def restore_opportunity(opportunity_id: str):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        repo.restore_opportunity(opportunity_id)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.delete("/{opportunity_id}")
def permanent_delete(opportunity_id: str):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        repo.permanent_delete(opportunity_id)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


@router.put("/{opportunity_id}/meta")
def update_opportunity_meta(opportunity_id: str, updates: dict):
    from app.repository.opportunity_repo import OpportunityRepository
    repo = OpportunityRepository()
    try:
        repo.update_meta(opportunity_id, updates)
        return {"status": "success"}
    except Exception as e:
        logger.exception("Unhandled error")
        raise HTTPException(status_code=500, detail="内部服务器错误")
    finally:
        repo.close()


# ── Batch Operations ──

class BatchOpportunityRequest(BaseModel):
    opportunity_ids: List[str]


@router.post("/batch-trash")
def batch_move_to_trash(req: BatchOpportunityRequest):
    """批量移至回收站"""
    repo = OpportunityRepository()
    results = {"success": [], "failed": []}
    try:
        for pid in req.opportunity_ids:
            try:
                repo.move_to_trash(pid)
                results["success"].append(pid)
            except Exception as e:
                results["failed"].append({"id": pid, "error": str(e)})
        return results
    finally:
        repo.close()
