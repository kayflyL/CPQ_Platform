# -*- coding: utf-8 -*-
"""agent_tools —— 全系统 LLM 工具的唯一注册表（ToolRegistry）。

把确定性能力包成工具，LLM 负责推理/编排，精确性交给工具。消费方式：
  - 推理流（需求分析）：文本式 ReAct（agent_react.run_react_loop）多轮调用；
  - 方案助手：数据工具 query_cpq_data 走「LLM 提参 → 服务端执行 → 注入作答」。
为什么不用原生 function calling：cloudprime 代理只认 web_search 工具变体、拒绝标准
function（400 unknown variant），故统一走 chat_json 文本协议（见 agent_react docstring）。

设计原则（用户定调「拒绝硬编码」）：
  - 工具是数据：name/description/parameters/category/default_enabled 在 _TOOL_SPECS 声明，
    画布抽屉按目录勾选启用；tool_catalog() 供前端「AI 工具」目录页与提参提示渲染。
  - 工具只读/确定性：select_models 选机型、pick_kp_parts 配件、build_plan 组方案、
    search_cases 案例检索、query_cpq_data 业务数据查询……复用现有实现，不重造；
    handler 把工具结果压成 LLM 友好的 digest（防上下文爆炸）。
  - default_enabled=False 的工具不进默认全集（如 query_cpq_data），避免影响现有节点行为。

工具只读、不落库、不改系统状态（案例库同理只读，见 case_provider.py）。
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# 单工具 digest 最大字符数（防 LLM 上下文爆炸）
_MAX_DIGEST_CHARS = 4000


def _truncate(s: str, limit: int = _MAX_DIGEST_CHARS) -> str:
    s = s or ""
    return s if len(s) <= limit else s[:limit] + "\n…(截断)"


class ToolRegistry:
    """工具注册表：schemas() 给 LLM 看、execute() 执行工具。

    registry.schemas() → OpenAI tools 格式（喂 LLM 渲染工具清单，见 agent_react）。
    registry.execute(name, args) → 工具结果（dict/str，喂回 LLM 作 role:tool 消息）。
    """

    def __init__(self, allowed_data_sources: list = None):
        self._tools: Dict[str, dict] = {}
        self._allowed_data_sources = set(allowed_data_sources or []) if allowed_data_sources is not None else None

    def register(self, name: str, description: str, parameters: dict,
                 handler: Callable[[dict], Any], data_sources: list = None):
        self._tools[name] = {"name": name, "description": description,
                             "parameters": parameters, "handler": handler,
                             "data_sources": data_sources or []}

    def schemas(self) -> List[dict]:
        return [{"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["parameters"]}} for t in self._tools.values()]

    def names(self) -> List[str]:
        return list(self._tools.keys())

    async def execute(self, name: str, args: dict) -> Any:
        spec = self._tools.get(name)
        if not spec:
            return {"error": f"未知工具: {name}"}
        required = spec.get("data_sources") or []
        if self._allowed_data_sources is not None and required:
            missing = [item for item in required if item not in self._allowed_data_sources]
            if missing:
                return {"error": f"工具 {name} 缺少数据域权限: {', '.join(sorted(missing))}"}
        try:
            return await spec["handler"](args or {})
        except Exception as e:
            logger.exception("工具 %s 执行失败", name)
            return {"error": f"工具 {name} 执行失败: {e}"}


# ── 工具 handler：把现有确定性函数包成 agent 工具（结果压成 digest） ──────

async def _tool_select_models(args: dict) -> Any:
    """select_models → 候选机型 digest（名称/系列/形态/盘位/卖点，给 LLM 推理）。"""
    from app.api.candidate_search import select_models
    baselines = select_models(
        usage=args.get("usage") or "",
        server_type_name=args.get("server_type_name"),
        series=args.get("series"),
        form=args.get("form"),
        limit=int(args.get("limit") or 6),
        fallback_order=args.get("fallback_order") or ["exact", "same_series", "same_form", "all"],
    )
    if not baselines:
        return {"count": 0, "candidates": [],
                "note": "无匹配机型；建议放宽 server_type/form，或补 usage 关键词"}
    note = (baselines[0].get("fallback_note") or "")
    digest = [{
        "config_id": b.get("id"),
        "server_model_id": b.get("server_model_id"),
        "name": b.get("name") or "",
        "series": b.get("series") or "",
        "form": b.get("form") or "",
        "bays": b.get("bays"),
        "recommend_level": b.get("recommend_level") or "",
        "selling_points": _truncate(b.get("selling_points") or "", 300),
        "match_stage": b.get("match_stage"),
        "fallback_note": b.get("fallback_note") or "",
    } for b in baselines]
    return {"count": len(digest), "candidates": digest, "note": note}


async def _tool_pick_kp_parts(args: dict) -> Any:
    """pick_kp_parts → 配件匹配 digest（pn/name/category/qty/matched_spec）。"""
    from app.api.candidate_search import pick_kp_parts, kp_categories_for_type
    cats = args.get("categories")
    server_type = args.get("server_type_name")
    if not cats and server_type:
        cats = kp_categories_for_type(server_type)
    if not cats:
        return {"error": "缺 categories，且 server_type_name 无法推断标准配件类目"}
    picks = pick_kp_parts(
        categories=cats,
        keywords=args.get("keywords") or [],
        requirement_text=args.get("requirement_text") or "",
        representative_pick=args.get("representative_pick") or "min_price",
    )
    digest = [{
        "category": p.get("category") or "",
        "pn": p.get("pn") or "",
        "name": p.get("name") or "",
        "qty": p.get("qty") or 1,
        "matched_spec": p.get("matched_spec") or "",
        "unmatched": bool(p.get("unmatched")),
        "unmatched_reason": p.get("unmatched_reason") or "",
    } for p in picks]
    return {"count": len(digest), "parts": digest}


async def _tool_select_parts(args: dict) -> Any:
    """select_parts → 干净版配件匹配 digest（pn/name/category/qty，供 agent 编排）。"""
    from app.services.part_selector import select_parts
    _kw = args.get("keywords") or []
    picks = select_parts(
        categories=args.get("categories"),
        server_type_name=args.get("server_type_name"),
        search=args.get("search") or (_kw[0] if _kw and isinstance(_kw, list) else None),
        qty_map=args.get("qty_map"),
        search_map=args.get("search_map"),
        representative_pick=args.get("representative_pick") or "min_price",
    )
    if not picks:
        return {"count": 0, "parts": [], "note": "无品类/无常可配，请补 categories 或 server_type_name"}
    digest = [{
        "category": p.get("category") or "",
        "pn": p.get("pn") or "",
        "name": p.get("name") or "",
        "qty": p.get("qty") or 1,
        "matched_spec": p.get("matched_spec") or "",
        "unit_price": float(p.get("unit_price") or 0),
        "currency": p.get("currency") or "RMB",
        "unmatched": bool(p.get("unmatched")),
        "unmatched_reason": p.get("unmatched_reason") or "",
    } for p in picks]
    return {"count": len(digest), "parts": digest}


async def _tool_build_plan(args: dict) -> Any:
    """build_plan → 整机方案 digest（机型/成本/未匹配件，给 LLM 推荐理由用）。"""
    from app.api.candidate_search import build_plan
    baseline = args.get("baseline")
    kp_parts = args.get("kp_parts")
    if not baseline or kp_parts is None:
        return {"error": "缺 baseline 或 kp_parts"}
    plan = build_plan(baseline, kp_parts)
    return {
        "name": plan.get("name") or "",
        "model": plan.get("model") or "",
        "series": plan.get("series") or "",
        "form": plan.get("form") or "",
        "summary": plan.get("summary") or {},
        "unmatched": plan.get("unmatched") or [],
        "selling_points": _truncate(plan.get("selling_points") or "", 400),
    }


async def _tool_cost_breakdown(args: dict) -> Any:
    """cost_breakdown → 整机方案成本结构 digest（L6 底盘 / KP 关键件 / 总成本）。"""
    plan = args.get("plan")
    if not isinstance(plan, dict):
        return {"error": "缺 plan 对象"}
    summary = plan.get("summary") or {}
    if not isinstance(summary, dict):
        return {"error": "plan 缺少 summary 成本摘要"}
    if summary.get("total_cost") is None and summary.get("l6_cost") is None and summary.get("kp_cost") is None:
        return {"error": "plan 缺少成本摘要，请先通过 build_plan 生成方案"}
    return {
        "name": plan.get("name") or "",
        "model": plan.get("model") or "",
        "series": plan.get("series") or "",
        "form": plan.get("form") or "",
        "cost": {
            "l6_cost": summary.get("l6_cost"),
            "kp_cost": summary.get("kp_cost"),
            "total_cost": summary.get("total_cost"),
            "currency": summary.get("currency") or "RMB",
            "rates": summary.get("rates") or {},
        },
        "parts_count": summary.get("parts_count"),
        "kp_count": summary.get("kp_count"),
        "unmatched_count": summary.get("unmatched_count"),
        "unmatched": plan.get("unmatched") or [],
    }


async def _tool_quote_draft(args: dict) -> Any:
    """quote_draft → 整机方案报价草稿 digest（基准成本 / 建议毛利 / 含税报价）。"""
    plan = args.get("plan")
    if not isinstance(plan, dict):
        return {"error": "缺 plan 对象"}
    summary = plan.get("summary") or {}
    if not isinstance(summary, dict):
        return {"error": "plan 缺少 summary 成本摘要"}
    total_cost = float(summary.get("total_cost") or 0)
    if total_cost <= 0:
        return {"error": "plan 缺少有效总成本，请先通过 build_plan 生成方案"}
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            margin_rate = float(repo.get_value("profit_margin", 0.1) or 0.1)
        finally:
            repo.close()
    except Exception:
        margin_rate = 0.1
    return {
        "draft": {
            "name": f"方案-{plan.get('name') or plan.get('model') or '未命名'}",
            "model": plan.get("model") or "",
            "series": plan.get("series") or "",
            "form": plan.get("form") or "",
            "base_cost": round(total_cost, 2),
            "margin_pct": round(margin_rate * 100, 2),
            "final_price": round(total_cost * (1 + margin_rate), 2),
            "currency": summary.get("currency") or "RMB",
            "status": "draft",
            "note": "草稿未落库，需用户确认后才能转为正式报价单",
        },
        "cost": {
            "l6_cost": summary.get("l6_cost"),
            "kp_cost": summary.get("kp_cost"),
            "total_cost": summary.get("total_cost"),
        },
    }


def _search_cases_handler(case_cfg: dict):
    """构造 search_cases 工具 handler（闭包捕获用户可配的 case_source/top_k/match）。

    底层复用 CaseProvider（InternalBomCaseProvider 查 rules.bom_cases，只读不入库）。
    case_cfg 来自 llm_agent 节点 config（画布抽屉可改）：case_source / case_top_k / case_match。
    """
    top_k_default = int(case_cfg.get("case_top_k") or 2)
    provider_cfg = {
        "case_source": case_cfg.get("case_source", "internal"),
        "case_match": case_cfg.get("case_match", "tags_keyword"),
    }

    async def _h(args: dict) -> Any:
        from app.services.case_provider import get_case_provider
        provider = get_case_provider(provider_cfg)
        query = args.get("query") or args.get("requirement") or ""
        tags = args.get("tags") if isinstance(args.get("tags"), list) else None
        try:
            top_k = int(args.get("top_k") or top_k_default)
        except (TypeError, ValueError):
            top_k = top_k_default
        cases = provider.retrieve(query, tags=tags, top_k=top_k)
        return {"count": len(cases), "cases": cases}
    return _h

# ── 数据工具：query_cpq_data —— CPQ 业务数据查询（统计/分布/排行/趋势/重点商机）──
_DATA_PERIODS = ("week", "last_week", "month", "half_year", "year", "custom")
_DATA_FOCUS = ("all", "kpi", "platform", "chassis", "rank", "trend", "highlights", "profit", "opportunities")

def _normalize_period(value: Any) -> str:
    """仅接受数据工具枚举值；非法输入回退默认 week。"""
    raw = str(value or "week").strip()
    return raw if raw in _DATA_PERIODS else "week"

def _normalize_focus(value: Any) -> str:
    """仅接受数据工具枚举值；非法输入回退默认 all。"""
    raw = str(value or "all").strip()
    return raw if raw in _DATA_FOCUS else "all"


def _resolve_data_range(period: str, start: Any, end: Any):
    """把查询参数映射为 dashboard summary 的 (period, start, end)。"""
    from datetime import datetime, timedelta
    today = datetime.now()
    if period == "last_week":
        # 上周一 ~ 上周日（与驾驶舱「上周」预设算法一致）
        s = today - timedelta(days=today.weekday() + 7)
        e = s + timedelta(days=6)
        return "custom", s.strftime("%Y-%m-%d"), e.strftime("%Y-%m-%d")
    if period == "half_year":
        return "custom", (today - timedelta(days=180)).strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")
    if period == "custom":
        return "custom", start, end
    return period, None, None


def _fmt_data_text(summary: dict, focus: str = "all") -> str:
    """把 dashboard summary dict 转紧凑文本，作为查询结果给 LLM。"""
    if not isinstance(summary, dict):
        return "(无数据)"
    if focus == "profit":
        boxes = ((summary.get("charts") or {}).get("chart5") or {}).get("boxes") or []
        if not boxes:
            return "【机型利润率】暂无利润率样本。"
        lines = ["【机型利润率（按中位数降序，% 为报价单利润率百分点）】"]
        for b in boxes[:12]:
            name = b.get("name") or "未命名机型"
            med = b.get("median")
            n = b.get("n")
            lines.append(f"{name}：中位 {med}%（样本 {n}）" if med is not None else f"{name}：样本 {n}")
        return "\n".join(lines)
    label = summary.get("period_label") or ""
    kpi = summary.get("kpi") or {}
    parts = [f"【{label}】"]
    if focus in ("all", "kpi"):
        parts.append(
            f"核心指标：总商机 {kpi.get('total_opportunities', 0)}、总配置 {kpi.get('total_configs', 0)}、"
            f"新增商机 {kpi.get('new_opportunities', 0)}、新增配置 {kpi.get('new_configs', 0)}"
        )
    if focus in ("all", "platform"):
        plats = (summary.get("structure") or {}).get("platforms") or []
        if plats:
            parts.append("平台分布：" + "、".join(f"{p.get('name') or '未分类'} {p.get('count', 0)} 个" for p in plats))
    if focus in ("all", "chassis"):
        chassis = (summary.get("structure") or {}).get("chassis") or []
        if chassis:
            parts.append("机箱分布：" + "、".join(f"{c.get('name') or '未分类'} {c.get('count', 0)} 个" for c in chassis))
    if focus in ("all", "rank"):
        top = (summary.get("sales_rank") or {}).get("top") or []
        if top:
            parts.append("销售排行：" + "、".join(
                f"{t.get('name')} {t.get('count', 0)} 个" + (f"（成交 {t.get('won', 0)}）" if t.get("won") else "")
                for t in top
            ))
    if focus in ("all", "trend"):
        series = ((summary.get("charts") or {}).get("chart1") or {}).get("total_series") or []
        if series:
            parts.append(f"逐期趋势（{len(series)} 期）：" + "、".join(f"{d.get('date')}:{d.get('value')}" for d in series))
    return "\n".join(p for p in parts if p)


def _query_opportunities(args: dict) -> str:
    """查商机列表明细（最近 N 条，默认 20，上限 50）。"""
    try:
        limit = int(args.get("limit") or 0)
    except (TypeError, ValueError):
        limit = 0
    limit = max(1, min(limit or 20, 50))
    try:
        from app.repository.opportunity_repo import OpportunityRepository
        repo = OpportunityRepository()
        try:
            items, total = repo.list_opportunities(False, 1, limit, sort_by="updated_at", sort_order="desc")
        finally:
            repo.close()
    except Exception as e:  # noqa: BLE001
        logger.exception("商机列表查询失败")
        return f"商机列表查询失败：{e}"
    if not items:
        return "【商机列表】暂无商机。"
    lines = [f"【商机列表（最近 {len(items)} 条 / 共 {total} 条）】"]
    for it in items:
        lines.append(
            f"{it.get('customer_name') or '未命名'} / 销售 {it.get('sales_person') or '-'} / "
            f"{it.get('platform_type') or '-'} / {it.get('chassis_form') or '-'} / "
            f"{it.get('purchase_qty') or 0} 台 / {it.get('config_count') or 0} 配置 / "
            f"状态 {it.get('status') or '-'} / 结果 {it.get('result') or '-'}"
        )
    return "\n".join(lines)


def _query_cpq_data_sync(args: dict) -> str:
    """执行 CPQ 业务数据查询（同步 DB 调用，调用方经 asyncio.to_thread）。"""
    args = args or {}
    period = _normalize_period(args.get("period") or "week")
    focus = _normalize_focus(args.get("focus") or "all")
    start = args.get("start")
    end = args.get("end")
    if period not in _DATA_PERIODS:
        return f"不支持的周期：{period}（可选 {'/'.join(_DATA_PERIODS)}）"
    if focus not in _DATA_FOCUS:
        focus = "all"
    if focus == "highlights":
        limit = 0
        try:
            limit = int(args.get("limit") or 0)
        except (TypeError, ValueError):
            limit = 0
        if not limit:
            limit = 10
        limit = max(1, min(limit, 50))
        from app.api.dashboard import get_highlights
        rows = get_highlights(limit)
        if not rows:
            return "【近期重点商机】近半年内暂无重点商机。"
        lines = [
            f"{r['customer_name'] or '未命名'} / {r['platform_type'] or '-'} / {r['chassis_form'] or '-'} / "
            f"{r['purchase_qty'] or 0} 台 / {r['config_count']} 配置 / {r['result'] or '-'}"
            for r in rows
        ]
        return f"【近期重点商机（近半年，按台数 Top {len(rows)}）】\n" + "\n".join(lines)
    if focus == "profit":
        # 利润率不限周期（chart5 取全量利润样本），period 仅作占位
        from app.api.dashboard import get_dashboard_summary
        summary = get_dashboard_summary(period="month", start=None, end=None)
        return _fmt_data_text(summary, "profit")
    if focus == "opportunities":
        return _query_opportunities(args)
    if period == "custom" and (not start or not end):
        return "自定义区间需要同时提供 start 与 end（YYYY-MM-DD）"
    rp, rs, re = _resolve_data_range(period, start, end)
    try:
        from app.api.dashboard import get_dashboard_summary
        summary = get_dashboard_summary(period=rp, start=rs, end=re)
    except Exception as e:  # noqa: BLE001 —— 查询结果要给 LLM 看，异常转文本
        logger.exception("query_cpq_data 查询失败")
        return f"统计查询失败：{e}"
    return _fmt_data_text(summary, focus)


async def _tool_query_cpq_data(args: dict) -> Any:
    """query_cpq_data 工具 handler：查 CPQ 业务数据（周期统计/分布/排行/趋势/重点商机）。"""
    return await asyncio.to_thread(_query_cpq_data_sync, args or {})





# ── 服务器机型只读工具：真实读取 server_types / server_models ──

async def _server_catalog_repo():
    from app.repository.server_catalog_repo import ServerCatalogRepository
    return ServerCatalogRepository()


async def _tool_list_server_types(args: dict) -> Any:
    """list_server_types -> 服务器类型目录 digest。"""
    repo = await _server_catalog_repo()
    types = await asyncio.to_thread(repo.list_types)
    digest = [{
        "id": t.get("id"),
        "name": t.get("name") or "",
        "description": _truncate(t.get("description") or "", 300),
    } for t in types]
    return {"count": len(digest), "server_types": digest}


async def _tool_list_server_models(args: dict) -> Any:
    """list_server_models -> 机型目录 digest（名称/系列/形态/盘位/状态）。"""
    repo = await _server_catalog_repo()
    type_id = args.get("server_type_id")
    try:
        if type_id not in (None, ""):
            type_id = int(type_id)
    except (TypeError, ValueError):
        return {"error": "server_type_id 必须是整数"}
    models = await asyncio.to_thread(
        repo.list_models,
        type_id=type_id,
        series=args.get("series"),
        form=args.get("form"),
        published_only=bool(args.get("published_only")),
    )
    digest = []
    for m in models:
        bc = m.get("base_config") or {}
        digest.append({
            "id": m.get("id"),
            "name": m.get("name") or "",
            "server_type_id": m.get("server_type_id"),
            "use": m.get("use") or "",
            "description": _truncate(m.get("description") or "", 300),
            "lifecycle_status": m.get("lifecycle_status") or "",
            "is_published": bool(m.get("is_published")),
            "series": bc.get("series") or "",
            "form": bc.get("form") or "",
            "bays": bc.get("bays"),
        })
    return {"count": len(digest), "server_models": digest}


async def _tool_get_server_model(args: dict) -> Any:
    """get_server_model -> 单个机型详情 digest（含产品内容/配置变体）。"""
    raw_id = args.get("server_model_id") or args.get("id")
    if raw_id in (None, ""):
        return {"error": "缺 server_model_id"}
    try:
        model_id = int(raw_id)
    except (TypeError, ValueError):
        return {"error": "server_model_id 必须是整数"}
    repo = await _server_catalog_repo()
    m = await asyncio.to_thread(repo.get_model, model_id)
    if not m:
        return {"error": f"未找到机型: {model_id}"}
    bc = m.get("base_config") or {}
    configs = m.get("configs") or []
    import json
    pc = m.get("product_content")
    product_content_text = None
    if pc is not None:
        try:
            product_content_text = _truncate(json.dumps(pc, ensure_ascii=False), 1200)
        except Exception:
            product_content_text = _truncate(str(pc), 1200)
    return {
        "id": m.get("id"),
        "name": m.get("name") or "",
        "server_type_id": m.get("server_type_id"),
        "use": m.get("use") or "",
        "description": _truncate(m.get("description") or "", 800),
        "lifecycle_status": m.get("lifecycle_status") or "",
        "is_published": bool(m.get("is_published")),
        "series": bc.get("series") or "",
        "form": bc.get("form") or "",
        "bays": bc.get("bays"),
        "product_content_text": product_content_text,
        "configs": [{
            "id": c.get("id"),
            "name": c.get("name") or "",
            "series": c.get("series") or "",
            "form": c.get("form") or "",
            "bays": c.get("bays"),
        } for c in configs],
    }


_SERVER_TYPE_WRITE_FIELDS = {"name", "description", "sort_order", "showcase_config"}
_SERVER_MODEL_WRITE_FIELDS = {
    "name", "server_type_id", "base_config_id", "sort_order",
    "description", "image_url", "lifecycle_status", "product_content", "is_published",
}
_LIFECYCLE_STATUSES = {"new", "active", "eol", "discontinued"}


def _server_type_update_payload(args: dict) -> dict:
    updates = {k: args[k] for k in _SERVER_TYPE_WRITE_FIELDS if k in args and args[k] is not None}
    if "name" in updates and not str(updates["name"]).strip():
        raise ValueError("name 不能为空")
    if "sort_order" in updates:
        try:
            updates["sort_order"] = int(updates["sort_order"])
        except (TypeError, ValueError):
            raise ValueError("sort_order 必须是整数")
    if not updates:
        raise ValueError("没有可更新的服务器类型字段")
    return updates


def _server_model_update_payload(args: dict) -> dict:
    updates = {k: args[k] for k in _SERVER_MODEL_WRITE_FIELDS if k in args and args[k] is not None}
    if "name" in updates and not str(updates["name"]).strip():
        raise ValueError("name 不能为空")
    for key in ("server_type_id", "base_config_id", "sort_order"):
        if key in updates:
            try:
                updates[key] = int(updates[key])
            except (TypeError, ValueError):
                raise ValueError(f"{key} 必须是整数")
    if "lifecycle_status" in updates and updates["lifecycle_status"] not in _LIFECYCLE_STATUSES:
        raise ValueError("lifecycle_status 只能是 new/active/eol/discontinued")
    if "product_content" in updates and not isinstance(updates["product_content"], (dict, list)):
        raise ValueError("product_content 必须是对象或数组")
    if not updates:
        raise ValueError("没有可更新的机型字段")
    return updates


async def _tool_update_server_type(args: dict) -> Any:
    """update_server_type -> 生成服务器类型/产品系列内容草稿，不直接落库。"""
    raw_id = args.get("server_type_id") or args.get("id")
    if raw_id in (None, ""):
        return {"error": "缺 server_type_id"}
    try:
        type_id = int(raw_id)
    except (TypeError, ValueError):
        return {"error": "server_type_id 必须是整数"}
    try:
        updates = _server_type_update_payload(args)
    except ValueError as e:
        return {"error": str(e)}
    repo = await _server_catalog_repo()
    before = await asyncio.to_thread(repo.get_type, type_id)
    if not before:
        return {"error": f"服务器类型不存在: {type_id}"}
    return {
        "server_type_id": type_id,
        "updates": updates,
        "before": {
            "id": before.get("id"),
            "name": before.get("name") or "",
            "description": _truncate(before.get("description") or "", 300),
        },
        "message": "已生成服务器类型/产品系列内容草稿，等待审批后落库",
    }


async def _tool_update_server_model(args: dict) -> Any:
    """update_server_model -> 生成机型内容草稿，不直接落库。"""
    raw_id = args.get("server_model_id") or args.get("id")
    if raw_id in (None, ""):
        return {"error": "缺 server_model_id"}
    try:
        model_id = int(raw_id)
    except (TypeError, ValueError):
        return {"error": "server_model_id 必须是整数"}
    try:
        updates = _server_model_update_payload(args)
    except ValueError as e:
        return {"error": str(e)}
    repo = await _server_catalog_repo()
    before = await asyncio.to_thread(repo.get_model, model_id)
    if not before:
        return {"error": f"机型不存在: {model_id}"}
    return {
        "server_model_id": model_id,
        "updates": updates,
        "before": {
            "id": before.get("id"),
            "name": before.get("name") or "",
            "server_type_id": before.get("server_type_id"),
            "lifecycle_status": before.get("lifecycle_status") or "",
            "is_published": bool(before.get("is_published")),
        },
        "message": "已生成机型内容草稿，等待审批后落库",
    }



# ── 工具元数据全集（name/description/parameters + handler）—— 画布可勾选启用 ──
_TOOL_SPECS = {
    "select_models": {
        "category": "selection",
        "data_sources": ["candidate_search"],
        "default_enabled": True,
        "description": ("根据服务器需求挑选在售机型基准配置候选，返回候选清单"
                        "（名称/系列/形态/盘位数/卖点）。当能确定服务器类型/形态或系列时调用。"
                        "形态(1U/2U/4U)或系列时调用，用于锁定机型。"),
        "parameters": {
            "type": "object",
            "properties": {
                "server_type_name": {"type": "string", "description": "服务器类型全名（从在售类型清单选，不确定可省略）"},
                "form": {"type": "string", "description": "机箱形态 1U/2U/4U；不确定可省略"},
                "series": {"type": "string", "description": "产品系列 Orion/Polaris/Intel；不确定可省略"},
                "usage": {"type": "string", "description": "用途/场景关键词，如 web/数据库/虚拟化"},
            },
        },
        "handler": _tool_select_models,
    },
    "select_parts": {
        "category": "selection",
        "data_sources": ["kp_price"],
        "default_enabled": False,
        "description": ("按指定配件类目从配件库挑代表件（CPU/内存/硬盘/GPU/网卡等），返回料号/型号/单价/数量。"
                        "要精确某型号或规格时传 search 关键词；同一类目可多次调用换关键词。"),
        "parameters": {
            "type": "object",
            "properties": {
                "categories": {"type": "array", "items": {"type": "string"}, "description": "要匹配的配件类目，如 CPU/GPU/Memory/HDD/SSD/NIC"},
                "server_type_name": {"type": "string", "description": "服务器类型全名（据此推断标准配件类目）"},
                "search": {"type": "string", "description": "型号/规格关键词，如 RTX 5090 / 8C / 64G"},
                "qty_map": {"type": "object", "description": "每类目数量，如 {CPU:2, Memory:8, HDD/SSD:4}"},
                "search_map": {"type": "object", "description": "按类目给关键词，如 {CPU:Xeon, Memory:DDR5, GPU:RTX 5090}"},
                "representative_pick": {"type": "string", "description": "min_price/max_price/first，默认 min_price"},
            },
        },
        "handler": _tool_select_parts,
    },
    "pick_kp_parts": {
        "category": "selection",
        "data_sources": ["kp_price"],
        "default_enabled": True,
        "description": ("为指定机型类型匹配合适的 CPU/内存/硬盘/GPU/网卡等关键配件，"
                        "返回每类一件代表件的料号/规格/数量。需先确定服务器类型或类目。"),
        "parameters": {
            "type": "object",
            "properties": {
                "server_type_name": {"type": "string", "description": "服务器类型全名（据此推断标准配件类目）"},
                "categories": {"type": "array", "items": {"type": "string"}, "description": "要匹配的配件类目，如 CPU/GPU/Memory/HDD/NIC"},
                "keywords": {"type": "array", "items": {"type": "string"}, "description": "需求里的型号/规格关键词"},
                "requirement_text": {"type": "string", "description": "原始需求文本（用于规格/数量解析）"},
            },
        },
        "handler": _tool_pick_kp_parts,
    },
    "build_plan": {
        "category": "selection",
        "data_sources": ["bom", "kp_price"],
        "default_enabled": True,
        "description": ("把一个机型基准配置 + 配件清单组合成整机方案，返回机型名/总成本/未匹配件清单。"
                        "用于预估方案成本与完整性。"),
        "parameters": {
            "type": "object",
            "properties": {
                "baseline": {"type": "object", "description": "select_models 返回的某个候选机型（含 id/name/series/form 等）"},
                "kp_parts": {"type": "array", "items": {"type": "object"}, "description": "pick_kp_parts 返回的配件清单"},
            },
            "required": ["baseline", "kp_parts"],
        },
        "handler": _tool_build_plan,
    },
    "cost_breakdown": {
        "category": "cost",
        "data_sources": ["bom", "kp_price", "cost"],
        "default_enabled": False,
        "description": ("拆解一个整机方案的成本结构，返回 L6 底盘成本、KP 关键件成本、总成本、"
                        "数量与未匹配件。回答成本/成本明细/成本差异问题时调用；plan 必须是 build_plan 输出的方案对象。"),
        "parameters": {
            "type": "object",
            "properties": {
                "plan": {"type": "object", "description": "build_plan 返回的方案对象，需包含 summary.l6_cost / kp_cost / total_cost"},
            },
            "required": ["plan"],
        },
        "handler": _tool_cost_breakdown,
    },
    "quote_draft": {
        "category": "quote",
        "approval_required": True,
        "data_sources": ["quotation", "opportunities", "bom", "kp_price", "cost"],
        "default_enabled": False,
        "description": ("根据一个整机方案生成报价单草稿，返回基准成本、建议毛利率、含税报价和草稿状态。"
                        "报价/生成报价单草稿/解释价格构成时调用；plan 必须是 build_plan 输出的方案对象。"),
        "parameters": {
            "type": "object",
            "properties": {
                "plan": {"type": "object", "description": "build_plan 返回的方案对象，需包含 summary.total_cost"},
            },
            "required": ["plan"],
        },
        "handler": _tool_quote_draft,
    },
    "search_cases": {
        "category": "data",
        "data_sources": ["candidate_search", "bom"],
        "default_enabled": True,
        "description": ("检索【选型配置案例库】里与当前需求相似的历史案例（需求→机型/底盘配置 对照），"
                        "作为接地参考。需求模糊、或想参照同类已验证配置（如「8卡GPU AI服务器一般配什么底盘/电源」）时调用。"
                        "只读，绝不改案例库。"),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "用于检索的需求/场景文本"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "场景标签过滤（可选），如 ['AI','8卡GPU','Polaris','4U']"},
            },
        },
        # handler 由 build_tool_registry 按 case 配置（case_source/top_k/match）注入
        "handler": None,
    },
    "query_cpq_data": {
        "category": "data",
        "data_sources": ["opportunities", "dashboard"],
        "default_enabled": False,
        "description": ("查询 CPQ 平台的商机/配置业务数据：按周期（本周/上周/本月/近半年/今年/自定义区间）"
                        "或聚焦维度（核心指标/平台分布/机箱分布/销售排行/逐期趋势/近期重点商机/机型利润率/商机列表）返回真实数据。"
                        "回答业务数据类问题（商机数、配置数、平台/机箱分布、销售排行、趋势、重点大单、利润率、商机列表）时调用。"),
        "parameters": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "enum": list(_DATA_PERIODS),
                           "description": "周期，必须原样使用英文枚举：week=本周、last_week=上周（周一至周日）、month=本月、half_year=近半年（180 天）、year=今年（年初至今）、custom=自定义区间。‘8.16之前/从上周开始算’优先用 last_week；custom 必须同时给 start 和 end。"},
                "start": {"type": "string", "description": "自定义区间开始日期 YYYY-MM-DD（period=custom 时必填，其他周期不要传）"},
                "end": {"type": "string", "description": "自定义区间结束日期 YYYY-MM-DD（period=custom 时必填，其他周期不要传）"},
                "focus": {"type": "string", "enum": list(_DATA_FOCUS),
                          "description": "聚焦维度，必须原样使用英文枚举（默认 all）：kpi=核心指标、platform=平台分布、chassis=机箱分布、rank=销售排行、trend=逐期趋势、highlights=近期重点商机、profit=机型利润率、opportunities=商机列表、all=全量"},
                "limit": {"type": "integer", "description": "focus=highlights 时的重点商机条数（缺省 10，最多 50）"},
            },
            "required": ["period"],
        },
        "handler": _tool_query_cpq_data,
    },
    "list_server_types": {
        "category": "data",
        "data_sources": ["server_catalog"],
        "default_enabled": False,
        "description": "查询服务器类型目录，返回类型 id/名称/简介。回答“有哪些服务器类型”时调用。",
        "parameters": {"type": "object", "properties": {}},
        "handler": _tool_list_server_types,
    },
    "list_server_models": {
        "category": "data",
        "data_sources": ["server_catalog"],
        "default_enabled": False,
        "description": "查询服务器机型目录，可按服务器类型/系列/形态过滤，返回机型名称、系列、形态、盘位、生命周期状态。回答“有哪些服务器产品/机型”时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "server_type_id": {"type": "integer", "description": "服务器类型 id（可选）"},
                "series": {"type": "string", "description": "产品系列，如 Polaris/Orion/Intel（可选）"},
                "form": {"type": "string", "description": "机箱形态 1U/2U/4U（可选）"},
                "published_only": {"type": "boolean", "description": "是否只返回已发布机型，默认 false"},
            },
        },
        "handler": _tool_list_server_models,
    },
    "get_server_model": {
        "category": "data",
        "data_sources": ["server_catalog", "server_product_content"],
        "default_enabled": False,
        "description": "查询单个机型详情，返回名称/用途/描述/生命周期/系列形态盘位/产品介绍内容/配置变体。回答某个机型介绍或机型详情时调用。",
        "parameters": {
            "type": "object",
            "properties": {
                "server_model_id": {"type": "integer", "description": "机型 id（必填）"},
            },
            "required": ["server_model_id"],
        },
        "handler": _tool_get_server_model,
    },
    "update_server_type": {
        "category": "content",
        "approval_required": True,
        "data_sources": ["server_catalog"],
        "default_enabled": False,
        "description": "生成服务器类型/产品系列内容修改草稿，可改名称、描述、排序、3D 展示配置；不直接落库，需审批。",
        "parameters": {
            "type": "object",
            "properties": {
                "server_type_id": {"type": "integer", "description": "服务器类型/产品系列 id（必填）"},
                "name": {"type": "string", "description": "产品系列名称"},
                "description": {"type": "string", "description": "产品系列描述"},
                "sort_order": {"type": "integer", "description": "排序值"},
                "showcase_config": {"type": "object", "description": "3D 展示配置（glb_path/title/description/bullets/render）"},
            },
            "required": ["server_type_id"],
        },
        "handler": _tool_update_server_type,
    },
    "update_server_model": {
        "category": "content",
        "approval_required": True,
        "data_sources": ["server_catalog", "server_product_content"],
        "default_enabled": False,
        "description": "生成机型内容修改草稿，可改机型名、类型、生命周期、上架状态、图片、产品内容等；不直接落库，需审批。",
        "parameters": {
            "type": "object",
            "properties": {
                "server_model_id": {"type": "integer", "description": "机型 id（必填）"},
                "name": {"type": "string", "description": "机型名"},
                "server_type_id": {"type": "integer", "description": "服务器类型 id"},
                "base_config_id": {"type": "integer", "description": "主配置 id"},
                "sort_order": {"type": "integer", "description": "排序值"},
                "description": {"type": "string", "description": "机型简介"},
                "image_url": {"type": "string", "description": "产品主图 URL"},
                "lifecycle_status": {"type": "string", "enum": ["new", "active", "eol", "discontinued"], "description": "生命周期：new/active/eol/discontinued"},
                "is_published": {"type": "boolean", "description": "是否上架"},
                "product_content": {"type": "object", "description": "产品内容：tagline/overview/highlights/capabilities/specs/scenarios"},
            },
            "required": ["server_model_id"],
        },
        "handler": _tool_update_server_model,
    },
}

# 全部可用工具名（给画布抽屉候选 + 默认值用）
ALL_TOOL_NAMES = list(_TOOL_SPECS.keys())


def tool_required_data_sources(tool_ids: Optional[list] = None) -> list:
    """返回一组工具运行所需的数据域，用于 AI 同事绑定 Skill 时自动授权。"""
    sources: set = set()
    for tool_id in tool_ids or []:
        spec = _TOOL_SPECS.get(str(tool_id or "").strip())
        if not spec:
            continue
        sources.update(str(item) for item in (spec.get("data_sources") or []) if str(item))
    return sorted(sources)


def tool_requires_approval(tool_name: str) -> bool:
    """工具级审批开关：只有真实写库/出报价类工具才需要审批。

    Skill 内部的选择、匹配、BOM 组装、案例检索等草稿计算不在此列。
    """
    spec = _TOOL_SPECS.get(str(tool_name or "").strip())
    return bool(spec and spec.get("approval_required"))


def tool_catalog() -> List[dict]:
    """全量工具目录（无 handler），供前端「AI 工具」目录页与方案助手提参提示渲染。

    每个条目：name / category(selection|data) / description / parameters / default_enabled。
    """
    return [{
        "name": name,
        "category": spec.get("category") or "selection",
        "description": spec["description"],
        "parameters": spec["parameters"],
        "default_enabled": bool(spec.get("default_enabled", True)),
    } for name, spec in _TOOL_SPECS.items()]


def registered_tool_ids() -> List[str]:
    """返回 agent_tools 注册表里所有工具 ID（供能力 spec 校验 / 默认工具取用）。"""
    return list(_TOOL_SPECS.keys())


def build_tool_registry(config: dict, allowed_tool_ids: list = None, allowed_data_sources: list = None) -> ToolRegistry:
    """按节点 config 启用的工具集建 registry。

    config.enabled_tools: list[str] —— 启用的工具名（画布抽屉勾选）；
    未配置或空 → 默认启用全集（向后兼容）。
    allowed_tool_ids: list[str] —— AI 同事的 tool_ids 白名单；传 None 不限制，
    传 [] 表示同事不允许任何工具。
    """
    cfg = config or {}
    # 默认全集 = default_enabled=True 的工具；default_enabled=False（如 query_cpq_data）
    # 不进任何节点默认配置，需要时由调用方显式启用（避免改变现有推理流行为）
    enabled = cfg.get("enabled_tools") or [
        name for name, spec in _TOOL_SPECS.items() if spec.get("default_enabled", True)
    ]
    if allowed_tool_ids is not None:
        allowed_set = set(allowed_tool_ids)
        enabled = [name for name in enabled if name in allowed_set]
    reg = ToolRegistry(allowed_data_sources=allowed_data_sources)
    for name in enabled:
        spec = _TOOL_SPECS.get(name)
        if not spec:
            continue
        handler = spec["handler"]
        # search_cases 需要用户可配的 case 参数（case_source/top_k/match）→ 闭包注入
        if name == "search_cases":
            handler = _search_cases_handler(cfg)
        if handler is None:
            continue
        reg.register(name, spec["description"], spec["parameters"], handler, data_sources=spec.get("data_sources"))
    return reg
