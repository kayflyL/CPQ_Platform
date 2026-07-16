"""Repository for business_fields configuration + audit/references/stats"""
import json
import re
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal, rules_engine
from ..models.business_field import BusinessField
from ..models.field_reference import FieldReference
from ..models.field_audit_log import FieldAuditLog
from ..models.field_usage_stats import FieldUsageStats


class BusinessFieldRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    # ==================== Basic CRUD ====================

    def list_all(self) -> list[dict]:
        fields = self.session.query(BusinessField).order_by(BusinessField.sort_order, BusinessField.id).all()
        return [f.to_dict() for f in fields]

    def list_enabled(self) -> list[dict]:
        fields = (
            self.session.query(BusinessField)
            .filter(BusinessField.enabled == True)
            .order_by(BusinessField.sort_order, BusinessField.id)
            .all()
        )
        return [f.to_dict() for f in fields]

    def get_by_key(self, key: str) -> dict | None:
        field = self.session.query(BusinessField).filter(BusinessField.key == key).first()
        return field.to_dict() if field else None

    def create(self, data: dict, operator: str = 'system') -> dict:
        now = datetime.now().isoformat()
        data['created_at'] = now
        data['updated_at'] = now
        data['created_by'] = operator
        data['updated_by'] = operator
        
        field = BusinessField(**data)
        self.session.add(field)
        self.session.flush()
        
        # Write audit log
        self._write_audit_log(field.key, 'create', None, operator, now)
        
        # Init usage stats
        stats = FieldUsageStats(field_key=field.key, usage_count=0)
        self.session.add(stats)
        
        self.session.commit()
        return field.to_dict()

    def update(self, key: str, data: dict, operator: str = 'system') -> dict | None:
        field = self.session.query(BusinessField).filter(BusinessField.key == key).first()
        if not field:
            return None
        
        now = datetime.now().isoformat()
        
        # Track changes for audit
        changes = {}
        for k, v in data.items():
            if hasattr(field, k) and k not in ('id', 'key', 'created_at', 'created_by'):
                old_val = getattr(field, k)
                if str(old_val) != str(v):
                    changes[k] = {"old": old_val, "new": v}
                setattr(field, k, v)
        
        field.updated_at = now
        field.updated_by = operator
        
        if changes:
            self._write_audit_log(key, 'update', changes, operator, now)
        
        self.session.commit()
        return field.to_dict()

    def delete(self, key: str, operator: str = 'system') -> bool:
        field = self.session.query(BusinessField).filter(BusinessField.key == key).first()
        if not field:
            return False
        
        now = datetime.now().isoformat()
        self._write_audit_log(key, 'delete', None, operator, now)
        
        # Cascade: delete references, audit logs, usage stats
        self.session.query(FieldReference).filter(FieldReference.field_key == key).delete()
        self.session.query(FieldAuditLog).filter(FieldAuditLog.field_key == key).delete()
        self.session.query(FieldUsageStats).filter(FieldUsageStats.field_key == key).delete()
        self.session.delete(field)
        self.session.commit()
        return True

    def batch_update_sort(self, items: list[dict]) -> None:
        """items: [{"key": "...", "sort_order": N}, ...]"""
        for item in items:
            field = self.session.query(BusinessField).filter(BusinessField.key == item["key"]).first()
            if field:
                field.sort_order = item["sort_order"]
        self.session.commit()

    # ==================== Reference Checking ====================

    def get_references(self, key: str) -> list[dict]:
        """Get all references to a field"""
        refs = self.session.query(FieldReference).filter(FieldReference.field_key == key).all()
        return [r.to_dict() for r in refs]

    def add_reference(self, field_key: str, ref_type: str, ref_id: int, ref_name: str = None) -> dict:
        """Add a reference from a template/export/rule to a field"""
        existing = (
            self.session.query(FieldReference)
            .filter(
                FieldReference.field_key == field_key,
                FieldReference.ref_type == ref_type,
                FieldReference.ref_id == ref_id
            )
            .first()
        )
        if existing:
            return existing.to_dict()
        
        ref = FieldReference(
            field_key=field_key,
            ref_type=ref_type,
            ref_id=ref_id,
            ref_name=ref_name,
            created_at=datetime.now().isoformat()
        )
        self.session.add(ref)
        self.session.commit()
        return ref.to_dict()

    def remove_reference(self, field_key: str, ref_type: str, ref_id: int) -> bool:
        """Remove a reference"""
        ref = (
            self.session.query(FieldReference)
            .filter(
                FieldReference.field_key == field_key,
                FieldReference.ref_type == ref_type,
                FieldReference.ref_id == ref_id
            )
            .first()
        )
        if not ref:
            return False
        self.session.delete(ref)
        self.session.commit()
        return True

    def check_references(self, keys: list[str]) -> dict[str, list[dict]]:
        """Check references for multiple fields. Returns {field_key: [references]}"""
        result = {}
        for key in keys:
            refs = self.get_references(key)
            if refs:
                result[key] = refs
        return result

    # ==================== Audit Logs ====================

    def get_audit_history(self, key: str, limit: int = 50) -> list[dict]:
        """Get audit history for a field"""
        logs = (
            self.session.query(FieldAuditLog)
            .filter(FieldAuditLog.field_key == key)
            .order_by(FieldAuditLog.operated_at.desc())
            .limit(limit)
            .all()
        )
        return [log.to_dict() for log in logs]

    def _write_audit_log(self, field_key: str, action: str, changes: dict | None, operator: str, timestamp: str):
        """Internal: write an audit log entry"""
        log = FieldAuditLog(
            field_key=field_key,
            action=action,
            changes=json.dumps(changes) if changes else None,
            operator=operator,
            operated_at=timestamp
        )
        self.session.add(log)

    # ==================== Usage Stats ====================

    def get_usage_stats(self, key: str) -> dict | None:
        stats = self.session.query(FieldUsageStats).filter(FieldUsageStats.field_key == key).first()
        return stats.to_dict() if stats else None

    def get_all_usage_stats(self) -> dict[str, dict]:
        """Get usage stats for all fields. Returns {field_key: stats_dict}"""
        stats_list = self.session.query(FieldUsageStats).all()
        return {s.field_key: s.to_dict() for s in stats_list}

    def record_usage(self, key: str) -> None:
        """Increment usage count and update last_used_at"""
        stats = self.session.query(FieldUsageStats).filter(FieldUsageStats.field_key == key).first()
        if stats:
            stats.usage_count += 1
            stats.last_used_at = datetime.now().isoformat()
            self.session.commit()

    def record_batch_usage(self, keys: list[str]) -> None:
        """Record usage for multiple fields at once"""
        now = datetime.now().isoformat()
        for key in keys:
            stats = self.session.query(FieldUsageStats).filter(FieldUsageStats.field_key == key).first()
            if stats:
                stats.usage_count += 1
                stats.last_used_at = now
        self.session.commit()

    # ==================== Import/Export ====================

    def export_fields(self, keys: list[str] = None) -> list[dict]:
        """Export field definitions (without id/timestamps)"""
        query = self.session.query(BusinessField)
        if keys:
            query = query.filter(BusinessField.key.in_(keys))
        fields = query.order_by(BusinessField.sort_order).all()
        
        result = []
        for f in fields:
            d = f.to_dict()
            # Remove internal fields
            for k in ('id', 'created_at', 'updated_at', 'created_by', 'updated_by'):
                d.pop(k, None)
            result.append(d)
        return result

    def import_fields(self, data: list[dict], mode: str = 'skip', operator: str = 'system') -> dict:
        """
        Import field definitions.
        mode: 'skip' = skip existing, 'overwrite' = overwrite existing
        Returns: {"created": N, "updated": N, "skipped": N, "errors": [...]}
        """
        result = {"created": 0, "updated": 0, "skipped": 0, "errors": []}
        
        for item in data:
            key = item.get('key')
            if not key:
                result["errors"].append({"item": item, "error": "Missing key"})
                continue
            
            existing = self.get_by_key(key)
            
            if existing:
                if mode == 'skip':
                    result["skipped"] += 1
                    continue
                elif mode == 'overwrite':
                    # Remove key from data to avoid updating it
                    update_data = {k: v for k, v in item.items() if k not in ('key',)}
                    self.update(key, update_data, operator)
                    result["updated"] += 1
            else:
                try:
                    self.create(item, operator)
                    result["created"] += 1
                except Exception as e:
                    result["errors"].append({"key": key, "error": str(e)})
        
        return result

    # ==================== Validation ====================

    def validate_field_value(self, key: str, value) -> dict:
        """
        Validate a value against field's validation_rules and options.
        Returns: {"valid": bool, "errors": [...]}
        """
        field = self.session.query(BusinessField).filter(BusinessField.key == key).first()
        if not field:
            return {"valid": False, "errors": [f"Field '{key}' not found"]}
        
        errors = []
        
        # Enum options check (independent of validation_rules)
        if field.display_type == 'enum' and field.options:
            try:
                options = json.loads(field.options)
                valid_values = []
                for opt in options:
                    if isinstance(opt, dict):
                        valid_values.append(opt.get('value'))
                    else:
                        valid_values.append(opt)
                if value not in valid_values:
                    errors.append(f"字段 '{field.label}' 值不在可选范围内")
            except json.JSONDecodeError:
                pass
        
        # Validation rules check
        if field.validation_rules:
            try:
                rules = json.loads(field.validation_rules)
            except json.JSONDecodeError:
                rules = {}  # Invalid rules, skip validation
            
            # Required check
            if rules.get('required') and (value is None or value == '' or value == []):
                errors.append(f"字段 '{field.label}' 为必填项")
                return {"valid": False, "errors": errors}  # No point checking further
            
            if value is None or value == '':
                return {"valid": True, "errors": errors}  # Not required and empty, OK
            
            # Pattern check
            if 'pattern' in rules:
                if not re.match(rules['pattern'], str(value)):
                    errors.append(f"字段 '{field.label}' 格式不正确")
            
            # Min/Max for numbers
            if 'min' in rules:
                try:
                    if float(value) < rules['min']:
                        errors.append(f"字段 '{field.label}' 不能小于 {rules['min']}")
                except (ValueError, TypeError):
                    errors.append(f"字段 '{field.label}' 必须是数字")
            
            if 'max' in rules:
                try:
                    if float(value) > rules['max']:
                        errors.append(f"字段 '{field.label}' 不能大于 {rules['max']}")
                except (ValueError, TypeError):
                    pass  # Already caught by min check
            
            # MinLength/MaxLength for strings
            if 'minLength' in rules:
                if len(str(value)) < rules['minLength']:
                    errors.append(f"字段 '{field.label}' 长度不能小于 {rules['minLength']}")
            
            if 'maxLength' in rules:
                if len(str(value)) > rules['maxLength']:
                    errors.append(f"字段 '{field.label}' 长度不能大于 {rules['maxLength']}")
        
        return {"valid": len(errors) == 0, "errors": errors}

    def close(self):
        self.session.close()
