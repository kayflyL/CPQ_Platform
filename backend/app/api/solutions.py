"""API endpoints for solutions (解决方案)。"""
import os
import re
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from app.repository.solution_repo import SolutionRepository
from app.services.solution_seed import SCENES
from app.api.deps import get_current_user, require_perms

# 逐路由鉴权（同 artifact-templates 模式）：写操作收登录 + 「解决方案」页权限；
# 正文插图读取公开——Markdown <img> 标签不带 Authorization 头。
router = APIRouter(prefix="/api/solutions", tags=["solutions"])

_REQUIRED = ("key", "scene_key", "scene", "title")

# 方案正文插图：存 backend/app/static/solution_images，uuid 重命名防覆盖（同 artifact logo 模式）。
# 读取端点公开：Markdown <img> 标签不带 Authorization 头（同 artifact logo 理由）。
_IMG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "solution_images")
_IMG_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
_IMG_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".svg": "image/svg+xml", ".webp": "image/webp"}


@router.post("/images", dependencies=[Depends(get_current_user), Depends(require_perms("page.strategies"))])
async def upload_solution_image(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _IMG_EXTS:
        raise HTTPException(status_code=400, detail="仅支持 png/jpg/jpeg/svg/webp")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="图片不能超过 5MB")
    os.makedirs(_IMG_DIR, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(_IMG_DIR, name), "wb") as f:
        f.write(content)
    return {"url": f"/api/solutions/images/{name}", "filename": name}


@router.get("/images/{filename}")
def get_solution_image(filename: str):
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$", filename or ""):
        raise HTTPException(status_code=404)
    path = os.path.join(_IMG_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404)
    mime = _IMG_MIME.get(os.path.splitext(filename)[1].lower(), "application/octet-stream")
    with open(path, "rb") as f:
        return Response(content=f.read(), media_type=mime)


@router.get("/scenes", dependencies=[Depends(get_current_user)])
def list_scenes():
    return {"scenes": SCENES}


@router.get("/", dependencies=[Depends(get_current_user)])
def list_solutions(scene_key: str = None):
    repo = SolutionRepository()
    try:
        return {"solutions": repo.list(scene_key=scene_key)}
    finally:
        repo.close()


@router.get("/{key}", dependencies=[Depends(get_current_user)])
def get_solution(key: str):
    repo = SolutionRepository()
    try:
        sol = repo.get_by_key(key)
        if not sol:
            raise HTTPException(404, f"Solution {key} not found")
        return sol
    finally:
        repo.close()


@router.post("/", dependencies=[Depends(get_current_user), Depends(require_perms("page.strategies"))])
def create_solution(data: dict):
    for k in _REQUIRED:
        if not data.get(k):
            raise HTTPException(400, f"Missing field: {k}")
    repo = SolutionRepository()
    try:
        existing = repo.get_by_key(data["key"])
        if existing:
            raise HTTPException(400, f"Solution key already exists: {data['key']}")
        return repo.create(data, operator=data.get("operator", "system"))
    finally:
        repo.close()


@router.put("/{key}", dependencies=[Depends(get_current_user), Depends(require_perms("page.strategies"))])
def update_solution(key: str, data: dict):
    repo = SolutionRepository()
    try:
        sol = repo.update(key, data, operator=data.get("operator", "system"))
        if not sol:
            raise HTTPException(404, f"Solution {key} not found")
        return sol
    finally:
        repo.close()


@router.delete("/{key}", dependencies=[Depends(get_current_user), Depends(require_perms("page.strategies"))])
def delete_solution(key: str):
    repo = SolutionRepository()
    try:
        if not repo.delete(key):
            raise HTTPException(404, f"Solution {key} not found")
        return {"success": True}
    finally:
        repo.close()