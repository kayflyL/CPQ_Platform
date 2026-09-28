"""
Rules API endpoints.
"""
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
import pandas as pd
import io
import json
from urllib.parse import quote
from app.api.deps import get_current_user, require_perms
from app.repository.rules_repo import RulesRepository

# 读接口（含报价弹窗运行时）登录即可；设置页结构写操作需 page.settings.excel。
router = APIRouter(
    prefix="/api/rules",
    tags=["rules"],
    dependencies=[Depends(get_current_user)],
)

rules_repo = RulesRepository()


# ========== CPU List (from KP DB) ==========

@router.get("/cpu-list")
def get_cpu_list():
    """从KP数据库获取所有去重的CPU型号"""
    from app.repository.kp_repo import KPRepository
    repo = KPRepository()
    try:
        cpus = repo.get_distinct_cpu_models()
        return {"cpus": cpus}
    finally:
        repo.close()


# ========== KP Category Mappings ==========

@router.get("/kp-category-mappings")
def get_kp_category_mappings():
    """Get all KP category mappings."""
    return {"mappings": rules_repo.get_kp_category_mappings()}


@router.put("/kp-category-mappings", dependencies=[Depends(require_perms("page.settings.excel"))])
def bulk_update_kp_category_mappings(data: list[dict]):
    """Bulk update all KP category mappings."""
    return rules_repo.bulk_update_kp_category_mappings(data)


@router.put("/kp-category-mappings/{mapping_id}", dependencies=[Depends(require_perms("page.settings.excel"))])
def update_kp_category_mapping(mapping_id: int, data: dict):
    """Update a KP category mapping."""
    success = rules_repo.update_kp_category_mapping(mapping_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"status": "success"}


@router.post("/kp-category-mappings", dependencies=[Depends(require_perms("page.settings.excel"))])
def add_kp_category_mapping(data: dict):
    """Add a new KP category mapping."""
    mapping_id = rules_repo.add_kp_category_mapping(data)
    return {"id": mapping_id, "status": "success"}


@router.delete("/kp-category-mappings/{mapping_id}", dependencies=[Depends(require_perms("page.settings.excel"))])
def delete_kp_category_mapping(mapping_id: int):
    """Delete a KP category mapping."""
    success = rules_repo.delete_kp_category_mapping(mapping_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"status": "success"}



# ========== Initialize Default Rules ==========

@router.post("/init-defaults", dependencies=[Depends(require_perms("page.settings.excel"))])
def initialize_default_rules():
    """Initialize default rules if database is empty."""
    # Check if rules already exist (kp mappings 作为已初始化标志)
    if rules_repo.get_kp_category_mappings():
        return {"status": "already_initialized", "message": "Rules already exist"}

    # Default KP Category Mappings
    default_kp_mappings = [
        {"keyword": "cpu", "category": "CPU", "priority": 1},
        {"keyword": "processor", "category": "CPU", "priority": 2},
        {"keyword": "memory", "category": "Memory", "priority": 1},
        {"keyword": "ram", "category": "Memory", "priority": 2},
        {"keyword": "hdd", "category": "HDD/SSD", "priority": 1},
        {"keyword": "ssd", "category": "HDD/SSD", "priority": 2},
        {"keyword": "raid", "category": "Raid card", "priority": 1},
        {"keyword": "network", "category": "NIC", "priority": 1},
        {"keyword": "nic", "category": "NIC", "priority": 2},
        {"keyword": "gpu", "category": "GPU", "priority": 1},
        {"keyword": "power", "category": "Power", "priority": 1},
        {"keyword": "psu", "category": "Power", "priority": 2},
        {"keyword": "fan", "category": "Fan", "priority": 1},
        {"keyword": "heatsink", "category": "Heatsink", "priority": 1},
        {"keyword": "cooler", "category": "Heatsink", "priority": 2},
        {"keyword": "cable", "category": "Cable", "priority": 1},
        {"keyword": "wire", "category": "Cable", "priority": 2},
        {"keyword": "rail", "category": "Rail", "priority": 1},
    ]
    for mapping in default_kp_mappings:
        rules_repo.add_kp_category_mapping(mapping)
    
    return {"status": "success", "message": "Default rules initialized"}


# ========== Number Precision ==========

@router.get("/number-precision")
def get_number_precision():
    """获取当前数字精度配置（小数位数）"""
    precision = rules_repo.get_number_precision()
    return {"precision": precision}


@router.put("/number-precision", dependencies=[Depends(require_perms("page.settings.excel"))])
def set_number_precision(data: dict):
    """更新数字精度配置（允许值：0, 2, 4）"""
    precision = data.get("precision")
    if precision is None or not isinstance(precision, int) or precision not in (0, 2, 4):
        raise HTTPException(status_code=400, detail="precision 必须是 0、2 或 4")
    success = rules_repo.set_number_precision(precision)
    if not success:
        raise HTTPException(status_code=500, detail="更新失败")
    return {"status": "success", "precision": precision}


# ========== Export Categories ==========

@router.get("/export-categories")
def get_export_categories():
    """获取导出分类配置"""
    categories = rules_repo.get_export_categories()
    return {"custom": categories}


@router.put("/export-categories", dependencies=[Depends(require_perms("page.settings.excel"))])
def update_export_categories(data: dict):
    """更新导出分类配置"""
    custom = data.get("custom", [])
    success = rules_repo.update_export_categories(custom)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update categories")
    return {"status": "success"}


# ========== Parse Templates ==========

@router.get("/parse-templates")
def get_parse_templates():
    """所有解析模板（含兜底），按 sort_order。"""
    return {"templates": rules_repo.get_parse_templates()}


@router.post("/parse-templates", dependencies=[Depends(require_perms("page.settings.excel"))])
def add_parse_template(data: dict):
    """新建解析模板（空壳，区域/规则走 parse-regions 带 template_id）。"""
    name = (data.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="模板名不能为空")
    if any(t["name"] == name for t in rules_repo.get_parse_templates()):
        raise HTTPException(status_code=409, detail="模板名已存在")
    template_id = rules_repo.add_parse_template(data)
    return {"status": "success", "id": template_id}


@router.put("/parse-templates/{template_id}", dependencies=[Depends(require_perms("page.settings.excel"))])
def update_parse_template(template_id: int, data: dict):
    """更新模板元信息（名称/指纹/排序/启停/备注）。"""
    try:
        success = rules_repo.update_parse_template(template_id, data)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not success:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "success"}


@router.delete("/parse-templates/{template_id}", dependencies=[Depends(require_perms("page.settings.excel"))])
def delete_parse_template(template_id: int):
    """删除模板及其区域/字段规则（兜底模板不可删）。"""
    success = rules_repo.delete_parse_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="模板不存在或为兜底模板不可删除")
    return {"status": "success"}


@router.post("/parse-templates/{template_id}/clone", dependencies=[Depends(require_perms("page.settings.excel"))])
def clone_parse_template(template_id: int, data: dict):
    """克隆模板（区域 + 字段规则深拷贝）。"""
    from app.services.parse_template_service import ParseTemplateService
    new_name = (data.get("name") or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="新模板名不能为空")
    clone_id = rules_repo.clone_parse_template(template_id, new_name)
    if clone_id is None:
        raise HTTPException(status_code=409, detail="模板名已存在或源模板不存在")
    rules_repo.update_parse_template(clone_id, {
        "note": data.get("note") or f"克隆自模板 #{template_id}",
    })
    return {"status": "success", "id": clone_id, "template": rules_repo.get_parse_template(clone_id)}


@router.get("/parse-scope-bindings")
def list_parse_scope_bindings():
    """使用位置绑定列表（登录即可读：上传弹窗显示当前所用模板）。"""
    from app.services.parse_template_service import ParseTemplateService
    return {"bindings": ParseTemplateService().list_scope_bindings()}


@router.put("/parse-scope-bindings/{scope_key}", dependencies=[Depends(require_perms("page.settings.excel"))])
def update_parse_scope_binding(scope_key: str, data: dict):
    """配置某使用位置绑定哪个解析模板。"""
    from app.services.parse_template_service import ParseTemplateService
    try:
        template_id = int(data.get("template_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="template_id 必填")
    try:
        return ParseTemplateService().set_scope_binding(scope_key, template_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/parse-templates/{template_id}/std-file/generate", dependencies=[Depends(require_perms("page.settings.excel"))])
def generate_std_file(template_id: int):
    """（重新）生成标准文件 + 自检样例 + 期望快照，并立即跑自检。"""
    from app.services.parse_template_service import ParseTemplateService
    try:
        result = ParseTemplateService(rules_repo).generate_std_file(template_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", **result, "template": rules_repo.get_parse_template(template_id)}


@router.post("/parse-templates/{template_id}/std-file/replace", dependencies=[Depends(require_perms("page.settings.excel"))])
async def replace_std_file(template_id: int, file: UploadFile = File(...)):
    """上传替换标准文件（校验后落盘）。"""
    from app.services.parse_template_service import ParseTemplateService
    contents = await file.read()
    try:
        result = ParseTemplateService(rules_repo).replace_std_file(template_id, contents)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", **result, "template": rules_repo.get_parse_template(template_id)}


@router.get("/parse-templates/{template_id}/std-file/download", dependencies=[Depends(require_perms("page.settings.excel"))])
def download_std_file(template_id: int, force: int = 0):
    """下载标准文件（自检 failed/stale 时拦截下发，force=1 强制）。"""
    from app.services.parse_template_service import ParseTemplateService
    tpl = rules_repo.get_parse_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    if not force and tpl["selfcheck_status"] in ("failed", "stale"):
        raise HTTPException(
            status_code=409,
            detail=f"自检状态为 {tpl['selfcheck_status']}，标准文件暂停下发；请先重跑自检或确认强制下载",
        )
    try:
        content, _key = ParseTemplateService(rules_repo).read_std_file(template_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    filename = f"{tpl['name']}_标准文件_v{tpl['std_version'] or 1}.xlsx"
    from fastapi.responses import Response
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/parse-templates/{template_id}/selfcheck/run", dependencies=[Depends(require_perms("page.settings.excel"))])
def run_selfcheck(template_id: int):
    """跑自检回归（样例 vs 期望快照逐值比对），结果落模板。"""
    from app.services.parse_template_service import ParseTemplateService
    try:
        detail = ParseTemplateService(rules_repo).run_selfcheck(template_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "success", "detail": detail, "template": rules_repo.get_parse_template(template_id)}


# ========== Parse Regions (Excel Parser) ==========

@router.get("/parse-regions")
def get_parse_regions(template_id: int = None):
    """获取解析区域配置（template_id 筛选模板作用域）。"""
    regions = rules_repo.get_parse_regions(template_id)
    return {"regions": regions}


@router.post("/parse-regions", dependencies=[Depends(require_perms("page.settings.excel"))])
def save_parse_regions(data: dict):
    """创建解析区域；兼容旧前端的 {regions:[...]} 批量路径。"""
    if "regions" in data and isinstance(data.get("regions"), list):
        result = rules_repo.save_parse_regions(data["regions"])
        return result
    region_id = rules_repo.add_parse_region(data)
    return {"status": "success", "id": region_id}


@router.put("/parse-regions/{region_id}", dependencies=[Depends(require_perms("page.settings.excel"))])
def update_parse_region(region_id: int, data: dict):
    """更新单个解析区域"""
    success = rules_repo.update_parse_region(region_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Region not found")
    return {"status": "success"}


@router.delete("/parse-regions/{region_id}", dependencies=[Depends(require_perms("page.settings.excel"))])
def delete_parse_region(region_id: int):
    """删除解析区域"""
    success = rules_repo.delete_parse_region(region_id)
    if not success:
        raise HTTPException(status_code=404, detail="Region not found")
    return {"status": "success"}


# ========== Parse Field Rules (Excel Parser) ==========

@router.get("/parse-field-rules")
def get_parse_field_rules(template_id: int = None):
    """获取字段解析规则（template_id 筛选模板作用域）。"""
    rules = rules_repo.get_parse_field_rules(template_id)
    return {"rules": rules}


@router.post("/parse-field-rules", dependencies=[Depends(require_perms("page.settings.excel"))])
def save_parse_field_rules(data: dict):
    """创建字段规则；兼容旧前端的 {rules:[...]} 批量路径。"""
    if "rules" in data and isinstance(data.get("rules"), list):
        result = rules_repo.save_parse_field_rules(data["rules"])
        return result
    rule_id = rules_repo.add_parse_field_rule(data)
    return {"status": "success", "id": rule_id}


@router.put("/parse-field-rules/{rule_id}", dependencies=[Depends(require_perms("page.settings.excel"))])
def update_parse_field_rule(rule_id: int, data: dict):
    """更新单个字段规则"""
    success = rules_repo.update_parse_field_rule(rule_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "success"}


@router.delete("/parse-field-rules/{rule_id}", dependencies=[Depends(require_perms("page.settings.excel"))])
def delete_parse_field_rule(rule_id: int):
    """删除字段规则"""
    success = rules_repo.delete_parse_field_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "success"}


# ========== Excel Parser Preview (White-box) ==========

@router.post("/excel-parser-preview")
async def excel_parser_preview(
    file: UploadFile = File(...),
    sheet_name: str = Form(None),
    template_id: int = Form(None),
    scope: str = Form(None),
    parse_overrides: str = Form(None),
):
    """使用新 ExcelParser 引擎预览解析（带溯源信息）

    返回白盒化解析结果：
    - match_info: 模板裁决结果（设置页预览=显式 template_id；上传弹窗=scope 绑定；
      解析不出时落通用兜底 default）
    - static_fields: 静态字段及溯源
    - dynamic_regions: 动态区域数据及溯源
    - trace: 解析过程追踪
    - preview: 区域热力图预览（含补丁生效后的区域边界）
    parse_overrides: 解析弹窗的会话补丁 JSON（skip_rows/col_binds/region_ends），
    保证「预览看到的=确认生成的」。
    """
    from app.engine.excel_parser import ExcelParser
    import pandas as pd
    import io

    # Read Excel file
    contents = await file.read()
    fname = (file.filename or "").lower()
    if fname.endswith(".xls") and not fname.endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="旧版 .xls 请先用 Excel 另存为 .xlsx 再上传")
    try:
        xl = pd.ExcelFile(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析 Excel 文件: {str(e)}")

    valid_sheet_names = [sn for sn in xl.sheet_names if '原始需求' not in sn and 'Reference' not in sn]

    # Find target sheet
    if sheet_name and sheet_name in valid_sheet_names:
        target_sheet = sheet_name
    else:
        target_sheet = valid_sheet_names[0] if valid_sheet_names else None

    if not target_sheet:
        raise HTTPException(status_code=400, detail="未找到有效的报价 Sheet")

    df = xl.parse(target_sheet, header=None)
    if df.empty:
        raise HTTPException(status_code=400, detail="Sheet 为空")

    overrides = None
    if parse_overrides:
        try:
            overrides = json.loads(parse_overrides)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=400, detail="parse_overrides 不是合法 JSON")

    # 模板裁决：显式 template_id（设置页预览）优先，其次 scope 绑定（上传弹窗），
    # 显式 id 已删除/停用时落兜底——防并发删模板后旧页签带回死 id 静默解析出空
    from app.services.parse_template_service import ParseTemplateService
    match_info = ParseTemplateService().resolve_scope_template(
        scope, template_id if template_id is not None and template_id > 0 else None)
    resolved_template_id = match_info.get("template_id")

    # Use ExcelParser
    parser = ExcelParser(rules_repo)
    try:
        # Parse with trace
        parse_result = parser.parse(
            df, return_trace=True,
            template_id=resolved_template_id, overrides=overrides)

        # Also generate heatmap preview
        preview_result = parser.preview_parse(
            df, max_row=50, max_col=20,
            template_id=resolved_template_id, overrides=overrides)

        return {
            "sheet_name": target_sheet,
            "sheet_names": valid_sheet_names,
            "match_info": match_info,
            "parse_result": parse_result,
            "preview": preview_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
