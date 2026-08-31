"""Repository for Opportunity metadata (商机线索)."""
import json
from datetime import datetime
from typing import List, Optional
from sqlalchemy import delete, or_, and_
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

    _REQUIREMENT_FIELD_KEYS = ("platform_type", "chassis_form", "purchase_qty", "warranty_years")

    def _current_slot_map(self, opp_ids: Optional[List[str]] = None) -> dict:
        """读取各商机需求单 slots，用于替代 opportunities 旧列派生平台/机箱/数量/维保。

        优先级：current 需求单 > 最新 draft 需求单；仅当 current 缺失时才回退 draft。
        """
        from app.models.flow import OpportunityRequirement
        q = self.session.query(
            OpportunityRequirement.opportunity_id,
            OpportunityRequirement.status,
            OpportunityRequirement.version,
            OpportunityRequirement.slots,
        ).filter(OpportunityRequirement.status.in_(["current", "draft"]))
        if opp_ids:
            q = q.filter(OpportunityRequirement.opportunity_id.in_(opp_ids))
        q = q.order_by(
            OpportunityRequirement.opportunity_id,
            OpportunityRequirement.version.desc(),
        )

        def _parse(raw):
            slots = raw or {}
            if isinstance(slots, str):
                try:
                    slots = json.loads(slots)
                except (json.JSONDecodeError, TypeError):
                    slots = {}
            return slots if isinstance(slots, dict) else {}

        current: dict = {}
        draft: dict = {}
        for oid, status, _version, raw in q.all():
            parsed = _parse(raw)
            if status == "current" and oid not in current:
                current[oid] = parsed
            elif status == "draft" and oid not in draft:
                draft[oid] = parsed

        out: dict = {}
        all_ids = set(current) | set(draft)
        for oid in all_ids:
            out[oid] = current.get(oid) or draft.get(oid) or {}
        return out

    def _merge_requirement_fields(self, opp_dicts: List[dict]) -> None:
        """把当前需求单派生字段合并到 Opportunity dict，保持旧 API 字段兼容。"""
        if not opp_dicts:
            return
        ids = [d.get("opportunity_id") for d in opp_dicts if d.get("opportunity_id")]
        slot_map = self._current_slot_map(ids)
        for d in opp_dicts:
            slots = slot_map.get(d.get("opportunity_id"), {})
            d["platform_type"] = slots.get("platform_type") or ""
            d["chassis_form"] = slots.get("chassis_form") or ""
            d["purchase_qty"] = slots.get("purchase_qty") or 0
            d["warranty_years"] = slots.get("warranty_years") or ""

    def list_opportunities(self, include_deleted: bool = False,
                      page: int = 1, page_size: int = 50,
                      search: str = None, status: str = None,
                      platform: str = None, chassis: str = None,
                      result: str = None, industry: str = None, order_type: str = None,
                      sales_person: str = None, owner_user_id: str = None,
                      owner_sales_person: str = None,
                      has_committed_requirement: bool = False,
                      sort_by: str = "updated_at", sort_order: str = "desc") -> tuple[List[dict], int]:
        q = self.session.query(Opportunity)
        # AI Office 内部商机只在转真实商机后进入业务列表。
        q = q.filter(Opportunity.status != "ai_office")
        if has_committed_requirement:
            # 商机线索页只显示已提交需求单的商机：有 current 需求单，或流程已推进出 requirement。
            from app.models.flow import OpportunityRequirement, OpportunityFlow
            from sqlalchemy import exists
            q = q.filter(
                exists().where(
                    OpportunityRequirement.opportunity_id == Opportunity.opportunity_id,
                    OpportunityRequirement.status == "current",
                )
                | exists().where(
                    OpportunityFlow.opportunity_id == Opportunity.opportunity_id,
                    OpportunityFlow.current_node != "requirement",
                )
            )
        if not include_deleted:
            q = q.filter(Opportunity.status != "deleted")
        if status and status != "all":
            q = q.filter(Opportunity.status == status)
        if result and result != "all":
            q = q.filter(Opportunity.result == result)
        if owner_user_id:
            owner_cond = [Opportunity.owner_user_id == owner_user_id]
            if owner_sales_person:
                owner_cond.append(
                    and_(Opportunity.owner_user_id.is_(None), Opportunity.sales_person == owner_sales_person)
                )
            q = q.filter(or_(*owner_cond))
        elif owner_sales_person:
            q = q.filter(Opportunity.sales_person == owner_sales_person)
        if sales_person:
            persons = [s.strip() for s in sales_person.split(',') if s.strip()]
            if persons:
                q = q.filter(Opportunity.sales_person.in_(persons))
        if industry:
            inds = [s.strip() for s in industry.split(',') if s.strip()]
            if inds:
                q = q.filter(Opportunity.industry.in_(inds))
        if order_type:
            cts = [s.strip() for s in order_type.split(',') if s.strip()]
            if cts:
                q = q.filter(Opportunity.order_type.in_(cts))
        if search:
            q = q.filter(
                Opportunity.customer_name.ilike(f"%{search}%") |
                Opportunity.sales_person.ilike(f"%{search}%")
            )
        if platform or chassis:
            # 旧列已迁移到需求单 slots，列表筛选改为基于当前需求单派生值过滤。
            candidate_ids = [r.opportunity_id for r in q.with_entities(Opportunity.opportunity_id).all()]
            slot_map = self._current_slot_map(candidate_ids)
            def _slot_match(oid: str, field: str, values: list) -> bool:
                raw = str((slot_map.get(oid, {}).get(field)) or "").strip()
                if "未分类" in values and raw == "":
                    return True
                named = [v for v in values if v != "未分类"]
                return raw in named
            if platform:
                plats = [s.strip() for s in platform.split(',') if s.strip()]
                candidate_ids = [oid for oid in candidate_ids if _slot_match(oid, "platform_type", plats)]
            if chassis:
                chas = [s.strip() for s in chassis.split(',') if s.strip()]
                candidate_ids = [oid for oid in candidate_ids if _slot_match(oid, "chassis_form", chas)]
            q = q.filter(Opportunity.opportunity_id.in_(candidate_ids or [""]))
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
            # 每商机「当前版本」的 config_count（status=active 中 version 最大的一条），
            # 与工作台"当前版本"口径一致，避免多版本报价单的 config_count 被重复相加。
            _rn = func.row_number().over(
                partition_by=Quotation.opportunity_id,
                order_by=(Quotation.version.desc(), Quotation.created_at.desc()),
            ).label("rn")
            stats_rows = self.session.query(
                Quotation.opportunity_id.label("oid"),
                func.count(Quotation.quotation_id).over(
                    partition_by=Quotation.opportunity_id
                ).label("quotation_count"),
                Quotation.config_count.label("cc"),
                _rn,
            ).filter(
                Quotation.opportunity_id.in_(opp_ids),
                Quotation.status == "active",
            ).all()
            stats_map = {}
            for s in stats_rows:
                if s.oid not in stats_map:
                    stats_map[s.oid] = {"quotation_count": s.quotation_count, "config_count": 0}
                if s.rn == 1:
                    stats_map[s.oid]["config_count"] = s.cc or 0

        result = []
        for r in rows:
            opp_dict = r.to_dict()
            stats = stats_map.get(r.opportunity_id, {})
            opp_dict["quotation_count"] = stats.get("quotation_count", 0)
            opp_dict["config_count"] = stats.get("config_count", 0)
            result.append(opp_dict)

        self._merge_requirement_fields(result)

        return result, total

    def list_ai_office_opportunities(self, page: int = 1, page_size: int = 50,
                                     search: str = None,
                                     owner_user_id: str = None,
                                     owner_sales_person: str = None) -> tuple[List[dict], int]:
        """AI 办公室隐藏商机（status=ai_office）列表，供 AI 线索页使用。"""
        q = self.session.query(Opportunity).filter(Opportunity.status == "ai_office")
        if owner_user_id:
            owner_cond = [Opportunity.owner_user_id == owner_user_id]
            if owner_sales_person:
                owner_cond.append(
                    and_(Opportunity.owner_user_id.is_(None), Opportunity.sales_person == owner_sales_person)
                )
            q = q.filter(or_(*owner_cond))
        elif owner_sales_person:
            q = q.filter(Opportunity.sales_person == owner_sales_person)
        if search:
            q = q.filter(Opportunity.customer_name.ilike(f"%{search}%"))
        q = q.order_by(Opportunity.updated_at.desc())
        total = q.count()
        rows = q.offset((page - 1) * page_size).limit(page_size).all()
        return [r.to_dict() for r in rows], total

    def ai_lead_content_flags(self, opp_ids: List[str]) -> dict:
        """AI 线索内容标记：是否已登记需求单 / 是否已出 BOM 方案。"""
        from app.models.flow import OpportunityRequirement, OpportunityBomScheme
        ids = [i for i in opp_ids if i]
        if not ids:
            return {}
        req_ids = {
            r[0] for r in self.session.query(OpportunityRequirement.opportunity_id).filter(
                OpportunityRequirement.opportunity_id.in_(ids)
            ).all()
        }
        bom_ids = {
            r[0] for r in self.session.query(OpportunityBomScheme.opportunity_id).filter(
                OpportunityBomScheme.opportunity_id.in_(ids)
            ).all()
        }
        return {oid: {"has_requirement": oid in req_ids, "has_bom_scheme": oid in bom_ids} for oid in ids}

    def hard_delete_ai_lead(self, opportunity_id: str) -> bool:
        """级联物理删除 AI 线索（需求单/BOM 方案/商机行；会话与消息由调用方清理）。仅限 ai_office。"""
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id,
            Opportunity.status == "ai_office",
        ).first()
        if not opp:
            return False
        from app.models.flow import OpportunityRequirement, OpportunityBomScheme
        self.session.execute(delete(OpportunityRequirement).where(
            OpportunityRequirement.opportunity_id == opportunity_id))
        self.session.execute(delete(OpportunityBomScheme).where(
            OpportunityBomScheme.opportunity_id == opportunity_id))
        self.session.execute(delete(Opportunity).where(
            Opportunity.opportunity_id == opportunity_id))
        self.session.commit()
        return True

    def get_opportunity(self, opportunity_id: str) -> Optional[dict]:
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if not opp:
            return None
        result = opp.to_dict()
        self._merge_requirement_fields([result])
        return result

    def get_opportunity_with_items(self, opportunity_id: str) -> Optional[dict]:
        """Get opportunity with all quotations and their items."""
        from app.models.quotation import Quotation
        from app.models.quotation_item import QuotationItem
        
        opp = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if not opp:
            return None
        
        result = opp.to_dict()
        self._merge_requirement_fields([result])
        
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
            items = self.session.query(QuotationItem).filter(
                QuotationItem.quotation_id == quo.quotation_id
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
        # purchase_qty 保留用户输入值，不覆盖；config_count 显示报价单数量
        result['config_count'] = total_configs
        
        return result

    def create_or_update_opportunity(self, opportunity_id: str, info: dict) -> bool:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing = self.session.query(Opportunity).filter(
            Opportunity.opportunity_id == opportunity_id
        ).first()
        if existing:
            for key, val in info.items():
                if hasattr(existing, key) and key not in ("opportunity_id", "created_at", "owner_user_id", "tenant_id"):
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
                customer_name=info.get("customer_name", ""),
                sales_person=info.get("sales_person", ""),
                owner_user_id=info.get("owner_user_id"),
                fae=info.get("fae", ""),
                created_at=now,
                updated_at=now,
                status="active",
            )
            self.session.add(opp)
        self.session.commit()
        return True

    # Core fields that are actual DB columns (not in extra_fields JSON)
    _CORE_COLUMNS = {
        "opportunity_id", "customer_name",
        "sales_person", "owner_user_id", "fae", "quotation_person",
        "industry", "order_type", "result",
        "created_at", "updated_at", "status", "extra_fields", "tenant_id",
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
            if key in ("opportunity_id", "tenant_id"):
                continue
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
        from app.models.quotation_item import QuotationItem
        
        quotations = self.session.query(Quotation).filter(
            Quotation.opportunity_id == opportunity_id
        ).all()
        
        for quo in quotations:
            self.session.execute(delete(QuotationItem).where(
                QuotationItem.quotation_id == quo.quotation_id
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
