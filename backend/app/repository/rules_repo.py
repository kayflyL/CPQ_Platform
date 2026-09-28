"""
Repository for rules database operations.
"""
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from app.models.rules import KPCategoryMapping, MatchingRule, ParseRegion, ParseFieldRule, ParseTemplate, ParseScopeBinding
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

    # ========== Parse Templates ==========

    @staticmethod
    def _template_now() -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _template_dict(self, t) -> dict:
        return {
            "id": t.id,
            "name": t.name,
            "is_fallback": bool(t.is_fallback),
            "std_file_key": t.std_file_key or "",
            "std_source_key": t.std_source_key or "",
            "std_version": t.std_version or 0,
            "std_generated_at": t.std_generated_at or "",
            "sample_file_key": t.sample_file_key or "",
            "has_expected": bool(t.expected_snapshot),
            "selfcheck_status": t.selfcheck_status or "none",
            "selfcheck_ran_at": t.selfcheck_ran_at or "",
            "selfcheck_detail": json.loads(t.selfcheck_detail) if t.selfcheck_detail else None,
            "enabled": bool(t.enabled),
            "sort_order": t.sort_order,
            "note": t.note or "",
        }

    def get_parse_templates(self) -> list[dict]:
        """所有解析模板（含兜底），按 sort_order。"""
        with self.session_factory() as session:
            rows = session.query(ParseTemplate).order_by(ParseTemplate.sort_order, ParseTemplate.id).all()
            return [self._template_dict(t) for t in rows]

    def get_parse_template(self, template_id: int) -> dict | None:
        with self.session_factory() as session:
            t = session.query(ParseTemplate).filter_by(id=template_id).first()
            return self._template_dict(t) if t else None

    def add_parse_template(self, data: dict) -> int:
        now = self._template_now()
        with self.session_factory() as session:
            t = ParseTemplate(
                name=(data.get("name") or "").strip(),
                is_fallback=1 if data.get("is_fallback") else 0,
                enabled=1 if data.get("enabled", True) else 0,
                sort_order=data.get("sort_order", 0) or 0,
                note=data.get("note") or "",
                created_at=now,
                updated_at=now,
            )
            session.add(t)
            session.commit()
            return t.id

    _TEMPLATE_UPDATABLE = ["name", "std_file_key", "std_source_key",
                           "std_version", "std_generated_at", "sample_file_key",
                           "expected_snapshot", "selfcheck_status", "selfcheck_ran_at",
                           "selfcheck_detail", "enabled", "sort_order", "note", "is_fallback"]

    def update_parse_template(self, template_id: int, data: dict) -> bool:
        with self.session_factory() as session:
            t = session.query(ParseTemplate).filter_by(id=template_id).first()
            if not t:
                return False
            for key in self._TEMPLATE_UPDATABLE:
                if key not in data:
                    continue
                value = data[key]
                if key in ("expected_snapshot", "selfcheck_detail") and isinstance(value, dict):
                    value = json.dumps(value, ensure_ascii=False)
                if key in ("enabled", "is_fallback"):
                    value = 1 if value else 0
                setattr(t, key, value)
            t.updated_at = self._template_now()
            session.commit()
            return True

    def delete_parse_template(self, template_id: int) -> bool:
        """删除模板及其区域/字段规则（FK CASCADE；兜底模板不可删）。"""
        with self.session_factory() as session:
            t = session.query(ParseTemplate).filter_by(id=template_id).first()
            if not t or t.is_fallback:
                return False
            session.query(ParseFieldRule).filter_by(template_id=template_id).delete()
            session.query(ParseRegion).filter_by(template_id=template_id).delete()
            session.delete(t)
            session.commit()
            return True

    # ── 使用位置绑定（入口→模板；scope 注册表在 ParseTemplateService）──

    def get_parse_scope_bindings(self) -> list[dict]:
        with self.session_factory() as session:
            rows = session.query(ParseScopeBinding).all()
            return [{"scope_key": b.scope_key, "template_id": b.template_id} for b in rows]

    def get_parse_scope_binding(self, scope_key: str) -> int | None:
        with self.session_factory() as session:
            b = session.query(ParseScopeBinding).filter_by(scope_key=scope_key).first()
            return b.template_id if b else None

    def set_parse_scope_binding(self, scope_key: str, template_id: int) -> None:
        now = self._template_now()
        with self.session_factory() as session:
            b = session.query(ParseScopeBinding).filter_by(scope_key=scope_key).first()
            if b:
                b.template_id = template_id
                b.updated_at = now
            else:
                session.add(ParseScopeBinding(scope_key=scope_key, template_id=template_id, updated_at=now))
            session.commit()

    def clone_parse_template(self, template_id: int, new_name: str,
                             extra_template_fields: dict | None = None) -> int | None:
        """深克隆模板（区域 + 字段规则）；不给指纹/标准文件，从零开始配。"""
        now = self._template_now()
        with self.session_factory() as session:
            src = session.query(ParseTemplate).filter_by(id=template_id).first()
            if not src:
                return None
            if session.query(ParseTemplate).filter_by(name=new_name).first():
                return None
            clone = ParseTemplate(
                name=new_name,
                is_fallback=0,
                enabled=1,
                sort_order=999,
                note=(extra_template_fields or {}).get("note") or f"克隆自「{src.name}」",
                created_at=now,
                updated_at=now,
            )
            session.add(clone)
            session.flush()

            old_regions = session.query(ParseRegion).filter_by(template_id=template_id).order_by(ParseRegion.sort_order).all()
            region_id_map = {}
            for r in old_regions:
                nr = ParseRegion(
                    name=r.name, region_key=f"{r.region_key}_tpl{clone.id}" if r.region_key else None,
                    region_type=r.region_type, start_keywords=r.start_keywords,
                    end_keywords=r.end_keywords, skip_header_rows=r.skip_header_rows,
                    sort_order=r.sort_order, enabled=r.enabled, start_mode=r.start_mode,
                    start_config=r.start_config, template_id=clone.id,
                    exclude_keywords=r.exclude_keywords,
                )
                session.add(nr)
                session.flush()
                region_id_map[r.id] = nr.id

            for fr in session.query(ParseFieldRule).filter_by(template_id=template_id).order_by(ParseFieldRule.sort_order).all():
                session.add(ParseFieldRule(
                    field_key=fr.field_key, region=fr.region,
                    region_id=region_id_map.get(fr.region_id), source_type=fr.source_type,
                    source_config=fr.source_config, fallback_config=fr.fallback_config,
                    enabled=fr.enabled, sort_order=fr.sort_order, template_id=clone.id,
                ))
            session.commit()
            return clone.id

    def mark_template_selfcheck_stale(self, template_id: int | None) -> None:
        """规则变动后把对应模板自检状态置 stale（有期望快照才有意义）。"""
        if not template_id:
            return
        with self.session_factory() as session:
            t = session.query(ParseTemplate).filter_by(id=template_id).first()
            if t and t.expected_snapshot and t.selfcheck_status != "stale":
                t.selfcheck_status = "stale"
                t.updated_at = self._template_now()
                session.commit()

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
            "start_config": (json.dumps(data["start_config"], ensure_ascii=False)
                             if isinstance(data.get("start_config"), dict) else data.get("start_config")),
            "template_id": data.get("template_id"),
            "exclude_keywords": (data.get("exclude_keywords") or "").strip(),
        }

    def get_parse_regions(self, template_id: int = None) -> list[dict]:
        """Get parse regions ordered by sort_order; template_id 筛选模板作用域。"""
        with self.session_factory() as session:
            q = session.query(ParseRegion).order_by(ParseRegion.sort_order)
            if template_id is not None:
                q = q.filter(ParseRegion.template_id == template_id)
            regions = q.all()
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
                    "start_config": json.loads(r.start_config) if r.start_config else None,
                    "template_id": r.template_id,
                    "exclude_keywords": r.exclude_keywords or "",
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
                    # region_key 唯一性按模板作用域；不带 template_id 会跨模板误吞
                    region = session.query(ParseRegion).filter(
                        ParseRegion.region_key == values["region_key"],
                        ParseRegion.template_id == values.get("template_id"),
                    ).first()
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
                        "skip_header_rows", "sort_order", "enabled", "start_mode",
                        "start_config", "template_id", "exclude_keywords"]:
                if key in data:
                    if key == "enabled":
                        setattr(region, key, 1 if data[key] else 0)
                    elif key == "start_config" and isinstance(data[key], dict):
                        setattr(region, key, json.dumps(data[key], ensure_ascii=False))
                    else:
                        setattr(region, key, data[key])
            tpl_id = region.template_id
            session.commit()
        self.mark_template_selfcheck_stale(tpl_id)
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
            "template_id": data.get("template_id"),
        }

    def get_parse_field_rules(self, template_id: int = None) -> list[dict]:
        """Get parse field rules ordered by sort_order; template_id 筛选模板作用域。"""
        with self.session_factory() as session:
            q = session.query(ParseFieldRule).order_by(ParseFieldRule.sort_order)
            if template_id is not None:
                q = q.filter(ParseFieldRule.template_id == template_id)
            rules = q.all()
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
                    "sort_order": r.sort_order,
                    "template_id": r.template_id,
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
            if "template_id" in data:
                rule.template_id = data["template_id"]
            tpl_id = rule.template_id
            session.commit()
        self.mark_template_selfcheck_stale(tpl_id)
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
