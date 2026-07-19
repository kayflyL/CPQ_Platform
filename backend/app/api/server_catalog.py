"""服务器类型 / 机型目录 API（配置面选机型入口）"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from app.repository.server_catalog_repo import ServerCatalogRepository

router = APIRouter(prefix="/api/server-catalog", tags=["server-catalog"])


@router.get("/types")
def list_types():
    return {"types": ServerCatalogRepository().list_types()}


@router.post("/types")
def create_type(data: dict):
    try:
        return {"id": ServerCatalogRepository().insert_type(data)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/models")
def list_models(type_id: Optional[int] = None):
    return {"models": ServerCatalogRepository().list_models(type_id)}


@router.get("/models/{model_id}")
def get_model(model_id: int):
    m = ServerCatalogRepository().get_model(model_id)
    if not m:
        raise HTTPException(404, "机型不存在")
    return m


@router.post("/models")
def create_model(data: dict):
    try:
        return {"id": ServerCatalogRepository().insert_model(data)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/models/{model_id}")
def update_model(model_id: int, updates: dict):
    ServerCatalogRepository().update_model(model_id, updates)
    return {"ok": True}


@router.delete("/models/{model_id}")
def delete_model(model_id: int):
    ServerCatalogRepository().delete_model(model_id)
    return {"ok": True}
