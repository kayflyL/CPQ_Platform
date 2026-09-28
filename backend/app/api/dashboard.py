"""Dashboard statistics API — unified summary + detail endpoints."""
from datetime import datetime, timedelta
from typing import Optional, List
import re
import statistics
from fastapi import APIRouter, Query, Depends
from sqlalchemy import func, case
import json

from app.models.opportunity import Opportunity
from app.models.quotation import Quotation
from app.models.base import Opportunity_SessionLocal
from app.api.deps import get_current_user, user_has_permission
# 口径核心已下沉到服务层（与商机线索页/AI 统计工具同一份实现），此处别名保持原调用点不变
from app.services.opp_stats import (
    bucket as _bucket,
    fill_dates as _fill_dates,
    resolve_range as _resolve_range,
)
from app.repository.opp_caliber_repo import (
    current_config_subquery as _current_config_subquery,
    current_slot_map as _current_slot_map,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

CHAS_COLORS = {"2U": "#26E2D1", "4U": "#FA8C16", "5U": "#A855F7", "4.5U": "#1890FF", "工作站": "#A855F7", "2U/4U": "#8A94A8", "8U": "#8A94A8"}

# PN 提取：config_server_models 里混存干净 PN（ZSA240 V2）和整机名（Orion 2U25 标准基准机箱），
# 用正则把 PN-like 段抠出来归一；提不出来的退化成"其他机型"，不污染机型维度。
_PN_RE = re.compile(r'([A-Z]{2,4}[\dA-Z]{1,6}(?:[- ][A-Z\d]+)?)')


def _normalize_pn(raw: str) -> str:
    """从 config_server_models 的值里抽出规范 PN（大写、去空格）；提不出返回 ''。"""
    m = _PN_RE.search((raw or '').upper().replace(' ', ''))
    return m.group(1) if m else ''


def _pct_quartiles(values: list) -> dict:
    """对一组利润率(百分点)算箱线五元组 + 均值/样本数。样本<4 时前端用散点兜底，这里照给。"""
    if not values:
        return None
    vs = sorted(float(v) for v in values if v is not None and -50 < float(v) < 200)
    if not vs:
        return None

    def _q(p: float) -> float:
        if len(vs) == 1:
            return vs[0]
        idx = p * (len(vs) - 1)
        lo = int(idx)
        hi = min(lo + 1, len(vs) - 1)
        frac = idx - lo
        return round(vs[lo] + (vs[hi] - vs[lo]) * frac, 2)

    return {
        "min": vs[0], "q1": _q(0.25), "median": _q(0.5), "q3": _q(0.75), "max": vs[-1],
        "mean": round(statistics.mean(vs), 2), "n": len(vs),
        # 散点（原始利润点），箱体样本不足时前端直接画散点不画箱
        "scatter": vs,
    }


@router.get("/summary")
def get_dashboard_summary(
    period: str = Query(default="week"),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    sales_person: Optional[str] = Query(default=None),
    result: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    chassis: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    part_filters: Optional[str] = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """Unified endpoint: KPIs + chart data + structure breakdown."""
    if not isinstance(user, dict):
        user = {}
    session = Opportunity_SessionLocal()
    try:
        s_dt, e_dt, granularity, period_label = _resolve_range(period, start, end)
        start_str = s_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_str = (e_dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        de = func.substr(Opportunity.created_at, 1, 10)
        view_all = user_has_permission(user, "page.opportunities_all")
        owner_user_id = None if view_all else user.get("user_id")
        sales_person_filter = sales_person if view_all else None
        sales_persons = [s.strip() for s in (sales_person_filter or "").split(",") if s.strip()]
        result_filter = result if result and result != "all" else None
        platforms = [s.strip() for s in (platform or "").split(",") if s.strip()]
        chassis_forms = [s.strip() for s in (chassis or "").split(",") if s.strip()]
        search_q = (search or "").strip()
        part_rows = None
        if part_filters:
            try:
                part_rows = json.loads(part_filters)
            except (json.JSONDecodeError, TypeError):
                part_rows = None

        base_conds = [
            Opportunity.status != "ai_office",
            Opportunity.status != "deleted",
        ]
        if owner_user_id:
            base_conds.append(Opportunity.owner_user_id == owner_user_id)
        if sales_persons:
            base_conds.append(Opportunity.sales_person.in_(sales_persons))
        if result_filter:
            base_conds.append(Opportunity.result == result_filter)
        if search_q:
            base_conds.append(
                Opportunity.customer_name.ilike(f"%{search_q}%") |
                Opportunity.sales_person.ilike(f"%{search_q}%") |
                Opportunity.opportunity_id.ilike(f"%{search_q}%")
            )

        slot_filter_ids = None
        if platforms or chassis_forms:
            candidate_ids = [
                r.opportunity_id
                for r in session.query(Opportunity.opportunity_id).filter(*base_conds).all()
            ]
            slot_map = _current_slot_map(session, candidate_ids)

            def _slot_match(oid, field, values):
                raw = str((slot_map.get(oid, {}) or {}).get(field) or "").strip()
                if "未分类" in values and raw == "":
                    return True
                named = [v for v in values if v != "未分类"]
                return raw in named

            if platforms:
                candidate_ids = [oid for oid in candidate_ids if _slot_match(oid, "platform_type", platforms)]
            if chassis_forms:
                candidate_ids = [oid for oid in candidate_ids if _slot_match(oid, "chassis_form", chassis_forms)]
            slot_filter_ids = candidate_ids

        # 配件筛选：匹配 unit=报价单（status=active），周期窗口落报价创建时间，
        # 命中商机集合与 slot 筛选在 opp_scope 里相与——与商机列表同一份 helper，口径一致。
        part_filter_ids = None
        if part_rows:
            from app.repository.opp_part_filter import match_opportunities_by_parts
            part_candidates = [
                r.opportunity_id
                for r in session.query(Opportunity.opportunity_id).filter(*base_conds).all()
            ]
            part_hits = match_opportunities_by_parts(
                session, part_candidates, part_rows,
                quote_start=start_str, quote_end=end_str,
            )
            part_filter_ids = list(part_hits.keys())

        # 配件筛选生效时时间窗口已落在报价创建时间，商机创建时间窗口不再叠加
        time_conds = [] if part_filter_ids is not None else [
            Opportunity.created_at >= start_str, Opportunity.created_at < end_str,
        ]

        _id_scopes = [s for s in (slot_filter_ids, part_filter_ids) if s is not None]

        def opp_scope(*conditions):
            conds = list(base_conds)
            if _id_scopes:
                inter = set.intersection(*(set(s) for s in _id_scopes))
                conds.append(Opportunity.opportunity_id.in_(inter or [""]))
            conds.extend(conditions)
            return conds

        # === KPIs ===
        total_opps = session.query(func.count(Opportunity.opportunity_id)).filter(*opp_scope(Opportunity.status != "deleted")).scalar() or 0
        # 总配置数 = 每个商机「当前版本」(status=active 中 version 最大) 的 config_count 求和，
        # 与商机列表口径一致，避免多版本报价单重复相加。
        _cfg_subq = _current_config_subquery(session, opp_scope())
        total_configs = session.query(func.sum(_cfg_subq.c.cc)).filter(_cfg_subq.c.rn == 1).scalar() or 0
        new_opps = session.query(func.count(Opportunity.opportunity_id)).filter(
            *opp_scope(Opportunity.status != "deleted", *time_conds)
        ).scalar() or 0
        # 周新增配置：统计本周新建商机「当前版本」的配置数（按商机创建时间），
        # 同一商机多版本报价单只取最新一版，避免重复相加。
        _cfg_subq_new = _current_config_subquery(session, opp_scope(
            Opportunity.status != "deleted",
            *time_conds,
        ))
        new_configs = session.query(func.sum(_cfg_subq_new.c.cc)).filter(_cfg_subq_new.c.rn == 1).scalar() or 0

        # === Chart 1: Opp total + platform trend（按天查，按 granularity 桶聚合）===
        opp_rows = session.query(de.label("date"), func.count(Opportunity.opportunity_id).label("count")).filter(
            *opp_scope(Opportunity.status != "deleted", *time_conds)
        ).group_by(de).order_by(de).all()
        period_opps = session.query(Opportunity.opportunity_id, de.label("date")).filter(
            *opp_scope(Opportunity.status != "deleted", *time_conds)
        ).all()
        period_slot_map = _current_slot_map(session, [r.opportunity_id for r in period_opps])

        opp_map = {}
        for r in opp_rows:
            bk = _bucket(str(r.date), granularity)
            opp_map[bk] = opp_map.get(bk, 0) + r.count
        plat_map = {}
        for r in period_opps:
            bk = _bucket(str(r.date), granularity)
            p = (period_slot_map.get(r.opportunity_id, {}).get("platform_type")) or "未分类"
            plat_map.setdefault(bk, {})[p] = plat_map.setdefault(bk, {}).get(p, 0) + 1

        all_dates = _fill_dates(s_dt, e_dt, granularity)
        all_plats = sorted(set(p for d in plat_map.values() for p in d.keys()))
        chart1 = {
            "total_series": [{"date": dk, "value": opp_map.get(dk, 0)} for dk in all_dates],
            "platform_series": {p: [{"date": dk, "value": plat_map.get(dk, {}).get(p, 0)} for dk in all_dates] for p in all_plats},
        }

        # === Chart 2: 机型趋势河流（ThemeRiver）— 月×机型(PN) 报价次数 ===
        # 删原"配置平台趋势"：平台维度已由 chart1 分线覆盖，这里换成细粒度机型(PN)维度。
        # PN 从 quotations.config_server_models(JSON: {CFG1: "ZSA240 V2"}) 抽取归一；
        # 一张报价单里出现多个 PN 时各计一次（机型出现即曝光）。
        pn_rows = session.query(
            de.label("date"), Quotation.config_server_models, Quotation.config_count,
        ).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(
            *opp_scope(Quotation.status != "deleted", Opportunity.status != "deleted",
            *time_conds,
            Quotation.config_server_models.isnot(None)),
        ).all()

        # 河流数据：{月份: {PN: 报价次数}}，沿用与 chart1 相同的 _bucket 分桶口径
        river_map: dict = {}
        pn_total: dict = {}  # PN → 累计次数，用于排序取主力机型
        for r in pn_rows:
            try:
                d = json.loads(r.config_server_models) if isinstance(r.config_server_models, str) else r.config_server_models
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(d, dict):
                continue
            bk = _bucket(str(r.date), granularity)
            pns = set()
            for v in d.values():
                pn = _normalize_pn(str(v))
                if pn:
                    pns.add(pn)
            for pn in pns:
                river_map.setdefault(bk, {})[pn] = river_map.setdefault(bk, {}).get(pn, 0) + 1
                pn_total[pn] = pn_total.get(pn, 0) + 1

        # 主力机型 Top8，其余归"其他"避免河流色带过多糊成一团
        TOP_PN = 8
        top_pns = [p for p, _ in sorted(pn_total.items(), key=lambda x: x[1], reverse=True)[:TOP_PN]]
        chart2_data = []  # ThemeRiver 扁平格式：[日期, 值, 机型名]
        for dk in all_dates:
            m = river_map.get(dk, {})
            other_sum = 0
            for pn, cnt in m.items():
                if pn in top_pns:
                    chart2_data.append([dk, cnt, pn])
                else:
                    other_sum += cnt
            if other_sum > 0:
                chart2_data.append([dk, other_sum, "其他机型"])
        chart2 = {"data": chart2_data, "models": top_pns + (["其他机型"] if len(pn_total) > TOP_PN else [])}

        # === Chart 3: Chassis stacked bar（按商机创建时间，与 KPI 口径一致）===
        _cfg_subq_c3 = _current_config_subquery(session, opp_scope(
            Opportunity.status != "deleted",
            *time_conds,
        ))
        quote_chassis_rows = session.query(
            _cfg_subq_c3.c.oid,
            _cfg_subq_c3.c.cc.label("count"),
            _cfg_subq_c3.c.date,
        ).filter(_cfg_subq_c3.c.rn == 1).all()

        ch_map = {}
        for r in quote_chassis_rows:
            bk = _bucket(str(r.date), granularity)
            # 拆分多值（逗号分隔），分别统计
            forms = ((period_slot_map.get(r.oid, {}).get("chassis_form")) or "未分类").split(',')
            for form in forms:
                c = form.strip() or "未分类"
                ch_map.setdefault(bk, {})[c] = ch_map.setdefault(bk, {}).get(c, 0) + r.count
        all_chassis = sorted(set(c for d in ch_map.values() for c in d.keys()))
        chart3 = {c: [{"date": dk, "value": ch_map.get(dk, {}).get(c, 0)} for dk in all_dates] for c in all_chassis}

        # === Structure ===
        plat_agg: dict = {}
        ch_agg: dict = {}
        for r in period_opps:
            slots = period_slot_map.get(r.opportunity_id, {})
            p = slots.get("platform_type") or "未分类"
            plat_agg[p] = plat_agg.get(p, 0) + 1
            forms = (slots.get("chassis_form") or "未分类").split(',')
            for form in forms:
                c = form.strip() or "未分类"
                ch_agg[c] = ch_agg.get(c, 0) + 1
        plat_struct = [{"name": k, "count": v} for k, v in plat_agg.items()]
        ch_struct = [{"name": k, "count": v} for k, v in ch_agg.items()]
        plat_struct.sort(key=lambda x: x["count"], reverse=True)
        ch_struct.sort(key=lambda x: x["count"], reverse=True)

        # === Sales Rank ===
        sales_rows = session.query(
            Opportunity.sales_person,
            func.count(Opportunity.opportunity_id).label("count"),
            func.sum(case((Opportunity.result == "won", 1), else_=0)).label("won"),
        ).filter(
            *opp_scope(Opportunity.status != "deleted", *time_conds)
        ).group_by(Opportunity.sales_person).order_by(func.count(Opportunity.opportunity_id).desc()).all()

        # 过滤空值，取 Top 5；won = 周期内成交（result=won）数，随周期/筛选变化
        sales_rank = [{"name": r.sales_person, "count": r.count, "won": int(r.won or 0)} for r in sales_rows if r.sales_person]
        top5 = sales_rank[:5]
        total_sales = sum(r["count"] for r in sales_rank)
        others_count = sum(r["count"] for r in sales_rank[5:])
        others = {"count": others_count, "people": len(sales_rank) - 5} if len(sales_rank) > 5 else None
        # Top5 之后的逐人明细，供前端「点击其他展开」用
        others_list = sales_rank[5:]

        # === Chart 5: 机型利润箱线（各 PN 的 profit_margin 分布）===
        # 不限本周期——利润样本本就稀疏（config_server_models 是新字段，集中在近 3 月），
        # 按周期切会把单机型切成个位数点，画不出箱。这里取全量，让箱体样本尽量厚。
        profit_rows = session.query(
            Quotation.config_server_models, Quotation.profit_margin,
        ).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(
            *opp_scope(Quotation.status != "deleted", Opportunity.status != "deleted",
            Quotation.config_server_models.isnot(None),
            Quotation.profit_margin.isnot(None)),
        ).all()

        pn_profits: dict = {}  # PN → [利润率...]
        for r in profit_rows:
            try:
                d = json.loads(r.config_server_models) if isinstance(r.config_server_models, str) else r.config_server_models
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(d, dict):
                continue
            for v in d.values():
                pn = _normalize_pn(str(v))
                if pn:
                    pn_profits.setdefault(pn, []).append(float(r.profit_margin or 0))

        # 样本 ≥4 才单独成箱（画得出四分位），其余折叠进"其他机型"聚合箱
        BOX_MIN_N = 4
        boxes = []
        other_vals: list = []
        for pn, vals in pn_profits.items():
            if len(vals) >= BOX_MIN_N:
                q = _pct_quartiles(vals)
                if q:
                    boxes.append({"name": pn, **q})
            else:
                other_vals.extend(vals)
        # 按中位数降序：高利润机型居左，一眼看到"谁赚得多"
        boxes.sort(key=lambda x: x["median"], reverse=True)
        other_box = _pct_quartiles(other_vals) if other_vals else None
        if other_box:
            boxes.append({"name": "其他机型", **other_box})
        chart5 = {"boxes": boxes}

        return {
            "period_label": period_label,
            "kpi": {"total_opportunities": total_opps, "total_configs": total_configs,
                    "new_opportunities": new_opps, "new_configs": new_configs},
            "charts": {"chart1": chart1, "chart2": chart2, "chart3": chart3, "chart5": chart5},
            "structure": {"platforms": plat_struct, "chassis": ch_struct},
            "sales_rank": {"top": top5, "others": others, "others_list": others_list, "total": total_sales},
            "dates": all_dates,
        }
    finally:
        session.close()


def get_highlights(limit: int = 10) -> list:
    """近期重点商机：近半年内按 purchase_qty 降序取 Top `limit`（供方案助手查数工具用）。"""
    today = datetime.now()
    half_start_dt = (today - timedelta(days=180)).strftime("%Y-%m-%d") + " 00:00:00"
    session = Opportunity_SessionLocal()
    try:
        _cfg_subq_hl = _current_config_subquery(session, [
            Opportunity.status != "deleted",
            Opportunity.created_at >= half_start_dt,
        ])
        rows = session.query(
            Opportunity.opportunity_id, Opportunity.customer_name, Opportunity.sales_person, Opportunity.result,
            func.coalesce(func.max(_cfg_subq_hl.c.cc), 0).label("config_count"),
        ).outerjoin(
            _cfg_subq_hl,
            (_cfg_subq_hl.c.oid == Opportunity.opportunity_id) & (_cfg_subq_hl.c.rn == 1),
        ).filter(
            Opportunity.status != "deleted",
            Opportunity.created_at >= half_start_dt,
        ).group_by(
            Opportunity.opportunity_id, Opportunity.customer_name,
            Opportunity.sales_person, Opportunity.result,
        ).all()
        slot_map = _current_slot_map(session, [r.opportunity_id for r in rows])
        rows.sort(key=lambda r: int((slot_map.get(r.opportunity_id, {}).get("purchase_qty")) or 0), reverse=True)
        rows = rows[:limit]
        return [{
            "customer_name": r.customer_name or "",
            "sales_person": r.sales_person or "",
            "platform_type": (slot_map.get(r.opportunity_id, {}).get("platform_type")) or "",
            "chassis_form": (slot_map.get(r.opportunity_id, {}).get("chassis_form")) or "",
            "purchase_qty": (slot_map.get(r.opportunity_id, {}).get("purchase_qty")) or 0,
            "config_count": int(r.config_count or 0),
            "result": r.result or "",
        } for r in rows]
    finally:
        session.close()
