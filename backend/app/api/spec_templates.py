"""
规格书模板 API

路由前缀：/api/spec-templates

功能：
- CRUD：创建、读取、更新、删除模板
- Logo 上传
- 设为默认
- 获取默认模板（供 ConfigWizard 使用）
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, List, Any
import os
import uuid
from app.repository.spec_template_repo import SpecTemplateRepo
from app.services.preview_data_loader import load_preview_data
from app.services.default_spec_template import get_default_template_config

router = APIRouter(prefix="/api/spec-templates", tags=["spec-templates"])

repo = SpecTemplateRepo()

# Logo 存储路径
LOGO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "static", "spec_logos")
os.makedirs(LOGO_DIR, exist_ok=True)


# ── 请求/响应模型 ──

class TemplateCreate(BaseModel):
    name: str
    display_name: str
    is_default: bool = False
    branding: dict = {}
    display_options: dict = {}


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    is_default: Optional[bool] = None
    branding: Optional[dict] = None
    display_options: Optional[dict] = None


# ── 预览数据 ──

@router.get("/preview-data")
def get_preview_data(opportunity_id: str, quotation_id: Optional[str] = None):
    """获取真实预览数据（供编辑器预览使用）"""
    try:
        data = load_preview_data(opportunity_id, quotation_id)
        return data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载预览数据失败: {str(e)}")


# ── CRUD ──

@router.get("")
def list_templates():
    """列表查询（不含完整配置）"""
    return repo.list()


@router.get("/default")
def get_default_template():
    """获取默认模板"""
    template = repo.get_default()
    if not template:
        raise HTTPException(status_code=404, detail="No default template found")
    return template


@router.get("/{template_id}")
def get_template(template_id: int):
    """详情查询（含完整配置）"""
    template = repo.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("")
def create_template(data: TemplateCreate):
    """创建模板"""
    # 如果未提供配置，使用默认配置
    template_data = data.model_dump()
    if not template_data.get("branding") or not template_data.get("display_options"):
        default_config = get_default_template_config()
        template_data["branding"] = template_data.get("branding") or default_config["branding"]
        template_data["display_options"] = template_data.get("display_options") or default_config["display_options"]
    return repo.create(template_data)


@router.put("/{template_id}")
def update_template(template_id: int, data: TemplateUpdate):
    """更新模板"""
    update_data = {k: v for k, v in data.model_dump().items() if v is not None}
    result = repo.update(template_id, update_data)
    if not result:
        raise HTTPException(status_code=404, detail="Template not found")
    return result


@router.delete("/{template_id}")
def delete_template(template_id: int):
    """删除模板"""
    if not repo.delete(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Deleted"}


@router.post("/{template_id}/set-default")
def set_default(template_id: int):
    """设为默认模板"""
    if not repo.set_default(template_id):
        raise HTTPException(status_code=404, detail="Template not found")
    return {"message": "Set as default"}


@router.post("/{template_id}/copy")
def copy_template(template_id: int):
    """复制模板"""
    template = repo.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # 创建副本
    copy_data = dict(template)
    copy_data.pop('id', None)
    copy_data['name'] = f"{template.get('name', 'template')}_copy"
    copy_data['display_name'] = f"{template.get('display_name', '模板')} (副本)"
    copy_data['is_default'] = False

    # 更新时间
    from datetime import datetime
    now = datetime.now().isoformat()
    copy_data['created_at'] = now
    copy_data['updated_at'] = now

    created = repo.create(copy_data)
    return created


# ── Logo 上传 ──

@router.post("/upload-logo")
async def upload_logo(file: UploadFile = File(...)):
    """上传 Logo 图片，返回 URL"""
    # 生成唯一文件名
    ext = os.path.splitext(file.filename)[1] if file.filename else ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(LOGO_DIR, filename)
    
    # 保存文件
    content = await file.read()
    with open(filepath, "wb") as f:
        f.write(content)
    
    # 返回可访问的 URL
    url = f"/static/spec_logos/{filename}"
    return {"url": url, "filename": filename}
