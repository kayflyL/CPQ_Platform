"""
Startup event to initialize rules database tables and default rules.
"""
from app.models.base import rules_engine, l6_history_engine, Base
from app.models.rules import L6RegionConfig, KPRegionConfig, KPCategoryMapping, MotherboardMapping, MatchingRule
from app.models.l6 import L6PriceHistory
from app.models.export_template import ExportTemplate
from app.repository.rules_repo import RulesRepository
import json


def init_rules_db():
    """Create rules database tables and initialize default rules if empty."""
    # Create all tables for rules DB
    Base.metadata.create_all(bind=rules_engine)
    # Create tables for L6 history DB
    Base.metadata.create_all(bind=l6_history_engine)
    
    # Initialize default rules if empty
    rules_repo = RulesRepository()
    
    # --- L6 Region Config ---
    l6_config = rules_repo.get_l6_region_config()
    if not l6_config:
        default_l6_config = {
            "region_start_keywords": "L6",
            "field_mapping": '{"catalogue":"D", "description":"E", "quantity":"F"}',
            "region_end_keywords": "Keyparts,KP"
        }
        rules_repo.add_l6_region_config(default_l6_config)
    
    # --- KP Region Config ---
    kp_config = rules_repo.get_kp_region_config()
    if not kp_config:
        default_kp_config = {
            "region_start_keywords": "Keyparts,KP",
            "field_mapping": '{"catalogue":"D", "model":"E", "quantity":"F", "price":"G"}',
            "region_end_keywords": "Warranty,Total"
        }
        rules_repo.add_kp_region_config(default_kp_config)
    
    # --- KP Category Mappings ---
    kp_mappings = rules_repo.get_kp_category_mappings()
    if not kp_mappings:
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
    
    # --- Motherboard Mappings ---
    mb_mappings = rules_repo.get_motherboard_mappings()
    if not mb_mappings:
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
    
    # --- Matching Rules ---
    matching_rules = rules_repo.get_matching_rules()
    if not matching_rules:
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
                "rule_name": "price_diff_threshold",
                "rule_value": "0.01",
                "description": "价格差异阈值（小于此值视为一致）"
            },
        ]
        for rule in default_rules:
            rules_repo.add_matching_rule(rule)
    
    print("✅ Rules database initialized")

    # Clean up old temporary files on startup
    try:
        from app.utils.file_storage import FileStorage
        fs = FileStorage()
        removed = fs.cleanup_temp(max_age_hours=24)
        if removed:
            print(f"🧹 Cleaned up {removed} old temp file(s)")
    except Exception:
        pass
