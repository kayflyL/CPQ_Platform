"""服务器类型 / 机型目录 API（配置面选机型入口）"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from typing import Optional
from app.repository.server_catalog_repo import ServerCatalogRepository
from app.utils.file_storage import FileStorage

router = APIRouter(prefix="/api/server-catalog", tags=["server-catalog"])

_MODEL_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_MODEL_IMAGE_MAX = 5 * 1024 * 1024


@router.get("/types")
def list_types():
    return {"types": ServerCatalogRepository().list_types()}


@router.post("/types")
def create_type(data: dict):
    try:
        return {"id": ServerCatalogRepository().insert_type(data)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.put("/types/{type_id}")
def update_type(type_id: int, updates: dict):
    """更新服务器类型，包括 showcase_config"""
    repo = ServerCatalogRepository()
    if not repo.get_type(type_id):
        raise HTTPException(404, "服务器类型不存在")
    repo.update_type(type_id, updates)
    return {"ok": True}


@router.post("/types/glb")
async def upload_showcase_glb(file: UploadFile = File(...)):
    """上传 3D 展示模型（GLB/GLTF），返回可直接用于 useServerModel3D 的 URL。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in {'.glb', '.gltf'}:
        raise HTTPException(
            400, f"不支持的模型格式 {ext or '(无)'}，仅支持 .glb/.gltf"
        )
    content = await file.read()
    max_size = 20 * 1024 * 1024  # 20MB
    if len(content) > max_size:
        raise HTTPException(400, "模型文件过大（>20MB）")
    try:
        info = FileStorage().save_showcase_model(content, file.filename or "model.glb")
    except Exception as e:
        raise HTTPException(500, f"模型保存失败：{e}")
    return {"url": info["url"], "filename": info["filename"]}


@router.get("/showcase-models/{filename}")
def get_showcase_model(filename: str):
    """读取 3D 展示模型（GLB/GLTF）"""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "非法文件名")
    path = FileStorage().base_path / "showcase-models" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "模型文件不存在")
    return FileResponse(str(path))


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


# ---- 机型主图（本地上传）----
@router.post("/models/image")
async def upload_model_image(file: UploadFile = File(...)):
    """本地上传机型主图，落盘 storage/model-images/，返回可直接用于 <img :src> 的 URL。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _MODEL_IMAGE_EXTS:
        raise HTTPException(
            400, f"不支持的图片格式 {ext or '(无)'}，仅支持 {'/'.join(sorted(_MODEL_IMAGE_EXTS))}"
        )
    content = await file.read()
    if len(content) > _MODEL_IMAGE_MAX:
        raise HTTPException(400, "图片过大（>5MB）")
    try:
        info = FileStorage().save_model_image(content, file.filename or "model.png")
    except Exception as e:
        raise HTTPException(500, f"图片保存失败：{e}")
    return {"url": f"/api/server-catalog/model-image/{info['filename']}", "filename": info["filename"]}


@router.get("/model-image/{filename}")
def get_model_image(filename: str):
    """读取机型主图（FileResponse，供 <img :src> 直接用）。"""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "非法文件名")
    path = FileStorage().base_path / "model-images" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "图片不存在")
    return FileResponse(str(path))
