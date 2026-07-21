"""Repository for Opportunity metadata (商机线索)."""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.models.opportunity import Opportunity
from app.models.base import Opportunity_SessionLocal


class OpportunityRepository:
    def __init__(self):
        self._session: Optional[Session] = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = Opportunity_SessionLocal()
        return self._session

    def list_opportunities(self, include_deleted: bool = False,
                      page: int = 1, page_size: int = 50,
                      search: str = None, status: str = None,
                      platform: str = None, chassis: str = None,
                      sort_by: str = "updated_at", sort_order: str = "desc") -> tuple[List[dict], int]:
        q = self.session.query(Opportunity)
        if not include_deleted:
            q = q.filter(Opportunity.status != "deleted")
        if status and status != "all":
            q = q.filter(Opportunity.status == status)
        if platform:
            plats = [s.strip() for s in platform.split(',') if s.strip()]
            if plats:
                q = q.filter(Opportunity.platform_type.in_(plats))
        if chassis:
            chas = [s.strip() for s in chassis.split(',') if s.strip()]
            if chas:
                q = q.filter(Opportunity.chassis_form.in_(chas))
        if search:
            q = q.filter(
                Opportunity.opportunity_name.ilike(f"%{search}%") |
                Opportunity.customer_name.ilike(f"%{search}%") |
                Opportunity.sales_person.ilike(f"%{search}%")
            )
        _SORT_COLS = {"updated_at": Opportunity.updated_at, "created_at": Opportunity.created_at}
        _col = _SORT_COLS.get(sort_by, Opportunity.updated_at)
        q = q.order_by(_col.asc() if sort_order == "asc" else _col.desc())

        total = q.count()
        rows = q.offset((page - 1) * page_size).limit(page_size).all()

        # Batch-query quotation stats to avoid N+1 (single aggregated query)
        from app.models.quotation import Quotation
        from sqlalchemy import func

        opp_ids = [r.opportunity_id for r in rows]
        stats_map: dict = {}
        if opp_ids:
            stats_rows = (
                self.session.query(
                    Quotation.opportunity_id,
                    func.count(Quotation.quotation_id).label("quotation_count"),
                    func.max(Quotation.config_count).label("max_config_count"),
                )
                .filter(
                    Quotation.opportunity_id.in_(opp_ids),
                    Quotation.status == "active",
                )
                .group_by(Quotation.opportunity_id)
                .all()
            )
            stats_map = {
                s.opportunity_id: {
                    "quotation_count": s.quotation_count,
                    "config_count": s.max_config_count or 0,
                }
                for s in stats_rows
            }

        result = []
        for r in rows:
            opp_dict = r.to_dict()
            stats = stats_map.get(r.opportunity_id, {})
            opp_dict["quotation_count"] = stats.get("quotation_count", 0)
            opp_dict["config_count"] = stats.get("config_count", 0)
            result.append(opp_dict)

        return result, total

    def get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        return opp.to_dict() if opp else None

    def get_opportunity_with_items(self, opportunity_id: str) -> Optional[dict]:
        """Get opportunity with all quotations and their items."""
        from app.models.quotation import Quotation
        from app.models.opportunity_item import OpportunityItem
        
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if not opp:
            return None
        
        result = opp.to_dict()
        
        # Get all active quotations for this opportunity
        quotations = self.session.query(Quotation).filter(
            Quotation.opportunity_id == opportunity_id,
            Quotation.status == "active"
        ).order_by(Quotation.version.desc()).all()
        
        # Aggregate items from all quotations
        all_items = []
        total_l6_price = 0.0
        total_qty = 0
        total_configs = 0
        
        for quo in quotations:
            items = self.session.query(OpportunityItem).filter(
                OpportunityItem.quotation_id == quo.quotation_id
            ).all()
            for item in items:
                item_dict = item.to_dict()
                item_dict['quotation_id'] = quo.quotation_id
                item_dict['quotation_version'] = quo.version
                all_items.append(item_dict)
            
            total_l6_price += (quo.l6_price or 0)
            total_qty += (quo.total_qty or 0)
            total_configs += 1
        
        result['quotations'] = [q.to_dict() for q in quotations]
        result['items'] = all_items
        result['l6_price'] = total_l6_price
        result['purchase_qty'] = total_qty
        result['config_count'] = total_configs
        
        return result

    def create_or_update_opportunity(self, opportunity_id: str, info: dict) -> bool:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if existing:
            for key, val in info.items():
                if hasattr(existing, key) and key not in ("opportunity_id", "created_at"):
                    # 防御：incoming 为空值时不覆盖已有非空值，避免报价保存擦掉商机名等元数据
                    cur = getattr(existing, key)
                    if (val is None or (isinstance(val, str) and val == "")) and cur not in (None, ""):
                        continue
                    setattr(existing, key, val)
            existing.updated_at = now
            existing.status = "active"
        else:
            opp = Opportunity(
                opportunity_id=opportunity_id,
                folder_name=info.get("folder_name"),
                opportunity_name=info.get("opportunity_name", ""),
                customer_name=info.get("customer_name", ""),
                sales_person=info.get("sales_person", ""),
                fae=info.get("fae", ""),
                purchase_qty=info.get("purchase_qty", 0),
                platform_type=info.get("platform_type", ""),
                chassis_form=info.get("chassis_form", ""),
                created_at=now,
                updated_at=now,
                status="active",
            )
            self.session.add(opp)
        self.session.commit()
        return True

    # Core fields that are actual DB columns (not in extra_fields JSON)
    _CORE_COLUMNS = {
        "opportunity_id", "folder_name", "opportunity_name", "customer_name",
        "sales_person", "fae", "quotation_person", "platform_type", "chassis_form",
        "purchase_qty", "created_at", "updated_at", "status", "extra_fields", "tenant_id",
    }

    def update_meta(self, opportunity_id: str, updates: dict) -> bool:
        import json
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if not opp:
            return False
        
        # Load existing extra_fields
        extra = {}
        if opp.extra_fields:
            try:
                extra = json.loads(opp.extra_fields)
            except (json.JSONDecodeError, TypeError):
                extra = {}
        
        for key, val in updates.items():
            if key in self._CORE_COLUMNS:
                # Core column: set directly
                setattr(opp, key, val)
            else:
                # Dynamic field: write to extra_fields JSON
                extra[key] = val
        
        # Save extra_fields back
        opp.extra_fields = json.dumps(extra, ensure_ascii=False) if extra else None
        opp.updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.session.commit()
        return True

    def move_to_trash(self, opportunity_id: str) -> bool:
        """软删除商机及其所有报价单（单次事务，保证原子性）。"""
        from app.models.quotation import Quotation
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 更新商机状态
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if opp:
            opp.status = "deleted"
            opp.updated_at = now

        # 级联软删除所有报价单
        quotations = self.session.query(Quotation).filter(
            Quotation.opportunity_id == opportunity_id
        ).all()
        for quo in quotations:
            quo.status = "deleted"

        self.session.commit()
        return True

    def restore_opportunity(self, opportunity_id: str) -> bool:
        """恢复商机及其所有报价单（单次事务，保证原子性）。"""
        from app.models.quotation import Quotation
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 恢复商机状态
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if opp:
            opp.status = "active"
            opp.updated_at = now

        # 级联恢复所有报价单
        quotations = self.session.query(Quotation).filter(
            Quotation.opportunity_id == opportunity_id
        ).all()
        for quo in quotations:
            quo.status = "active"

        self.session.commit()
        return True

    def permanent_delete(self, opportunity_id: str) -> bool:
        # Delete all quotations and their items
        from app.models.quotation import Quotation
        from app.models.opportunity_item import OpportunityItem
        
        quotations = self.session.query(Quotation).filter(
            Quotation.opportunity_id == opportunity_id
        ).all()
        
        for quo in quotations:
            self.session.execute(delete(OpportunityItem).where(
                OpportunityItem.quotation_id == quo.quotation_id
            ))
        
        self.session.execute(delete(Quotation).where(
            Quotation.opportunity_id == opportunity_id
        ))
        self.session.execute(delete(Opportunity).where(
            Opportunity.opportunity_id == opportunity_id
        ))
        self.session.commit()
        return True

    def close(self):
        if self._session:
            self._session.close()
            self._session = None
