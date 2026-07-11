"""Quotation repository — manages quotation CRUD operations"""
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.quotation import Quotation
from app.models.opportunity_item import OpportunityItem
from app.models.base import Opp_SessionLocal
from datetime import datetime


class QuotationRepository:
    def __init__(self):
        self.db: Session = Opp_SessionLocal()

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

    def update(self, quotation_id: str, **kwargs) -> Optional[Quotation]:
        """Update quotation fields"""
        quotation = self.get_by_id(quotation_id)
        if not quotation:
            return None
        
        for key, value in kwargs.items():
            if hasattr(quotation, key):
                setattr(quotation, key, value)
        
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

    def save_items(self, quotation_id: str, items: List[dict]) -> int:
        """Save configuration items for a quotation"""
        # Delete existing items
        self.db.query(OpportunityItem).filter(
            OpportunityItem.quotation_id == quotation_id
        ).delete()
        
        # Insert new items
        for item_data in items:
            item = OpportunityItem(
                quotation_id=quotation_id,
                config_name=item_data.get("config_name", ""),
                category=item_data.get("category", ""),
                part_name=item_data.get("part_name", ""),
                spec=item_data.get("spec", ""),
                qty=item_data.get("qty", 0),
                confirmed_price=item_data.get("confirmed_price", 0.0),
                base_price=item_data.get("base_price", 0.0),
                final_price=item_data.get("final_price", 0.0),
                profit_margin=item_data.get("profit_margin", 0.0)
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

    def save_items(self, quotation_id: str, items: list) -> None:
        """Replace all items for a quotation (delete + insert)."""
        # Delete existing items
        self.db.query(OpportunityItem).filter(
            OpportunityItem.quotation_id == quotation_id
        ).delete()
        # Insert new items
        for item_data in items:
            if isinstance(item_data, dict):
                item = OpportunityItem(quotation_id=quotation_id, **{
                    k: v for k, v in item_data.items()
                    if hasattr(OpportunityItem, k) and k != 'id'
                })
                self.db.add(item)
        self.db.commit()

    def delete(self, quotation_id: str) -> bool:
        """Soft delete a quotation."""
        quo = self.db.query(Quotation).filter(
            Quotation.quotation_id == quotation_id
        ).first()
        if quo:
            quo.status = "deleted"
            self.db.commit()
            return True
        return False

    def restore(self, quotation_id: str) -> bool:
        """Restore a soft-deleted quotation."""
        quo = self.db.query(Quotation).filter(
            Quotation.quotation_id == quotation_id
        ).first()
        if quo:
            quo.status = "active"
            self.db.commit()
            return True
        return False

    def close(self):
        if self.db:
            self.db.close()
