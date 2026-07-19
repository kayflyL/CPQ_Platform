"""
Univer 导出模板 API（全新，与旧 /api/export-templates 完全独立）

路由前缀：/api/univer-templates

功能：
- CRUD：创建、读取、更新、删除模板
- 上传：Excel → Univer workbook_snapshot 转换
- 预览：填充数据后返回 snapshot（不保存）
- 导出：填充数据后生成 Excel 文件
"""
from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List, Any
import io
import openpyxl
from openpyxl.utils import get_column_letter
from app.repository.univer_template_repo import UniverTemplateRepo
from app.services.template_filler import fill_snapshot
from app.services.preview_data_loader import load_preview_data
from app.services.snapshot_converter import excel_to_snapshot

router = APIRouter(prefix="/api/univer-templates", tags=["univer-templates"])

repo = UniverTemplateRepo()


# ── 请求/响应模型 ──

class PreviewRequest(BaseModel):
    bindings: Optional[List[Any]] = None

class TemplateCreate(BaseModel):
    name: str
    display_name: str
    is_default: bool = False
    workbook_snapshot: dict
    bindings: list = []
    sheet_config: dict = {}


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    is_default: Optional[bool] = None
    workbook_snapshot: Optional[dict] = None
    bindings: Optional[list] = None
    sheet_config: Optional[dict] = None


# ── CRUD ──

@router.get("")
def list_templates():
    """列表查询（不含 workbook_snapshot）"""
    return repo.list()


@router.get("/{template_id}")
def get_template(template_id: int):
    """详情查询（含完整 snapshot）"""
    template = repo.get_by_id(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.post("")
def create_template(data: TemplateCreate):
    """创建模板"""
    return repo.create(data.model_dump())


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


# ── 上传 Excel ──

@router.post("/upload")
async def upload_excel(file: UploadFile = File(...)):
    """
    上传 Excel 文件 → 转为 Univer workbook_snapshot 格式
    
    返回：
    {
        workbook_snapshot: Univer 原生格式，
        sheet_config: Sheet 角色标记（默认第一个为 cover，其他为 config）
    }
    """
    content = await file.read()
    file_stream = io.BytesIO(content)
    
    try:
        snapshot, sheet_config = excel_to_snapshot(file_stream)
        return {
            "workbook_snapshot": snapshot,
            "sheet_config": sheet_config,
            "original_filename": file.filename,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel: {str(e)}")


# ── 预览 ──

@router.post("/{template_id}/preview")
def preview_template(
    template_id: int,
    request: PreviewRequest,
    opportunity_id: str = Query(...),
    quotation_id: Optional[str] = Query(None),
):
    """
    预览：返回填充数据后的 workbook_snapshot
    
    前端拿到后直接在 Univer 中渲染（不保存到 DB）
    bindings 可选：如果提供，使用传入的 bindings；否则从数据库读取
    """
    try:
        # 1. 读取模板
        template = repo.get_by_id(template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
        
        workbook_snapshot = template["workbook_snapshot"]
        # 优先使用前端传入的 bindings，否则从数据库读取
        bindings = request.bindings if request.bindings is not None else template["bindings"]
        sheet_config = template.get("sheet_config", {})
        
        # 2. 加载数据（传入 bindings 以支持 selectedParts）
        data = load_preview_data(opportunity_id, quotation_id, bindings)
        
        # 3. 填充 snapshot
        filled_snapshot = fill_snapshot(workbook_snapshot, bindings, data, sheet_config)
        
        # 4. 返回
        return {
            "workbook_snapshot": filled_snapshot,
            "binding_count": len(bindings),
            "data_summary": {
                "static_fields": sum(1 for b in bindings if b.get("dataType") == "static"),
                "dynamic_regions": sum(1 for b in bindings if b.get("dataType") == "dynamic"),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")
