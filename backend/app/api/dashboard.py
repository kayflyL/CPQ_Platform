"""Dashboard statistics API — unified summary + detail endpoints."""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Query
from sqlalchemy import func
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
        deq = func.substr(Quotation.created_at, 1, 10)

        # === KPIs ===
        total_opps = session.query(func.count(Opportunity.opportunity_id)).filter(Opportunity.status != "deleted").scalar() or 0
        # 总配置数 = 所有报价单的 config_count 求和（不是报价单条数）
        total_configs = session.query(func.sum(Quotation.config_count)).filter(Quotation.status != "deleted").scalar() or 0
        new_opps = session.query(func.count(Opportunity.opportunity_id)).filter(
            Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
        ).scalar() or 0
        new_configs = session.query(func.sum(Quotation.config_count)).filter(
            Quotation.status != "deleted", Quotation.created_at >= start_str, Quotation.created_at < end_str
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

        # === Chart 2: Config platform trend ===
        cfg_plat_rows = session.query(deq.label("date"), Opportunity.platform_type, func.count(Quotation.quotation_id).label("count")).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(Quotation.status != "deleted", Quotation.created_at >= start_str, Quotation.created_at < end_str
        ).group_by(deq, Opportunity.platform_type).order_by(deq).all()

        cfg_plat_map = {}
        for r in cfg_plat_rows:
            bk = _bucket(str(r.date), granularity)
            p = r.platform_type or "未分类"
            cfg_plat_map.setdefault(bk, {})[p] = cfg_plat_map.setdefault(bk, {}).get(p, 0) + r.count
        all_cfg_plats = sorted(set(p for d in cfg_plat_map.values() for p in d.keys()))
        chart2 = {p: [{"date": dk, "value": cfg_plat_map.get(dk, {}).get(p, 0)} for dk in all_dates] for p in all_cfg_plats}

        # === Chart 3: Chassis stacked bar ===
        ch_rows = session.query(deq.label("date"), Opportunity.chassis_form, func.count(Quotation.quotation_id).label("count")).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(Quotation.status != "deleted", Quotation.created_at >= start_str, Quotation.created_at < end_str
        ).group_by(deq, Opportunity.chassis_form).order_by(deq).all()

        ch_map = {}
        for r in ch_rows:
            bk = _bucket(str(r.date), granularity)
            c = r.chassis_form or "未分类"
            ch_map.setdefault(bk, {})[c] = ch_map.setdefault(bk, {}).get(c, 0) + r.count
        all_chassis = sorted(set(c for d in ch_map.values() for c in d.keys()))
        chart3 = {c: [{"date": dk, "value": ch_map.get(dk, {}).get(c, 0)} for dk in all_dates] for c in all_chassis}

        # === Structure ===
        plat_struct = [{"name": r.platform_type or "未分类", "count": r.count} for r in
            session.query(Opportunity.platform_type, func.count(Opportunity.opportunity_id).label("count")).filter(
                Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
            ).group_by(Opportunity.platform_type).all()]
        ch_struct = [{"name": r.chassis_form or "未分类", "count": r.count} for r in
            session.query(Opportunity.chassis_form, func.count(Opportunity.opportunity_id).label("count")).filter(
                Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
            ).group_by(Opportunity.chassis_form).all()]
        plat_struct.sort(key=lambda x: x["count"], reverse=True)
        ch_struct.sort(key=lambda x: x["count"], reverse=True)

        return {
            "period_label": period_label,
            "kpi": {"total_opportunities": total_opps, "total_configs": total_configs,
                    "new_opportunities": new_opps, "new_configs": new_configs},
            "charts": {"chart1": chart1, "chart2": chart2, "chart3": chart3},
            "structure": {"platforms": plat_struct, "chassis": ch_struct},
            "dates": all_dates,
        }
    finally:
        session.close()
