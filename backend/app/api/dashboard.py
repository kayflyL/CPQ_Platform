"""Dashboard statistics API — unified summary + detail endpoints."""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Query
from sqlalchemy import func
import json

from app.models.opportunity import Opportunity
from app.models.quotation import Quotation
from app.models.base import Opportunity_SessionLocal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

PLAT_COLORS = {"Polaris": "#26E2D1", "Orion": "#FA8C16", "Intel": "#8A94A8", "其他": "#8A94A8", "工作站": "#A855F7"}
CHAS_COLORS = {"2U": "#26E2D1", "4U": "#FA8C16", "5U": "#A855F7", "4.5U": "#1890FF", "工作站": "#A855F7", "2U/4U": "#8A94A8", "8U": "#8A94A8"}

PERIODS = {
    "week": lambda: (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
    "month": lambda: datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    "year": lambda: datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
}


def _resolve_range(period: str, start: Optional[str], end: Optional[str]):
    """解析时间区间 → (start_dt, end_dt, granularity, label)。

    给定 start/end(YYYY-MM-DD) 时按自定义区间；否则按 period 枚举(week/month/year)。
    granularity: 短区间(≤10天)按天，月维度区间(11~90天)按周，长区间(>90天或跨年)按月。
    end_dt 为闭区间当天 00:00。
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    if start and end:
        s = datetime.strptime(start, "%Y-%m-%d")
        e = datetime.strptime(end, "%Y-%m-%d")
        span = (e - s).days
        if span > 90 or s.year != e.year:
            granularity = "month"
        elif span > 10:
            granularity = "week"
        else:
            granularity = "day"
        if s.year == e.year:
            label = f"{s.strftime('%Y.%m.%d')} ~ {e.strftime('%m.%d')}"
        else:
            label = f"{s.strftime('%Y.%m.%d')} ~ {e.strftime('%Y.%m.%d')}"
        return s, e, granularity, label
    if period == "year":
        s = PERIODS["year"]()
        granularity, label = "month", today.strftime("%Y")
    elif period == "month":
        s = PERIODS["month"]()
        granularity, label = "week", today.strftime("%Y.%m")
    else:  # week
        s = PERIODS["week"]()
        granularity = "day"
        label = f"{s.strftime('%Y.%m.%d')} ~ {today.strftime('%m.%d')}"
    return s, today, granularity, label


def _bucket(date_str: str, granularity: str) -> str:
    """把按天查询的 'YYYY-MM-DD' 归到显示桶：day=当天，week=所在周一，month=月首。"""
    if granularity == "day":
        return date_str
    d = datetime.strptime(date_str, "%Y-%m-%d")
    if granularity == "week":
        return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
    return d.strftime("%Y-%m")


def _fill_dates(start_dt: datetime, end_dt: datetime, granularity: str):
    dates = []
    if granularity == "month":
        c = start_dt.replace(day=1)
        end_m = end_dt.replace(day=1)
        while c <= end_m:
            dates.append(c.strftime("%Y-%m"))
            c = c.replace(year=c.year + 1, month=1) if c.month == 12 else c.replace(month=c.month + 1)
    elif granularity == "week":
        c = start_dt - timedelta(days=start_dt.weekday())
        last = end_dt - timedelta(days=end_dt.weekday())
        while c <= last:
            dates.append(c.strftime("%Y-%m-%d"))
            c += timedelta(days=7)
    else:
        c = start_dt
        while c <= end_dt:
            dates.append(c.strftime("%Y-%m-%d"))
            c += timedelta(days=1)
    return dates


@router.get("/summary")
def get_dashboard_summary(
    period: str = Query(default="week"),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
):
    """Unified endpoint: KPIs + chart data + structure breakdown."""
    session = Opportunity_SessionLocal()
    try:
        s_dt, e_dt, granularity, period_label = _resolve_range(period, start, end)
        start_str = s_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_str = (e_dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        de = func.substr(Opportunity.created_at, 1, 10)

        # === KPIs ===
        total_opps = session.query(func.count(Opportunity.opportunity_id)).filter(Opportunity.status != "deleted").scalar() or 0
        # 总配置数 = 所有报价单的 config_count 求和（不是报价单条数）
        total_configs = session.query(func.sum(Quotation.config_count)).filter(Quotation.status != "deleted").scalar() or 0
        new_opps = session.query(func.count(Opportunity.opportunity_id)).filter(
            Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).scalar() or 0
        # 周新增配置：统计本周新建商机下的配置数（按商机创建时间，非报价单创建时间）
        new_configs = session.query(func.sum(Quotation.config_count)).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(
            Opportunity.status != "deleted", Quotation.status != "deleted",
            Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).scalar() or 0

        # === Chart 1: Opp total + platform trend（按天查，按 granularity 桶聚合）===
        opp_rows = session.query(de.label("date"), func.count(Opportunity.opportunity_id).label("count")).filter(
            Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).group_by(de).order_by(de).all()
        plat_rows = session.query(de.label("date"), Opportunity.platform_type, func.count(Opportunity.opportunity_id).label("count")).filter(
            Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).group_by(de, Opportunity.platform_type).order_by(de).all()

        opp_map = {}
        for r in opp_rows:
            bk = _bucket(str(r.date), granularity)
            opp_map[bk] = opp_map.get(bk, 0) + r.count
        plat_map = {}
        for r in plat_rows:
            bk = _bucket(str(r.date), granularity)
            p = r.platform_type or "未分类"
            plat_map.setdefault(bk, {})[p] = plat_map.setdefault(bk, {}).get(p, 0) + r.count

        all_dates = _fill_dates(s_dt, e_dt, granularity)
        all_plats = sorted(set(p for d in plat_map.values() for p in d.keys()))
        chart1 = {
            "total_series": [{"date": dk, "value": opp_map.get(dk, 0)} for dk in all_dates],
            "platform_series": {p: [{"date": dk, "value": plat_map.get(dk, {}).get(p, 0)} for dk in all_dates] for p in all_plats},
        }

        # === Chart 2: Config platform trend（按商机创建时间，与 KPI 口径一致）===
        cfg_plat_rows = session.query(de.label("date"), Opportunity.platform_type, func.sum(Quotation.config_count).label("count")).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(Quotation.status != "deleted", Opportunity.status != "deleted",
                  Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).group_by(de, Opportunity.platform_type).order_by(de).all()

        cfg_plat_map = {}
        for r in cfg_plat_rows:
            bk = _bucket(str(r.date), granularity)
            p = r.platform_type or "未分类"
            cfg_plat_map.setdefault(bk, {})[p] = cfg_plat_map.setdefault(bk, {}).get(p, 0) + r.count
        all_cfg_plats = sorted(set(p for d in cfg_plat_map.values() for p in d.keys()))
        chart2 = {p: [{"date": dk, "value": cfg_plat_map.get(dk, {}).get(p, 0)} for dk in all_dates] for p in all_cfg_plats}

        # === Chart 3: Chassis stacked bar（按商机创建时间，与 KPI 口径一致）===
        ch_rows = session.query(de.label("date"), Opportunity.chassis_form, func.sum(Quotation.config_count).label("count")).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(Quotation.status != "deleted", Opportunity.status != "deleted",
                  Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).group_by(de, Opportunity.chassis_form).order_by(de).all()

        ch_map = {}
        for r in ch_rows:
            bk = _bucket(str(r.date), granularity)
            # 拆分多值（逗号分隔），分别统计
            forms = (r.chassis_form or "未分类").split(',')
            for form in forms:
                c = form.strip() or "未分类"
                ch_map.setdefault(bk, {})[c] = ch_map.setdefault(bk, {}).get(c, 0) + r.count
        all_chassis = sorted(set(c for d in ch_map.values() for c in d.keys()))
        chart3 = {c: [{"date": dk, "value": ch_map.get(dk, {}).get(c, 0)} for dk in all_dates] for c in all_chassis}

        # === Structure ===
        plat_struct = [{"name": r.platform_type or "未分类", "count": r.count} for r in
            session.query(Opportunity.platform_type, func.count(Opportunity.opportunity_id).label("count")).filter(
                Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
            ).group_by(Opportunity.platform_type).all()]
        # 机箱形态结构：拆分多值后聚合统计
        ch_raw = session.query(Opportunity.chassis_form, func.count(Opportunity.opportunity_id).label("count")).filter(
            Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).group_by(Opportunity.chassis_form).all()
        ch_agg: dict = {}
        for r in ch_raw:
            forms = (r.chassis_form or "未分类").split(',')
            for form in forms:
                c = form.strip() or "未分类"
                ch_agg[c] = ch_agg.get(c, 0) + r.count
        ch_struct = [{"name": k, "count": v} for k, v in ch_agg.items()]
        plat_struct.sort(key=lambda x: x["count"], reverse=True)
        ch_struct.sort(key=lambda x: x["count"], reverse=True)

        # === Sales Rank ===
        sales_rows = session.query(
            Opportunity.sales_person, func.count(Opportunity.opportunity_id).label("count")
        ).filter(
            Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).group_by(Opportunity.sales_person).order_by(func.count(Opportunity.opportunity_id).desc()).all()

        # 过滤空值，取 Top 5
        sales_rank = [{"name": r.sales_person, "count": r.count} for r in sales_rows if r.sales_person]
        top5 = sales_rank[:5]
        total_sales = sum(r["count"] for r in sales_rank)
        others_count = sum(r["count"] for r in sales_rank[5:])
        others = {"count": others_count, "people": len(sales_rank) - 5} if len(sales_rank) > 5 else None

        return {
            "period_label": period_label,
            "kpi": {"total_opportunities": total_opps, "total_configs": total_configs,
                    "new_opportunities": new_opps, "new_configs": new_configs},
            "charts": {"chart1": chart1, "chart2": chart2, "chart3": chart3},
            "structure": {"platforms": plat_struct, "chassis": ch_struct},
            "sales_rank": {"top": top5, "others": others, "total": total_sales},
            "dates": all_dates,
        }
    finally:
        session.close()


@router.get("/trend-overview")
def get_trend_overview(limit: int = Query(default=10, ge=5, le=20)):
    """趋势分析富数据:周 / 月 / 近半年三周期聚合 + 近期重点商机明细。

    供方案助手「分析本期趋势」快捷指令注入,一次取齐避免前端多次请求。
    近半年走 start/end(_resolve_range 无 half_year 枚举)→ 自动按月分桶,可算逐月环比。
    重点商机近半年内按 purchase_qty 降序取 Top `limit`。
    """
    today = datetime.now()
    half_start = (today - timedelta(days=180)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")

    # 三周期聚合(复用 summary)
    # 注意：显式传 start/end=None 覆盖路由签名里的 Query 默认对象，否则 Query 对象
    # 会被 _resolve_range 当成非空字符串，strptime 报 TypeError（路由函数不能当普通函数裸调）。
    week_summary = get_dashboard_summary(period="week", start=None, end=None)
    month_summary = get_dashboard_summary(period="month", start=None, end=None)
    half_summary = get_dashboard_summary(period="year", start=half_start, end=today_str)

    # 近期重点商机:近半年内,按 purchase_qty 降序(coalesce 把 NULL 当 0 排后),Top limit
    half_start_dt = half_start + " 00:00:00"
    session = Opportunity_SessionLocal()
    try:
        rows = session.query(
            Opportunity.customer_name, Opportunity.sales_person, Opportunity.platform_type,
            Opportunity.chassis_form, Opportunity.purchase_qty, Opportunity.result,
            func.coalesce(func.sum(Quotation.config_count), 0).label("config_count"),
        ).outerjoin(
            Quotation,
            (Quotation.opportunity_id == Opportunity.opportunity_id) & (Quotation.status != "deleted"),
        ).filter(
            Opportunity.status != "deleted",
            Opportunity.created_at >= half_start_dt,
        ).group_by(Opportunity.opportunity_id).order_by(
            func.coalesce(Opportunity.purchase_qty, 0).desc()
        ).limit(limit).all()
        highlights = [{
            "customer_name": r.customer_name or "",
            "sales_person": r.sales_person or "",
            "platform_type": r.platform_type or "",
            "chassis_form": r.chassis_form or "",
            "purchase_qty": r.purchase_qty or 0,
            "config_count": int(r.config_count or 0),
            "result": r.result or "",
        } for r in rows]
    finally:
        session.close()

    return {
        "week": week_summary,
        "month": month_summary,
        "half_year": half_summary,
        "highlights": highlights,
    }
