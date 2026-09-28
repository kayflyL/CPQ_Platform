"""服务器类型 / 机型目录 API（配置面选机型入口）"""
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from typing import Optional
from app.api.deps import require_admin
from app.repository.server_catalog_repo import ServerCatalogRepository
from app.repository.system_config_repo import SystemConfigRepository
from app.utils.svg_sanitizer import sanitize_svg
from app.utils.file_storage import FileStorage

router = APIRouter(prefix="/api/server-catalog", tags=["server-catalog"])

_MODEL_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
_MODEL_IMAGE_MAX = 5 * 1024 * 1024

# 门户 banner 配置（system_config 键）：标题/副标题可空（空=前端用内置默认文案），images 为轮播图 URL 列表
_PORTAL_BANNER_KEY = "server_portal_banner"


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
def list_models(type_id: Optional[int] = None, published_only: bool = False):
    """机型列表。published_only=true 只返回上架机型（服务器货架/机型目录用）；
    缺省全量——管理面、报价工作台、推理流等工作场景仍可见下架机型。"""
    return {"models": ServerCatalogRepository().list_models(type_id, published_only=published_only)}


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
    """更新机型；换图（主图/场景图）后旧文件若无引用自动删除（替换语义）。"""
    repo = ServerCatalogRepository()
    old = repo.get_model(model_id)
    repo.update_model(model_id, updates)
    dropped = set()
    if old:
        new = repo.get_model(model_id) or {}
        dropped = _model_image_urls(old) - _model_image_urls(new)
    removed = _delete_unreferenced_model_images(dropped)
    return {"ok": True, "removed_images": removed}


@router.delete("/models/{model_id}")
def delete_model(model_id: int):
    """删除机型；其独占引用的图片文件一并清理。"""
    repo = ServerCatalogRepository()
    old = repo.get_model(model_id)
    repo.delete_model(model_id)
    removed = _delete_unreferenced_model_images(_model_image_urls(old)) if old else 0
    return {"ok": True, "removed_images": removed}


# ---- 机型图片（主图/场景/banner 共用内容寻址图片池；见 FileStorage.save_model_image） ----
_MODEL_IMAGE_URL_PREFIX = "/api/server-catalog/model-image/"


def _model_image_urls(rec) -> set:
    """收集一条机型记录引用的本站图片 URL（主图 image_url + product_content 亮点配图/场景配图）。"""
    out: set = set()

    def add(u):
        if isinstance(u, str) and u.startswith(_MODEL_IMAGE_URL_PREFIX):
            out.add(u)

    add(rec.get("image_url"))
    pc = rec.get("product_content")
    if isinstance(pc, dict):
        add(pc.get("highlight_image"))
        for s in pc.get("scenarios") or []:
            if isinstance(s, dict):
                add(s.get("image"))
    return out


def _banner_image_urls(raw_images) -> set:
    """轮播图列表 → URL 集合（兼容存量纯字符串项与 {url, subtitle} 对象项；图片引用判断用）。"""
    urls = set()
    for e in raw_images or []:
        if isinstance(e, dict):
            u = e.get("url")
            if isinstance(u, str) and u:
                urls.add(u)
        elif isinstance(e, str) and e:
            urls.add(e)
    return urls


def _delete_unreferenced_model_images(urls: set) -> int:
    """删除不再被任何机型（主图/场景图）和 banner 配置引用的本站图片文件。

    调用时机：机型行/banner 配置已更新（引用已落地），本函数扫全库兜底确认后删文件；
    跨机型共用同一张图（同 URL）时另一处仍引用则不删。返回删除数。
    """
    if not urls:
        return 0
    repo = ServerCatalogRepository()
    banner_imgs: set = set()
    try:
        cfg = SystemConfigRepository().get_value(_PORTAL_BANNER_KEY, {})
        if isinstance(cfg, dict):
            banner_imgs = _banner_image_urls(cfg.get("images"))
    except Exception:
        pass
    removed = 0
    for u in urls:
        if u in banner_imgs or repo.count_image_references(u) > 0:
            continue
        if FileStorage().delete_model_image(u.removeprefix(_MODEL_IMAGE_URL_PREFIX)):
            removed += 1
    return removed


@router.post("/models/image")
async def upload_model_image(
    file: UploadFile = File(...),
    type: str = Query(None, description="图片用途：product=机型主图 / scenario=场景配图 / highlight=为什么选它配图 / portal-banner=门户 banner 轮播图（内容寻址后仅作记录）"),
    model_id: int = Query(None, description="机型 id（兼容保留：内容寻址落盘不再依赖机型归属）"),
):
    """上传图片到内容寻址图片池 storage/model-images/（同内容幂等去重，URL 跨机型通用）。
    返回可直接用于 <img :src> 的 URL。"""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in _MODEL_IMAGE_EXTS:
        raise HTTPException(
            400, f"不支持的图片格式 {ext or '(无)'}，仅支持 {'/'.join(sorted(_MODEL_IMAGE_EXTS))}"
        )
    content = await file.read()
    if len(content) > _MODEL_IMAGE_MAX:
        raise HTTPException(400, "图片过大（>5MB）")
    try:
        info = FileStorage().save_model_image(content, file.filename or "model.png",
                                              model_key=None, img_type=type)
    except Exception as e:
        raise HTTPException(500, f"图片保存失败：{e}")
    return {"url": f"/api/server-catalog/model-image/{info['filename']}", "filename": info["filename"]}


@router.get("/model-image/{file_path:path}")
def get_model_image(file_path: str):
    """读取机型图片（FileResponse，供 <img :src> 直接用）。
    兼容新分类路径 {model_id}/{type}/{name} 与存量平铺 {name}。"""
    if ".." in file_path or "\\" in file_path or not file_path:
        raise HTTPException(400, "非法文件名")
    path = FileStorage().base_path / "model-images" / file_path
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "图片不存在")
    return FileResponse(str(path))


# ---- 门户 banner 配置（标题 + 轮播图，每图可带独立副标题；存 system_config JSON，门户 /servers 消费）----
def _normalize_portal_banner(raw) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HTTPException(400, "banner 配置必须是对象")
    title = raw.get("title")
    if title is not None and not isinstance(title, str):
        raise HTTPException(400, "title 必须是字符串")
    images = raw.get("images")
    if images is None:
        images = []
    if not isinstance(images, list):
        raise HTTPException(400, "images 必须是数组")
    out = []
    for e in images:
        if isinstance(e, str):                      # 存量格式：纯 URL 字符串
            if not e:
                raise HTTPException(400, "图片项 url 不能为空")
            out.append({"url": e, "subtitle": ""})
        elif isinstance(e, dict):
            url = e.get("url")
            subtitle = e.get("subtitle") or ""
            if not isinstance(url, str) or not url:
                raise HTTPException(400, "图片项 url 必须是非空字符串")
            if not isinstance(subtitle, str):
                raise HTTPException(400, "图片项 subtitle 必须是字符串")
            out.append({"url": url, "subtitle": subtitle})
        else:
            raise HTTPException(400, "images 项必须是 URL 字符串或 {url, subtitle} 对象")
    return {"title": title or "", "images": out}


@router.get("/portal-banner")
def get_portal_banner():
    """读门户 banner 配置；未配置返回空对象（前端回落内置默认标题+银河场景）。"""
    repo = SystemConfigRepository()
    try:
        raw = repo.get_value(_PORTAL_BANNER_KEY, {})
        return _normalize_portal_banner(raw if isinstance(raw, dict) else {})
    finally:
        repo.close()


@router.get("/portal-banner/images")
def list_portal_banner_images():
    """列出本站图片池全量文件（storage/model-images/ 递归，含历史子目录，mtime 倒序）。
    管理面「门户设置」用：机型主图/场景图/banner 图都可加进轮播或复制链接复用。"""
    d = FileStorage().base_path / "model-images"
    items = []
    if d.exists():
        for f in sorted(d.rglob("*"), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file():
                rel = str(f.relative_to(d)).replace("\\", "/")
                items.append({
                    "url": f"/api/server-catalog/model-image/{rel}",
                    "filename": rel,
                    "size": f.stat().st_size,
                })
    return {"images": items}


@router.put("/portal-banner")
def set_portal_banner(data: dict, admin: dict = Depends(require_admin)):
    """保存门户 banner 配置（管理面「门户设置」）；移出轮播且无引用的图片文件一并清理。"""
    cfg = _normalize_portal_banner(data)
    repo = SystemConfigRepository()
    try:
        old_imgs: list = []
        old_raw = repo.get_value(_PORTAL_BANNER_KEY, {})
        if isinstance(old_raw, dict):
            old_imgs = old_raw.get("images") or []
        repo.set(_PORTAL_BANNER_KEY, cfg, type="json",
                 description="服务器门户 banner 配置（标题/轮播图，每图可带副标题）",
                 operator=admin.get("username", "system") if isinstance(admin, dict) else "system")
    finally:
        repo.close()
    _delete_unreferenced_model_images(_banner_image_urls(old_imgs) - _banner_image_urls(cfg["images"]))
    return cfg


# ---- 性能六维打分锚点表（system_config JSON；配置页雷达消费，管理面改锚点零发版生效）----
_PERF_SCORE_KEY = "performance_score_config"


@router.get("/performance-score-config")
def get_performance_score_config():
    """读性能六维打分锚点表；未配置返回空对象（前端回落内置默认锚点）。"""
    repo = SystemConfigRepository()
    try:
        raw = repo.get_value(_PERF_SCORE_KEY, {})
        return raw if isinstance(raw, dict) else {}
    finally:
        repo.close()


# ---- 服务器可视化图纸（SVG 上传 + 标注配置，drawing_config JSONB）----
_DRAWING_VIEWS = {"top", "front", "rear"}
_DRAWING_MAX = 5 * 1024 * 1024
_DRAWING_MAX_REGIONS = 50
_DRAWING_HISTORY_MAX = 10


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
        # region_type = 料号库大类 id（动态数据，由 /api/parts/major-categories 下发，后端不做枚举校验）
        rtype = str(r.get("region_type") or "")
        if not rtype:
            raise ValueError(f"regions[{i}].region_type 必填")
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


def _now_iso() -> str:
    """UTC 时间 ISO 字符串（版本创建时间）。"""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _version_id(svg_url: Optional[str], created_at: Optional[str] = None, salt: str = "") -> str:
    """稳定的版本 id（同一 svg_url 生成结果一致，便于删除/回退定位）。"""
    seed = f"{svg_url or ''}|{created_at or ''}|{salt}"
    return "v-" + hashlib.md5(seed.encode("utf-8")).hexdigest()[:10]


def _drawing_snapshot(vd: dict) -> dict:
    """取视图配置快照（不含 prev/history 等版本结构键）。"""
    return {
        "svg_url": vd.get("svg_url"),
        "viewBox": vd.get("viewBox"),
        "regions": vd.get("regions") or [],
        "layers": vd.get("layers") or [],
    }


def _drawing_history(vd: dict) -> list:
    """归一化历史版本列表：老数据的单层 prev 自动并入（读取侧，不落库）。"""
    entries = []
    seen = set()
    legacy = vd.get("prev")
    if isinstance(legacy, dict) and legacy.get("svg_url"):
        entries.append({
            "id": _version_id(legacy["svg_url"]),
            "svg_url": legacy["svg_url"],
            "viewBox": legacy.get("viewBox"),
            "regions": legacy.get("regions") or [],
            "layers": legacy.get("layers") or [],
            "created_at": None,
        })
        seen.add(legacy["svg_url"])
    for i, h in enumerate(vd.get("history") or []):
        if not isinstance(h, dict) or not h.get("svg_url"):
            continue
        if h["svg_url"] in seen:
            continue
        seen.add(h["svg_url"])
        entries.append({
            "id": str(h.get("id") or _version_id(h["svg_url"], str(h.get("created_at") or ""), str(i)))[:40],
            "svg_url": h["svg_url"],
            "viewBox": h.get("viewBox"),
            "regions": h.get("regions") or [],
            "layers": h.get("layers") or [],
            "created_at": h.get("created_at"),
        })
    return entries[-_DRAWING_HISTORY_MAX:]


def _finalize_drawing_view(vd: dict) -> dict:
    """落库前归一化版本结构：合并遗留 prev → history，并把当前版压入历史（保留最近 N 个）。"""
    out = _drawing_snapshot(vd)
    history = _drawing_history(vd)
    if vd.get("svg_url"):
        history = history + [{
            "id": _version_id(vd["svg_url"], _now_iso()),
            "svg_url": vd["svg_url"],
            "viewBox": vd.get("viewBox"),
            "regions": vd.get("regions") or [],
            "layers": vd.get("layers") or [],
            "created_at": _now_iso(),
        }]
        # 与最新一条历史完全相同（如连续回退）时不重复入栈
        if len(history) >= 2 and history[-1]["svg_url"] == history[-2]["svg_url"]                 and history[-1]["viewBox"] == history[-2]["viewBox"]                 and history[-1]["created_at"] == history[-2]["created_at"]:
            history = history[:-1]
    out["history"] = history[-_DRAWING_HISTORY_MAX:]
    return out


def _drawing_rel_path(svg_url: Optional[str]) -> Optional[str]:
    """从 svg_url 提取 drawing-svgs 相对路径（兼容旧平铺 /drawing-svg/name 与新 /drawing-svg/{model_id}/name）。"""
    if not svg_url:
        return None
    marker = "/drawing-svg/"
    idx = svg_url.rfind(marker)
    rel = svg_url[idx + len(marker):] if idx >= 0 else svg_url.lstrip("/")
    if ".." in rel or not rel:
        return None
    return rel


def _drawing_file_exists(svg_url: Optional[str]) -> bool:
    rel = _drawing_rel_path(svg_url)
    if not rel:
        return False
    return (FileStorage().base_path / "drawing-svgs" / rel).is_file()


def _collect_referenced_drawing_files() -> set:
    """扫描全部机型配置中被引用的图纸相对路径（当前版 + 历史版 + 遗留 prev）。

    相对路径以 drawing-svgs 为根（如 16/xxx.svg 或旧平铺 xxx.svg），供 GC 比对。
    """
    repo = ServerCatalogRepository()
    refs = set()
    for row in repo.list_all_drawing_configs():
        cfg = row.get("drawing_config")
        if not isinstance(cfg, dict):
            continue
        for vdict in (cfg.get("views") or {}).values():
            if not isinstance(vdict, dict):
                continue
            for u in [vdict.get("svg_url")] + [
                h.get("svg_url") for h in (vdict.get("history") or []) if isinstance(h, dict)
            ]:
                rel = _drawing_rel_path(u)
                if rel:
                    refs.add(rel)
            legacy = vdict.get("prev")
            if isinstance(legacy, dict) and legacy.get("svg_url"):
                rel = _drawing_rel_path(legacy["svg_url"])
                if rel:
                    refs.add(rel)
    return refs


def gc_drawing_files() -> int:
    """删除 drawing-svgs 下未被任何机型配置引用的文件（递归子目录）；返回删除数量。"""
    fs = FileStorage()
    d = fs.base_path / "drawing-svgs"
    if not d.is_dir():
        return 0
    refs = _collect_referenced_drawing_files()
    removed = 0
    for f in d.rglob("*"):
        try:
            if f.is_file():
                rel = str(f.relative_to(d)).replace("\\", "/")
                if rel not in refs:
                    f.unlink()
                    removed += 1
        except Exception:
            pass
    # 清理空子目录（机型图纸全部删完后）
    for sub in sorted(d.iterdir(), reverse=True):
        try:
            if sub.is_dir() and not any(sub.iterdir()):
                sub.rmdir()
        except Exception:
            pass
    return removed


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
        info = FileStorage().save_drawing_svg(cleaned.encode("utf-8"), file.filename or "drawing.svg", model_id=model_id)
    except Exception as e:
        raise HTTPException(500, f"图纸保存失败：{e}")
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    cur = views.get(view) or {}
    # 已有图纸时把当前版压入历史（替换向导/回退/版本管理用；保留最近 N 个）
    new_view = _finalize_drawing_view(cur)
    new_view["svg_url"] = info["url"]
    new_view["viewBox"] = view_box
    new_view["regions"] = cur.get("regions") or []
    new_view["layers"] = cur.get("layers") or []
    views[view] = new_view
    repo.update_model(model_id, {"drawing_config": cfg})
    removed_files = gc_drawing_files()
    return {"url": info["url"], "viewBox": view_box,
            "regions": views[view]["regions"],
            "history": views[view].get("history") or [], "removed_files": removed_files}


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
        info = FileStorage().save_drawing_svg(cleaned.encode("utf-8"), "drawing.svg", model_id=model_id)
    except Exception as e:
        raise HTTPException(500, f"图纸保存失败：{e}")
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    cur = views.get(view) or {}
    # 编辑保存同样留版本：旧文件进入历史，避免编辑后无法恢复
    new_view = _finalize_drawing_view(cur)
    new_view["svg_url"] = info["url"]
    new_view["viewBox"] = view_box
    views[view] = new_view
    repo.update_model(model_id, {"drawing_config": cfg})
    gc_drawing_files()
    return {"ok": True, "url": info["url"], "viewBox": view_box}


@router.post("/models/{model_id}/drawing/rollback")
def rollback_model_drawing(model_id: int, view: str = Query("top"),
                           version_id: Optional[str] = Query(None)):
    """回退到历史版本：默认回退到最近一版；可指定 version_id。当前版会压入历史。"""
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    cur = views.get(view) or {}
    history = _drawing_history(cur)
    if not history:
        raise HTTPException(400, "没有可回退的历史版本")
    if version_id:
        idx = next((i for i, h in enumerate(history) if h.get("id") == version_id), None)
        if idx is None:
            raise HTTPException(404, "版本不存在")
        target = history[idx]
        remaining = history[:idx] + history[idx + 1:]
    else:
        target = history[-1]
        remaining = history[:-1]
    if not _drawing_file_exists(target.get("svg_url")):
        raise HTTPException(400, "目标版本图纸文件已不存在，无法回退（可在版本历史中删除该版本）")
    cur_snap = _drawing_snapshot(cur)
    if cur_snap.get("svg_url"):
        remaining.append({**cur_snap, "id": _version_id(cur_snap["svg_url"], _now_iso()), "created_at": _now_iso()})
    views[view] = {**target, "history": remaining[-_DRAWING_HISTORY_MAX:]}
    repo.update_model(model_id, {"drawing_config": cfg})
    gc_drawing_files()
    return {"ok": True, "view": views[view]}


@router.get("/models/{model_id}/drawing/versions")
def list_model_drawing_versions(model_id: int, view: str = Query("top")):
    """版本列表：当前版 + 历史版（从新到旧），标注文件是否存在。"""
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    cfg = repo.get_drawing_config(model_id) or {}
    cur = (cfg.get("views") or {}).get(view) or {}
    current = {**_drawing_snapshot(cur), "id": "current", "created_at": None,
               "is_current": True, "file_exists": _drawing_file_exists(cur.get("svg_url"))}
    history = []
    for h in reversed(_drawing_history(cur)):
        history.append({
            "id": h["id"], "svg_url": h["svg_url"], "viewBox": h.get("viewBox"),
            "regions": h.get("regions") or [], "layers": h.get("layers") or [],
            "created_at": h.get("created_at"), "is_current": False,
            "file_exists": _drawing_file_exists(h.get("svg_url")),
        })
    return {"versions": [current] + history}


@router.delete("/models/{model_id}/drawing/versions/{version_id}")
def delete_model_drawing_version(model_id: int, version_id: str, view: str = Query("top")):
    """删除一个历史版本；其 SVG 文件若无任何引用则一并删除。"""
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    cur = views.get(view) or {}
    history = _drawing_history(cur)
    target = next((h for h in history if h.get("id") == version_id), None)
    if not target:
        raise HTTPException(404, "版本不存在")
    new_history = [h for h in history if h.get("id") != version_id]
    views[view] = {**_drawing_snapshot(cur), "history": new_history}
    repo.update_model(model_id, {"drawing_config": cfg})
    removed_files = gc_drawing_files()
    return {"ok": True, "removed_files": removed_files}


@router.delete("/models/{model_id}/drawing")
def delete_model_drawing(model_id: int, view: str = Query("top")):
    """删除某视图整张图纸配置（含历史版本）；对应文件一并清理。"""
    if view not in _DRAWING_VIEWS:
        raise HTTPException(400, f"不支持的视图类型 {view}")
    repo = ServerCatalogRepository()
    if not repo.get_model(model_id):
        raise HTTPException(404, "机型不存在")
    cfg = repo.get_drawing_config(model_id) or {"views": {}}
    views = cfg.setdefault("views", {})
    if view not in views or not (views.get(view) or {}).get("svg_url"):
        raise HTTPException(404, "该视图未配置图纸")
    views.pop(view, None)
    if not views:
        cfg.pop("views", None)
    repo.update_model(model_id, {"drawing_config": cfg})
    removed_files = gc_drawing_files()
    return {"ok": True, "removed_files": removed_files}


@router.get("/drawing-svg/{path:path}")
def get_drawing_svg(path: str):
    """读取机型图纸 SVG（清洗后落盘；nosniff + CSP 防脚本执行）。

    兼容两种 URL：新格式 /drawing-svg/{model_id}/{name}（按机型归档），
    旧格式 /drawing-svg/{name}（平铺目录，存量数据）。
    """
    if ".." in path or not path:
        raise HTTPException(400, "非法文件名")
    rel = path.replace("\\", "/")
    file_path = FileStorage().base_path / "drawing-svgs" / rel
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(404, "图纸不存在")
    return FileResponse(
        str(file_path), media_type="image/svg+xml",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "script-src 'none'; object-src 'none'",
        },
    )
