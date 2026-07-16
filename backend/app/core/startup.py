"""
Startup event to initialize rules database tables and default rules.
"""
from app.models.base import rules_engine, l6_history_engine, Base
from app.models.rules import L6RegionConfig, KPRegionConfig, KPCategoryMapping, MatchingRule
from app.models.l6 import L6PriceHistory
from app.repository.rules_repo import RulesRepository
from app.repository.system_config_repo import SystemConfigRepository
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
    
    print("✅ Rules database initialized")

    # Initialize system_config defaults
    config_repo = SystemConfigRepository()
    try:
        config_repo.init_defaults()
        print("✅ System config initialized")
    finally:
        config_repo.close()

    # Clean up old temporary files on startup
    try:
        from app.utils.file_storage import FileStorage
        fs = FileStorage()
        removed = fs.cleanup_temp(max_age_hours=24)
        if removed:
            print(f"🧹 Cleaned up {removed} old temp file(s)")
    except Exception:
        pass
