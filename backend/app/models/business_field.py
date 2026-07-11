"""Business fields configuration model — stored in kp_data.db"""
from typing import Optional
from sqlalchemy import Integer, String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from .base import Base, kp_engine


class BusinessField(Base):
    __tablename__ = "business_fields"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False)  # opportunity/item/l6/kp/system
    source: Mapped[str] = mapped_column(String, nullable=False)  # Opportunity/L6Record/KPRecord/System
    source_column: Mapped[Optional[str]] = mapped_column(String, default=None)
    type: Mapped[str] = mapped_column(String, default='text')  # text/number/date/boolean
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # Field management v2 columns
    description: Mapped[Optional[str]] = mapped_column(String, default=None)
    display_type: Mapped[str] = mapped_column(String, default='text')  # text/money/percent/date/enum
    group_name: Mapped[Optional[str]] = mapped_column(String, default=None)
    scope: Mapped[str] = mapped_column(String, default='all')  # all/cover/config/rules
    permission: Mapped[str] = mapped_column(String, default='editable')  # editable/readonly/hidden
    
    # Field management v3 columns
    validation_rules: Mapped[Optional[str]] = mapped_column(Text, default=None)  # JSON: {"required": true, "pattern": "...", "min": 0, "max": 100}
    options: Mapped[Optional[str]] = mapped_column(Text, default=None)  # JSON: ["option1", "option2"] or [{"value": "A", "label": "选项A"}]
    dependencies: Mapped[Optional[str]] = mapped_column(Text, default=None)  # JSON: {"field": "platform_type", "operator": "eq", "value": "A"}
    created_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    updated_at: Mapped[Optional[str]] = mapped_column(String, default=None)
    created_by: Mapped[str] = mapped_column(String, default='system')
    updated_by: Mapped[str] = mapped_column(String, default='system')

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "label": self.label,
            "category": self.category,
            "source": self.source,
            "source_column": self.source_column,
            "type": self.type,
            "enabled": self.enabled,
            "sort_order": self.sort_order,
            "description": self.description,
            "display_type": self.display_type,
            "group_name": self.group_name,
            "scope": self.scope,
            "permission": self.permission,
            "validation_rules": self.validation_rules,
            "options": self.options,
            "dependencies": self.dependencies,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "created_by": self.created_by,
            "updated_by": self.updated_by,
        }
