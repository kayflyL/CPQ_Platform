"""服务器类型 / 机型目录 API（配置面选机型入口）"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from typing import Optional
from app.repository.server_catalog_repo import ServerCatalogRepository
from app.utils.svg_sanitizer import sanitize_svg
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


# ---- 服务器可视化图纸（SVG 上传 + 标注配置，drawing_config JSONB）----
_DRAWING_VIEWS = {"top", "front", "rear"}
_DRAWING_MAX = 5 * 1024 * 1024
_DRAWING_REGION_TYPES = {"bays", "cpus", "gpu", "fans", "psu", "io", "plain"}
_DRAWING_MAX_REGIONS = 50


def _normalize_regions(raw) -> list:
    """校验并归一化区域标注数组；非法输入抛 ValueError（调用方转 400）。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("regions 必须是数组")
    if len(raw) > _DRAWING_MAX_REGIONS:
        raise ValueError(f"区域数量超出上限（{_DRAWING_MAX_REGIONS}）")
    out = []
    for i, r in enumerate(raw):
        if not isinstance(r, dict):
            raise ValueError(f"regions[{i}] 必须是对象")
        name = str(r.get("name") or "").strip()[:50]
        if not name:
            raise ValueError(f"regions[{i}].name 必填")
        rtype = str(r.get("region_type") or "")
        if rtype not in _DRAWING_REGION_TYPES:
            raise ValueError(f"regions[{i}].region_type 非法：{rtype}")
        uid = str(r.get("uid") or f"r{i}")[:40]
        x, y = float(r.get("x", 0)), float(r.get("y", 0))
        w, h = float(r.get("width", 0)), float(r.get("height", 0))
        for v in (x, y, w, h):
            if v != v or v in (float("inf"), float("-inf")):
                raise ValueError(f"regions[{i}] 坐标必须是有限数字")
        if w <= 0 or h <= 0:
            raise ValueError(f"regions[{i}] 宽高必须大于 0")
        remark = str(r.get("remark") or "").strip()[:200] or None
        out.append({"uid": uid, "name": name, "region_type": rtype,
                    "x": x, "y": y, "width": w, "height": h, "remark": remark})
    return out


def _normalize_view_box(raw) -> Optional[list]:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        raise ValueError("viewBox 必须是 [x, y, width, height]")
    out = [float(v) for v in raw]
    for v in out:
        if v != v or v in (float("inf"), float("-inf")):
            raise ValueError("viewBox 必须是有限数字")
    if out[2] <= 0 or out[3] <= 0:
        raise ValueError("viewBox 宽高必须大于 0")
    return out


_DRAWING_MAX_LAYERS = 500


def _normalize_layers(raw) -> Optional[list]:
    """归一化图层元数据：[{id, name?, visible?, locked?, opacity?}]；None 表示未修改。"""
    if raw is None:
        return None
    if not isinstance(raw, list):
        raise ValueError("layers 必须是数组")
    if len(raw) > _DRAWING_MAX_LAYERS:
        raise ValueError(f"图层数量超出上限（{_DRAWING_MAX_LAYERS}）")
    out = []
    for i, l in enumerate(raw):
        if not isinstance(l, dict):
            raise ValueError(f"layers[{i}] 必须是对象")
        lid = str(l.get("id") or "").strip()[:100]
        if not lid:
            raise ValueError(f"layers[{i}].id 必填")
        item = {"id": lid}
        if l.get("name") is not None:
            item["name"] = str(l["name"]).strip()[:100] or None
        if l.get("visible") is not None:
            item["visible"] = bool(l["visible"])
        if l.get("locked") is not None:
            item["locked"] = bool(l["locked"])
        if l.get("opacity") is not None:
            op = float(l["opacity"])
            if op != op or op < 0 or op > 1:
                raise ValueError(f"layers[{i}].opacity 必须在 0~1")
            item["opacity"] = op
        if len(item) > 1:
            out.append(item)
    return out


@router.post("/models/{model_id}/drawing")
async def upload_model_drawing(model_id: int, view: str = Query("top"),
                               file: UploadFile = File(...)):
    """上传机型视图图纸（SVG，服务端清洗后落盘），并挂到 drawing_config.views[view]。"""
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    ext = Path(file.filename or "").suffix.lower()
    if ext != ".svg":
        raise HTTPException(400, "仅支持 .svg 图纸")
    content = await file.read()
    if len(content) > _DRAWING_MAX:
        raise HTTPException(400, "图纸过大（>5MB）")
    try:
        cleaned, view_box = sanitize_svg(content)
    except ValueError as e:
        raise HTTPException(400, f"SVG 内容校验失败：{e}")
    try:
        info = FileStorage().save_drawing_svg(cleaned.encode("utf-8"), file.filename or "drawing.svg")
    except Exception as e:
        raise HTTPException(500, f"图纸保存失败：{e}")
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    cur = views.get(view) or {}
    # 已有图纸时先备份当前全套到 prev（替换向导/回退用；只保留一层）
    prev_data = None
    if cur.get("svg_url"):
        prev_data = {
            "svg_url": cur.get("svg_url"),
            "viewBox": cur.get("viewBox"),
            "regions": cur.get("regions") or [],
            "layers": cur.get("layers") or [],
        }
    views[view] = {
        "svg_url": info["url"],
        "viewBox": view_box,
        "regions": cur.get("regions") or [],
        "layers": cur.get("layers") or [],
    }
    if prev_data:
        views[view]["prev"] = prev_data
    repo.update_model(model_id, {"drawing_config": cfg})
    return {"url": info["url"], "viewBox": view_box,
            "regions": views[view]["regions"], "prev": prev_data}


@router.get("/models/{model_id}/drawing")
def get_model_drawing(model_id: int, view: str = Query("top")):
    """读取机型某视图的图纸配置；未配置返回 null。"""
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    cfg = repo.get_drawing_config(model_id) or {}
    return (cfg.get("views") or {}).get(view) or None


@router.put("/models/{model_id}/drawing")
def save_model_drawing(model_id: int, data: dict):
    """保存机型某视图的标注配置：{view, viewBox?, regions[]}（svg_url 由上传接口写入）。"""
    view = data.get("view")
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    try:
        regions = _normalize_regions(data.get("regions"))
        view_box = _normalize_view_box(data.get("viewBox"))
        layers = _normalize_layers(data.get("layers"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    cur = views.get(view) or {}
    cur["viewBox"] = view_box
    cur["regions"] = regions
    if "layers" in data:
        cur["layers"] = layers
    views[view] = cur
    repo.update_model(model_id, {"drawing_config": cfg})
    return {"ok": True, "view": views[view]}


@router.put("/models/{model_id}/drawing/svg")
async def save_model_drawing_svg(model_id: int, view: str = Query("top"), data: dict = None):
    """保存编辑后的图纸 SVG（整份文本）：服务端清洗后落盘并更新 svg_url，不动 regions/layers/prev。"""
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    content = (data or {}).get("svg") or ""
    if not content.strip():
        raise HTTPException(400, "svg 内容不能为空")
    if len(content.encode("utf-8")) > _DRAWING_MAX:
        raise HTTPException(400, "图纸过大（>5MB）")
    try:
        cleaned, view_box = sanitize_svg(content.encode("utf-8"))
    except ValueError as e:
        raise HTTPException(400, f"SVG 内容校验失败：{e}")
    try:
        info = FileStorage().save_drawing_svg(cleaned.encode("utf-8"), "drawing.svg")
    except Exception as e:
        raise HTTPException(500, f"图纸保存失败：{e}")
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    cur = views.get(view) or {}
    cur["svg_url"] = info["url"]
    cur["viewBox"] = view_box
    views[view] = cur
    repo.update_model(model_id, {"drawing_config": cfg})
    return {"ok": True, "url": info["url"], "viewBox": view_box}


@router.post("/models/{model_id}/drawing/rollback")
def rollback_model_drawing(model_id: int, view: str = Query("top")):
    """回退到上一版图纸：当前与 prev 互换（再点一次可切回）。"""
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    cur = views.get(view) or {}
    prev = cur.get("prev")
    if not prev:
        raise HTTPException(400, "没有上一版可回退")
    views[view] = {**prev, "prev": {k: cur.get(k) for k in ("svg_url", "viewBox", "regions", "layers") if cur.get(k)}}
    repo.update_model(model_id, {"drawing_config": cfg})
    return {"ok": True, "view": views[view]}


@router.get("/drawing-svg/{filename}")
def get_drawing_svg(filename: str):
    """读取机型图纸 SVG（清洗后落盘；nosniff + CSP 防脚本执行）。"""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "非法文件名")
    path = FileStorage().base_path / "drawing-svgs" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "图纸不存在")
    return FileResponse(
        str(path), media_type="image/svg+xml",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "script-src 'none'; object-src 'none'",
        },
    )
