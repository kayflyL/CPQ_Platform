"""API endpoints for system configuration"""
from fastapi import APIRouter, HTTPException
from typing import Any
from app.repository.system_config_repo import SystemConfigRepository

router = APIRouter(prefix="/api/system-config", tags=["system-config"])


@router.get("/")
def list_configs():
    """Get all system configs"""
    repo = SystemConfigRepository()
    try:
        return repo.get_all()
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
