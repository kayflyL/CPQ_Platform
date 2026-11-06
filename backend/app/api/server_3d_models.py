"""服务器3D模型管理 API — 登记参数化3D配置台模型并关联机型(多对多)。

读:list / by-model 挂 get_optional_user(配置页登录用户可用,公开侧未放行);
写:POST/PUT/DELETE 收 page.settings.admin(与图纸配置同门)。
model_ids:绑定的机型id列表——绑定即上架(配置页中部显示该3D场景),解绑即隐藏。
"""
from fastapi import APIRouter, Depends, HTTPException
from app.api.deps import get_optional_user, require_perms
from app.repository.server_3d_model_repo import Server3dModelRepository

router = APIRouter(prefix="/api/server-3d-models", tags=["server-3d-models"])


def _clean(data: dict) -> dict:
    data = dict(data or {})
    for k in ("id", "created_at", "updated_at", "model_id", "model_ids"):
        data.pop(k, None)
    return data


def _model_ids(data: dict) -> list:
    ids = data.get("model_ids") or []
    return [int(x) for x in ids if x]


@router.get("/", dependencies=[Depends(get_optional_user)])
def list_3d_models():
    return {"models": Server3dModelRepository().list()}


@router.get("/by-model/{model_id}", dependencies=[Depends(get_optional_user)])
def get_3d_model_by_model(model_id: int):
    """配置页按机型反查绑定着的3D模型;未绑定返回 null,前端回落2D图纸。"""
    return Server3dModelRepository().get_by_model(model_id) or None


@router.post("/", dependencies=[Depends(require_perms("page.settings.admin"))])
def create_3d_model(data: dict):
    """登记新行(管理页「复制模型」分裂用);部件绑定/组装配置由前端整存整取进 layout_config。"""
    payload = _clean(data)
    if not str(payload.get("name") or "").strip():
        raise HTTPException(400, "请填写模型名称")
    repo = Server3dModelRepository()
    return {"ok": True, "model": repo.create(payload, _model_ids(data))}


@router.put("/{model_3d_id}", dependencies=[Depends(require_perms("page.settings.admin"))])
def update_3d_model(model_3d_id: int, data: dict):
    repo = Server3dModelRepository()
    if not repo.get(model_3d_id):
        raise HTTPException(404, "3D模型不存在")
    payload = _clean(data)
    if not str(payload.get("name") or "").strip():
        raise HTTPException(400, "请填写模型名称")
    repo.update(model_3d_id, payload, _model_ids(data))
    return {"ok": True, "model": repo.get(model_3d_id)}


@router.delete("/{model_3d_id}", dependencies=[Depends(require_perms("page.settings.admin"))])
def delete_3d_model(model_3d_id: int):
    Server3dModelRepository().delete(model_3d_id)
    return {"ok": True}
