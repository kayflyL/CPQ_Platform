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


# ========== L6 Price List ==========

@router.get("/l6/list")
def get_l6_list():
    """获取所有L6价格记录（用于匹配规则Demo）"""
    from app.repository.l6_repo import L6Repository
    repo = L6Repository()
    try:
        records = repo.get_all_for_matching()
        return {"records": records, "total": len(records)}
    finally:
        repo.close()


@router.post("/l6/preview-match")
def preview_l6_match(data: dict):
    """Preview L6 matching process step by step.
    data: {chassis, model, drive_bays, psu, motherboard}
    """
    from app.engine.pricing_engine import PricingEngine
    engine = PricingEngine()
    try:
        result = engine.preview_l6_match(data)
        return result
    finally:
        engine.close()


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


# ========== Motherboard Mappings ==========

@router.get("/motherboard-mappings")
def get_motherboard_mappings():
    """Get all motherboard mappings."""
    return {"mappings": rules_repo.get_motherboard_mappings()}


@router.put("/motherboard-mappings")
def bulk_update_motherboard_mappings(data: list[dict]):
    """Bulk update all motherboard mappings."""
    return rules_repo.bulk_update_motherboard_mappings(data)


@router.put("/motherboard-mappings/{mapping_id}")
def update_motherboard_mapping(mapping_id: int, data: dict):
    """Update a motherboard mapping."""
    success = rules_repo.update_motherboard_mapping(mapping_id, data)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"status": "success"}


@router.post("/motherboard-mappings")
def add_motherboard_mapping(data: dict):
    """Add a new motherboard mapping."""
    mapping_id = rules_repo.add_motherboard_mapping(data)
    return {"id": mapping_id, "status": "success"}


@router.delete("/motherboard-mappings/{mapping_id}")
def delete_motherboard_mapping(mapping_id: int):
    """Delete a motherboard mapping."""
    success = rules_repo.delete_motherboard_mapping(mapping_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"status": "success"}


# ========== Matching Rules ==========

@router.get("/matching-rules")
def get_matching_rules():
    """Get all matching rules."""
    return {"rules": rules_repo.get_matching_rules()}


@router.put("/matching-rules")
def bulk_update_matching_rules(data: list[dict]):
    """Bulk update all matching rules."""
    return rules_repo.bulk_update_matching_rules(data)


@router.get("/matching-rules/{rule_name}")
def get_matching_rule(rule_name: str):
    """Get a specific matching rule by name."""
    rule = rules_repo.get_matching_rule(rule_name)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


@router.put("/matching-rules/{rule_name}")
def update_matching_rule(rule_name: str, data: dict):
    """Update a matching rule value."""
    rule_value = data.get("rule_value")
    if rule_value is None:
        raise HTTPException(status_code=400, detail="rule_value is required")
    success = rules_repo.update_matching_rule(rule_name, rule_value)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "success"}


@router.post("/matching-rules")
def add_matching_rule(data: dict):
    """Add a new matching rule."""
    rule_id = rules_repo.add_matching_rule(data)
    return {"id": rule_id, "status": "success"}


@router.delete("/matching-rules/{rule_id}")
def delete_matching_rule(rule_id: int):
    """Delete a matching rule."""
    success = rules_repo.delete_matching_rule(rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
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
    
    # Default Motherboard Mappings
    default_mb_mappings = [
        {"cpu_feature": "KH50000", "motherboard_model": "Polaris MB", "priority": 1},
        {"cpu_feature": "KH30000", "motherboard_model": "Orion MB", "priority": 1},
        {"cpu_feature": "KH20000", "motherboard_model": "Orion MB", "priority": 2},
        {"cpu_feature": "AMD", "motherboard_model": "TTY TG658V3", "priority": 1},
        {"cpu_feature": "EPYC", "motherboard_model": "TTY TG658V3", "priority": 2},
        {"cpu_feature": "INTEL", "motherboard_model": "TTY TG658V3", "priority": 3},
        {"cpu_feature": "XEON", "motherboard_model": "TTY TG658V3", "priority": 4},
    ]
    for mapping in default_mb_mappings:
        rules_repo.add_motherboard_mapping(mapping)
    
    # Default Matching Rules
    default_rules = [
        {
            "rule_name": "l6_match_dimensions",
            "rule_value": '["chassis", "model", "drive_bays", "psu", "motherboard"]',
            "description": "L6 匹配维度优先级（JSON 数组）"
        },
        {
            "rule_name": "l6_fallback_dimensions",
            "rule_value": '["chassis", "model", "drive_bays"]',
            "description": "L6 降级匹配维度（5维匹配失败时使用）"
        },
        {
            "rule_name": "allow_motherboard_fallback",
            "rule_value": "true",
            "description": "是否允许主板降级匹配（Polaris → Orion）"
        },
        {
            "rule_name": "allow_chassis_fuzzy",
            "rule_value": "true",
            "description": "是否允许机箱模糊匹配（4U → 4.5U）"
        },
        {
            "rule_name": "chassis_fuzzy_rules",
            "rule_value": '[{"from": "2U", "to": "2.5U"}, {"from": "4U", "to": "4.5U"}, {"from": "1U", "to": "2U"}]',
            "description": "机箱模糊匹配规则（JSON数组）"
        },
    ]
    for rule in default_rules:
        rules_repo.add_matching_rule(rule)
    
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
