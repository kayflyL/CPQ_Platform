"""API endpoints for system configuration"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from typing import Any
from app.repository.system_config_repo import SystemConfigRepository
from app.utils.file_storage import FileStorage

router = APIRouter(prefix="/api/system-config", tags=["system-config"])

_BRANDING_KEY = "branding"
_BRANDING_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".svg"}
_BRANDING_LOGO_URL = "/api/system-config/branding/logo"


@router.get("/")
def list_configs():
    """Get all system configs (excluding branding, which is now managed via spec templates)"""
    repo = SystemConfigRepository()
    try:
        all_configs = repo.get_all()
        # 过滤掉 branding 参数（已迁移至规格书模板管理）
        return [c for c in all_configs if c.get("key") != _BRANDING_KEY]
    finally:
        repo.close()


@router.get("/{key}")
def get_config(key: str):
    """Get config by key"""
    repo = SystemConfigRepository()
    try:
        config = repo.get(key)
        if not config:
            raise HTTPException(status_code=404, detail=f"Config '{key}' not found")
        return config
    finally:
        repo.close()


@router.get("/{key}/value")
def get_config_value(key: str, default: Any = None):
    """Get config value only"""
    repo = SystemConfigRepository()
    try:
        value = repo.get_value(key, default)
        return {"key": key, "value": value}
    finally:
        repo.close()


@router.put("/{key}")
def set_config(key: str, data: dict):
    """Set config value"""
    repo = SystemConfigRepository()
    try:
        value = data.get("value")
        if value is None:
            raise HTTPException(status_code=400, detail="Missing 'value' field")
        
        type = data.get("type", "string")
        description = data.get("description")
        operator = data.get("operator", "system")
        
        return repo.set(key, value, type, description, operator)
    finally:
        repo.close()


@router.delete("/{key}")
def delete_config(key: str):
    """Delete config"""
    repo = SystemConfigRepository()
    try:
        success = repo.delete(key)
        if not success:
            raise HTTPException(status_code=404, detail=f"Config '{key}' not found")
        return {"success": True}
    finally:
        repo.close()


@router.post("/init-defaults")
def init_defaults():
    """Initialize default configs"""
    repo = SystemConfigRepository()
    try:
        repo.init_defaults()
        return {"success": True, "message": "Default configs initialized"}
    finally:
        repo.close()


@router.post("/branding/logo")
async def upload_branding_logo(file: UploadFile = File(...)):
    """上传品牌 logo（覆盖式，落盘到 storage/branding/logo<ext>，并写回 branding.logo_path）。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _BRANDING_LOGO_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式 {ext or '(无)'}，仅支持 {'/'.join(sorted(_BRANDING_LOGO_EXTS))}",
        )
    content = await file.read()
    storage = FileStorage()
    try:
        info = storage.save_branding_logo(content, file.filename or "logo.png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"logo 保存失败：{e}")
    repo = SystemConfigRepository()
    try:
        branding = repo.get_value(_BRANDING_KEY, {}) or {}
        if not isinstance(branding, dict):
            branding = {}
        branding["logo_path"] = info["stored_path"]
        branding["logo_url"] = _BRANDING_LOGO_URL
        repo.set(_BRANDING_KEY, branding, type="json")
    finally:
        repo.close()
    return {
        "logo_path": info["stored_path"],
        "logo_url": _BRANDING_LOGO_URL,
        "file_size": info["file_size"],
    }


@router.get("/branding/logo")
def get_branding_logo():
    """读取品牌 logo（FileResponse，供 <img :src> 直接用）。"""
    repo = SystemConfigRepository()
    try:
        branding = repo.get_value(_BRANDING_KEY, {}) or {}
    finally:
        repo.close()
    logo_path = branding.get("logo_path") if isinstance(branding, dict) else None
    if not logo_path:
        raise HTTPException(status_code=404, detail="未设置 logo")
    abs_path = FileStorage().base_path / logo_path
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="logo 文件不存在")
    return FileResponse(
        str(abs_path),
        headers={"Cache-Control": "no-cache, must-revalidate"},
    )
