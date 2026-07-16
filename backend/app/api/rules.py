"""
Rules API endpoints.
"""
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
import pandas as pd
import io
from app.repository.rules_repo import RulesRepository

router = APIRouter(prefix="/api/rules", tags=["rules"])

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


# ========== L6 Region Config ==========

@router.get("/l6-region-config")
def get_l6_region_config():
    """Get L6 region config."""
    config = rules_repo.get_l6_region_config()
    return {"config": config}


@router.post("/l6-region-config")
def create_l6_region_config(data: dict):
    """Create L6 region config."""
    config_id = rules_repo.add_l6_region_config(data)
    return {"id": config_id, "status": "success"}


@router.put("/l6-region-config/{config_id}")
def update_l6_region_config(config_id: int, data: dict):
    """Update L6 region config by ID."""
    success = rules_repo.update_l6_region_config_by_id(config_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Config not found")
    return {"status": "success"}


# ========== KP Region Config ==========

@router.get("/kp-region-config")
def get_kp_region_config():
    """Get KP region config."""
    config = rules_repo.get_kp_region_config()
    return {"config": config}


@router.post("/kp-region-config")
def create_kp_region_config(data: dict):
    """Create KP region config."""
    config_id = rules_repo.add_kp_region_config(data)
    return {"id": config_id, "status": "success"}


@router.put("/kp-region-config/{config_id}")
def update_kp_region_config(config_id: int, data: dict):
    """Update KP region config by ID."""
    success = rules_repo.update_kp_region_config_by_id(config_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Config not found")
    return {"status": "success"}


@router.post("/parse-preview")
async def parse_preview(
    file: UploadFile = File(...),
    template_config: str = Form("{}")
):
    """Parse uploaded Excel for heatmap preview. Returns grid + cell marks + meta."""
    from app.engine.pricing_engine import PricingEngine
    from app.repository.kp_repo import KPRepository
    from app.repository.l6_repo import L6Repository
    from app.repository.opportunity_repo import OpportunityRepository
    import json
    
    # Parse template_config
    try:
        config = json.loads(template_config) if template_config else {}
    except json.JSONDecodeError:
        config = {}
    
    # Read Excel file
    contents = await file.read()
    try:
        xl = pd.ExcelFile(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail="无法解析Excel文件")
    
    # Find first valid sheet (skip 原始需求/Reference)
    target_sheet = None
    for sheet_name in xl.sheet_names:
        if '原始需求' not in sheet_name and 'Reference' not in sheet_name:
            target_sheet = sheet_name
            break
    
    if not target_sheet:
        raise HTTPException(status_code=400, detail="未找到有效的报价Sheet")
    
    df = xl.parse(target_sheet, header=None)
    if df.empty:
        raise HTTPException(status_code=400, detail="Sheet为空")
    
    kp_repo = KPRepository()
    l6_repo = L6Repository()
    project_repo = OpportunityRepository()
    engine = PricingEngine(kp_repo, l6_repo, project_repo, rules_repo)
    try:
        kp_mappings = config.get('kp_mappings', [])
        result = engine.preview_parse(df, max_row=None, max_col=None, kp_mappings=kp_mappings)
        result['sheet_name'] = target_sheet
        return result
    finally:
        kp_repo.close()
        l6_repo.close()
        project_repo.close()


# ========== KP Category Mappings ==========

@router.get("/kp-category-mappings")
def get_kp_category_mappings():
    """Get all KP category mappings."""
    return {"mappings": rules_repo.get_kp_category_mappings()}


@router.put("/kp-category-mappings")
def bulk_update_kp_category_mappings(data: list[dict]):
    """Bulk update all KP category mappings."""
    return rules_repo.bulk_update_kp_category_mappings(data)


@router.put("/kp-category-mappings/{mapping_id}")
def update_kp_category_mapping(mapping_id: int, data: dict):
    """Update a KP category mapping."""
    success = rules_repo.update_kp_category_mapping(mapping_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"status": "success"}


@router.post("/kp-category-mappings")
def add_kp_category_mapping(data: dict):
    """Add a new KP category mapping."""
    mapping_id = rules_repo.add_kp_category_mapping(data)
    return {"id": mapping_id, "status": "success"}


@router.delete("/kp-category-mappings/{mapping_id}")
def delete_kp_category_mapping(mapping_id: int):
    """Delete a KP category mapping."""
    success = rules_repo.delete_kp_category_mapping(mapping_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"status": "success"}



# ========== Initialize Default Rules ==========

@router.post("/init-defaults")
def initialize_default_rules():
    """Initialize default rules if database is empty."""
    # Check if rules already exist
    l6_config = rules_repo.get_l6_region_config()
    if l6_config:
        return {"status": "already_initialized", "message": "Rules already exist"}
    
    # Default L6 Region Config
    default_l6_config = {
        "region_start_keywords": "L6",
        "field_mapping": '{"catalogue":"D", "description":"E", "quantity":"F"}',
        "region_end_keywords": "Keyparts,KP"
    }
    rules_repo.add_l6_region_config(default_l6_config)
    
    # Default KP Region Config
    default_kp_config = {
        "region_start_keywords": "Keyparts,KP",
        "field_mapping": '{"catalogue":"D", "model":"E", "quantity":"F", "price":"G"}',
        "region_end_keywords": "Warranty,Total"
    }
    rules_repo.add_kp_region_config(default_kp_config)
    
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


@router.put("/number-precision")
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


@router.put("/export-categories")
def update_export_categories(data: dict):
    """更新导出分类配置"""
    custom = data.get("custom", [])
    success = rules_repo.update_export_categories(custom)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to update categories")
    return {"status": "success"}


# ========== Parse Regions (Excel Parser) ==========

@router.get("/parse-regions")
def get_parse_regions():
    """获取所有解析区域配置"""
    regions = rules_repo.get_parse_regions()
    return {"regions": regions}


@router.post("/parse-regions")
def save_parse_regions(data: dict):
    """批量保存解析区域（替换所有）"""
    regions = data.get("regions", [])
    result = rules_repo.save_parse_regions(regions)
    return result


@router.put("/parse-regions/{region_id}")
def update_parse_region(region_id: int, data: dict):
    """更新单个解析区域"""
    success = rules_repo.update_parse_region(region_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Region not found")
    return {"status": "success"}


@router.delete("/parse-regions/{region_id}")
def delete_parse_region(region_id: int):
    """删除解析区域"""
    success = rules_repo.delete_parse_region(region_id)
    if not success:
        raise HTTPException(status_code=404, detail="Region not found")
    return {"status": "success"}


# ========== Parse Field Rules (Excel Parser) ==========

@router.get("/parse-field-rules")
def get_parse_field_rules():
    """获取所有字段解析规则"""
    rules = rules_repo.get_parse_field_rules()
    return {"rules": rules}


@router.post("/parse-field-rules")
def save_parse_field_rules(data: dict):
    """批量保存字段规则（替换所有）"""
    rules = data.get("rules", [])
    result = rules_repo.save_parse_field_rules(rules)
    return result


@router.put("/parse-field-rules/{rule_id}")
def update_parse_field_rule(rule_id: int, data: dict):
    """更新单个字段规则"""
    success = rules_repo.update_parse_field_rule(rule_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "success"}


@router.delete("/parse-field-rules/{rule_id}")
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
    sheet_name: str = Form(None)
):
    """使用新 ExcelParser 引擎预览解析（带溯源信息）
    
    返回白盒化解析结果：
    - static_fields: 静态字段及溯源
    - dynamic_regions: 动态区域数据及溯源
    - trace: 解析过程追踪
    - region_bounds: 区域定位结果
    """
    from app.engine.excel_parser import ExcelParser
    import pandas as pd
    import io
    
    # Read Excel file
    contents = await file.read()
    try:
        xl = pd.ExcelFile(io.BytesIO(contents))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法解析 Excel 文件: {str(e)}")
    
    # Find target sheet
    if sheet_name and sheet_name in xl.sheet_names:
        target_sheet = sheet_name
    else:
        # Find first valid sheet (skip 原始需求/Reference)
        target_sheet = None
        for sn in xl.sheet_names:
            if '原始需求' not in sn and 'Reference' not in sn:
                target_sheet = sn
                break
    
    if not target_sheet:
        raise HTTPException(status_code=400, detail="未找到有效的报价 Sheet")
    
    df = xl.parse(target_sheet, header=None)
    if df.empty:
        raise HTTPException(status_code=400, detail="Sheet 为空")
    
    # Use ExcelParser
    parser = ExcelParser(rules_repo)
    try:
        # Parse with trace
        parse_result = parser.parse(df, return_trace=True)
        
        # Also generate heatmap preview
        preview_result = parser.preview_parse(df, max_row=50, max_col=20)
        
        return {
            "sheet_name": target_sheet,
            "parse_result": parse_result,
            "preview": preview_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")
