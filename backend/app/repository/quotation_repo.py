"""Quotation repository — manages quotation CRUD operations"""
import json
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.quotation import Quotation
from app.models.opportunity_item import OpportunityItem
from app.models.base import Opportunity_SessionLocal
from datetime import datetime


class QuotationRepository:
    def __init__(self):
        self.db: Session = Opportunity_SessionLocal()

    def close(self):
        if self.db:
            self.db.close()

    def create(self, opportunity_id: str, file_path: Optional[str] = None,
               quotation_date: str = None, quotation_name: str = None) -> Quotation:
        """Create a new quotation for an opportunity"""
        # Get max version for this opportunity
        latest = self.db.query(Quotation).filter(
            Quotation.opportunity_id == opportunity_id
        ).order_by(Quotation.version.desc()).first()
        
        if latest and latest.version:
            # Extract version number and increment (safely handle non-standard formats)
            try:
                version_num = int(latest.version.lstrip('v')) + 1
                version = f"v{version_num}"
            except (ValueError, AttributeError):
                version = "v1"
        else:
            version = "v1"
        
        quotation_id = f"QUO-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        
        # Auto-generate default name if not provided
        if not quotation_name:
            from datetime import datetime as dt
            date_part = dt.now().strftime('%Y%m%d')
            quotation_name = f"报价单-{date_part}-{version}"
        
        quotation = Quotation(
            quotation_id=quotation_id,
            opportunity_id=opportunity_id,
            version=version,
            quotation_name=quotation_name,
            file_path=file_path,
            quotation_date=quotation_date,
            l6_price=0.0,
            total_qty=0,
            config_count=0,
            total_price=0.0,
            profit_margin=0.0,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            status="active"
        )
        
        self.db.add(quotation)
        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def get_by_id(self, quotation_id: str) -> Optional[Quotation]:
        """Get quotation by ID"""
        return self.db.query(Quotation).filter(
            Quotation.quotation_id == quotation_id,
            Quotation.status == "active"
        ).first()

    def get_by_opportunity(self, opportunity_id: str) -> List[Quotation]:
        """Get all quotations for an opportunity"""
        return self.db.query(Quotation).filter(
            Quotation.opportunity_id == opportunity_id,
            Quotation.status == "active"
        ).order_by(Quotation.version.desc()).all()

    # Core fields that are actual DB columns (not in extra_fields JSON)
    _CORE_COLUMNS = {
        "quotation_id", "opportunity_id", "version", "quotation_name", "file_path",
        "l6_price", "total_qty", "config_count", "created_at", "updated_at", "status",
        "quotation_date", "config_quantities", "config_descriptions", "config_server_models",
        "total_price", "profit_margin", "extra_fields", "tenant_id",
    }

    def update(self, quotation_id: str, **kwargs) -> Optional[Quotation]:
        """Update quotation fields. Core fields go to columns, others to extra_fields JSON."""
        quotation = self.get_by_id(quotation_id)
        if not quotation:
            return None
        
        # Load existing extra_fields
        extra = {}
        if quotation.extra_fields:
            try:
                extra = json.loads(quotation.extra_fields)
            except (json.JSONDecodeError, TypeError):
                extra = {}
        
        for key, value in kwargs.items():
            if key in self._CORE_COLUMNS:
                # Core column: set directly
                setattr(quotation, key, value)
            else:
                # Dynamic field: write to extra_fields JSON
                extra[key] = value
        
        # Save extra_fields back
        quotation.extra_fields = json.dumps(extra, ensure_ascii=False) if extra else None
        quotation.updated_at = datetime.now().isoformat()
        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def delete(self, quotation_id: str) -> bool:
        """Soft delete quotation"""
        quotation = self.get_by_id(quotation_id)
        if not quotation:
            return False
        
        quotation.status = "deleted"
        quotation.updated_at = datetime.now().isoformat()
        self.db.commit()
        return True

    def restore(self, quotation_id: str) -> bool:
        """Restore a soft-deleted quotation"""
        quotation = self.db.query(Quotation).filter(
            Quotation.quotation_id == quotation_id
        ).first()
        if not quotation:
            return False
        
        quotation.status = "active"
        quotation.updated_at = datetime.now().isoformat()
        self.db.commit()
        return True

    # Core fields for items that are actual DB columns
    _ITEM_CORE_COLUMNS = {
        "item_id", "quotation_id", "config_name", "category", "part_name",
        "spec", "qty", "confirmed_price", "base_price", "final_price",
        "profit_margin", "extra_fields", "tenant_id",
    }

    def save_items(self, quotation_id: str, items: List[dict]) -> int:
        """Save configuration items for a quotation. Supports dynamic fields via extra_fields."""
        # Delete existing items
        self.db.query(OpportunityItem).filter(
            OpportunityItem.quotation_id == quotation_id
        ).delete()
        
        # Insert new items
        for item_data in items:
            # Separate core and dynamic fields
            extra = {}
            core_kwargs = {}
            for key, value in item_data.items():
                if key in self._ITEM_CORE_COLUMNS:
                    core_kwargs[key] = value
                else:
                    extra[key] = value
            
            item = OpportunityItem(
                quotation_id=core_kwargs.get("quotation_id", quotation_id),
                config_name=core_kwargs.get("config_name", ""),
                category=core_kwargs.get("category", ""),
                part_name=core_kwargs.get("part_name", ""),
                spec=core_kwargs.get("spec", ""),
                qty=core_kwargs.get("qty", 0),
                confirmed_price=core_kwargs.get("confirmed_price", 0.0),
                base_price=core_kwargs.get("base_price", 0.0),
                final_price=core_kwargs.get("final_price", 0.0),
                profit_margin=core_kwargs.get("profit_margin", 0.0),
                extra_fields=json.dumps(extra, ensure_ascii=False) if extra else None,
            )
            self.db.add(item)
        
        self.db.commit()
        
        # 自动计算并更新 total_price 和 profit_margin
        self.calculate_totals(quotation_id)
        
        return len(items)

    def calculate_totals(self, quotation_id: str) -> dict:
        """Calculate and update total_price and profit_margin for a quotation"""
        quotation = self.get_by_id(quotation_id)
        if not quotation:
            return {"total_price": 0.0, "profit_margin": 0.0}
        
        # 从 opportunity_items 计算
        items = self.db.query(OpportunityItem).filter(
            OpportunityItem.quotation_id == quotation_id
        ).all()
        
        total_price = 0.0
        total_base = 0.0
        
        for item in items:
            total_price += (item.final_price or 0.0) * (item.qty or 0)
            total_base += (item.base_price or 0.0) * (item.qty or 0)
        
        # 计算利润率
        if total_base > 0:
            profit_margin = round((total_price - total_base) / total_base * 100, 2)
        else:
            profit_margin = 0.0
        
        # 更新 quotation
        quotation.total_price = round(total_price, 2)
        quotation.profit_margin = profit_margin
        quotation.updated_at = datetime.now().isoformat()
        self.db.commit()
        
        return {
            "total_price": quotation.total_price,
            "profit_margin": quotation.profit_margin
        }

    def get_items(self, quotation_id: str) -> List[OpportunityItem]:
        """Get all items for a quotation"""
        return self.db.query(OpportunityItem).filter(
            OpportunityItem.quotation_id == quotation_id
        ).all()


