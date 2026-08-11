"""Dashboard statistics API — unified summary + detail endpoints."""
from datetime import datetime, timedelta
from typing import Optional, List
import re
import statistics
from fastapi import APIRouter, Query
from sqlalchemy import func, case
import json

from app.models.opportunity import Opportunity
from app.models.quotation import Quotation
from app.models.base import Opportunity_SessionLocal

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

CHAS_COLORS = {"2U": "#26E2D1", "4U": "#FA8C16", "5U": "#A855F7", "4.5U": "#1890FF", "工作站": "#A855F7", "2U/4U": "#8A94A8", "8U": "#8A94A8"}

# PN 提取：config_server_models 里混存干净 PN（ZSA24V2-P）和整机名（Orion 2U25 标准基准机箱），
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

        # === Chart 2: 机型趋势河流（ThemeRiver）— 月×机型(PN) 报价次数 ===
        # 删原"配置平台趋势"：平台维度已由 chart1 分线覆盖，这里换成细粒度机型(PN)维度。
        # PN 从 quotations.config_server_models(JSON: {CFG1: "ZSA24V2-P"}) 抽取归一；
        # 一张报价单里出现多个 PN 时各计一次（机型出现即曝光）。
        pn_rows = session.query(
            de.label("date"), Quotation.config_server_models, Quotation.config_count,
        ).join(
            Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id
        ).filter(
            Quotation.status != "deleted", Opportunity.status != "deleted",
            Opportunity.created_at >= start_str, Opportunity.created_at < end_str,
            Quotation.config_server_models.isnot(None),
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
            Opportunity.sales_person,
            func.count(Opportunity.opportunity_id).label("count"),
            func.sum(case((Opportunity.result == "won", 1), else_=0)).label("won"),
        ).filter(
            Opportunity.status != "deleted", Opportunity.created_at >= start_str, Opportunity.created_at < end_str
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
        ).filter(
            Quotation.status != "deleted",
            Quotation.config_server_models.isnot(None),
            Quotation.profit_margin.isnot(None),
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
