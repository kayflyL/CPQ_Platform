"""Dashboard statistics API."""
from datetime import datetime, timedelta
from fastapi import APIRouter
from sqlalchemy import func, cast, Date
from app.models.opportunity import Opportunity
from app.models.quotation import Quotation
from app.models.base import Opportunity_SessionLocal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def get_week_start() -> str:
    """Get the start of current week (Monday 00:00:00)."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M:%S")


@router.get("/stats")
def get_dashboard_stats():
    """Get dashboard statistics: total opportunities, total configs, this week's new opportunities/configs."""
    session = Opportunity_SessionLocal()
    try:
        week_start = get_week_start()
        
        # Total opportunities
        total_opportunities = session.query(func.count(Opportunity.opportunity_id)).filter(
            Opportunity.status != "deleted"
        ).scalar() or 0
        
        # Total configs (count of quotations)
        total_configs = session.query(func.count(Quotation.quotation_id)).filter(
            Quotation.status != "deleted"
        ).scalar() or 0
        
        # This week's new opportunities
        new_opportunities_this_week = session.query(func.count(Opportunity.opportunity_id)).filter(
            Opportunity.status != "deleted",
            Opportunity.created_at >= week_start
        ).scalar() or 0
        
        # This week's new configs
        new_configs_this_week = session.query(func.count(Quotation.quotation_id)).filter(
            Quotation.status != "deleted",
            Quotation.created_at >= week_start
        ).scalar() or 0
        
        return {
            "total_opportunities": total_opportunities,
            "total_configs": total_configs,
            "new_opportunities_this_week": new_opportunities_this_week,
            "new_configs_this_week": new_configs_this_week,
        }
    finally:
        session.close()


@router.get("/trend")
def get_dashboard_trend(days: int = 30):
    """Get daily opportunity/config creation trend for the last N days."""
    session = Opportunity_SessionLocal()
    try:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        
        # Daily opportunity counts - created_at is String, extract date part
        opp_trend = session.query(
            func.substr(Opportunity.created_at, 1, 10).label("date"),
            func.count(Opportunity.opportunity_id).label("count")
        ).filter(
            Opportunity.status != "deleted",
            Opportunity.created_at >= cutoff
        ).group_by("date").order_by("date").all()
        
        # Daily config counts - created_at is String, extract date part
        config_trend = session.query(
            func.substr(Quotation.created_at, 1, 10).label("date"),
            func.count(Quotation.quotation_id).label("count")
        ).filter(
            Quotation.status != "deleted",
            Quotation.created_at >= cutoff
        ).group_by("date").order_by("date").all()
        
        # Convert to dict format
        opp_map = {str(row.date): row.count for row in opp_trend}
        config_map = {str(row.date): row.count for row in config_trend}
        
        # Fill in all dates (even zeros)
        result = []
        for i in range(days):
            date = (datetime.now() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            result.append({
                "date": date,
                "opportunities": opp_map.get(date, 0),
                "configs": config_map.get(date, 0)
            })
        
        return result
    finally:
        session.close()
