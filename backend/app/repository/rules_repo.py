"""
Repository for rules database operations.
"""
from sqlalchemy.orm import Session
from app.models.rules import L6RegionConfig, KPRegionConfig, KPCategoryMapping, MatchingRule, ParseRegion, ParseFieldRule
from app.models.base import Rules_SessionLocal
import json


class RulesRepository:
    """Manages configurable business rules."""
    
    def __init__(self):
        self.session_factory = Rules_SessionLocal
    
    # ========== L6 Region Config ==========
    
    def get_l6_region_config(self) -> dict | None:
        """Get L6 region config (singleton)."""
        with self.session_factory() as session:
            config = session.query(L6RegionConfig).first()
            if not config:
                return None
            return {
                "id": config.id,
                "region_start_keywords": config.region_start_keywords,
                "field_mapping": json.loads(config.field_mapping) if config.field_mapping else {},
                "region_end_keywords": config.region_end_keywords
            }
    
    def add_l6_region_config(self, data: dict) -> int:
        """Add L6 region config."""
        with self.session_factory() as session:
            fm = data.get('field_mapping', {})
            config = L6RegionConfig(
                region_start_keywords=data.get('region_start_keywords', ''),
                field_mapping=json.dumps(fm, ensure_ascii=False) if isinstance(fm, dict) else fm,
                region_end_keywords=data.get('region_end_keywords', '')
            )
            session.add(config)
            session.commit()
            return config.id
    
    def update_l6_region_config(self, data: dict) -> bool:
        """Update L6 region config (singleton - updates first record)."""
        with self.session_factory() as session:
            config = session.query(L6RegionConfig).first()
            if not config:
                return False
            if 'region_start_keywords' in data:
                config.region_start_keywords = data['region_start_keywords']
            if 'field_mapping' in data:
                fm = data['field_mapping']
                config.field_mapping = json.dumps(fm, ensure_ascii=False) if isinstance(fm, dict) else fm
            if 'region_end_keywords' in data:
                config.region_end_keywords = data['region_end_keywords']
            session.commit()
            return True
    
    def update_l6_region_config_by_id(self, config_id: int, data: dict) -> bool:
        """Update L6 region config by ID."""
        with self.session_factory() as session:
            config = session.query(L6RegionConfig).filter(L6RegionConfig.id == config_id).first()
            if not config:
                return False
            if 'region_start_keywords' in data:
                config.region_start_keywords = data['region_start_keywords']
            if 'field_mapping' in data:
                fm = data['field_mapping']
                config.field_mapping = json.dumps(fm, ensure_ascii=False) if isinstance(fm, dict) else fm
            if 'region_end_keywords' in data:
                config.region_end_keywords = data['region_end_keywords']
            session.commit()
            return True
    
    # ========== KP Region Config ==========
    
    def get_kp_region_config(self) -> dict | None:
        """Get KP region config (singleton)."""
        with self.session_factory() as session:
            config = session.query(KPRegionConfig).first()
            if not config:
                return None
            return {
                "id": config.id,
                "region_start_keywords": config.region_start_keywords,
                "field_mapping": json.loads(config.field_mapping) if config.field_mapping else {},
                "region_end_keywords": config.region_end_keywords
            }
    
    def add_kp_region_config(self, data: dict) -> int:
        """Add KP region config."""
        with self.session_factory() as session:
            fm = data.get('field_mapping', {})
            config = KPRegionConfig(
                region_start_keywords=data.get('region_start_keywords', ''),
                field_mapping=json.dumps(fm, ensure_ascii=False) if isinstance(fm, dict) else fm,
                region_end_keywords=data.get('region_end_keywords', '')
            )
            session.add(config)
            session.commit()
            return config.id
    
    def update_kp_region_config(self, data: dict) -> bool:
        """Update KP region config (singleton - updates first record)."""
        with self.session_factory() as session:
            config = session.query(KPRegionConfig).first()
            if not config:
                return False
            if 'region_start_keywords' in data:
                config.region_start_keywords = data['region_start_keywords']
            if 'field_mapping' in data:
                fm = data['field_mapping']
                config.field_mapping = json.dumps(fm, ensure_ascii=False) if isinstance(fm, dict) else fm
            if 'region_end_keywords' in data:
                config.region_end_keywords = data['region_end_keywords']
            session.commit()
            return True
    
    def update_kp_region_config_by_id(self, config_id: int, data: dict) -> bool:
        """Update KP region config by ID."""
        with self.session_factory() as session:
            config = session.query(KPRegionConfig).filter(KPRegionConfig.id == config_id).first()
            if not config:
                return False
            if 'region_start_keywords' in data:
                config.region_start_keywords = data['region_start_keywords']
            if 'field_mapping' in data:
                fm = data['field_mapping']
                config.field_mapping = json.dumps(fm, ensure_ascii=False) if isinstance(fm, dict) else fm
            if 'region_end_keywords' in data:
                config.region_end_keywords = data['region_end_keywords']
            session.commit()
            return True
    
    # ========== KP Category Mappings ==========
    
    def get_kp_category_mappings(self) -> list[dict]:
        """Get all KP category mappings."""
        with self.session_factory() as session:
            mappings = session.query(KPCategoryMapping).order_by(KPCategoryMapping.priority).all()
            return [
                {
                    "id": m.id,
                    "keyword": m.keyword,
                    "category": m.category,
                    "priority": m.priority
                }
                for m in mappings
            ]
    
    def update_kp_category_mapping(self, mapping_id: int, data: dict) -> bool:
        """Update a KP category mapping."""
        with self.session_factory() as session:
            mapping = session.query(KPCategoryMapping).filter_by(id=mapping_id).first()
            if not mapping:
                return False
            for key, value in data.items():
                if hasattr(mapping, key):
                    setattr(mapping, key, value)
            session.commit()
            return True
    
    # ========== Bulk Operations ==========
    
    def add_kp_category_mapping(self, data: dict) -> int:
        """Add a new KP category mapping."""
        with self.session_factory() as session:
            mapping = KPCategoryMapping(**data)
            session.add(mapping)
            session.commit()
            return mapping.id
    
    def bulk_update_kp_category_mappings(self, mappings: list[dict]) -> dict:
        """Bulk update KP category mappings."""
        with self.session_factory() as session:
            existing = session.query(KPCategoryMapping).all()
            existing_ids = {m.id for m in existing}
            incoming_ids = {m.get('id') for m in mappings if m.get('id')}
            
            for mapping in existing:
                if mapping.id not in incoming_ids:
                    session.delete(mapping)
            
            for data in mappings:
                mapping_id = data.get('id')
                if mapping_id and mapping_id in existing_ids:
                    mapping = session.query(KPCategoryMapping).filter_by(id=mapping_id).first()
                    if mapping:
                        for key in ['keyword', 'category', 'priority']:
                            if key in data:
                                setattr(mapping, key, data[key])
                else:
                    new_mapping = KPCategoryMapping(
                        keyword=data.get('keyword', ''),
                        category=data.get('category', ''),
                        priority=data.get('priority', 1)
                    )
                    session.add(new_mapping)
            
            session.commit()
            return {"status": "success", "count": len(mappings)}
    
    def delete_kp_category_mapping(self, mapping_id: int) -> bool:
        """Delete a KP category mapping."""
        with self.session_factory() as session:
            mapping = session.query(KPCategoryMapping).filter_by(id=mapping_id).first()
            if not mapping:
                return False
            session.delete(mapping)
            session.commit()
            return True
    
    # ========== Export Category Mappings (part_name -> variable) ==========

    def get_export_category_mappings(self) -> list[dict]:
        """Get export category mappings (part_name keyword -> template variable)."""
        with self.session_factory() as session:
            rule = session.query(MatchingRule).filter_by(rule_name="export_category_mappings").first()
            if not rule:
                return []
            try:
                return json.loads(rule.rule_value)
            except:
                return []

    def update_export_category_mappings(self, mappings: list[dict]) -> bool:
        """Update export category mappings."""
        with self.session_factory() as session:
            rule = session.query(MatchingRule).filter_by(rule_name="export_category_mappings").first()
            value = json.dumps(mappings, ensure_ascii=False)
            if rule:
                rule.rule_value = value
            else:
                new_rule = MatchingRule(
                    rule_name="export_category_mappings",
                    rule_value=value,
                    description="Part name keyword to template variable mappings for export"
                )
                session.add(new_rule)
            session.commit()
            return True

    # ========== Number Precision ==========
    
    def get_number_precision(self) -> int:
        """Get number precision (default 2)."""
        with self.session_factory() as session:
            rule = session.query(MatchingRule).filter_by(rule_name="number_precision").first()
            if not rule:
                return 2
            try:
                return int(rule.rule_value)
            except (ValueError, TypeError):
                return 2
    
    def set_number_precision(self, precision: int) -> bool:
        """Set number precision (0, 2, or 4)."""
        if precision not in (0, 2, 4):
            return False
        with self.session_factory() as session:
            rule = session.query(MatchingRule).filter_by(rule_name="number_precision").first()
            if rule:
                rule.rule_value = str(precision)
            else:
                new_rule = MatchingRule(
                    rule_name="number_precision",
                    rule_value=str(precision),
                    description="数字精度（小数位数）：0/2/4"
                )
                session.add(new_rule)
            session.commit()
            return True

    # ========== Type Keywords ==========
    
    def get_type_keywords(self) -> dict:
        """Get type keywords mapping from matching rules."""
        with self.session_factory() as session:
            rule = session.query(MatchingRule).filter_by(rule_name="type_keywords").first()
            if not rule:
                return {}
            try:
                return json.loads(rule.rule_value)
            except:
                return {}

    # ========== Export Categories ==========
    
    def get_export_categories(self) -> list:
        """Get custom export categories from matching rules."""
        default_categories = ["cpu", "gpu", "memory", "disk", "psu", "motherboard"]
        try:
            with self.session_factory() as session:
                rule = session.query(MatchingRule).filter_by(rule_name="export_custom_categories").first()
                if not rule:
                    return default_categories
                try:
                    categories = json.loads(rule.rule_value)
                    if not categories:
                        return default_categories
                    return categories
                except:
                    return default_categories
        except Exception:
            return default_categories
    
    def update_export_categories(self, categories: list) -> bool:
        """Update custom export categories in matching rules."""
        with self.session_factory() as session:
            rule = session.query(MatchingRule).filter_by(rule_name="export_custom_categories").first()
            if rule:
                rule.rule_value = json.dumps(categories)
            else:
                new_rule = MatchingRule(
                    rule_name="export_custom_categories",
                    rule_value=json.dumps(categories),
                    description="Custom export categories"
                )
                session.add(new_rule)
            session.commit()
            return True

    # ========== Parse Regions ==========

    def get_parse_regions(self) -> list[dict]:
        """Get all parse regions ordered by sort_order."""
        with self.session_factory() as session:
            regions = session.query(ParseRegion).order_by(ParseRegion.sort_order).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "start_keywords": r.start_keywords or "",
                    "end_keywords": r.end_keywords or "",
                    "skip_header_rows": r.skip_header_rows,
                    "sort_order": r.sort_order
                }
                for r in regions
            ]

    def save_parse_regions(self, regions: list[dict]) -> dict:
        """Bulk save parse regions (replace all)."""
        with self.session_factory() as session:
            session.query(ParseRegion).delete()
            for i, data in enumerate(regions):
                region = ParseRegion(
                    name=data.get("name", ""),
                    start_keywords=data.get("start_keywords", ""),
                    end_keywords=data.get("end_keywords", ""),
                    skip_header_rows=data.get("skip_header_rows", 0),
                    sort_order=data.get("sort_order", i)
                )
                session.add(region)
            session.commit()
            return {"status": "success", "count": len(regions)}

    def add_parse_region(self, data: dict) -> int:
        """Add a single parse region."""
        with self.session_factory() as session:
            region = ParseRegion(
                name=data.get("name", ""),
                start_keywords=data.get("start_keywords", ""),
                end_keywords=data.get("end_keywords", ""),
                skip_header_rows=data.get("skip_header_rows", 0),
                sort_order=data.get("sort_order", 0)
            )
            session.add(region)
            session.commit()
            return region.id

    def update_parse_region(self, region_id: int, data: dict) -> bool:
        """Update a parse region by ID."""
        with self.session_factory() as session:
            region = session.query(ParseRegion).filter_by(id=region_id).first()
            if not region:
                return False
            for key in ["name", "start_keywords", "end_keywords", "skip_header_rows", "sort_order"]:
                if key in data:
                    setattr(region, key, data[key])
            session.commit()
            return True

    def delete_parse_region(self, region_id: int) -> bool:
        """Delete a parse region by ID."""
        with self.session_factory() as session:
            region = session.query(ParseRegion).filter_by(id=region_id).first()
            if not region:
                return False
            session.delete(region)
            session.commit()
            return True

    # ========== Parse Field Rules ==========

    def get_parse_field_rules(self) -> list[dict]:
        """Get all parse field rules ordered by sort_order."""
        with self.session_factory() as session:
            rules = session.query(ParseFieldRule).order_by(ParseFieldRule.sort_order).all()
            return [
                {
                    "id": r.id,
                    "field_key": r.field_key,
                    "region": r.region,
                    "source_type": r.source_type,
                    "source_config": json.loads(r.source_config) if r.source_config else {},
                    "fallback_config": json.loads(r.fallback_config) if r.fallback_config else None,
                    "enabled": bool(r.enabled),
                    "sort_order": r.sort_order
                }
                for r in rules
            ]

    def save_parse_field_rules(self, rules: list[dict]) -> dict:
        """Bulk save parse field rules (replace all)."""
        with self.session_factory() as session:
            session.query(ParseFieldRule).delete()
            for i, data in enumerate(rules):
                sc = data.get("source_config", {})
                fc = data.get("fallback_config")
                rule = ParseFieldRule(
                    field_key=data.get("field_key", ""),
                    region=data.get("region", ""),
                    source_type=data.get("source_type", "column"),
                    source_config=json.dumps(sc, ensure_ascii=False) if isinstance(sc, dict) else sc,
                    fallback_config=json.dumps(fc, ensure_ascii=False) if isinstance(fc, dict) and fc else (fc if fc else None),
                    enabled=1 if data.get("enabled", True) else 0,
                    sort_order=data.get("sort_order", i)
                )
                session.add(rule)
            session.commit()
            return {"status": "success", "count": len(rules)}

    def add_parse_field_rule(self, data: dict) -> int:
        """Add a single parse field rule."""
        with self.session_factory() as session:
            sc = data.get("source_config", {})
            fc = data.get("fallback_config")
            rule = ParseFieldRule(
                field_key=data.get("field_key", ""),
                region=data.get("region", ""),
                source_type=data.get("source_type", "column"),
                source_config=json.dumps(sc, ensure_ascii=False) if isinstance(sc, dict) else sc,
                fallback_config=json.dumps(fc, ensure_ascii=False) if isinstance(fc, dict) and fc else (fc if fc else None),
                enabled=1 if data.get("enabled", True) else 0,
                sort_order=data.get("sort_order", 0)
            )
            session.add(rule)
            session.commit()
            return rule.id

    def update_parse_field_rule(self, rule_id: int, data: dict) -> bool:
        """Update a parse field rule by ID."""
        with self.session_factory() as session:
            rule = session.query(ParseFieldRule).filter_by(id=rule_id).first()
            if not rule:
                return False
            for key in ["field_key", "region", "source_type", "enabled", "sort_order"]:
                if key in data:
                    if key == "enabled":
                        setattr(rule, key, 1 if data[key] else 0)
                    else:
                        setattr(rule, key, data[key])
            if "source_config" in data:
                sc = data["source_config"]
                rule.source_config = json.dumps(sc, ensure_ascii=False) if isinstance(sc, dict) else sc
            if "fallback_config" in data:
                fc = data["fallback_config"]
                rule.fallback_config = json.dumps(fc, ensure_ascii=False) if isinstance(fc, dict) and fc else (fc if fc else None)
            session.commit()
            return True

    def delete_parse_field_rule(self, rule_id: int) -> bool:
        """Delete a parse field rule by ID."""
        with self.session_factory() as session:
            rule = session.query(ParseFieldRule).filter_by(id=rule_id).first()
            if not rule:
                return False
            session.delete(rule)
            session.commit()
            return True
