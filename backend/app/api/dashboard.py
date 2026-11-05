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


def _split_set(v: Optional[str]) -> list:
    return [s.strip() for s in (v or "").split(",") if s.strip()]


# 地区推断：库中无省/国字段，按客户名关键词推省份（仅驾驶舱展示口径，不落库）。
# 键=geoJSON 里的省级全名（frontend/public/geo/china.json），值=匹配关键词（省名核心+主要城市）。
# 海外：客户名含 ≥3 连续英文字母视为海外客户（库中无国家字段，海外不细分到国）。
_PROVINCE_TABLE = [
    ("北京市", ("北京",)), ("天津市", ("天津",)), ("上海市", ("上海",)), ("重庆市", ("重庆",)),
    ("河北省", ("河北", "石家庄", "唐山", "保定")), ("山西省", ("山西", "太原")),
    ("内蒙古自治区", ("内蒙古", "呼和浩特", "包头")), ("辽宁省", ("辽宁", "沈阳", "大连")),
    ("吉林省", ("吉林", "长春")), ("黑龙江省", ("黑龙江", "哈尔滨")),
    ("江苏省", ("江苏", "南京", "苏州", "无锡")), ("浙江省", ("浙江", "杭州", "宁波")),
    ("安徽省", ("安徽", "合肥")), ("福建省", ("福建", "福州", "厦门")), ("江西省", ("江西", "南昌")),
    ("山东省", ("山东", "济南", "青岛")), ("河南省", ("河南", "郑州", "洛阳")),
    ("湖北省", ("湖北", "武汉")), ("湖南省", ("湖南", "长沙")),
    ("广东省", ("广东", "广州", "深圳", "东莞", "佛山")), ("广西壮族自治区", ("广西", "南宁")),
    ("海南省", ("海南",)), ("四川省", ("四川", "成都")), ("贵州省", ("贵州",)),
    ("云南省", ("云南", "昆明")), ("西藏自治区", ("西藏",)), ("陕西省", ("陕西", "西安")),
    ("甘肃省", ("甘肃", "兰州")), ("青海省", ("青海",)), ("宁夏回族自治区", ("宁夏",)),
    ("新疆维吾尔自治区", ("新疆", "乌鲁木齐")), ("台湾省", ("台湾",)),
    ("香港特别行政区", ("香港",)), ("澳门特别行政区", ("澳门",)),
]


def _infer_province(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return ""
    if re.search(r"[A-Za-z]{3,}", n):
        return "海外"
    for full, kws in _PROVINCE_TABLE:
        if any(kw in n for kw in kws):
            return full
    return ""


def _infer_region(name: str) -> str:
    return _infer_province(name) or "未分类"


def _parse_dt(s: Optional[str]):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("T", " ")[:19])
    except ValueError:
        return None


_MARKUP_BINS = [(0, 5, "0~5%"), (5, 10, "5~10%"), (10, 15, "10~15%"), (15, 20, "15~20%"), (20, 30, "20~30%"), (30, 10 ** 9, ">30%")]
_CYCLE_BINS = [(0, 15, "≤15天"), (15, 30, "16~30天"), (30, 60, "31~60天"), (60, 90, "61~90天"), (90, 10 ** 9, ">90天")]


@router.get("/cockpit")
def get_cockpit(
    period: str = Query(default="year"),
    start: Optional[str] = Query(default=None),
    end: Optional[str] = Query(default=None),
    result: Optional[str] = Query(default=None),
    platform: Optional[str] = Query(default=None),
    chassis: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    otype: Optional[str] = Query(default=None),
    sales: Optional[str] = Query(default=None),
    pn: Optional[str] = Query(default=None),
    customer: Optional[str] = Query(default=None),
    province: Optional[str] = Query(default=None),
    user: dict = Depends(get_current_user),
):
    """商机驾驶舱聚合端点。

    口径与 /summary 同源：商机不含 AI 办公室/回收站，配置数=当前版本求和，成单=result=won。
    全量行取回后 Python 侧过滤聚合（商机量级数百行），KPI 总量类不受周期窗口影响；
    prev=同比窗口（去年同期/上月同期/上周）。地区为关键词推断展示口径。
    """
    if not isinstance(user, dict):
        user = {}
    session = Opportunity_SessionLocal()
    try:
        s_dt, e_dt, _granularity, period_label = _resolve_range(period, start, end)
        view_all = user_has_permission(user, "page.opportunities_all")
        base = [Opportunity.status != "ai_office", Opportunity.status != "deleted"]
        if not view_all:
            base.append(Opportunity.owner_user_id == user.get("user_id"))

        # 字典 label 解析（禁用/删除 key 回退显示 key 本身）
        def _labels(dict_key: str) -> dict:
            from app.repository.system_config_repo import SystemConfigRepository
            repo = SystemConfigRepository()
            try:
                items = repo.get_value(dict_key, []) or []
            finally:
                repo.close()
            return {r.get("key"): (r.get("label") or r.get("key")) for r in items if isinstance(r, dict)}

        win_labels = _labels("opportunity.win_reasons")
        loss_labels = _labels("opportunity.loss_reasons")

        # ── 取全量行组装内存记录 ──
        opps = session.query(Opportunity).filter(*base).all()
        ids = [o.opportunity_id for o in opps]
        slot_map = _current_slot_map(session, ids)
        cfg_subq = _current_config_subquery(session, base)
        cfg_map = {r.oid: int(r.cc or 0) for r in session.query(
            cfg_subq.c.oid, cfg_subq.c.cc).filter(cfg_subq.c.rn == 1).all()}
        q_rows = session.query(
            Quotation.opportunity_id, Quotation.config_server_models, Quotation.profit_margin,
        ).filter(Quotation.opportunity_id.in_(ids or [""]), Quotation.status != "deleted").all()

        quote_count: dict = {}
        oid_pns: dict = {}       # oid → 该商机报价中出现过的 PN 集合
        oid_quotes: dict = {}    # oid → [(pn, 加点或None)]（报价单逐 PN 曝光）
        pn_exposure: dict = {}   # pn → 次数（全量口径，供筛选项）
        pn_markups: dict = {}    # pn → [加点样本]（全量口径，供筛选项）
        for r in q_rows:
            oid = r.opportunity_id
            quote_count[oid] = quote_count.get(oid, 0) + 1
            try:
                d = json.loads(r.config_server_models) if isinstance(r.config_server_models, str) else r.config_server_models
            except (json.JSONDecodeError, TypeError):
                d = {}
            if not isinstance(d, dict):
                d = {}
            pns = set()
            for v in d.values():
                p = _normalize_pn(str(v))
                if not p:
                    continue
                pns.add(p)
                pn_exposure[p] = pn_exposure.get(p, 0) + 1
                mv = None
                if r.profit_margin is not None:
                    try:
                        mv = float(r.profit_margin)
                    except (TypeError, ValueError):
                        mv = None
                    if mv is not None and not (-50 < mv < 200):
                        mv = None
                oid_quotes.setdefault(oid, []).append((p, mv))
                if mv is not None:
                    pn_markups.setdefault(p, []).append(mv)
            if pns:
                oid_pns.setdefault(oid, set()).update(pns)

        recs = []
        for o in opps:
            ex = {}
            if o.extra_fields:
                try:
                    ex = json.loads(o.extra_fields)
                except (json.JSONDecodeError, TypeError):
                    ex = {}
            created = _parse_dt(o.created_at)
            changed = _parse_dt(ex.get("result_changed_at"))
            win_days = None
            if o.result == "won" and created and changed and changed >= created:
                win_days = (changed - created).days
            slots = slot_map.get(o.opportunity_id, {}) or {}
            recs.append({
                "oid": o.opportunity_id,
                "customer": o.customer_name or "",
                "sales": o.sales_person or "",
                "result": o.result or "pending",
                "industry": o.industry or "",
                "otype": o.order_type or "",
                "platform": slots.get("platform_type") or "未分类",
                "chassis": (slots.get("chassis_form") or "未分类").split(",")[0].strip() or "未分类",
                "cfg": cfg_map.get(o.opportunity_id, 0),
                "quotes": quote_count.get(o.opportunity_id, 0),
                "created": created,
                "win_days": win_days,
                "win_keys": ex.get("win_reason_keys") or [],
                "loss_keys": ex.get("loss_reason_keys") or [],
                "region": _infer_region(o.customer_name or ""),
                "province": _infer_province(o.customer_name or ""),
            })
        rec_by_oid = {r["oid"]: r for r in recs}

        # ── 维度筛选（周期之外的全部过滤）──
        f_platform, f_chassis, f_industry, f_otype = _split_set(platform), _split_set(chassis), _split_set(industry), _split_set(otype)
        f_sales, f_pn, f_result, f_customer = _split_set(sales), _split_set(pn), (result or "").strip(), (customer or "").strip()
        f_province = _split_set(province)
        # pn 筛选：命中的商机集合（报价里出现过该 PN）
        pn_hit_oids = None
        if f_pn:
            pn_hit_oids = set()
            for r in q_rows:
                try:
                    d = json.loads(r.config_server_models) if isinstance(r.config_server_models, str) else r.config_server_models
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(d, dict) and any(_normalize_pn(str(v)) in f_pn for v in d.values()):
                    pn_hit_oids.add(r.opportunity_id)

        def dims_ok(rec) -> bool:
            if f_result and rec["result"] != f_result:
                return False
            if f_platform and rec["platform"] not in f_platform:
                return False
            if f_chassis and rec["chassis"] not in f_chassis:
                return False
            if f_industry and (rec["industry"] or "未分类") not in f_industry:
                return False
            if f_otype and (rec["otype"] or "未分类") not in f_otype:
                return False
            if f_sales and rec["sales"] not in f_sales:
                return False
            if pn_hit_oids is not None and rec["oid"] not in pn_hit_oids:
                return False
            if f_customer and f_customer.lower() not in rec["customer"].lower():
                return False
            if f_province and rec["province"] not in f_province:
                return False
            return True

        RD = [r for r in recs if dims_ok(r)]
        in_period = lambda rec: rec["created"] and (s_dt <= rec["created"] < e_dt + timedelta(days=1))
        span = e_dt - s_dt
        prev_start = s_dt - span
        # 周期窗口作用于全部指标（口径对齐商机线索页：选本周就只看本周）；
        # 月度趋势固定近12月、仅随维度筛选。Prev=维度筛选下的同期窗口（供环比）。
        R = [r for r in RD if in_period(r)]
        P = R
        if period != "all":
            Prev = [r for r in RD if r["created"] and prev_start <= r["created"] < s_dt]
        else:
            Prev = []
        # 机型维度按当前筛选+周期集合重算（pn_exposure/pn_markups 是全量口径，仅供筛选项）
        oid_set = {r["oid"] for r in R}
        s_exposure: dict = {}
        s_markups: dict = {}
        markup_win_s: list = []   # (加点, oid)
        for r in R:
            for p, mv in oid_quotes.get(r["oid"], []):
                s_exposure[p] = s_exposure.get(p, 0) + 1
                if mv is not None:
                    s_markups.setdefault(p, []).append(mv)
                    markup_win_s.append((mv, r["oid"]))

        def _count(items, key):
            m = {}
            for r in items:
                v = r[key] or ("未分类" if key in ("industry", "otype") else "")
                if not v:
                    continue
                m[v] = m.get(v, 0) + 1
            out = [{"name": k, "count": v} for k, v in m.items()]
            out.sort(key=lambda x: x["count"], reverse=True)
            return out

        # ── KPI ──
        won_recs = [r for r in R if r["result"] == "won"]
        total_cfg = sum(r["cfg"] for r in R)
        kpi = {
            "total_opportunities": len(R),
            "total_configs": total_cfg,
            "customers": len({r["customer"] for r in R if r["customer"]}),
            "quotes": sum(r["quotes"] for r in R),
            "new_opportunities": len(P),
            "new_configs": sum(r["cfg"] for r in P),
            "won": len(won_recs),
            "win_rate": round(len(won_recs) / len(R) * 100, 1) if R else 0.0,
            "lost": len([r for r in R if r["result"] == "lost"]),
            "expired": len([r for r in R if r["result"] == "expired"]),
            "pending": len([r for r in R if r["result"] == "pending"]),
        }
        prev_won = [r for r in Prev if r["result"] == "won"]
        prev_kpi = {
            "new_opportunities": len(Prev),
            "new_configs": sum(r["cfg"] for r in Prev),
            "won": len(prev_won),
            "win_rate": round(len(prev_won) / len(Prev) * 100, 1) if Prev else None,
            "customers": len({r["customer"] for r in Prev if r["customer"]}),
            "quotes": sum(r["quotes"] for r in Prev),
            "lost": len([r for r in Prev if r["result"] == "lost"]),
            "expired": len([r for r in Prev if r["result"] == "expired"]),
        }

        # ── 月度趋势（近12月，维度筛选生效、不受周期窗口影响）──
        today = datetime.now().replace(day=1)
        months = []
        for i in range(11, -1, -1):
            t = today.year * 12 + today.month - 1 - i
            months.append(f"{t // 12}-{t % 12 + 1:02d}")
        month_key = lambda rec: rec["created"].strftime("%Y-%m") if rec["created"] else ""
        m_total = [len([r for r in RD if month_key(r) == m]) for m in months]
        m_won = [len([r for r in RD if month_key(r) == m and r["result"] == "won"]) for m in months]
        top_plats = [d["name"] for d in _count(R, "platform")[:3]]
        plat_series = {p: [len([r for r in RD if month_key(r) == m and r["platform"] == p]) for m in months]
                       for p in top_plats}

        # ── 业务排行 ──
        rank_map = {}
        for r in R:
            if not r["sales"]:
                continue
            e = rank_map.setdefault(r["sales"], {"count": 0, "won": 0})
            e["count"] += 1
            if r["result"] == "won":
                e["won"] += 1
        rank_list = [{"name": k, "count": v["count"], "won": v["won"]}
                     for k, v in sorted(rank_map.items(), key=lambda x: x[1]["count"], reverse=True)]
        rank_total = sum(d["count"] for d in rank_list)

        # ── 机型：热度 + 加点箱线 ──
        models = sorted(s_exposure.items(), key=lambda x: x[1], reverse=True)
        boxes = []
        other_vals = []
        for pn_name, _c in models:
            vals = s_markups.get(pn_name, [])
            if not vals:
                continue
            if len(vals) >= 4:
                q = _pct_quartiles(vals)
                if q:
                    boxes.append({"name": pn_name, **q})
            else:
                other_vals.extend(vals)
        boxes.sort(key=lambda x: x["median"], reverse=True)
        other_box = _pct_quartiles(other_vals) if other_vals else None
        if other_box:
            boxes.append({"name": "其他机型", **other_box})
        bins_out = []
        for lo, hi, label in _MARKUP_BINS:
            hit = [(mv, oid) for mv, oid in markup_win_s if lo <= mv < hi]
            won_n = sum(1 for _mv, oid in hit if rec_by_oid.get(oid, {}).get("result") == "won")
            bins_out.append({"label": label, "count": len(hit), "won": won_n,
                             "rate": round(won_n / len(hit) * 100, 1) if hit else 0.0})

        # ── 成单与输单 ──
        wr_map = {}
        for r in won_recs:
            for k in r["win_keys"]:
                wr_map[k] = wr_map.get(k, 0) + 1
        win_reasons = [{"key": k, "label": win_labels.get(k, k), "count": v}
                       for k, v in sorted(wr_map.items(), key=lambda x: x[1], reverse=True)]
        ls_map = {}
        for r in R:
            if r["result"] in ("lost", "expired"):
                for k in r["loss_keys"]:
                    ls_map[k] = ls_map.get(k, 0) + 1
        loss_reasons = [{"key": k, "label": loss_labels.get(k, k), "count": v}
                        for k, v in sorted(ls_map.items(), key=lambda x: x[1], reverse=True)]
        # 成单机型：按成单商机的 PN 曝光统计（一单多 PN 各计一次），平均加点=该商机的报价加点均值
        won_pn_stats = {}
        for r in won_recs:
            pns = oid_pns.get(r["oid"])
            if not pns:
                continue
            mv_list = [mv for mv, oid in markup_win_s if oid == r["oid"]]
            avg = round(sum(mv_list) / len(mv_list), 1) if mv_list else None
            for p in pns:
                e = won_pn_stats.setdefault(p, {"count": 0, "markups": []})
                e["count"] += 1
                if avg is not None:
                    e["markups"].append(avg)
        won_models = [{"name": k, "count": v["count"],
                       "avg_markup": round(sum(v["markups"]) / len(v["markups"]), 1) if v["markups"] else None}
                      for k, v in sorted(won_pn_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:8]]
        days_list = sorted(r["win_days"] for r in won_recs if r["win_days"] is not None)
        cycle_bins = [{"label": lb, "count": len([d for d in days_list if lo <= d < hi])}
                      for lo, hi, lb in _CYCLE_BINS]
        cycle = {"bins": cycle_bins,
                 "median": days_list[len(days_list) // 2] if days_list else None,
                 "p90": days_list[min(len(days_list) - 1, int(len(days_list) * 0.9))] if days_list else None}
        first_month = {}
        for r in recs:
            k = month_key(r)
            if k and (r["customer"] not in first_month or k < first_month[r["customer"]]):
                first_month[r["customer"]] = k
        new_c = sum(1 for r in won_recs if first_month.get(r["customer"]) == month_key(r))
        new_vs_repeat = {"new": new_c, "repeat": len(won_recs) - new_c}

        # ── 地区（推断口径）+ 客户排行 ──
        province_counts = [d for d in _count(R, "province") if d["name"] != "海外"]
        overseas = len([r for r in R if r["province"] == "海外"])
        cust_map = {}
        for r in R:
            if not r["customer"]:
                continue
            e = cust_map.setdefault(r["customer"], {"count": 0, "won": 0})
            e["count"] += 1
            if r["result"] == "won":
                e["won"] += 1
        customers = [{"name": k, "count": v["count"], "won": v["won"]}
                     for k, v in sorted(cust_map.items(), key=lambda x: x[1]["count"], reverse=True)[:15]]

        # ── 筛选下拉选项（全量口径，不随筛选收缩）──
        options = {
            "platform": sorted({r["platform"] for r in recs if r["platform"]}),
            "chassis": sorted({r["chassis"] for r in recs if r["chassis"]}),
            "industry": sorted({r["industry"] or "未分类" for r in recs} | {"未分类"}),
            "otype": sorted({r["otype"] or "未分类" for r in recs} | {"未分类"}),
            "sales": sorted({r["sales"] for r in recs if r["sales"]}),
            "pn": sorted(pn_exposure.keys()),
        }

        return {
            "period_label": period_label,
            "view_all": view_all,
            "generated_at": datetime.now().strftime("%H:%M:%S"),
            "kpi": kpi,
            "prev": prev_kpi,
            "monthly": {"months": months, "total": m_total, "won": m_won, "platform_series": plat_series},
            "structure": {"platforms": _count(R, "platform"), "chassis": _count(R, "chassis"),
                          "industry": _count(R, "industry"), "otype": _count(R, "otype")},
            "rank": {"top": rank_list[:5], "others": (
                {"count": sum(d["count"] for d in rank_list[5:]), "people": len(rank_list) - 5}
                if len(rank_list) > 5 else None),
                "others_list": rank_list[5:], "total": rank_total},
            "models": {"data": [[k, v] for k, v in models]},
            "markup": {"boxes": boxes, "bins": bins_out},
            "win": {"win_reasons": win_reasons, "loss_reasons": loss_reasons,
                    "won_models": won_models, "cycle": cycle, "new_vs_repeat": new_vs_repeat},
            "region": {"provinces": province_counts, "overseas": overseas},
            "customers": {"top": customers},
            "options": options,
        }
    finally:
        session.close()
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
