"""Repository for dynamic_source_fields"""
from sqlalchemy.orm import Session
from ..models.base import Rules_SessionLocal
from ..models.dynamic_source_field import DynamicSourceField


class DynamicSourceFieldRepository:
    def __init__(self):
        self.session: Session = Rules_SessionLocal()

    def list_all(self) -> list[dict]:
        """获取所有动态数据源子字段"""
        fields = self.session.query(DynamicSourceField).order_by(
            DynamicSourceField.source_key, 
            DynamicSourceField.sort_order
        ).all()
        return [f.to_dict() for f in fields]

    def list_by_source(self, source_key: str) -> list[dict]:
        """获取指定数据源的所有子字段"""
        fields = self.session.query(DynamicSourceField).filter(
            DynamicSourceField.source_key == source_key,
            DynamicSourceField.enabled == True
        ).order_by(DynamicSourceField.sort_order).all()
        return [f.to_dict() for f in fields]

    def list_enabled(self) -> list[dict]:
        """获取所有启用的子字段"""
        fields = self.session.query(DynamicSourceField).filter(
            DynamicSourceField.enabled == True
        ).order_by(
            DynamicSourceField.source_key,
            DynamicSourceField.sort_order
        ).all()
        return [f.to_dict() for f in fields]

    def get_by_key(self, source_key: str, field_key: str) -> dict | None:
        """获取指定数据源的指定字段"""
        field = self.session.query(DynamicSourceField).filter(
            DynamicSourceField.source_key == source_key,
            DynamicSourceField.field_key == field_key
        ).first()
        return field.to_dict() if field else None

    def create(self, data: dict) -> dict:
        """创建新的子字段"""
        field = DynamicSourceField(**data)
        self.session.add(field)
        self.session.commit()
        return field.to_dict()

    def update(self, source_key: str, field_key: str, data: dict) -> dict | None:
        """更新子字段"""
        field = self.session.query(DynamicSourceField).filter(
            DynamicSourceField.source_key == source_key,
            DynamicSourceField.field_key == field_key
        ).first()
        if not field:
            return None
        
        for k, v in data.items():
            if hasattr(field, k) and k not in ('id', 'source_key', 'field_key'):
                setattr(field, k, v)
        
        self.session.commit()
        return field.to_dict()

    def delete(self, source_key: str, field_key: str) -> bool:
        """删除子字段"""
        field = self.session.query(DynamicSourceField).filter(
            DynamicSourceField.source_key == source_key,
            DynamicSourceField.field_key == field_key
        ).first()
        if not field:
            return False
        
        self.session.delete(field)
        self.session.commit()
        return True

    def close(self):
        self.session.close()
