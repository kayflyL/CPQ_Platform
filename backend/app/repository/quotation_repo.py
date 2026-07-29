"""Quotation repository — manages quotation CRUD operations"""
import json
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.quotation import Quotation
from app.models.quotation_item import QuotationItem
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
        "exported_at", "cost_snapshot",
        "quotation_date", "config_quantities", "config_descriptions", "config_server_models",
        "config_warranty_info", "total_price", "profit_margin", "extra_fields", "tenant_id",
        "is_primary", "source", "strategy_snapshot",
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
        "item_id", "quotation_id", "config_name", "category", "catalogue",
        "description", "part_category", "qty", "base_price", "final_price",
        "profit_margin", "currency", "extra_fields", "tenant_id",
    }

    def save_items(self, quotation_id: str, items: List[dict]) -> int:
        """Save configuration items for a quotation. Supports dynamic fields via extra_fields."""
        # Delete existing items
        self.db.query(QuotationItem).filter(
            QuotationItem.quotation_id == quotation_id
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
            
            item = QuotationItem(
                quotation_id=core_kwargs.get("quotation_id", quotation_id),
                config_name=core_kwargs.get("config_name", ""),
                category=core_kwargs.get("category", ""),
                catalogue=core_kwargs.get("catalogue", ""),
                description=core_kwargs.get("description", ""),
                part_category=core_kwargs.get("part_category", None),
                qty=core_kwargs.get("qty", 0),
                base_price=core_kwargs.get("base_price", 0.0),
                final_price=core_kwargs.get("final_price", 0.0),
                profit_margin=core_kwargs.get("profit_margin", 0.0),
                currency=core_kwargs.get("currency", "RMB"),
                extra_fields=json.dumps(extra, ensure_ascii=False) if extra else None,
            )
            self.db.add(item)
        
        self.db.commit()
        
        # 自动计算并更新 total_price 和 profit_margin
        self.calculate_totals(quotation_id)
        
        return len(items)

    def calculate_totals(self, quotation_id: str) -> dict:
        """Calculate and update total_price, profit_margin, and config_count for a quotation"""
        quotation = self.get_by_id(quotation_id)
        if not quotation:
            return {"total_price": 0.0, "profit_margin": 0.0, "config_count": 0}
        
        # 从 quotation_items 计算价格和数量
        items = self.db.query(QuotationItem).filter(
            QuotationItem.quotation_id == quotation_id
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
        
        # 从 config_l6_picks 统计配置数量（包含所有用户创建的配置，即使没有 items）
        config_count = 0
        if quotation.extra_fields:
            try:
                extra = json.loads(quotation.extra_fields)
                config_l6_picks = extra.get("config_l6_picks", {})
                config_count = len(config_l6_picks) if config_l6_picks else 0
            except (json.JSONDecodeError, TypeError):
                pass
        
        # 如果没有 config_l6_picks，fallback 到 items 中的 config_name
        if config_count == 0 and items:
            config_count = len(set(item.config_name for item in items if item.config_name))
        
        # 更新 quotation
        quotation.total_price = round(total_price, 2)
        quotation.profit_margin = profit_margin
        quotation.config_count = config_count
        quotation.updated_at = datetime.now().isoformat()
        self.db.commit()
        
        return {
            "total_price": quotation.total_price,
            "profit_margin": quotation.profit_margin,
            "config_count": quotation.config_count
        }

    def set_primary(self, quotation_id: str) -> bool:
        """Toggle primary: set if not primary, clear if already primary."""
        quotation = self.db.query(Quotation).filter(
            Quotation.quotation_id == quotation_id
        ).first()
        if not quotation:
            return False

        # If already primary, just clear it (toggle off)
        if quotation.is_primary:
            quotation.is_primary = False
            quotation.updated_at = datetime.now().isoformat()
            self.db.commit()
            return True

        # Otherwise set as primary (clear others)
        self.db.query(Quotation).filter(
            Quotation.opportunity_id == quotation.opportunity_id
        ).update({Quotation.is_primary: False})

        quotation.is_primary = True
        quotation.updated_at = datetime.now().isoformat()
        self.db.commit()
        return True

    def get_items(self, quotation_id: str) -> List[QuotationItem]:
        """Get all items for a quotation"""
        return self.db.query(QuotationItem).filter(
            QuotationItem.quotation_id == quotation_id
        ).all()

    def find_draft(self, opportunity_id: str) -> Optional[Quotation]:
        """Return the single active draft (status='active' AND exported_at IS NULL) for an
        opportunity, or None. Used to enforce the 'one draft per opportunity' invariant."""
        return self.db.query(Quotation).filter(
            Quotation.opportunity_id == opportunity_id,
            Quotation.status == "active",
            Quotation.exported_at.is_(None),
        ).order_by(Quotation.created_at.desc()).first()

    def _sync_totals_from_snapshot(self, quotation: Quotation, snapshot: Optional[dict]) -> None:
        """从成本快照反写 total_price / profit_margin（+ total_qty），让列表行显示与
        快照一致。导出冻结 / 手工补录后都调一次。快照 schema:
          totals.totalSales / totals.marginPct；configs.<name>.qty（总台数）。"""
        if not snapshot or not isinstance(snapshot, dict):
            return
        totals = snapshot.get('totals') or {}
        try:
            if totals.get('totalSales') is not None:
                quotation.total_price = round(float(totals['totalSales']), 2)
            if totals.get('marginPct') is not None:
                quotation.profit_margin = round(float(totals['marginPct']), 2)
        except (TypeError, ValueError):
            pass
        # 总台数：Σ 各配置 qty（完整快照才有 configs；手工补录无 configs 则不动）
        configs = snapshot.get('configs') or {}
        if isinstance(configs, dict) and configs:
            try:
                quotation.total_qty = int(sum(int(c.get('qty') or 0) for c in configs.values()))
            except (TypeError, ValueError):
                pass

    def mark_exported(self, quotation_id: str, cost_snapshot: dict, exported_at: str) -> Optional[Quotation]:
        """Freeze a draft into an exported quotation: stamp exported_at and persist the
        cost snapshot captured by the frontend at export time."""
        quotation = self.db.query(Quotation).filter(
            Quotation.quotation_id == quotation_id
        ).first()
        if not quotation:
            return None
        quotation.exported_at = exported_at
        quotation.cost_snapshot = cost_snapshot
        self._sync_totals_from_snapshot(quotation, cost_snapshot)
        quotation.updated_at = datetime.now().isoformat()
        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def save_cost_snapshot(self, quotation_id: str, cost_snapshot: dict) -> Optional[Quotation]:
        """Persist a manually-entered cost snapshot for a historical quotation backfill.
        Writes cost_snapshot ONLY — exported_at stays untouched, keeping 'manually
        backfilled' distinct from 'exported/frozen'."""
        quotation = self.db.query(Quotation).filter(
            Quotation.quotation_id == quotation_id
        ).first()
        if not quotation:
            return None
        quotation.cost_snapshot = cost_snapshot
        self._sync_totals_from_snapshot(quotation, cost_snapshot)
        quotation.updated_at = datetime.now().isoformat()
        self.db.commit()
        self.db.refresh(quotation)
        return quotation

    def copy_quotation_state(self, source_id: str, target_id: str) -> Optional[Quotation]:
        """Clone a source quotation's structured state (config-level fields + items +
        extra_fields incl. config_l6_picks) into an already-created target row, stamping
        source_quotation_id lineage. Used by the 'copy exported → draft' flow — re-parsing
        the export Excel is unreliable (different layout), but the source's DB items are
        the authoritative structured data."""
        source = self.db.query(Quotation).filter(Quotation.quotation_id == source_id).first()
        target = self.db.query(Quotation).filter(Quotation.quotation_id == target_id).first()
        if not source or not target:
            return None

        # 配置级字段（用户填写）
        target.config_quantities = source.config_quantities
        target.config_descriptions = source.config_descriptions
        target.config_server_models = source.config_server_models
        target.config_warranty_info = source.config_warranty_info
        target.quotation_date = source.quotation_date
        target.file_path = source.file_path

        # extra_fields：继承源的（含 config_l6_picks）+ 标血统
        src_extra = {}
        if source.extra_fields:
            try:
                src_extra = json.loads(source.extra_fields)
            except (json.JSONDecodeError, TypeError):
                src_extra = {}
        src_extra["source_quotation_id"] = source_id
        target.extra_fields = json.dumps(src_extra, ensure_ascii=False)

        self.db.flush()

        # 克隆 items（保留全部业务列 + extra_fields）
        src_items = self.db.query(QuotationItem).filter(
            QuotationItem.quotation_id == source_id
        ).all()
        for it in src_items:
            self.db.add(QuotationItem(
                quotation_id=target_id,
                config_name=it.config_name,
                category=it.category,
                catalogue=it.catalogue,
                description=it.description,
                part_category=it.part_category,
                qty=it.qty,
                base_price=it.base_price,
                final_price=it.final_price,
                profit_margin=it.profit_margin,
                currency=it.currency,
                extra_fields=it.extra_fields,
            ))

        self.db.commit()
        # 重算 total_price / profit_margin / config_count
        self.calculate_totals(target_id)
        self.db.refresh(target)
        return target


