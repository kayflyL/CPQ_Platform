# -*- coding: utf-8 -*-
"""商机统计口径服务：AI 报告数字的确定性来源（2026-09-16）。

趋势报告曾让大脑手写 SQL 取数——平台/机箱口径、配置数口径、本周/本月窗口
每轮都在随机漂移。定调：报告里的全部统计数字来自本模块（与商机线索页/驾驶舱
共用 app.repository.opp_caliber_repo 的同一份口径实现），大脑只做分析叙述。

时间分桶工具（resolve_range/bucket/fill_dates）自 api/dashboard 下沉至此，
dashboard 反向引用（api→service 层次），保证「同一段代码」不是复制品。
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import case, func

from app.models.base import Opportunity_SessionLocal
from app.models.opportunity import Opportunity
from app.repository.opp_caliber_repo import current_config_subquery, current_slot_map

PERIODS = {
    "week": lambda: (datetime.now() - timedelta(days=datetime.now().weekday())).replace(hour=0, minute=0, second=0, microsecond=0),
    "month": lambda: datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0),
    "year": lambda: datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0),
}


def resolve_range(period: str, start: Optional[str], end: Optional[str]):
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
    elif period == "all":
        # 配件筛选默认不限时间：图表横轴取近 3 年按月分桶（KPI 不受窗口影响）
        s = today - timedelta(days=365 * 3)
        granularity, label = "month", "全部时间"
    else:  # week
        s = PERIODS["week"]()
        granularity = "day"
        label = f"{s.strftime('%Y.%m.%d')} ~ {today.strftime('%m.%d')}"
    return s, today, granularity, label


def bucket(date_str: str, granularity: str) -> str:
    """把按天查询的 'YYYY-MM-DD' 归到显示桶：day=当天，week=所在周一，month=月首。"""
    if granularity == "day":
        return date_str
    d = datetime.strptime(date_str, "%Y-%m-%d")
    if granularity == "week":
        return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
    return d.strftime("%Y-%m")


def fill_dates(start_dt: datetime, end_dt: datetime, granularity: str):
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


def _window_kpis(session, start_str, end_str):
    """窗口内新增商机/配置数（口径=驾驶舱 KPI：每商机当前版本 config_count）。"""
    conds = [
        Opportunity.status != "ai_office",
        Opportunity.status != "deleted",
        Opportunity.created_at >= start_str,
        Opportunity.created_at < end_str,
    ]
    new_opps = session.query(func.count(Opportunity.opportunity_id)).filter(*conds).scalar() or 0
    subq = current_config_subquery(session, conds)
    new_configs = session.query(func.sum(subq.c.cc)).filter(subq.c.rn == 1).scalar() or 0
    return int(new_opps), int(new_configs)


def _dist(session, start_str, end_str, field: str, split_comma: bool):
    """窗口内按 slots 字段的商机数分布；空值归「未分类」，逗号多值拆开各计一次。"""
    rows = session.query(Opportunity.opportunity_id, func.substr(Opportunity.created_at, 1, 10)).filter(
        Opportunity.status != "ai_office",
        Opportunity.status != "deleted",
        Opportunity.created_at >= start_str,
        Opportunity.created_at < end_str,
    ).all()
    slot_map = current_slot_map(session, [r[0] for r in rows])
    agg: dict = {}
    for oid, _date in rows:
        raw = str((slot_map.get(oid, {}) or {}).get(field) or "").strip()
        values = [v.strip() for v in raw.split(",")] if (split_comma and raw) else ([raw] if raw else [])
        for v in values or ["未分类"]:
            agg[v or "未分类"] = agg.get(v or "未分类", 0) + 1
    return dict(sorted(agg.items(), key=lambda x: x[1], reverse=True))


def _recent_window(session, s_dt, e_dt, label):
    start_str = s_dt.strftime("%Y-%m-%d %H:%M:%S")
    end_str = (e_dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    new_opps, new_configs = _window_kpis(session, start_str, end_str)
    return {
        "label": label,
        "new_opps": new_opps,
        "new_configs": new_configs,
        "platforms": _dist(session, start_str, end_str, "platform_type", False),
        "chassis": _dist(session, start_str, end_str, "chassis_form", True),
    }


def compute_opp_stats(start: str, end: str) -> dict:
    """窗口商机统计：与商机线索页同口径的确定性数字，报告统计唯一来源。

    start/end = YYYY-MM-DD（= 报告契约的数据范围）。返回窗口 KPI、逐桶序列
    （含逐桶平台分布）、平台/机箱分布、销售榜，以及本周/本月小窗（周数据/月数据
    两节直接取用，不需要再手写窗口 SQL）。
    """
    try:
        s_dt, e_dt, granularity, label = resolve_range("week", start, end)
    except ValueError:
        return {"ok": False, "error": "start/end 需为 YYYY-MM-DD 日期"}
    session = Opportunity_SessionLocal()
    try:
        start_str = s_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_str = (e_dt + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

        base_conds = [Opportunity.status != "ai_office", Opportunity.status != "deleted"]
        total_opps = session.query(func.count(Opportunity.opportunity_id)).filter(
            *(base_conds + [Opportunity.status != "deleted"])).scalar() or 0
        _cfg_subq = current_config_subquery(session, base_conds)
        total_configs = session.query(func.sum(_cfg_subq.c.cc)).filter(_cfg_subq.c.rn == 1).scalar() or 0
        new_opps, new_configs = _window_kpis(session, start_str, end_str)

        rows = session.query(
            Opportunity.opportunity_id, func.substr(Opportunity.created_at, 1, 10).label("date"),
        ).filter(
            *(base_conds + [Opportunity.created_at >= start_str, Opportunity.created_at < end_str])
        ).all()
        slot_map = current_slot_map(session, [r.opportunity_id for r in rows])

        _cfg_subq_win = current_config_subquery(session, base_conds + [
            Opportunity.created_at >= start_str, Opportunity.created_at < end_str])
        cfg_rows = session.query(
            _cfg_subq_win.c.oid, _cfg_subq_win.c.cc, _cfg_subq_win.c.date,
        ).filter(_cfg_subq_win.c.rn == 1).all()
        cfg_by_bucket: dict = {}
        for r in cfg_rows:
            cfg_by_bucket[bucket(str(r.date), granularity)] = cfg_by_bucket.get(bucket(str(r.date), granularity), 0) + int(r.cc or 0)

        opp_by_bucket: dict = {}
        plat_by_bucket: dict = {}
        for r in rows:
            bk = bucket(str(r.date), granularity)
            opp_by_bucket[bk] = opp_by_bucket.get(bk, 0) + 1
            p = str((slot_map.get(r.opportunity_id, {}) or {}).get("platform_type") or "未分类")
            plat_by_bucket.setdefault(bk, {})[p] = plat_by_bucket.setdefault(bk, {}).get(p, 0) + 1

        series = [{
            "bucket": bk,
            "new_opps": opp_by_bucket.get(bk, 0),
            "new_configs": cfg_by_bucket.get(bk, 0),
            "platforms": plat_by_bucket.get(bk, {}),
        } for bk in fill_dates(s_dt, e_dt, granularity)]

        sales_rows = session.query(
            Opportunity.sales_person,
            func.count(Opportunity.opportunity_id).label("count"),
            func.sum(case((Opportunity.result == "won", 1), else_=0)).label("won"),
        ).filter(
            *(base_conds + [Opportunity.created_at >= start_str, Opportunity.created_at < end_str])
        ).group_by(Opportunity.sales_person).order_by(func.count(Opportunity.opportunity_id).desc()).all()
        rank = [{"name": r.sales_person, "count": int(r.count), "won": int(r.won or 0)}
                for r in sales_rows if r.sales_person]

        return {
            "ok": True,
            "caliber": "与商机线索页一致：status 排除 ai_office/deleted；平台/机箱读需求单 slots（current 优先、空则最新 draft，缺省「未分类」）；配置数=每商机 status=active 最大 version 报价单的 config_count 求和",
            "window": {"start": s_dt.strftime("%Y-%m-%d"), "end": e_dt.strftime("%Y-%m-%d"),
                       "granularity": granularity, "label": label},
            "kpi": {"total_opps": int(total_opps), "total_configs": int(total_configs),
                    "new_opps": new_opps, "new_configs": new_configs},
            "recent": {
                "week": _recent_window(session, PERIODS["week"](),
                                       datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                                       "本周"),
                "month": _recent_window(session, PERIODS["month"](),
                                        datetime.now().replace(hour=0, minute=0, second=0, microsecond=0),
                                        "本月"),
            },
            "series": series,
            "platform_dist": _dist(session, start_str, end_str, "platform_type", False),
            "chassis_dist": _dist(session, start_str, end_str, "chassis_form", True),
            "sales_rank": {"top": rank[:5], "others_count": sum(r["count"] for r in rank[5:]),
                           "others_people": max(len(rank) - 5, 0)},
        }
    finally:
        session.close()
