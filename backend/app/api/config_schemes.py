"""配置方案 API（服务器页配置面产出 / 无价 BOM 保存读取）。"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from app.repository.config_scheme_repo import ConfigSchemeRepository

router = APIRouter(prefix="/api/config-schemes", tags=["config-schemes"])


@router.get("")
def list_schemes(model_id: Optional[int] = None):
    return {"schemes": ConfigSchemeRepository().list(model_id)}


@router.get("/{scheme_id}")
def get_scheme(scheme_id: int):
    s = ConfigSchemeRepository().get(scheme_id)
    if not s:
        raise HTTPException(404, "配置方案不存在")
    return s


@router.post("")
def create_scheme(data: dict):
    """data: { name?, model_id?, payload: {kp_lines, gpu_arch, rear, overrides, ...} }"""
    if "payload" not in data:
        raise HTTPException(400, "payload 必填")
    return {"id": ConfigSchemeRepository().insert(data)}


@router.delete("/{scheme_id}")
def delete_scheme(scheme_id: int):
    ConfigSchemeRepository().delete(scheme_id)
    return {"ok": True}
