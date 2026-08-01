"""Repository for KP (Key Parts) — 配件管理

指向新拆分的 6 张表：kp_categories, kp_parts, kp_part_specs, kp_price_history, kp_part_compat, kp_part_related
保持旧接口签名兼容（pricing_engine / quote_service 无感迁移）。
新增完整 CRUD 方法支持配件管理页面。
"""
from datetime import datetime, date, timedelta
import difflib
import json
import re
import statistics
from typing import List, Optional, Dict, Any
from sqlalchemy import text, select, func, exists, and_, Date
from sqlalchemy.orm import Session, joinedload
from app.models.base import KP_SessionLocal
from app.models.kp import (
    KPCategory, KPPart, KPPartSpec, KPPriceHistory, KPPartCompat, KPPartRelated
)

_NUM_SPEC_OPS = {">=", "<=", ">", "<"}

def _spec_num(val) -> Optional[float]:
    """从 spec 值提首个数字：'32 GB'→32.0 / '5600 MT/s'→5600.0 / 'DDR5'→None。"""
    if val is None:
        return None
    m = re.search(r"[\d.]+", str(val))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def _spec_match_all(spec_map: dict, parsed: list) -> str:
    """所有 (spec_key, op, value) AND 满足 → 返回命中标签串（如 'Type=DDR5 · Speed>=5600'）；任一不满足 → ''。
    数值型 op 且双方都能提数 → 数值比较；op='in' → 等值/数值等值集合；其余 → 字符串等值。"""
    hits = []
    for sk, op, val in parsed:
        sv = spec_map.get(sk)
        if sv is None:
            return ""  # 该 spec 不存在 → AND 不满足
        sv_num = _spec_num(sv)
        val_num = _spec_num(val) if not isinstance(val, list) else None
        if op in _NUM_SPEC_OPS and sv_num is not None and val_num is not None:
            ok = (sv_num >= val_num if op == ">="
                  else sv_num <= val_num if op == "<="
                  else sv_num > val_num if op == ">"
                  else sv_num < val_num if op == "<"
                  else abs(sv_num - val_num) < 1e-9)  # = / ==
            if not ok:
                return ""
            hits.append(f"{sk}{op}{val_num:g}")
        elif op == "in":
            vals = val if isinstance(val, list) else [val]
            if not any(str(sv).strip() == str(v).strip() or _spec_num(sv) == _spec_num(v) for v in vals):
                return ""
            hits.append(f"{sk}∈{{{','.join(str(v) for v in vals)}}}")
        else:
            sv_s = str(sv).strip()
            if not (sv_s == str(val).strip() or _spec_num(sv) == _spec_num(val)):
                return ""
            hits.append(f"{sk}={sv_s}")  # 显示真实 spec_value（DDR5 / 1G / 32 GB）
    return " · ".join(hits)


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

    def get_by_category_with_spec_filter(self, category: str, spec_filters: list[dict]) -> List[dict]:
        """品类下按 spec 过滤配件（多条件 AND，支持数值范围 + 等值/IN）。

        spec_filters: [{spec_key, op, value, unit?}, ...]，AND 组合。
        - 数值型 op（>= <= > < =）：spec_value 提数字比较（'32 GB'→32、'5600 MT/s'→5600）。
        - 等值/IN（op='=' 且 value 非数值，或 op='in'）：字符串等值匹配（Type=DDR5、Link Speed=1G）。
        KP 件少（品类级几十件），全取 + Python 过滤，避免拼动态 raw SQL（且能组合多条件）。
        无 spec_filters / 全无 spec_key → 退化 get_by_category（向后兼容）。
        """
        if not spec_filters:
            return self.get_by_category(category)
        parsed = []
        for f in spec_filters:
            sk = (f.get("spec_key") or "").strip()
            if sk:
                parsed.append((sk, (f.get("op") or "=").strip(), f.get("value")))
        if not parsed:
            return self.get_by_category(category)

        parts = self.session.query(KPPart).options(joinedload(KPPart.specs)) \
            .join(KPCategory, KPPart.category_id == KPCategory.id, isouter=True) \
            .filter(KPCategory.name == category) \
            .order_by(KPPart.name).all()

        out: list = []
        for part in parts:
            spec_map = {s.spec_key: s.spec_value for s in (part.specs or [])}
            hit = _spec_match_all(spec_map, parsed)
            if not hit:
                continue
            latest = self.session.query(KPPriceHistory) \
                .filter(KPPriceHistory.part_id == part.id) \
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc()) \
                .first()
            record_count = self.session.query(KPPriceHistory).filter(KPPriceHistory.part_id == part.id).count()
            out.append({
                "id": part.id,
                "category": category,
                "model": part.name,
                "price": latest.price if latest else 0.0,
                "currency": latest.currency if latest else "RMB",
                "date": latest.price_date.isoformat() if latest and latest.price_date else "",
                "note": latest.note if latest else "",
                "record_count": record_count,
                "matched_spec": hit,
            })
        return out

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

    # ---- 总览统计（仪表盘） ----
    def _summarize_parts(self, parts) -> list:
        """把 KPPart 列表归一成仪表盘用的摘要（含最新报价）"""
        out = []
        for part in parts:
            latest = self.session.query(KPPriceHistory) \
                .filter(KPPriceHistory.part_id == part.id) \
                .order_by(KPPriceHistory.price_date.desc().nullslast(), KPPriceHistory.id.desc()) \
                .first()
            out.append({
                "id": part.id,
                "name": part.name,
                "category_name": part.category.name if part.category else None,
                "brand": part.brand,
                "latest_price": latest.price if latest else None,
                "latest_currency": latest.currency if latest else None,
                "latest_date": latest.price_date.isoformat() if latest and latest.price_date else None,
                "created_at": part.created_at.isoformat() if part.created_at else None,
            })
        return out

    def get_stats(self, recent_limit: int = 6, series_days: int = 14) -> dict:
        """配件库总览：总数 / 本周新增 / 上周新增 / 有效价格数 / 每日新增序列 / 最近入库 / 最近调价"""
        now = datetime.utcnow()
        week_ago = now - timedelta(days=7)
        two_weeks_ago = now - timedelta(days=14)

        total = self.session.query(func.count(KPPart.id)).scalar() or 0
        this_week_new = self.session.query(func.count(KPPart.id)) \
            .filter(KPPart.created_at >= week_ago).scalar() or 0
        last_week_new = self.session.query(func.count(KPPart.id)) \
            .filter(KPPart.created_at >= two_weeks_ago, KPPart.created_at < week_ago).scalar() or 0

        # 有效价格：最新报价日在最近 2 天内的配件数
        cutoff = date.today() - timedelta(days=2)
        latest_price_date_sq = select(func.max(KPPriceHistory.price_date)) \
            .where(KPPriceHistory.part_id == KPPart.id).scalar_subquery()
        valid_price_count = self.session.query(func.count(KPPart.id)) \
            .filter(latest_price_date_sq >= cutoff).scalar() or 0

        # 最近 N 天每日新增序列（缺失日补 0）
        series_start_dt = now - timedelta(days=series_days - 1)
        series_start = series_start_dt.date()
        rows = self.session.query(
            func.cast(KPPart.created_at, Date).label("d"),
            func.count(KPPart.id),
        ).filter(KPPart.created_at >= series_start_dt) \
         .group_by(text("d")).order_by(text("d")).all()
        counts_by_day = {r[0]: int(r[1]) for r in rows}
        new_series = []
        for i in range(series_days):
            d = series_start + timedelta(days=i)
            new_series.append({"date": d.isoformat(), "count": counts_by_day.get(d, 0)})

        # 最近入库（按 created_at desc）
        recent_parts_q = self.session.query(KPPart) \
            .options(joinedload(KPPart.category)) \
            .order_by(KPPart.created_at.desc().nullslast(), KPPart.id.desc()) \
            .limit(recent_limit).all()
        recent_parts = self._summarize_parts(recent_parts_q)

        # 最近调价（按每个配件最新 price_date desc）
        latest_sub = select(
            KPPriceHistory.part_id.label("pid"),
            func.max(KPPriceHistory.price_date).label("lpd"),
        ).group_by(KPPriceHistory.part_id).subquery()
        price_rows = self.session.query(KPPart) \
            .join(latest_sub, latest_sub.c.pid == KPPart.id) \
            .options(joinedload(KPPart.category)) \
            .order_by(latest_sub.c.lpd.desc().nullslast(), KPPart.id.desc()) \
            .limit(recent_limit).all()
        recent_price_updates = self._summarize_parts(price_rows)

        return {
            "total": total,
            "this_week_new": this_week_new,
            "last_week_new": last_week_new,
            "valid_price_count": valid_price_count,
            "new_series": new_series,
            "recent_parts": recent_parts,
            "recent_price_updates": recent_price_updates,
        }

    # ---- 数据洞察：价格异动 / 比价矩阵 / 疑似重复 ----

    def _latest_price_map(self, part_ids: List[int]) -> Dict[int, KPPriceHistory]:
        """一次查全量价格历史，按 part_id 分组取最新一条（口径：price_date DESC NULLS LAST, id DESC）。"""
        if not part_ids:
            return {}
        rows = self.session.query(KPPriceHistory) \
            .filter(KPPriceHistory.part_id.in_(part_ids)) \
            .order_by(KPPriceHistory.part_id,
                      KPPriceHistory.price_date.desc().nullslast(),
                      KPPriceHistory.id.desc()).all()
        latest: Dict[int, KPPriceHistory] = {}
        for h in rows:
            if h.part_id not in latest:
                latest[h.part_id] = h
        return latest

    def get_price_movers(self, days: int = 7, limit: int = 10) -> dict:
        """价格异动看板：每个配件最新价 vs N 天前最近一条价的涨跌幅，返回涨幅/跌幅 TOP。"""
        cutoff_days = max(1, int(days))
        top_n = max(1, int(limit))

        # 一次拉全量价格历史，按 part_id 分组（已按最新价口径排序）
        all_hist = self.session.query(KPPriceHistory) \
            .order_by(KPPriceHistory.part_id,
                      KPPriceHistory.price_date.desc().nullslast(),
                      KPPriceHistory.id.desc()).all()
        by_part: Dict[int, List[KPPriceHistory]] = {}
        for h in all_hist:
            by_part.setdefault(h.part_id, []).append(h)

        candidates = []  # [(part_id, curr, prev, delta_pct)]
        for pid, hist in by_part.items():
            if len(hist) < 2:
                continue
            curr = hist[0]
            if not curr.price or curr.price_date is None:
                continue
            threshold_date = curr.price_date - timedelta(days=cutoff_days)
            prev = None
            for r in hist[1:]:
                if r.price_date is not None and r.price_date <= threshold_date:
                    prev = r
                    break
            if not prev or not prev.price:
                continue
            delta_pct = (curr.price - prev.price) / prev.price * 100
            candidates.append((pid, curr, prev, delta_pct))

        # 批量取 part 实体
        part_ids = [c[0] for c in candidates]
        parts_map = {}
        if part_ids:
            parts = self.session.query(KPPart).options(joinedload(KPPart.category)) \
                .filter(KPPart.id.in_(part_ids)).all()
            parts_map = {p.id: p for p in parts}

        def build(c):
            pid, curr, prev, delta_pct = c
            part = parts_map.get(pid)
            return {
                "id": pid,
                "name": part.name if part else None,
                "category_name": part.category.name if part and part.category else None,
                "brand": part.brand if part else None,
                "latest_price": curr.price,
                "latest_currency": curr.currency,
                "latest_date": curr.price_date.isoformat() if curr.price_date else None,
                "prev_price": prev.price,
                "prev_date": prev.price_date.isoformat() if prev.price_date else None,
                "delta_pct": round(delta_pct, 2),
            }

        gainers = sorted([build(c) for c in candidates if c[3] > 0],
                         key=lambda x: x["delta_pct"], reverse=True)[:top_n]
        losers = sorted([build(c) for c in candidates if c[3] < 0],
                        key=lambda x: x["delta_pct"])[:top_n]

        return {"days": cutoff_days, "gainers": gainers, "losers": losers}

    def get_price_matrix(self, category_id: int, group_key: str) -> dict:
        """比价矩阵：同分类下按某 spec_key 分组的价格分布（min/Q1/median/Q3/max + 明细）。"""
        parts = self.session.query(KPPart).options(joinedload(KPPart.category)) \
            .filter(KPPart.category_id == category_id).all()
        if not parts:
            return {"group_key": group_key, "groups": []}

        part_ids = [p.id for p in parts]
        latest_map = self._latest_price_map(part_ids)

        # 取每个 part 在 group_key 维度的 spec_value
        spec_rows = self.session.query(KPPartSpec.part_id, KPPartSpec.spec_value) \
            .filter(KPPartSpec.spec_key == group_key, KPPartSpec.part_id.in_(part_ids)).all()
        spec_map = {pid: (val or "").strip() for pid, val in spec_rows}

        groups: Dict[str, list] = {}
        for p in parts:
            val = spec_map.get(p.id, "")
            gv = val if val else "(未分组)"
            groups.setdefault(gv, []).append(p)

        result_groups = []
        for gv, plist in groups.items():
            priced = []  # [(part, price, latest)]
            for p in plist:
                lp = latest_map.get(p.id)
                if lp and lp.price is not None:
                    priced.append((p, lp.price, lp))
            if not priced:
                continue
            prices = [pr[1] for pr in priced]
            if len(prices) >= 2:
                try:
                    qs = statistics.quantiles(prices, n=4, method='inclusive')
                    q1, q3 = qs[0], qs[2]
                except Exception:
                    q1 = q3 = prices[0]
            else:
                q1 = q3 = prices[0]
            result_groups.append({
                "value": gv,
                "count": len(priced),
                "min": round(min(prices), 2),
                "max": round(max(prices), 2),
                "avg": round(statistics.mean(prices), 2),
                "median": round(statistics.median(prices), 2),
                "q1": round(q1, 2),
                "q3": round(q3, 2),
                "parts": [{
                    "id": p.id,
                    "name": p.name,
                    "brand": p.brand,
                    "category_name": p.category.name if p.category else None,
                    "latest_price": price,
                    "latest_currency": lp.currency,
                    "latest_date": lp.price_date.isoformat() if lp.price_date else None,
                } for p, price, lp in sorted(priced, key=lambda x: x[1])],
            })

        result_groups.sort(key=lambda x: x["count"], reverse=True)
        return {"group_key": group_key, "groups": result_groups}

    def detect_duplicates(self, threshold: float = 0.6) -> dict:
        """疑似重复检测：oem_sku/alt_sku 精确匹配（强信号）+ name difflib 相似度（弱信号）。
        返回重复组（不做合并，仅展示）。"""
        parts = self.session.query(KPPart).options(joinedload(KPPart.category)).all()
        if len(parts) < 2:
            return {"total_groups": 0, "total_duplicate_parts": 0, "groups": []}

        part_ids = [p.id for p in parts]
        latest_map = self._latest_price_map(part_ids)
        parts_by_id = {p.id: p for p in parts}

        def summary(p):
            lp = latest_map.get(p.id)
            return {
                "id": p.id,
                "name": p.name,
                "brand": p.brand,
                "oem_sku": p.oem_sku,
                "alt_sku": p.alt_sku,
                "category_name": p.category.name if p.category else None,
                "latest_price": lp.price if lp else None,
                "latest_currency": lp.currency if lp else None,
            }

        # Union-Find
        parent = {p.id: p.id for p in parts}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        pair_reasons: Dict[tuple, dict] = {}

        def record(a_id, b_id, reason, sim):
            key = tuple(sorted((a_id, b_id)))
            prev = pair_reasons.get(key)
            if not prev or sim > prev["similarity"]:
                pair_reasons[key] = {"reason": reason, "similarity": sim}

        def norm(s):
            return (s or "").strip()

        threshold_clamped = max(0.0, min(1.0, float(threshold)))

        # 按 brand 分桶（桶内两两比；桶过大时按 name 前缀再分小桶，防 O(n²) 爆炸）
        brand_buckets: Dict[str, List[KPPart]] = {}
        for p in parts:
            brand_buckets.setdefault(norm(p.brand), []).append(p)

        for bucket in brand_buckets.values():
            if len(bucket) < 2:
                continue
            if len(bucket) > 500:
                sub: Dict[str, List[KPPart]] = {}
                for p in bucket:
                    sub.setdefault(norm(p.name)[:3] or "_", []).append(p)
                iter_buckets = list(sub.values())
            else:
                iter_buckets = [bucket]

            for sub_list in iter_buckets:
                m = len(sub_list)
                for i in range(m):
                    a = sub_list[i]
                    a_oem, a_alt = norm(a.oem_sku), norm(a.alt_sku)
                    for j in range(i + 1, m):
                        b = sub_list[j]
                        b_oem, b_alt = norm(b.oem_sku), norm(b.alt_sku)

                        hit_reason, hit_sim = None, 0.0
                        if a_oem and a_oem == b_oem:
                            hit_reason, hit_sim = f"oem_sku 相同 ({a_oem})", 1.0
                        elif a_oem and a_oem == b_alt:
                            hit_reason, hit_sim = f"oem_sku/alt_sku 相同 ({a_oem})", 1.0
                        elif a_alt and a_alt == b_oem:
                            hit_reason, hit_sim = f"oem_sku/alt_sku 相同 ({a_alt})", 1.0
                        elif a_alt and a_alt == b_alt:
                            hit_reason, hit_sim = f"alt_sku 相同 ({a_alt})", 1.0

                        if not hit_reason and a.category_id == b.category_id:
                            ratio = difflib.SequenceMatcher(None, a.name or "", b.name or "").ratio()
                            if ratio >= threshold_clamped:
                                hit_reason, hit_sim = f"名称相似 ({ratio:.2f})", ratio

                        if hit_reason:
                            union(a.id, b.id)
                            record(a.id, b.id, hit_reason, hit_sim)

        # 按 root 聚合
        groups_map: Dict[int, List[int]] = {}
        for p in parts:
            groups_map.setdefault(find(p.id), []).append(p.id)

        result_groups = []
        for ids in groups_map.values():
            if len(ids) < 2:
                continue
            # 取该组内最强命中原因
            best = None
            for i in range(len(ids)):
                for j in range(i + 1, len(ids)):
                    pr = pair_reasons.get(tuple(sorted((ids[i], ids[j]))))
                    if pr and (not best or pr["similarity"] > best["similarity"]):
                        best = pr
            result_groups.append({
                "reason": best["reason"] if best else "疑似重复",
                "similarity": round(best["similarity"], 2) if best else 0.0,
                "parts": [summary(parts_by_id[pid]) for pid in sorted(ids)],
            })

        result_groups.sort(key=lambda g: (g["similarity"], len(g["parts"])), reverse=True)
        total_dup = sum(len(g["parts"]) for g in result_groups)
        return {
            "total_groups": len(result_groups),
            "total_duplicate_parts": total_dup,
            "groups": result_groups,
        }

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

    # ---- 批量导入/导出辅助 ----
    def find_or_create_category_by_name(self, name: Optional[str]) -> int:
        """按名称查找分类,不存在则创建(空名兜底「未分类」)。返回 category_id。"""
        nm = (str(name).strip() if name else "") or "未分类"
        cat = self.session.query(KPCategory).filter(KPCategory.name == nm).first()
        if not cat:
            cat = KPCategory(name=nm)
            self.session.add(cat)
            self.session.flush()
        return cat.id

    def find_parts_by_dedupe_key(self, oem_sku: Optional[str] = None,
                                 name: Optional[str] = None) -> List[KPPart]:
        """去重键查询:优先 oem_sku,空则按 name。返回列表(空/单/多 → new/update/conflict)。"""
        if oem_sku and str(oem_sku).strip():
            return self.session.query(KPPart)\
                .filter(KPPart.oem_sku == str(oem_sku).strip()).all()
        if name and str(name).strip():
            return self.session.query(KPPart)\
                .filter(KPPart.name == str(name).strip()).all()
        return []

    def list_all_for_export(self, category_id: Optional[int] = None) -> List[KPPart]:
        """导出用:不分页,eager load category/specs/price_history。"""
        q = self.session.query(KPPart).options(
            joinedload(KPPart.category),
            joinedload(KPPart.specs),
            joinedload(KPPart.price_history),
        )
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        return q.order_by(KPPart.id.asc()).all()

    def list_spec_keys(self, category_id: Optional[int] = None, top_n: int = 15) -> List[tuple]:
        """[(spec_key, freq)] 按 freq 降序,供导入模板预置高频规格列。"""
        q = self.session.query(KPPartSpec.spec_key, func.count(KPPartSpec.id))\
            .join(KPPart, KPPartSpec.part_id == KPPart.id)\
            .filter(KPPartSpec.spec_key.isnot(None), KPPartSpec.spec_key != '')
        if category_id:
            q = q.filter(KPPart.category_id == category_id)
        rows = q.group_by(KPPartSpec.spec_key)\
            .order_by(func.count(KPPartSpec.id).desc()).limit(top_n).all()
        return [(k, int(c)) for k, c in rows]

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

    def price_history_exists(self, part_id: int, price: float,
                             currency: Optional[str] = None,
                             price_date: Any = None) -> bool:
        """判断同 part 是否已存在相同(价格 + 币种 + 日期)的记录,用于导入去重防堆积。"""
        if price is None:
            return False
        pd_ = None
        if price_date:
            try:
                pd_ = datetime.strptime(str(price_date)[:10], "%Y-%m-%d").date()
            except ValueError:
                pd_ = None
        if pd_ is None:
            return False  # 没有日期不去重(避免误合并不同时点的报价)
        q = self.session.query(KPPriceHistory).filter(
            KPPriceHistory.part_id == part_id,
            KPPriceHistory.price == price,
            KPPriceHistory.currency == (currency or "RMB"),
            KPPriceHistory.price_date == pd_,
        )
        return self.session.query(q.exists()).scalar()

    def update_price_history(self, price_id: int, price: float = None,
                              currency: str = None,
                              price_date: str = None, note: str = None) -> bool:
        """更新价格记录"""
        h = self.session.query(KPPriceHistory).filter(KPPriceHistory.id == price_id).first()
        if not h:
            return False
        if price is not None:
            h.price = price
        if currency is not None:
            h.currency = currency
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
