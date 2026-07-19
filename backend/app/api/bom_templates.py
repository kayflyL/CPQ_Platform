"""BOM 模板 API — 左栏 L6 配置单的机型族行骨架。"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from pydantic import BaseModel
from app.repository.bom_template_repo import BomTemplateRepository

router = APIRouter(prefix="/api/bom-templates", tags=["bom-templates"])


@router.get("")
def list_templates():
    return {"templates": BomTemplateRepository().list()}


@router.get("/{template_id}")
def get_template(template_id: int):
    t = BomTemplateRepository().get(template_id)
    if not t:
        raise HTTPException(404, "模板不存在")
    return t


@router.get("/for-base-config/{base_config_id}")
def get_for_base_config(base_config_id: int):
    """取某基准配置关联的 BOM 模板（未关联返回 null）。"""
    return BomTemplateRepository().get_for_base_config(base_config_id)


@router.get("/{template_id}/usage")
def get_usage(template_id: int):
    """统计有多少 base_config 在用此模板"""
    return {"count": BomTemplateRepository().count_base_configs(template_id)}


class TemplateWriteRequest(BaseModel):
    name: str
    rows: list
    sort_order: Optional[int] = 0


@router.post("")
def create_template(req: TemplateWriteRequest):
    tid = BomTemplateRepository().create(req.name, req.rows, req.sort_order or 0)
    return {"id": tid}


@router.put("/{template_id}")
def update_template(template_id: int, req: TemplateWriteRequest):
    repo = BomTemplateRepository()
    if not repo.get(template_id):
        raise HTTPException(404, "模板不存在")
    repo.update(template_id, name=req.name, rows=req.rows)
    return {"ok": True}


@router.delete("/{template_id}")
def delete_template(template_id: int):
    repo = BomTemplateRepository()
    if not repo.get(template_id):
        raise HTTPException(404, "模板不存在")
    n = repo.count_base_configs(template_id)
    repo.delete(template_id)
    return {"ok": True, "detached_base_configs": n}
