"""Dashboard statistics API."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Query
from sqlalchemy import func, case
from app.models.opportunity import Opportunity
from app.models.quotation import Quotation
from app.models.base import Opportunity_SessionLocal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


PERIODS = {
    "week": lambda: (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
    "month": lambda: datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    "year": lambda: datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
}


def _period_start(period: str) -> datetime:
    return PERIODS.get(period, PERIODS["week"])()


def _period_label(period: str) -> str:
    now = datetime.now()
    if period == "week":
        start = _period_start(period)
        return f"{start.strftime('%Y.%m.%d')} ~ {now.strftime('%m.%d')}"
    if period == "month":
        return f"{now.strftime('%Y.%m')}"
    return f"{now.strftime('%Y')}"


def _date_range(period: str):
    """Return (start_str, format_str) for SQL date filtering."""
    start = _period_start(period)
    start_str = start.strftime("%Y-%m-%d %H:%M:%S")
    if period == "week":
        # Daily granularity for week
        return start_str, "%Y-%m-%d"
    if period == "month":
        return start_str, "%Y-%m-%d"
    # year: group by month
    return start_str, "%Y-%m"


@router.get("/stats")
def get_dashboard_stats(period: str = Query(default="week")):
    """Get dashboard KPIs: total opportunities, total configs, period new opps/configs, pending pricing."""
    session = Opportunity_SessionLocal()
    try:
        start_str = _period_start(period).strftime("%Y-%m-%d %H:%M:%S")

        total_opps = session.query(func.count(Opportunity.opportunity_id)).filter(
            Opportunity.status != "deleted"
        ).scalar() or 0

        total_configs = session.query(func.count(Quotation.quotation_id)).filter(
            Quotation.status != "deleted"
        ).scalar() or 0

        new_opps = session.query(func.count(Opportunity.opportunity_id)).filter(
            Opportunity.status != "deleted",
            Opportunity.created_at >= start_str
        ).scalar() or 0

        new_configs = session.query(func.count(Quotation.quotation_id)).filter(
            Quotation.status != "deleted",
            Quotation.created_at >= start_str
        ).scalar() or 0

        pending_pricing = 0
        all_opps = session.query(Opportunity).filter(
            Opportunity.status != "deleted"
        ).all()
        for o in all_opps:
            if o.extra_fields and "核价" in o.extra_fields:
                pending_pricing += 1

        return {
            "period_label": _period_label(period),
            "total_opportunities": total_opps,
            "total_configs": total_configs,
            "new_opportunities": new_opps,
            "new_configs": new_configs,
            "pending_pricing": pending_pricing,
        }
    finally:
        session.close()


@router.get("/trend")
def get_dashboard_trend(period: str = Query(default="week")):
    """Get daily/monthly opportunity trend for the selected period."""
    session = Opportunity_SessionLocal()
    try:
        start_str, fmt = _date_range(period)

        opp_trend = session.query(
            func.to_char(func.to_date(func.substr(Opportunity.created_at, 1, 10), 'YYYY-MM-DD'), fmt).label("date"),
            func.count(Opportunity.opportunity_id).label("count")
        ).filter(
            Opportunity.status != "deleted",
            Opportunity.created_at >= start_str
        ).group_by("date").order_by("date").all()

        cfg_trend = session.query(
            func.to_char(func.to_date(func.substr(Quotation.created_at, 1, 10), 'YYYY-MM-DD'), fmt).label("date"),
            func.count(Quotation.quotation_id).label("count")
        ).filter(
            Quotation.status != "deleted",
            Quotation.created_at >= start_str
        ).group_by("date").order_by("date").all()

        opp_map = {str(row.date): row.count for row in opp_trend}
        cfg_map = {str(row.date): row.count for row in cfg_trend}

        start = _period_start(period)
        now = datetime.now()
        result = []
        current = start
        while current <= now:
            if period == "year":
                date_key = current.strftime("%Y-%m")
            else:
                date_key = current.strftime("%Y-%m-%d")
            result.append({
                "date": date_key,
                "opportunities": opp_map.get(date_key, 0),
                "configs": cfg_map.get(date_key, 0)
            })
            if period == "year":
                if current.month == 12:
                    break
                current = current.replace(month=current.month + 1)
            else:
                current += timedelta(days=1)

        return result
    finally:
        session.close()


@router.get("/platform-trend")
def get_platform_trend(period: str = Query(default="week")):
    """Get platform-specific config count trend over time."""
    session = Opportunity_SessionLocal()
    try:
        start_str, fmt = _date_range(period)

        rows = session.query(
            func.to_char(func.to_date(func.substr(Quotation.created_at, 1, 10), 'YYYY-MM-DD'), fmt).label("date"),
            Opportunity.platform_type,
            func.count(Quotation.quotation_id).label("count")
        ).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(
            Quotation.status != "deleted",
            Quotation.created_at >= start_str
        ).group_by("date", Opportunity.platform_type).order_by("date").all()

        # Group by date, then by platform
        platform_map = {}
        for row in rows:
            date_key = str(row.date)
            plat = row.platform_type or "未分类"
            if date_key not in platform_map:
                platform_map[date_key] = {}
            platform_map[date_key][plat] = row.count

        start = _period_start(period)
        now = datetime.now()
        all_dates = []
        current = start
        while current <= now:
            if period == "year":
                date_key = current.strftime("%Y-%m")
            else:
                date_key = current.strftime("%Y-%m-%d")
            all_dates.append(date_key)
            if period == "year":
                if current.month == 12:
                    break
                current = current.replace(month=current.month + 1)
            else:
                current += timedelta(days=1)

        all_platforms = sorted(set(p for d in platform_map.values() for p in d.keys()))

        result = []
        for date_key in all_dates:
            entry = {"date": date_key}
            for plat in all_platforms:
                entry[plat] = platform_map.get(date_key, {}).get(plat, 0)
            result.append(entry)

        return {"dates": all_dates, "platforms": all_platforms, "data": result}
    finally:
        session.close()


@router.get("/chassis-distribution")
def get_chassis_distribution(period: str = Query(default="week")):
    """Get chassis form distribution over time (stacked bar)."""
    session = Opportunity_SessionLocal()
    try:
        start_str, fmt = _date_range(period)

        rows = session.query(
            func.to_char(func.to_date(func.substr(Quotation.created_at, 1, 10), 'YYYY-MM-DD'), fmt).label("date"),
            Opportunity.chassis_form,
            func.count(Quotation.quotation_id).label("count")
        ).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(
            Quotation.status != "deleted",
            Quotation.created_at >= start_str
        ).group_by("date", Opportunity.chassis_form).order_by("date").all()

        chassis_map = {}
        for row in rows:
            date_key = str(row.date)
            ch = row.chassis_form or "未分类"
            if date_key not in chassis_map:
                chassis_map[date_key] = {}
            chassis_map[date_key][ch] = row.count

        start = _period_start(period)
        now = datetime.now()
        all_dates = []
        current = start
        while current <= now:
            if period == "year":
                date_key = current.strftime("%Y-%m")
            else:
                date_key = current.strftime("%Y-%m-%d")
            all_dates.append(date_key)
            if period == "year":
                if current.month == 12:
                    break
                current = current.replace(month=current.month + 1)
            else:
                current += timedelta(days=1)

        all_chassis = sorted(set(c for d in chassis_map.values() for c in d.keys()))

        result = []
        for date_key in all_dates:
            entry = {"date": date_key}
            for ch in all_chassis:
                entry[ch] = chassis_map.get(date_key, {}).get(ch, 0)
            result.append(entry)

        return {"dates": all_dates, "chassis": all_chassis, "data": result}
    finally:
        session.close()


@router.get("/structure")
def get_structure(period: str = Query(default="week")):
    """Get current period platform and chassis breakdown (for sidebar mini bars)."""
    session = Opportunity_SessionLocal()
    try:
        start_str = _period_start(period).strftime("%Y-%m-%d %H:%M:%S")

        platform_rows = session.query(
            Opportunity.platform_type,
            func.count(Opportunity.opportunity_id).label("count")
        ).filter(
            Opportunity.status != "deleted",
            Opportunity.created_at >= start_str
        ).group_by(Opportunity.platform_type).all()

        chassis_rows = session.query(
            Opportunity.chassis_form,
            func.count(Opportunity.opportunity_id).label("count")
        ).filter(
            Opportunity.status != "deleted",
            Opportunity.created_at >= start_str
        ).group_by(Opportunity.chassis_form).all()

        platforms = [{"name": r.platform_type or "未分类", "count": r.count} for r in platform_rows]
        chassis = [{"name": r.chassis_form or "未分类", "count": r.count} for r in chassis_rows]

        platforms.sort(key=lambda x: x["count"], reverse=True)
        chassis.sort(key=lambda x: x["count"], reverse=True)

        return {"platforms": platforms, "chassis": chassis}
    finally:
        session.close()
