"""Repository for KP (Key Parts) — 配件管理

指向新拆分的 6 张表：kp_categories, kp_parts, kp_part_specs, kp_price_history, kp_part_compat, kp_part_related
保持旧接口签名兼容（pricing_engine / quote_service 无感迁移）。
新增完整 CRUD 方法支持配件管理页面。
"""
from datetime import datetime, date
import json
from typing import List, Optional, Dict, Any
from sqlalchemy import text, select, func, exists, and_
from sqlalchemy.orm import Session, joinedload
from app.models.base import KP_SessionLocal
from app.models.kp import (
    KPCategory, KPPart, KPPartSpec, KPPriceHistory, KPPartCompat, KPPartRelated
)


class KPRepository:
    """配件管理 Repository — 新表 + 旧接口兼容"""

    def __init__(self):
        self.session: Session = KP_SessionLocal()

    def close(self):
        if self.session:
            self.session.close()

    # ============================================================
    # 旧接口兼容层（pricing_engine / quote_service 使用）
    # ============================================================

    def get_latest_prices(self, search: str = "", category: str = "", sort_by: str = "date", sort_order: str = "desc") -> List[dict]:
        """获取每个配件的最新价格（兼容旧接口）"""
        # 白名单排序字段
        allowed_sort = {"name": "name", "price": "latest_price", "date": "latest_date", "category": "category_name"}
        sort_field = allowed_sort.get(sort_by, "latest_date")
        if sort_order.lower() not in ("asc", "desc"):
            sort_order = "desc"

        q = self.session.query(
            KPPart.id,
            KPPart.name,
            KPCategory.name.label("category_name"),
            KPPriceHistory.price,
            KPPriceHistory.currency,
            KPPriceHistory.price_date,
            KPPriceHistory.note,
        ).join(KPCategory, KPPart.category_id == KPCategory.id, isouter=True)\
         .join(KPPriceHistory, KPPart.id == KPPriceHistory.part_id, isouter=True)\
         .filter(KPPriceHistory.id == self._latest_price_subquery())

        if search:
            q = q.filter(KPPart.name.ilike(f"%{search}%") | KPPriceHistory.note.ilike(f"%{search}%"))
        if category:
            q = q.filter(KPCategory.name == category)

        # 动态排序
        if sort_field == "name":
            q = q.order_by(KPPart.name.asc() if sort_order == "asc" else KPPart.name.desc())
        elif sort_field == "latest_price":
            q = q.order_by(KPPriceHistory.price.asc() if sort_order == "asc" else KPPriceHistory.price.desc())
        elif sort_field == "latest_date":
            q = q.order_by(KPPriceHistory.price_date.asc() if sort_order == "asc" else KPPriceHistory.price_date.desc())
        elif sort_field == "category_name":
            q = q.order_by(KPCategory.name.asc() if sort_order == "asc" else KPCategory.name.desc())

        rows = q.all()
        result = []
        for r in rows:
            # 统计该配件的历史记录数
            record_count = self.session.query(KPPriceHistory).filter(KPPriceHistory.part_id == r.id).count()
            result.append({
                "id": r.id,
                "category": r.category_name or "",
                "model": r.name,
                "price": r.price or 0.0,
                "currency": r.currency or "RMB",
                "date": r.price_date.isoformat() if r.price_date else "",
                "note": r.note or "",
                "record_count": record_count,
            })
        return result

    def _latest_price_subquery(self):
        """子查询：每个 part_id 的最新 price_history id"""
        return text("""
            (SELECT MAX(id) FROM kp.kp_price_history ph2 WHERE ph2.part_id = kp.kp_parts.id)
        """)

    def get_latest_price_for_model(self, model: str) -> Optional[dict]:
        """根据配件名称获取最新价格（兼容旧接口）"""
        part = self.session.query(KPPart).filter(KPPart.name == model).first()
        if not part:
            return None
        latest = self.session.query(KPPriceHistory)\
            .filter(KPPriceHistory.part_id == part.id)\
            .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
            .first()
        if not latest:
            return None
        return {
            "category": part.category.name if part.category else "",
            "model": part.name,
            "price": latest.price,
            "currency": latest.currency,
            "date": latest.price_date.isoformat() if latest.price_date else "",
            "note": latest.note,
        }

    def fuzzy_match_price(self, model_fragment: str) -> Optional[dict]:
        """模糊匹配配件名称获取最新价格（pricing_engine 使用）"""
        part = self.session.query(KPPart).filter(KPPart.name.ilike(f"%{model_fragment}%")).first()
        if not part:
            return None
        latest = self.session.query(KPPriceHistory)\
            .filter(KPPriceHistory.part_id == part.id)\
            .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
            .first()
        if not latest:
            return None
        return {
            "category": part.category.name if part.category else "",
            "model": part.name,
            "price": latest.price,
            "currency": latest.currency,
            "date": latest.price_date.isoformat() if latest.price_date else "",
            "note": latest.note,
        }

    def get_price_history(self, model: str, limit: int = 20) -> List[dict]:
        """获取配件价格历史（兼容旧接口）"""
        part = self.session.query(KPPart).filter(KPPart.name == model).first()
        if not part:
            return []
        rows = self.session.query(KPPriceHistory)\
            .filter(KPPriceHistory.part_id == part.id)\
            .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
            .limit(limit)\
            .all()
        return [{
            "id": r.id,
            "category": part.category.name if part.category else "",
            "model": part.name,
            "price": r.price,
            "currency": r.currency,
            "date": r.price_date.isoformat() if r.price_date else "",
            "note": r.note,
        } for r in rows]

    def insert_price(self, category: str, model: str, price: float,
                     currency: str = "RMB", date: str = None, note: str = "") -> bool:
        """插入价格记录（兼容旧接口）"""
        # 查找或创建配件
        part = self.session.query(KPPart).filter(KPPart.name == model).first()
        if not part:
            # 查找或创建分类
            cat = self.session.query(KPCategory).filter(KPCategory.name == category).first()
            if not cat:
                cat = KPCategory(name=category)
                self.session.add(cat)
                self.session.flush()
            part = KPPart(category_id=cat.id, name=model)
            self.session.add(part)
            self.session.flush()

        # 解析日期
        price_date = None
        if date:
            try:
                price_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                price_date = datetime.now().date()
        else:
            price_date = datetime.now().date()

        history = KPPriceHistory(
            part_id=part.id,
            price=price,
            currency=currency,
            price_date=price_date,
            note=note
        )
        self.session.add(history)
        self.session.commit()
        return True

    def get_categories(self) -> List[dict]:
        """获取所有分类及其配件数量（兼容旧接口）"""
        rows = self.session.query(
            KPCategory.name,
            KPCategory.id,
            KPCategory.sort_order,
        ).outerjoin(KPPart, KPCategory.id == KPPart.category_id)\
         .group_by(KPCategory.id, KPCategory.name, KPCategory.sort_order)\
         .order_by(KPCategory.sort_order)\
         .all()

        result = []
        for r in rows:
            count = self.session.query(KPPart).filter(KPPart.category_id == r.id).count()
            result.append({
                "id": r.id,
                "category": r.name,
                "count": count,
                "sort_order": r.sort_order,
            })
        return result

    def get_by_category(self, category: str, search: str = "") -> List[dict]:
        """获取指定分类下的配件列表（兼容旧接口）"""
        q = self.session.query(KPPart, KPCategory.name.label("category_name"))\
            .join(KPCategory, KPPart.category_id == KPCategory.id, isouter=True)\
            .filter(KPCategory.name == category)

        if search:
            q = q.filter(KPPart.name.ilike(f"%{search}%"))

        q = q.order_by(KPPart.name)
        rows = q.all()

        result = []
        for part, cat_name in rows:
            latest = self.session.query(KPPriceHistory)\
                .filter(KPPriceHistory.part_id == part.id)\
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
                .first()
            record_count = self.session.query(KPPriceHistory).filter(KPPriceHistory.part_id == part.id).count()
            result.append({
                "id": part.id,
                "category": cat_name or "",
                "model": part.name,
                "price": latest.price if latest else 0.0,
                "currency": latest.currency if latest else "RMB",
                "date": latest.price_date.isoformat() if latest and latest.price_date else "",
                "note": latest.note if latest else "",
                "record_count": record_count,
            })
        return result

    def rename_model(self, old_model: str, new_model: str) -> bool:
        """重命名配件（兼容旧接口）"""
        part = self.session.query(KPPart).filter(KPPart.name == old_model).first()
        if part:
            part.name = new_model
            part.updated_at = datetime.utcnow()
            self.session.commit()
        return True

    def update_note(self, model: str, note: str) -> bool:
        """更新配件最新价格记录的备注（兼容旧接口）"""
        part = self.session.query(KPPart).filter(KPPart.name == model).first()
        if not part:
            return False
        latest = self.session.query(KPPriceHistory)\
            .filter(KPPriceHistory.part_id == part.id)\
            .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
            .first()
        if latest:
            latest.note = note
            self.session.commit()
        return True

    def get_distinct_cpu_models(self) -> List[str]:
        """获取所有 CPU 型号（pricing_engine 使用）"""
        cpu_cat = self.session.query(KPCategory).filter(KPCategory.name == "CPU").first()
        if not cpu_cat:
            return []
        rows = self.session.query(KPPart.name)\
            .filter(KPPart.category_id == cpu_cat.id, KPPart.name.isnot(None), KPPart.name != "")\
            .order_by(KPPart.name)\
            .all()
        return [r[0] for r in rows]

    # ============================================================
    # 新增方法：配件完整 CRUD
    # ============================================================

    # ---- 分类管理 ----
    def list_categories(self) -> List[dict]:
        """列出所有分类（含层级）"""
        rows = self.session.query(KPCategory).order_by(KPCategory.sort_order).all()
        return [c.to_dict() for c in rows]

    def create_category(self, data: dict) -> dict:
        """创建分类"""
        cat = KPCategory(
            name=data["name"],
            parent_id=data.get("parent_id"),
            icon=data.get("icon"),
            sort_order=data.get("sort_order", 0),
            description=data.get("description"),
        )
        self.session.add(cat)
        self.session.commit()
        self.session.refresh(cat)
        return cat.to_dict()

    def update_category(self, cat_id: int, data: dict) -> Optional[dict]:
        """更新分类"""
        cat = self.session.query(KPCategory).get(cat_id)
        if not cat:
            return None
        for key in ["name", "parent_id", "icon", "sort_order", "description"]:
            if key in data:
                setattr(cat, key, data[key])
        self.session.commit()
        return cat.to_dict()

    def delete_category(self, cat_id: int) -> bool:
        """删除分类（需先确保无配件关联）"""
        cat = self.session.query(KPCategory).get(cat_id)
        if not cat:
            return False
        count = self.session.query(KPPart).filter(KPPart.category_id == cat_id).count()
        if count > 0:
            raise ValueError(f"分类下还有 {count} 个配件，无法删除")
        self.session.delete(cat)
        self.session.commit()
        return True

    # ---- 配件管理 ----
    def list_parts(self, category_id: int = None, search: str = "", page: int = 1, page_size: int = 20,
                   sort_by: str = "name", sort_order: str = "asc",
                   brands: str = None, price_filter: str = None, specs: str = None) -> Dict[str, Any]:
        """分页列出配件

        sort_by 支持: name / price / updated_at；price 按每个配件最新一次报价排序。
        brands: 逗号分隔的品牌名；price_filter: has_price/no_price/multi；specs: JSON 字符串 {key:[values]}。
        """
        q = self.session.query(KPPart).options(joinedload(KPPart.category))
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        if search:
            q = q.filter(KPPart.name.ilike(f"%{search}%") | KPPart.oem_sku.ilike(f"%{search}%") | KPPart.brand.ilike(f"%{search}%"))

        # 品牌 / 价格记录 / 规格筛选
        if brands:
            brand_list = [b.strip() for b in brands.split(',') if b.strip()]
            if brand_list:
                q = q.filter(KPPart.brand.in_(brand_list))
        if price_filter in ('has_price', 'no_price', 'multi'):
            price_count_sq = select(func.count(KPPriceHistory.id))\
                .where(KPPriceHistory.part_id == KPPart.id).scalar_subquery()
            if price_filter == 'has_price':
                q = q.filter(price_count_sq > 0)
            elif price_filter == 'no_price':
                q = q.filter(price_count_sq == 0)
            elif price_filter == 'multi':
                q = q.filter(price_count_sq >= 3)
        if specs:
            specs_dict = None
            try:
                specs_dict = json.loads(specs) if isinstance(specs, str) else specs
            except Exception:
                specs_dict = None
            if isinstance(specs_dict, dict):
                for sk, svs in specs_dict.items():
                    values = svs if isinstance(svs, list) else [svs]
                    values = [str(v) for v in values if v is not None and str(v).strip()]
                    if not values:
                        continue
                    q = q.filter(exists().where(and_(
                        KPPartSpec.part_id == KPPart.id,
                        KPPartSpec.spec_key == sk,
                        KPPartSpec.spec_value.in_(values),
                    )))

        # 排序键：price 用标量子查询取最新报价（与列表 latest_price 口径一致，按 price_date desc, id desc）
        if sort_by == "price":
            sort_expr = select(KPPriceHistory.price)\
                .where(KPPriceHistory.part_id == KPPart.id)\
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
                .limit(1)\
                .scalar_subquery()
        elif sort_by == "updated_at":
            sort_expr = KPPart.updated_at
        else:
            sort_expr = KPPart.name

        sort_expr = sort_expr.desc() if sort_order == "desc" else sort_expr.asc()
        sort_expr = sort_expr.nullslast()

        total = q.count()
        rows = q.order_by(sort_expr).offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for part in rows:
            latest = self.session.query(KPPriceHistory)\
                .filter(KPPriceHistory.part_id == part.id)\
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc())\
                .first()
            d = part.to_dict()
            d["latest_price"] = latest.price if latest else None
            d["latest_date"] = latest.price_date.isoformat() if latest and latest.price_date else None
            d["latest_currency"] = latest.currency if latest else None
            items.append(d)

        return {"total": total, "page": page, "page_size": page_size, "items": items}

    def list_brands(self, category_id: int = None) -> list:
        """聚合品牌列表 + 计数（可选按分类过滤，用于筛选面板）"""
        q = self.session.query(KPPart.brand, func.count(KPPart.id))\
            .filter(KPPart.brand.isnot(None), KPPart.brand != '')
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        rows = q.group_by(KPPart.brand).order_by(func.count(KPPart.id).desc()).all()
        return [{"brand": b, "count": int(c)} for b, c in rows]

    def list_spec_facets(self, category_id: int = None) -> Dict[str, list]:
        """聚合规格维度：{spec_key: [{value, count}]}（可选按分类过滤，用于动态筛选面板）"""
        q = self.session.query(KPPartSpec.spec_key, KPPartSpec.spec_value, func.count(KPPart.id))\
            .join(KPPart, KPPartSpec.part_id == KPPart.id)\
            .filter(KPPartSpec.spec_value.isnot(None), KPPartSpec.spec_value != '')
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        rows = q.group_by(KPPartSpec.spec_key, KPPartSpec.spec_value).all()
        facets: Dict[str, list] = {}
        for k, v, c in rows:
            facets.setdefault(k, []).append({"value": v, "count": int(c)})
        for k in facets:
            facets[k].sort(key=lambda x: x["count"], reverse=True)
        return facets

    def get_part(self, part_id: int) -> Optional[dict]:
        """获取单个配件详情（含规格、价格历史、兼容机型）"""
        part = self.session.query(KPPart).options(
            joinedload(KPPart.category),
            joinedload(KPPart.specs),
            joinedload(KPPart.price_history),
            joinedload(KPPart.compat_servers),
        ).get(part_id)
        if not part:
            return None
        return part.to_dict(include_specs=True, include_history=True, include_compat=True)

    def create_part(self, data: dict) -> dict:
        """创建配件"""
        part = KPPart(
            category_id=data.get("category_id"),
            oem_sku=data.get("oem_sku"),
            alt_sku=data.get("alt_sku"),
            brand=data.get("brand"),
            name=data["name"],
            short_desc=data.get("short_desc"),
            full_desc=data.get("full_desc"),
            condition=data.get("condition", "全新"),
            lead_time=data.get("lead_time"),
            image_url=data.get("image_url"),
            datasheet_url=data.get("datasheet_url"),
            moq=data.get("moq", 1),
            applicable=data.get("applicable"),
        )
        self.session.add(part)
        self.session.flush()

        # 批量创建规格
        if "specs" in data and data["specs"]:
            for i, spec in enumerate(data["specs"]):
                s = KPPartSpec(part_id=part.id, spec_key=spec["key"], spec_value=spec.get("value"), sort_order=i)
                self.session.add(s)

        # 批量创建兼容机型
        if "compat_servers" in data and data["compat_servers"]:
            for model in data["compat_servers"]:
                c = KPPartCompat(part_id=part.id, server_model=model)
                self.session.add(c)

        self.session.commit()
        self.session.refresh(part)
        return part.to_dict()

    def update_part(self, part_id: int, data: dict) -> Optional[dict]:
        """更新配件"""
        part = self.session.query(KPPart).get(part_id)
        if not part:
            return None

        for key in ["category_id", "oem_sku", "alt_sku", "brand", "name", "short_desc",
                    "full_desc", "condition", "lead_time", "image_url", "datasheet_url", "moq", "applicable"]:
            if key in data:
                setattr(part, key, data[key])
        part.updated_at = datetime.utcnow()

        # 更新规格（全量替换）
        if "specs" in data:
            self.session.query(KPPartSpec).filter(KPPartSpec.part_id == part_id).delete()
            for i, spec in enumerate(data["specs"]):
                s = KPPartSpec(part_id=part_id, spec_key=spec["key"], spec_value=spec.get("value"), sort_order=i)
                self.session.add(s)

        # 更新兼容机型（全量替换）
        if "compat_servers" in data:
            self.session.query(KPPartCompat).filter(KPPartCompat.part_id == part_id).delete()
            for model in data["compat_servers"]:
                c = KPPartCompat(part_id=part_id, server_model=model)
                self.session.add(c)

        self.session.commit()
        return part.to_dict()

    def delete_part(self, part_id: int) -> bool:
        """删除配件（级联删除规格、价格历史、兼容机型）"""
        part = self.session.query(KPPart).get(part_id)
        if not part:
            return False
        self.session.delete(part)
        self.session.commit()
        return True

    # ---- 价格历史 ----
    def add_price_history(self, part_id: int, price: float, currency: str = "RMB",
                          price_date: str = None, note: str = "", source: str = "") -> dict:
        """添加价格记录"""
        pd = None
        if price_date:
            try:
                pd = datetime.strptime(price_date, "%Y-%m-%d").date()
            except ValueError:
                pd = datetime.now().date()
        else:
            pd = datetime.now().date()

        h = KPPriceHistory(part_id=part_id, price=price, currency=currency, price_date=pd, note=note, source=source)
        self.session.add(h)
        self.session.commit()
        self.session.refresh(h)
        return h.to_dict()

    def update_price_history(self, price_id: int, price: float = None,
                              price_date: str = None, note: str = None) -> bool:
        """更新价格记录"""
        h = self.session.query(KPPriceHistory).filter(KPPriceHistory.id == price_id).first()
        if not h:
            return False
        if price is not None:
            h.price = price
        if price_date is not None:
            try:
                h.price_date = datetime.strptime(price_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        if note is not None:
            h.note = note
        self.session.commit()
        return True

    def delete_price_history(self, price_id: int) -> bool:
        """删除价格记录"""
        h = self.session.query(KPPriceHistory).filter(KPPriceHistory.id == price_id).first()
        if not h:
            return False
        self.session.delete(h)
        self.session.commit()
        return True

    # ---- 关联配件 ----
    def list_related(self, part_id: int) -> List[dict]:
        """获取关联配件"""
        rows = self.session.query(KPPartRelated).filter(KPPartRelated.source_part_id == part_id)\
            .order_by(KPPartRelated.sort_order).all()
        result = []
        for r in rows:
            target = self.session.query(KPPart).get(r.target_part_id)
            result.append({
                "id": r.id,
                "source_part_id": r.source_part_id,
                "target_part_id": r.target_part_id,
                "target_name": target.name if target else None,
                "sort_order": r.sort_order,
            })
        return result

    def add_related(self, source_part_id: int, target_part_id: int, sort_order: int = 0) -> dict:
        """添加关联配件"""
        r = KPPartRelated(source_part_id=source_part_id, target_part_id=target_part_id, sort_order=sort_order)
        self.session.add(r)
        self.session.commit()
        self.session.refresh(r)
        return r.to_dict()

    def remove_related(self, relation_id: int) -> bool:
        """删除关联"""
        r = self.session.query(KPPartRelated).get(relation_id)
        if not r:
            return False
        self.session.delete(r)
        self.session.commit()
        return True
