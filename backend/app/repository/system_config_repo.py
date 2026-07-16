"""Repository for system_config table"""
import json
from datetime import datetime
from typing import Optional, Any
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.system_config import SystemConfig


class SystemConfigRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    def get(self, key: str) -> Optional[dict]:
        """Get config by key"""
        config = self.session.query(SystemConfig).filter(SystemConfig.key == key).first()
        return config.to_dict() if config else None

    def get_value(self, key: str, default: Any = None) -> Any:
        """Get config value with type conversion"""
        config = self.session.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not config:
            return default
        
        value = config.value
        config_type = config.type or 'string'
        
        if config_type == 'number':
            try:
                return float(value) if '.' in value else int(value)
            except (ValueError, TypeError):
                return default
        elif config_type == 'boolean':
            return value.lower() in ('true', '1', 'yes')
        elif config_type == 'json':
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return default
        return value

    def get_all(self) -> list[dict]:
        """Get all configs"""
        configs = self.session.query(SystemConfig).order_by(SystemConfig.key).all()
        return [c.to_dict() for c in configs]

    def set(self, key: str, value: Any, type: str = 'string', description: str = None, operator: str = 'system') -> dict:
        """Set config value (create or update)"""
        now = datetime.now().isoformat()
        
        # Convert value to string
        if isinstance(value, (dict, list)):
            str_value = json.dumps(value, ensure_ascii=False)
            type = 'json'
        elif isinstance(value, bool):
            str_value = str(value).lower()
            type = 'boolean'
        elif isinstance(value, (int, float)):
            str_value = str(value)
            type = 'number'
        else:
            str_value = str(value)
            type = type or 'string'
        
        existing = self.session.query(SystemConfig).filter(SystemConfig.key == key).first()
        if existing:
            existing.value = str_value
            existing.type = type
            if description is not None:
                existing.description = description
            existing.updated_at = now
            existing.updated_by = operator
            self.session.commit()
            return existing.to_dict()
        else:
            config = SystemConfig(
                key=key,
                value=str_value,
                type=type,
                description=description,
                updated_at=now,
                updated_by=operator
            )
            self.session.add(config)
            self.session.commit()
            return config.to_dict()

    def delete(self, key: str) -> bool:
        """Delete config by key"""
        config = self.session.query(SystemConfig).filter(SystemConfig.key == key).first()
        if not config:
            return False
        self.session.delete(config)
        self.session.commit()
        return True

    def init_defaults(self):
        """Initialize default configs if not exist"""
        defaults = [
            {"key": "tax_rate", "value": "0.13", "type": "number", "description": "税率"},
            {"key": "usd_to_rmb", "value": "7.0", "type": "number", "description": "美元兑人民币汇率"},
            {"key": "profit_margin", "value": "0.1", "type": "number", "description": "默认利润率"},
            {"key": "warranty_fee_rate", "value": "0.02", "type": "number", "description": "质保费率"},
            {"key": "warranty_desc_l6", "value": "质保3年，非人为及不可抗力引起的故障，软件FW问题支持远程Debug，硬件损坏支持免费寄修，其他需上门维护参考上门服务政策及收费标准。", "type": "string", "description": "L6 默认质保条款"},
            {"key": "warranty_desc_kp", "value": "质保1年，非人为及不可抗力引起的故障，支持远程Debug，硬件损坏支持免费寄修，其他需上门维护参考上门服务政策及收费标准。", "type": "string", "description": "KP 默认质保条款"},
        ]
        
        for d in defaults:
            existing = self.session.query(SystemConfig).filter(SystemConfig.key == d["key"]).first()
            if not existing:
                config = SystemConfig(
                    key=d["key"],
                    value=d["value"],
                    type=d["type"],
                    description=d["description"],
                    updated_at=datetime.now().isoformat(),
                    updated_by="system"
                )
                self.session.add(config)
        
        self.session.commit()

    def close(self):
        self.session.close()
