"""
Repository for rules database operations.
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.models.rules import KPCategoryMapping, MatchingRule, ParseRegion, ParseFieldRule
from app.models.base import Rules_SessionLocal
import json


class RulesRepository:
    """Manages configurable business rules."""
    
    def __init__(self):
        self.session_factory = Rules_SessionLocal
    
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

    def _region_defaults(self, data: dict) -> dict:
        """Normalize a region payload, deriving stable key and region type."""
        name = (data.get("name") or "").strip()
        key = (data.get("region_key") or "").strip() or name.lower()
        region_type = (data.get("region_type") or "").strip() or ("static" if name.lower() == "header" else "dynamic")
        end_keywords = (data.get("end_keywords") or "").strip()
        return {
            "name": name,
            "region_key": key,
            "region_type": region_type,
            "start_keywords": (data.get("start_keywords") or "").strip(),
            "end_keywords": end_keywords,
            "skip_header_rows": data.get("skip_header_rows", 0) or 0,
            "sort_order": data.get("sort_order", 0) if data.get("sort_order") is not None else 0,
            "enabled": 1 if data.get("enabled", 1) else 0,
            "start_mode": (data.get("start_mode") or "").strip() or "keyword",
            "end_mode": (data.get("end_mode") or "").strip() or ("keyword" if end_keywords else "eof"),
            "start_config": data.get("start_config"),
            "end_config": data.get("end_config"),
        }

    def get_parse_regions(self) -> list[dict]:
        """Get all parse regions ordered by sort_order."""
        with self.session_factory() as session:
            regions = session.query(ParseRegion).order_by(ParseRegion.sort_order).all()
            return [
                {
                    "id": r.id,
                    "name": r.name,
                    "region_key": r.region_key or (r.name or "").lower(),
                    "region_type": r.region_type or ("static" if (r.name or "").lower() == "header" else "dynamic"),
                    "start_keywords": r.start_keywords or "",
                    "end_keywords": r.end_keywords or "",
                    "skip_header_rows": r.skip_header_rows,
                    "sort_order": r.sort_order,
                    "enabled": bool(r.enabled),
                    "start_mode": r.start_mode or "keyword",
                    "end_mode": r.end_mode or "eof",
                    "start_config": json.loads(r.start_config) if r.start_config else None,
                    "end_config": json.loads(r.end_config) if r.end_config else None,
                }
                for r in regions
            ]

    def save_parse_regions(self, regions: list[dict]) -> dict:
        """Upsert parse regions by id/region_key; unlisted regions are preserved."""
        created = 0
        updated = 0
        with self.session_factory() as session:
            for i, data in enumerate(regions):
                values = self._region_defaults(data)
                if "sort_order" in data:
                    values["sort_order"] = data.get("sort_order", i)
                else:
                    values["sort_order"] = i
                region = None
                region_id = data.get("id")
                if region_id:
                    region = session.query(ParseRegion).filter_by(id=region_id).first()
                if region is None and values["region_key"]:
                    region = session.query(ParseRegion).filter_by(region_key=values["region_key"]).first()
                if region is None:
                    region = ParseRegion(**values)
                    session.add(region)
                    created += 1
                else:
                    for key, value in values.items():
                        setattr(region, key, value)
                    updated += 1
            session.commit()
            return {"status": "success", "count": len(regions), "created": created, "updated": updated}

    def add_parse_region(self, data: dict) -> int:
        """Add a single parse region."""
        with self.session_factory() as session:
            values = self._region_defaults(data)
            region = ParseRegion(**values)
            session.add(region)
            session.commit()
            return region.id

    def update_parse_region(self, region_id: int, data: dict) -> bool:
        """Update a parse region by ID."""
        with self.session_factory() as session:
            region = session.query(ParseRegion).filter_by(id=region_id).first()
            if not region:
                return False
            if "name" in data and not data.get("region_key"):
                region.region_key = (data.get("name") or "").strip().lower()
            for key in ["name", "region_key", "region_type", "start_keywords", "end_keywords",
                        "skip_header_rows", "sort_order", "enabled", "start_mode", "end_mode",
                        "start_config", "end_config"]:
                if key in data:
                    if key == "enabled":
                        setattr(region, key, 1 if data[key] else 0)
                    else:
                        setattr(region, key, data[key])
            session.commit()
            return True

    def delete_parse_region(self, region_id: int) -> bool:
        """Delete a parse region by ID, detaching its field rules first."""
        with self.session_factory() as session:
            region = session.query(ParseRegion).filter_by(id=region_id).first()
            if not region:
                return False
            session.query(ParseFieldRule).filter_by(region_id=region_id).update({"region_id": None})
            session.delete(region)
            session.commit()
            return True



    # ========== Parse Field Rules ==========

    def _resolve_region(self, session, data: dict):
        """Resolve a region reference by region_id first, then legacy name/key."""
        region_id = data.get("region_id")
        if region_id:
            return session.query(ParseRegion).filter_by(id=region_id).first()
        ref = (data.get("region") or "").strip()
        if not ref:
            return None
        lowered = ref.lower()
        return session.query(ParseRegion).filter(
            or_(func.lower(ParseRegion.region_key) == lowered,
                func.lower(ParseRegion.name) == lowered)
        ).first()

    @staticmethod
    def _field_values(data: dict) -> dict:
        sc = data.get("source_config", {})
        fc = data.get("fallback_config")
        return {
            "field_key": data.get("field_key", ""),
            "source_type": data.get("source_type", "column"),
            "source_config": json.dumps(sc, ensure_ascii=False) if isinstance(sc, dict) else sc,
            "fallback_config": json.dumps(fc, ensure_ascii=False) if isinstance(fc, dict) and fc else (fc if fc else None),
            "enabled": 1 if data.get("enabled", True) else 0,
            "sort_order": data.get("sort_order", 0),
        }

    def get_parse_field_rules(self) -> list[dict]:
        """Get all parse field rules ordered by sort_order."""
        with self.session_factory() as session:
            rules = session.query(ParseFieldRule).order_by(ParseFieldRule.sort_order).all()
            return [
                {
                    "id": r.id,
                    "field_key": r.field_key,
                    "region": r.region,
                    "region_id": r.region_id,
                    "source_type": r.source_type,
                    "source_config": json.loads(r.source_config) if r.source_config else {},
                    "fallback_config": json.loads(r.fallback_config) if r.fallback_config else None,
                    "enabled": bool(r.enabled),
                    "sort_order": r.sort_order
                }
                for r in rules
            ]

    def save_parse_field_rules(self, rules: list[dict]) -> dict:
        """Upsert parse field rules by id; resolve region_id from id or legacy name/key."""
        created = 0
        updated = 0
        with self.session_factory() as session:
            for i, data in enumerate(rules):
                values = self._field_values(data)
                values["sort_order"] = data.get("sort_order", i)
                region = self._resolve_region(session, data)
                rule = None
                rule_id = data.get("id")
                if rule_id:
                    rule = session.query(ParseFieldRule).filter_by(id=rule_id).first()
                if rule is None:
                    rule = ParseFieldRule(**values)
                    session.add(rule)
                    created += 1
                else:
                    for key, value in values.items():
                        setattr(rule, key, value)
                    updated += 1
                rule.region_id = region.id if region else data.get("region_id")
                rule.region = (data.get("region") or "").strip() or (region.name if region else "")
            session.commit()
            return {"status": "success", "count": len(rules), "created": created, "updated": updated}

    def add_parse_field_rule(self, data: dict) -> int:
        """Add a single parse field rule."""
        with self.session_factory() as session:
            values = self._field_values(data)
            region = self._resolve_region(session, data)
            rule = ParseFieldRule(**values)
            rule.region_id = region.id if region else data.get("region_id")
            rule.region = (data.get("region") or "").strip() or (region.name if region else "")
            session.add(rule)
            session.commit()
            return rule.id

    def update_parse_field_rule(self, rule_id: int, data: dict) -> bool:
        """Update a parse field rule by ID."""
        with self.session_factory() as session:
            rule = session.query(ParseFieldRule).filter_by(id=rule_id).first()
            if not rule:
                return False
            region = self._resolve_region(session, data) if ("region" in data or "region_id" in data) else None
            for key in ["field_key", "region", "source_type", "enabled", "sort_order"]:
                if key in data:
                    if key == "enabled":
                        setattr(rule, key, 1 if data[key] else 0)
                    else:
                        setattr(rule, key, data[key])
            if region is not None:
                rule.region_id = region.id
                rule.region = data.get("region") or region.name
            elif "region_id" in data:
                rule.region_id = data["region_id"]
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
