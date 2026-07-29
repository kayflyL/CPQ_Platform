"""Dashboard statistics API — unified summary + detail endpoints."""
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Query
from sqlalchemy import func
import json
import asyncio

from app.models.opportunity import Opportunity
from app.models.quotation import Quotation
from app.models.base import Opportunity_SessionLocal
from app.services.llm_client import stream_chat, LLMError
from app.repository.system_config_repo import SystemConfigRepository

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


@router.get("/ai-insights")
def get_ai_insights(
    period: str = Query(default="week"),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
):
    """基于当前统计数据生成 AI 趋势洞察"""
    import asyncio

    # 1. 获取统计数据
    summary = get_dashboard_summary(period, start, end)

    # 2. 读取 AI 设置（所有配置从 system_config 读取，拒绝硬编码）
    config_repo = SystemConfigRepository()
    try:
        ai_config = config_repo.get_value("ai_insights_config", {})
    finally:
        config_repo.close()

    # 从配置读取参数
    insight_count = ai_config.get("insight_count", 3)
    dimensions = ai_config.get("dimensions", ["growth", "risk", "suggestion"])
    data_scope = ai_config.get("data_scope", ["kpi", "platform", "sales", "trend"])
    depth = ai_config.get("depth", "brief")
    dimension_labels = ai_config.get("dimension_labels", {
        "growth": "增长信号",
        "risk": "风险预警",
        "suggestion": "行动建议"
    })
    prompt_template = ai_config.get("prompt_template", "")
    fallback_templates = ai_config.get("fallback_templates", {
        "no_data": "本周期暂无新增商机，建议关注跟进效率",
        "error": "刷新重试获取 AI 分析"
    })

    # 3. 构造数据描述（根据 data_scope 决定包含哪些数据）
    kpi = summary.get("kpi", {})
    platforms = summary.get("structure", {}).get("platforms", []) if "platform" in data_scope else []
    sales_rank = summary.get("sales_rank", {}).get("top", []) if "sales" in data_scope else []
    charts = summary.get("charts", {}) if "trend" in data_scope else {}

    # 提取趋势数据（最近几天的变化）
    trend_desc = ""
    if "trend" in data_scope and charts:
        chart1 = charts.get("chart1", {})
        total_series = chart1.get("total_series", [])[-7:] if chart1 else []
        if len(total_series) >= 2:
            first, last = total_series[0].get("value", 0), total_series[-1].get("value", 0)
            if first > 0:
                change = (last - first) / first * 100
                trend_desc = f"商机数趋势：从 {first} 变为 {last}（变化 {change:+.1f}%）"
            else:
                trend_desc = f"商机数趋势：最新 {last} 个"

    # 平台分布描述
    plat_desc = "、".join([f"{p['name']}({p['count']}个)" for p in platforms[:5]]) if platforms else ""

    # 业务排行描述
    sales_desc = "、".join([f"{s['name']}({s['count']}个)" for s in sales_rank[:5]]) if sales_rank else ""

    # 4. 构造维度描述（从配置读取标签）
    dim_desc = "、".join(dimension_labels.get(d, d) for d in dimensions)

    # 5. 构造提示词
    prompt_parts = [
        f"你是数据分析师，正在看商机驾驶舱的数据。",
        f"",
        f"时间周期：{summary.get('period_label', '')}",
        f"",
    ]

    # 根据数据范围添加数据
    if "kpi" in data_scope:
        prompt_parts.append(f"核心指标：")
        prompt_parts.append(f"- 总商机 {kpi.get('total_opportunities', 0)} 个，本周期新增 {kpi.get('new_opportunities', 0)} 个")
        prompt_parts.append(f"- 总配置 {kpi.get('total_configs', 0)} 套，本周期新增 {kpi.get('new_configs', 0)} 套")
        prompt_parts.append(f"")

    if plat_desc:
        prompt_parts.append(f"平台分布：{plat_desc}")
        prompt_parts.append(f"")

    if sales_desc:
        prompt_parts.append(f"业务排行：{sales_desc}")
        prompt_parts.append(f"")

    if trend_desc:
        prompt_parts.append(trend_desc)
        prompt_parts.append(f"")

    # 6. 添加分析要求（从配置模板读取）
    depth_desc = "一句话" if depth == "brief" else "两句，带数据支撑"
    if prompt_template:
        # 使用配置的模板
        prompt_parts.append(prompt_template.format(
            dimensions=dim_desc,
            count=insight_count,
            depth_desc=depth_desc
        ))
    else:
        # 兜底模板
        prompt_parts.extend([
            f"请分析以上数据，从以下维度发现值得关注的点：{dim_desc}。",
            f"",
            f"要求：",
            f"1. 输出 {insight_count} 条洞察",
            f"2. 每条洞察{depth_desc}",
            f"3. 不要套话，直接给结论",
            f"4. 如果发现增长，说明是什么在增长",
            f"5. 如果发现风险，说明具体风险点",
            f"6. 如果有建议，给出具体可操作的建议",
            f"",
            f"用 JSON 格式返回：",
            f'{{"insights": [{{"text": "...", "type": "growth|risk|suggestion"}}]}}',
        ])

    prompt = "\n".join(prompt_parts)

    # 7. 调用 LLM
    async def call_llm():
        messages = [{"role": "user", "content": prompt}]
        result_text = ""
        async for delta in stream_chat(messages):
            result_text += delta
        return result_text

    try:
        result_text = asyncio.run(call_llm())

        # 8. 解析 JSON
        import re
        json_match = re.search(r'\{[\s\S]*\}', result_text)
        if json_match:
            result = json.loads(json_match.group())
            insights = result.get("insights", [])
        else:
            insights = []

        # 兜底：如果解析失败，使用配置的兜底模板
        if not insights:
            new_opps = kpi.get('new_opportunities', 0)
            if new_opps == 0:
                insights = [{"type": "suggestion", "text": fallback_templates.get("no_data", "暂无新增商机")}]
            else:
                insights = [{"type": "growth", "text": f"本周期新增 {new_opps} 个商机"}]

        return {"insights": insights}

    except Exception as e:
        # 异常兜底：使用配置的错误模板
        return {
            "insights": [
                {"type": "growth", "text": f"总商机 {kpi.get('total_opportunities', 0)} 个"},
                {"type": "suggestion", "text": fallback_templates.get("error", "刷新重试获取 AI 分析")},
            ]
        }
