# -*- coding: utf-8 -*-
"""图表资产注册表 —— 产出物模板引用的系统已有图表（同源口径）。

原则：资产 = 取数查询 + option 构建器，注册在后端这一份权威源；模板编辑器预览
（iframe HTML）与 PDF 服务端渲染消费同一注册表，驾驶舱改口径报告自动跟。
option 构建器镜像前端 OpportunityCharts.vue 的视觉语言（PLAT_COLOR/环形中心总数）。

P0 注册八个驾驶舱资产：cockpit.trend（柱+分平台折线）/ cockpit.dist（环形）/
cockpit.model_trend（机型树图）/ cockpit.chassis_dist（机箱玫瑰）/ cockpit.sales_rank（业务排行横条）/
cockpit.profit（机型利润箱线）/ cockpit.kpi（指标）/ cockpit.top_opps（表）。
"""
from datetime import date, timedelta
from typing import Callable, Optional

from sqlalchemy import func

from ..models.base import Opportunity_SessionLocal
from ..models.opportunity import Opportunity

# 镜像 frontend/src/constants/platform.ts PLAT_COLOR（图表 canvas 色不走 CSS 变量的同一条铁律）
PLAT_COLOR = {
    "Orion": "#0EA5E9",
    "Polaris": "#FF3B5C",
    "Intel": "#1D4ED8",
    "工作站": "#A855F7",
    "INTEL&Orion": "#8A94A8",
}
FALLBACK_COLOR = "#6B7280"

_AXIS_LINE = "#E5E7EB"
_AXIS_LABEL = "#6B7280"
_SERIES_BLUE = "#1D4ED8"


def _plat_color(name: str) -> str:
    return PLAT_COLOR.get(name, FALLBACK_COLOR)


# 驾驶舱列表口径（dashboard.py base_conds）：排除 AI 办公室隐藏商机与已删除行
_ACTIVE_CONDS = (Opportunity.status != "ai_office", Opportunity.status != "deleted")


# ─────────────────────────── 取数（驾驶舱同口径） ───────────────────────────

def _trend_range(days: int):
    end = date.today() + timedelta(days=1)
    start = date.today() - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _fetch_trend(days: int = 56) -> dict:
    """按天分组计数 + 按平台分线（口径=驾驶舱 chart1：substr(created_at,1,10) + slot map）。"""
    from ..repository.opp_caliber_repo import current_slot_map
    start_str, end_str = _trend_range(days)
    day_expr = func.substr(Opportunity.created_at, 1, 10)
    session = Opportunity_SessionLocal()
    try:
        rows = (
            session.query(day_expr.label("d"), Opportunity.opportunity_id)
            .filter(
                *_ACTIVE_CONDS,
                Opportunity.created_at >= start_str,
                Opportunity.created_at < end_str,
            )
            .all()
        )
        ids = [r.opportunity_id for r in rows]
        slot_map = current_slot_map(session, ids) if ids else {}
    finally:
        session.close()
    # 填满日期桶
    labels, buckets = [], {}
    cur = date.today() - timedelta(days=days)
    for _ in range(days + 1):
        k = cur.isoformat()
        labels.append(k[5:].replace("-", "/"))
        buckets[k] = {"total": 0, "plat": {}}
        cur += timedelta(days=1)
    for r in rows:
        b = buckets.get((r.d or "")[:10])
        if b is None:
            continue
        b["total"] += 1
        plat = (slot_map.get(r.opportunity_id, {}).get("platform_type") or "").strip()
        plat = plat if plat else "未分类"
        b["plat"][plat] = b["plat"].get(plat, 0) + 1
    platforms = []
    seen: dict = {}
    for b in buckets.values():
        for p in b["plat"]:
            seen[p] = seen.get(p, 0) + b["plat"][p]
    # 平台按累计量排序，只画有量的
    platforms = [p for p, _ in sorted(seen.items(), key=lambda kv: -kv[1])]
    return {
        "labels": labels,
        "total": [b["total"] for b in buckets.values()],
        "platforms": platforms,
        "platform_series": {p: [b["plat"].get(p, 0) for b in buckets.values()] for p in platforms},
    }


def _fetch_dist(days: int = 56) -> dict:
    """平台分布（环形，口径同 trend 的 slot map 平台计数）。"""
    from ..repository.opp_caliber_repo import current_slot_map
    start_str, end_str = _trend_range(days)
    session = Opportunity_SessionLocal()
    try:
        rows = (
            session.query(Opportunity.opportunity_id)
            .filter(
                *_ACTIVE_CONDS,
                Opportunity.created_at >= start_str,
                Opportunity.created_at < end_str,
            )
            .all()
        )
        ids = [r.opportunity_id for r in rows]
        slot_map = current_slot_map(session, ids) if ids else {}
    finally:
        session.close()
    counts: dict = {}
    for oid in ids:
        plat = (slot_map.get(oid, {}).get("platform_type") or "").strip()
        plat = plat if plat else "未分类"
        counts[plat] = counts.get(plat, 0) + 1
    items = [{"name": n, "value": v} for n, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    return {"items": items, "total": sum(c["value"] for c in items)}


# KPI 指标原子目录：kpi 区块 blk.metrics 按 key 挑选/改名/排序；取数一次全量算（都是廉价计数）
_KPI_METRIC_CATALOG = [
    {"key": "total", "label": "累计商机", "unit": "条"},
    {"key": "new_week", "label": "近 7 天新增", "unit": "条"},
    {"key": "new_month", "label": "近 30 天新增", "unit": "条"},
    {"key": "won", "label": "累计赢单", "unit": "条"},
    {"key": "win_rate", "label": "赢单率", "unit": "%"},
    {"key": "open", "label": "进行中", "unit": "条"},
]


def kpi_metric_catalog() -> list:
    return [dict(m) for m in _KPI_METRIC_CATALOG]


def _fetch_kpi() -> dict:
    session = Opportunity_SessionLocal()
    try:
        base = list(_ACTIVE_CONDS)
        total = session.query(func.count(Opportunity.opportunity_id)).filter(*base).scalar() or 0
        week_start = (date.today() - timedelta(days=7)).isoformat()
        month_start = (date.today() - timedelta(days=30)).isoformat()
        new_week = (
            session.query(func.count(Opportunity.opportunity_id))
            .filter(*base, Opportunity.created_at >= week_start)
            .scalar() or 0
        )
        new_month = (
            session.query(func.count(Opportunity.opportunity_id))
            .filter(*base, Opportunity.created_at >= month_start)
            .scalar() or 0
        )
        won = (
            session.query(func.count(Opportunity.opportunity_id))
            .filter(*base, Opportunity.result == "won")
            .scalar() or 0
        )
        open_cnt = (
            session.query(func.count(Opportunity.opportunity_id))
            .filter(*base, Opportunity.result == "pending")
            .scalar() or 0
        )
    finally:
        session.close()
    rate = round(won / total * 100, 1) if total else 0.0
    vals = {"total": int(total), "new_week": int(new_week), "new_month": int(new_month),
            "won": int(won), "win_rate": rate, "open": int(open_cnt)}
    return {"items": [
        {"key": m["key"], "label": m["label"], "value": vals[m["key"]], "unit": m["unit"]}
        for m in _KPI_METRIC_CATALOG
    ]}


def _fetch_top_opps(limit: int = 5) -> dict:
    from ..repository.opp_caliber_repo import current_slot_map
    session = Opportunity_SessionLocal()
    try:
        rows = (
            session.query(
                Opportunity.opportunity_id,
                Opportunity.customer_name,
                Opportunity.sales_person,
                Opportunity.result,
                Opportunity.created_at,
            )
            .filter(*_ACTIVE_CONDS)
            .order_by(Opportunity.created_at.desc())
            .limit(limit)
            .all()
        )
        ids = [r.opportunity_id for r in rows]
        slot_map = current_slot_map(session, ids) if ids else {}
    finally:
        session.close()
    result_label = {"won": "赢单", "lost": "丢单", "pending": "进行中", "expired": "过期"}
    data = []
    for r in rows:
        plat = (slot_map.get(r.opportunity_id, {}).get("platform_type") or "").strip() or "未分类"
        data.append(
            {
                "customer": r.customer_name or "（未命名）",
                "platform": plat,
                "sales": r.sales_person or "—",
                "result": result_label.get(r.result or "", r.result or "—"),
                "created": (r.created_at or "")[:10],
            }
        )
    return {"columns": ["商机", "平台", "销售", "状态", "创建日期"], "rows": data}


def _pn_set_from_config(raw) -> set:
    """quotations.config_server_models(JSON: {CFG1: "ZSA240 V2"}) → PN 集合（归一，与驾驶舱 _normalize_pn 同一份）。"""
    import json as _json
    from ..api.dashboard import _normalize_pn
    try:
        d = _json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return set()
    if not isinstance(d, dict):
        return set()
    out = set()
    for v in d.values():
        pn = _normalize_pn(str(v))
        if pn:
            out.add(pn)
    return out


def _fetch_model_trend(days: int = 56) -> dict:
    """机型趋势（矩形树图）：周期内报价单按 PN 累计出现次数，主力 Top8+其他（口径=驾驶舱 chart2）。"""
    from ..models.quotation import Quotation
    start_str, _ = _trend_range(days)
    session = Opportunity_SessionLocal()
    try:
        rows = (
            session.query(Quotation.config_server_models)
            .join(Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id)
            .filter(
                *_ACTIVE_CONDS,
                Quotation.status != "deleted",
                Quotation.config_server_models.isnot(None),
                Quotation.created_at >= start_str,
            )
            .all()
        )
    finally:
        session.close()
    totals: dict = {}
    for r in rows:
        for pn in _pn_set_from_config(r.config_server_models):
            totals[pn] = totals.get(pn, 0) + 1
    TOP_PN = 8
    items = sorted(totals.items(), key=lambda kv: -kv[1])
    top = items[:TOP_PN]
    rest = items[TOP_PN:]
    data = [{"name": n, "value": v} for n, v in top]
    if rest:
        data.append({"name": "其他机型", "value": sum(v for _, v in rest)})
    return {"items": data, "total": sum(totals.values())}


def _fetch_chassis_dist(days: int = 56) -> dict:
    """机箱结构（玫瑰图）：商机 slot chassis_form 计数，多值逗号拆分（口径=驾驶舱 structure.chassis）。"""
    from ..repository.opp_caliber_repo import current_slot_map
    start_str, end_str = _trend_range(days)
    session = Opportunity_SessionLocal()
    try:
        rows = (
            session.query(Opportunity.opportunity_id)
            .filter(
                *_ACTIVE_CONDS,
                Opportunity.created_at >= start_str,
                Opportunity.created_at < end_str,
            )
            .all()
        )
        ids = [r.opportunity_id for r in rows]
        slot_map = current_slot_map(session, ids) if ids else {}
    finally:
        session.close()
    counts: dict = {}
    for oid in ids:
        forms = (slot_map.get(oid, {}).get("chassis_form") or "未分类").split(",")
        for form in forms:
            c = form.strip() or "未分类"
            counts[c] = counts.get(c, 0) + 1
    items = [{"name": n, "value": v} for n, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    return {"items": items, "total": sum(c["value"] for c in items)}


def _fetch_sales_rank(top_n: int = 5) -> dict:
    """业务排行（横条）：按销售商机数 Top N + 其他人聚合（口径=驾驶舱 sales_rank）。"""
    from sqlalchemy import case
    session = Opportunity_SessionLocal()
    try:
        rows = (
            session.query(
                Opportunity.sales_person,
                func.count(Opportunity.opportunity_id).label("cnt"),
                func.sum(case((Opportunity.result == "won", 1), else_=0)).label("won"),
            )
            .filter(*_ACTIVE_CONDS)
            .group_by(Opportunity.sales_person)
            .order_by(func.count(Opportunity.opportunity_id).desc())
            .all()
        )
    finally:
        session.close()
    ranked = [{"name": r.sales_person, "count": int(r.cnt), "won": int(r.won or 0)} for r in rows if r.sales_person]
    total = sum(r["count"] for r in ranked) or 1
    top = ranked[:top_n]
    others = ranked[top_n:]
    return {
        "rows": [{"name": r["name"], "count": r["count"], "rate": round(r["count"] / total * 100, 1), "others": False} for r in top]
        + (
            [{"name": f"其他 {len(others)} 人", "count": sum(r['count'] for r in others), "rate": round(sum(r['count'] for r in others) / total * 100, 1), "others": True}]
            if others
            else []
        ),
        "total": total,
    }


def _fetch_profit() -> dict:
    """机型利润（箱线）：各 PN 的 profit_margin 分布，样本≥4 成箱其余折叠其他（口径=驾驶舱 chart5，不限周期）。"""
    import json as _json
    from ..api.dashboard import _normalize_pn, _pct_quartiles
    from ..models.quotation import Quotation
    session = Opportunity_SessionLocal()
    try:
        rows = (
            session.query(Quotation.config_server_models, Quotation.profit_margin)
            .join(Opportunity, Quotation.opportunity_id == Opportunity.opportunity_id)
            .filter(
                *_ACTIVE_CONDS,
                Quotation.status != "deleted",
                Quotation.config_server_models.isnot(None),
                Quotation.profit_margin.isnot(None),
            )
            .all()
        )
    finally:
        session.close()
    pn_profits: dict = {}
    for r in rows:
        try:
            d = _json.loads(r.config_server_models) if isinstance(r.config_server_models, str) else r.config_server_models
        except (ValueError, TypeError):
            continue
        if not isinstance(d, dict):
            continue
        for v in d.values():
            pn = _normalize_pn(str(v))
            if pn:
                pn_profits.setdefault(pn, []).append(float(r.profit_margin or 0))
    BOX_MIN_N = 4
    boxes, other_vals = [], []
    for pn, vals in pn_profits.items():
        if len(vals) >= BOX_MIN_N:
            q = _pct_quartiles(vals)
            if q:
                boxes.append({"name": pn, **q})
        else:
            other_vals.extend(vals)
    boxes.sort(key=lambda x: x["median"], reverse=True)
    other_box = _pct_quartiles(other_vals) if other_vals else None
    if other_box:
        boxes.append({"name": "其他机型", **other_box})
    return {"boxes": boxes}


# ─────────────────────────── option 构建器（镜像前端视觉） ───────────────────────────

def _build_trend_option(data: dict, height: int = 240) -> dict:
    series = [
        {
            "name": "新增商机",
            "type": "bar",
            "data": data["total"],
            "barMaxWidth": 14,
            "itemStyle": {"color": _SERIES_BLUE, "borderRadius": [3, 3, 0, 0]},
        }
    ]
    for p in data["platforms"]:
        series.append(
            {
                "name": p,
                "type": "line",
                "smooth": True,
                "symbol": "circle",
                "symbolSize": 5,
                "showSymbol": False,
                "lineStyle": {"width": 2},
                "emphasis": {"focus": "series"},
                "itemStyle": {"color": _plat_color(p)},
                "data": data["platform_series"][p],
            }
        )
    return {
        "grid": {"left": 8, "right": 12, "top": 30, "bottom": 0, "containLabel": True},
        "tooltip": {"trigger": "axis"},
        "legend": {"top": 0, "right": 0, "itemWidth": 10, "itemHeight": 2, "textStyle": {"fontSize": 10, "color": _AXIS_LABEL}},
        "xAxis": {
            "type": "category",
            "data": data["labels"],
            "axisTick": {"show": False},
            "axisLine": {"lineStyle": {"color": _AXIS_LINE}},
            "axisLabel": {"color": _AXIS_LABEL, "fontSize": 10},
        },
        "yAxis": {
            "type": "value",
            "splitNumber": 3,
            "axisLabel": {"color": _AXIS_LABEL, "fontSize": 10},
            "splitLine": {"lineStyle": {"color": _AXIS_LINE, "type": "dashed"}},
        },
        "series": series,
    }


def _build_dist_option(data: dict, height: int = 240) -> dict:
    items = data["items"]
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}：{c}（{d}%）"},
        "legend": {"bottom": 0, "itemWidth": 8, "itemHeight": 8, "textStyle": {"fontSize": 10, "color": _AXIS_LABEL}},
        "title": {
            "text": str(data["total"]),
            "subtext": "总商机",
            "left": "center",
            "top": "38%",
            "textStyle": {"fontSize": 22, "fontWeight": 700, "color": "#111827"},
            "subtextStyle": {"fontSize": 10, "color": _AXIS_LABEL},
        },
        "series": [
            {
                "type": "pie",
                "radius": ["48%", "68%"],
                "center": ["50%", "44%"],
                "avoidLabelOverlap": True,
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2},
                "label": {"show": False},
                "data": [{"name": i["name"], "value": i["value"], "itemStyle": {"color": _plat_color(i["name"])}} for i in items],
            }
        ],
    }


# ─────────────────────────── option 构建器（镜像前端视觉·续） ───────────────────────────

_MODEL_COLORS = ["#1677FF", "#36CFCF", "#5B8FF9", "#722ED1", "#a855f7", "#FF3B5C", "#FA8C16", "#52C41A", "#6B7280"]
_PIE_COLORS = ["#1677FF", "#36CFCF", "#5B8FF9", "#722ED1", "#a855f7", "#FF3B5C", "#6B7280"]


def _build_model_trend_option(data: dict, height: int = 240) -> dict:
    total = data["total"] or 1
    items = [
        {
            "name": i["name"],
            "value": [i["value"], round(i["value"] / total * 100, 1)],
            "itemStyle": {"color": _MODEL_COLORS[idx % len(_MODEL_COLORS)]},
        }
        for idx, i in enumerate(data["items"])
    ]
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}<br/>报价 <b>{@[0]}</b> 次 · 占比 <b>{@[1]}%</b>"},
        "series": [
            {
                "type": "treemap",
                "roam": False,
                "nodeClick": False,
                "breadcrumb": {"show": False},
                "left": 0,
                "right": 0,
                "top": 4,
                "bottom": 0,
                "label": {
                    "show": True,
                    "position": "inside",
                    "fontWeight": 600,
                    "fontSize": 11,
                    "color": "#fff",
                    "formatter": "{b}\n{@[0]}次 · {@[1]}%",
                    "textShadowBlur": 4,
                    "textShadowColor": "rgba(0,0,0,0.3)",
                },
                "upperLabel": {"show": False},
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2, "gapWidth": 3},
                "levels": [{"itemStyle": {"borderColor": "#fff", "borderWidth": 2, "gapWidth": 3}}],
                "data": items,
            }
        ],
    }


def _build_chassis_dist_option(data: dict, height: int = 240) -> dict:
    return {
        "tooltip": {"trigger": "item", "formatter": "{b}：{c}（{d}%）"},
        "legend": {"bottom": 0, "type": "scroll", "itemWidth": 8, "itemHeight": 8, "textStyle": {"fontSize": 10, "color": _AXIS_LABEL}},
        "series": [
            {
                "type": "pie",
                "roseType": "radius",
                "radius": ["18%", "72%"],
                "center": ["50%", "44%"],
                "label": {"show": False},
                "labelLine": {"show": False},
                "itemStyle": {"borderColor": "#fff", "borderWidth": 2, "borderRadius": 3},
                "color": _PIE_COLORS,
                "data": data["items"],
            }
        ],
    }


def _build_sales_rank_option(data: dict, height: int = 240) -> dict:
    rows = data["rows"]
    names = [f"{i + 1}. {r['name']}" for i, r in enumerate(rows)]
    top = rows[0]["count"] if rows else 1
    return {
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": 4, "right": 44, "top": 8, "bottom": 4, "containLabel": True},
        "xAxis": {
            "type": "value",
            "max": max(1, -(-int(top * 1.2) // 1)),
            "splitLine": {"lineStyle": {"color": _AXIS_LINE, "type": "dashed"}},
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": _AXIS_LABEL, "fontSize": 10},
        },
        "yAxis": {
            "type": "category",
            "inverse": True,
            "data": names,
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"margin": 12, "color": "#374151", "fontSize": 11},
        },
        "series": [
            {
                "type": "bar",
                "barMaxWidth": 14,
                "itemStyle": {"borderRadius": [0, 6, 6, 0]},
                "label": {"show": True, "position": "right", "color": "#374151", "fontSize": 11, "fontWeight": 600},
                "data": [
                    {
                        "value": r["count"],
                        "itemStyle": {
                            "color": "#9CA3AF"
                            if r["others"]
                            else {
                                "type": "linear",
                                "x": 0, "y": 0, "x2": 1, "y2": 0,
                                "colorStops": [{"offset": 0, "color": "#93C5FD"}, {"offset": 1, "color": _SERIES_BLUE}],
                            }
                        },
                    }
                    for r in rows
                ],
            }
        ],
    }


def _build_profit_option(data: dict, height: int = 240) -> dict:
    boxes = data["boxes"]
    names = [b["name"] for b in boxes]
    box_data = [[b["min"], b["q1"], b["median"], b["q3"], b["max"]] for b in boxes]
    scatter: list = []
    for i, b in enumerate(boxes):
        for v in b.get("scatter") or []:
            scatter.append([i, v])
    return {
        "grid": {"left": 44, "right": 16, "top": 12, "bottom": 30},
        "xAxis": {
            "type": "category",
            "data": names,
            "boundaryGap": True,
            "axisLine": {"lineStyle": {"color": _AXIS_LINE}},
            "axisLabel": {"color": _AXIS_LABEL, "fontSize": 10, "rotate": 20 if len(names) > 4 else 0, "interval": 0},
            "axisTick": {"show": False},
            "splitLine": {"show": False},
        },
        "yAxis": {
            "type": "value",
            "name": "利润率%",
            "nameTextStyle": {"color": _AXIS_LABEL, "fontSize": 10},
            "splitLine": {"lineStyle": {"color": _AXIS_LINE, "type": "dashed"}},
            "axisLabel": {"color": _AXIS_LABEL, "fontSize": 10, "formatter": "{value}%"},
        },
        "series": [
            {
                "name": "利润分布",
                "type": "boxplot",
                "data": box_data,
                "itemStyle": {"color": "rgba(29, 78, 216, 0.25)", "borderColor": _SERIES_BLUE, "borderWidth": 1.5},
            },
            {
                "name": "利润点",
                "type": "scatter",
                "data": scatter,
                "symbolSize": 5,
                "itemStyle": {"color": _SERIES_BLUE, "opacity": 0.55},
            },
        ],
    }


# ─────────────────────────── 注册表 ───────────────────────────

_ASSET_DEFS: dict = {
    "cockpit.kpi": {
        "id": "cockpit.kpi",
        "name": "商机关键指标",
        "kind": "kpi",
        "source_page": "商机线索页",
        "desc": "指标原子目录：累计商机 / 近7天 / 近30天 / 累计赢单 / 赢单率 / 进行中（区块内勾选组合）",
        "params": [],
        "metrics": kpi_metric_catalog(),
        "fetch": _fetch_kpi,
    },
    "cockpit.trend": {
        "id": "cockpit.trend",
        "name": "新增商机趋势",
        "kind": "chart",
        "source_page": "商机线索页",
        "desc": "近 8 周按天新增柱状 + 分平台折线（Orion/Polaris/Intel…）",
        "params": [{"key": "days", "label": "统计天数", "default": 56, "min": 7, "max": 180, "step": 1, "unit": "天"}],
        "fetch": _fetch_trend,
        "option": _build_trend_option,
    },
    "cockpit.dist": {
        "id": "cockpit.dist",
        "name": "平台结构分布",
        "kind": "chart",
        "source_page": "商机线索页",
        "desc": "平台占比环形图，中心显示总商机数",
        "params": [{"key": "days", "label": "统计天数", "default": 56, "min": 7, "max": 180, "step": 1, "unit": "天"}],
        "fetch": _fetch_dist,
        "option": _build_dist_option,
    },
    "cockpit.top_opps": {
        "id": "cockpit.top_opps",
        "name": "最新商机明细",
        "kind": "table",
        "source_page": "商机线索页",
        "desc": "最近创建的商机：客户 / 平台 / 销售 / 状态 / 创建日期",
        "params": [{"key": "limit", "label": "行数", "default": 5, "min": 1, "max": 30, "step": 1, "unit": "行"}],
        "fetch": _fetch_top_opps,
    },
    "cockpit.model_trend": {
        "id": "cockpit.model_trend",
        "name": "机型趋势（树图）",
        "kind": "chart",
        "source_page": "商机线索页",
        "desc": "周期内报价单按机型(PN)出现次数的矩形树图，主力 Top8+其他",
        "params": [{"key": "days", "label": "统计天数", "default": 56, "min": 7, "max": 365, "step": 1, "unit": "天"}],
        "fetch": _fetch_model_trend,
        "option": _build_model_trend_option,
    },
    "cockpit.chassis_dist": {
        "id": "cockpit.chassis_dist",
        "name": "机箱结构（玫瑰图）",
        "kind": "chart",
        "source_page": "商机线索页",
        "desc": "商机按机箱形态占比的玫瑰图（多值拆分计数）",
        "params": [{"key": "days", "label": "统计天数", "default": 56, "min": 7, "max": 180, "step": 1, "unit": "天"}],
        "fetch": _fetch_chassis_dist,
        "option": _build_chassis_dist_option,
    },
    "cockpit.sales_rank": {
        "id": "cockpit.sales_rank",
        "name": "业务排行",
        "kind": "chart",
        "source_page": "商机线索页",
        "desc": "按销售的商机数 Top5 横条 + 其他人聚合",
        "params": [{"key": "top_n", "label": "上榜人数", "default": 5, "min": 1, "max": 15, "step": 1, "unit": "人"}],
        "fetch": _fetch_sales_rank,
        "option": _build_sales_rank_option,
    },
    "cockpit.profit": {
        "id": "cockpit.profit",
        "name": "机型利润（箱线）",
        "kind": "chart",
        "source_page": "商机线索页",
        "desc": "各机型报价利润率分布箱线+散点（样本≥4 成箱，不限周期）",
        "params": [],
        "fetch": _fetch_profit,
        "option": _build_profit_option,
    },
}


def list_assets() -> list[dict]:
    """给编辑器资产库的元数据（不带可调用对象）。"""
    out = []
    for a in _ASSET_DEFS.values():
        out.append({k: v for k, v in a.items() if k not in ("fetch", "option")})
    return out


def get_asset(asset_id: str) -> Optional[dict]:
    return _ASSET_DEFS.get(asset_id)


def resolve_asset_data(asset_id: str, params: Optional[dict] = None) -> Optional[dict]:
    asset = _ASSET_DEFS.get(asset_id)
    if asset is None:
        return None
    fetch: Callable = asset["fetch"]
    kwargs = {}
    params = params or {}
    for spec in asset.get("params") or []:
        raw = params.get(spec["key"])
        if raw is None or raw == "":
            continue
        try:
            v = int(raw)
        except (TypeError, ValueError):
            continue
        if spec.get("min") is not None:
            v = max(spec["min"], v)
        if spec.get("max") is not None:
            v = min(spec["max"], v)
        kwargs[spec["key"]] = v
    return fetch(**kwargs)


def resolve_chart_option(asset_id: str, params: Optional[dict] = None) -> Optional[dict]:
    asset = _ASSET_DEFS.get(asset_id)
    if asset is None or "option" not in asset:
        return None
    data = resolve_asset_data(asset_id, params)
    if data is None:
        return None
    return asset["option"](data)
