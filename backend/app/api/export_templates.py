"""Export template API — CRUD for Excel export templates"""
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.repository.export_template_repo import ExportTemplateRepository
from app.repository.business_field_repo import BusinessFieldRepository

router = APIRouter(prefix="/api/export-templates", tags=["export-templates"])


class TemplateCreateRequest(BaseModel):
    display_name: str
    template_json: Optional[dict] = {}


class TemplateUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    template_json: Optional[dict] = None


@router.get("/fields")
def get_field_definitions():
    """Get all enabled business fields for template binding (from database)"""
    repo = BusinessFieldRepository()
    try:
        return repo.list_enabled()
    finally:
        repo.close()


@router.get("/fields/all")
def get_all_field_definitions():
    """Get all business fields including disabled ones (for management)"""
    repo = BusinessFieldRepository()
    try:
        return repo.list_all()
    finally:
        repo.close()


@router.get("")
def list_templates():
    repo = ExportTemplateRepository()
    try:
        return repo.list()
    finally:
        repo.close()


@router.get("/{template_id}")
def get_template(template_id: int):
    repo = ExportTemplateRepository()
    try:
        result = repo.get_by_id(template_id)
        if not result:
            raise HTTPException(status_code=404, detail="Template not found")
        return result
    finally:
        repo.close()


@router.post("")
def create_template(req: TemplateCreateRequest):
    import random
    import string
    from sqlalchemy.exc import IntegrityError
    repo = ExportTemplateRepository()
    try:
        # 自动生成唯一 name：时间戳 + 4位随机数，碰撞时重试
        for _ in range(5):
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
            name = f"{timestamp}_{random_suffix}"
            try:
                return repo.create(name, req.display_name, req.template_json or {})
            except IntegrityError:
                repo.db.rollback()
                continue
        raise HTTPException(status_code=500, detail="无法生成唯一模板标识，请重试")
    finally:
        repo.close()


@router.put("/{template_id}")
def update_template(template_id: int, req: TemplateUpdateRequest):
    repo = ExportTemplateRepository()
    try:
        data = {}
        if req.display_name is not None:
            data["display_name"] = req.display_name
        if req.template_json is not None:
            data["template_json"] = req.template_json
        result = repo.update(template_id, data)
        if not result:
            raise HTTPException(status_code=404, detail="Template not found")
        return result
    finally:
        repo.close()


@router.delete("/{template_id}")
def delete_template(template_id: int):
    repo = ExportTemplateRepository()
    try:
        if not repo.delete(template_id):
            raise HTTPException(status_code=404, detail="Template not found")
        return {"success": True}
    finally:
        repo.close()


@router.post("/{template_id}/set-default")
def set_default(template_id: int):
    repo = ExportTemplateRepository()
    try:
        if not repo.set_default(template_id):
            raise HTTPException(status_code=404, detail="Template not found")
        return {"success": True}
    finally:
        repo.close()
