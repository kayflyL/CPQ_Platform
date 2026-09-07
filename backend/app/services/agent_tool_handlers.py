# -*- coding: utf-8 -*-
"""agent_tool_handlers —— 工具 handler 适配层。只做参数适配 + 结果 digest，业务实现来自 domain services。"""
import asyncio
from typing import Any, Dict, List, Optional
from app.services.agent_tool_registry import _truncate

# ── 工具 handler：把现有确定性函数包成 agent 工具（结果压成 digest） ──────

async def _tool_select_models(args: dict) -> Any:
    """select_models → 候选机型 digest（名称/系列/形态/盘位/卖点，给 LLM 推理）。"""
    from app.services.model_candidates import select_models
    _limit_arg = args.get("limit")
    try:
        limit = int(_limit_arg) if _limit_arg not in (None, "", 0) else None
    except (TypeError, ValueError):
        limit = None
    baselines = select_models(
        usage=args.get("usage") or "",
        server_type_name=args.get("server_type_name"),
        series=args.get("series"),
        form=args.get("form"),
        limit=limit,
    )
    if not baselines:
        return {"count": 0, "candidates": [],
                "note": "无匹配机型；建议放宽 server_type/form，或补 usage 关键词"}
    note = (baselines[0].get("fallback_note") or "")
    digest = [{
        "config_id": b.get("id"),
        "server_model_id": b.get("server_model_id"),
        "name": b.get("name") or "",
        "server_type_name": b.get("server_type_name") or "",
        "series": b.get("series") or "",
        "form": b.get("form") or "",
        "bays": b.get("bays"),
        "recommend_level": b.get("recommend_level") or "",
        "selling_points": _truncate(b.get("selling_points") or "", 300),
        "match_stage": b.get("match_stage"),
        "fallback_note": b.get("fallback_note") or "",
    } for b in baselines]
    result = {"count": len(digest), "candidates": digest, "note": note}
    if args.get("include_raw"):
        result["raw"] = baselines
    return result


async def _tool_list_kp_categories(args: dict) -> Any:
    """list_kp_categories -> 真实配件类目目录（规则键/库类目/数量/别名）。"""
    from app.services.part_selector import list_kp_categories
    cats = list_kp_categories()
    return {"count": len(cats), "categories": cats}


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
        cpu=args.get("cpu"),
        memory=args.get("memory"),
        storage=args.get("storage"),
        gpu=args.get("gpu"),
        raid=args.get("raid"),
        psu=args.get("psu"),
        nic=args.get("nic"),
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
        "request_spec": p.get("request_spec") or "",
        "grounded_spec": p.get("grounded_spec") or "",
        "spec_mismatch": bool(p.get("spec_mismatch")),
    } for p in picks]
    from app.services.skill_contracts import grounding_envelope
    return {"count": len(digest), "parts": digest, "grounding": grounding_envelope(digest)}


async def _tool_resolve_part_alias(args: dict) -> Any:
    """resolve_part_alias → 语义别名/同义术语 → 料号候选（兆芯→KH50000 等）。"""
    from app.services.part_selector import resolve_part_alias
    return await asyncio.to_thread(resolve_part_alias, args.get("term"), args.get("category"))


async def _tool_compose_memory(args: dict) -> Any:
    """compose_memory → 内存容量组合求解（128G → 64G×2 / 32G×4）。"""
    from app.services.part_selector import compose_memory
    total = args.get("total_gb")
    if total in (None, ""):
        return {"error": "缺 total_gb"}
    try:
        total = int(total)
    except (TypeError, ValueError):
        return {"error": "total_gb 必须是整数"}
    return await asyncio.to_thread(compose_memory, total, args.get("slots"))


async def _tool_build_plan(args: dict) -> Any:
    """build_plan → 整机方案 digest（机型/成本/未匹配件，给 LLM 推荐理由用）。"""
    from app.services.plan_builder import build_plan
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

# ── 数据原语：query_data —— 数据边界内只读 SELECT（权限在 data_boundary.execute_read）──

async def _tool_query_data(args: dict) -> Any:
    """query_data → 只读 SELECT（白名单表/只读事务/行数上限/敏感列脱敏，全在边界层物理强制）。"""
    from app.services.skill_chat import tool_query_data
    return await asyncio.to_thread(tool_query_data, args or {})


async def _server_catalog_repo():
    from app.repository.server_catalog_repo import ServerCatalogRepository
    return ServerCatalogRepository()


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





# ── Skill 对话脑动作（实现在 skill_chat，经线程上下文取状态）──────────
async def _tool_submit_registration(args: dict) -> Any:
    """角色判断信息足够后提交登记表，触发配置引擎。"""
    from app.services.skill_chat import tool_submit_registration
    return tool_submit_registration(args or {})


async def _tool_fill_requirement(args: dict) -> Any:
    """【任务期工具】agent_fill 登记回合专用：大脑亲自把客户需求逐项落进线索登记表。

    普通对话回合不挂载这个工具（进任务前不填表）；落表语义确定性（默认只填空槽）。
    """
    from app.services.skill_chat import tool_fill_requirement
    return tool_fill_requirement(args or {})


async def _tool_select_model(args: dict) -> Any:
    """【任务期工具】model_reason 机型选配回合专用：大脑从引擎候选池锁定一个机型。

    接地（B2）：候选池由引擎确定性构建（登记表信号 × 在售目录），工具只接受池内
    型号（id/名称皆可命中），池外一律拒绝——大脑无权凭空指定机型。
    """
    from app.services.skill_chat import tool_select_model
    return tool_select_model(args or {})


async def _tool_select_kp_parts(args: dict) -> Any:
    """【任务期工具】kp_reason 配件选配回合专用：大脑把未匹配部件行批量锁定为库内真实料号。

    接地（B2，按需检索版）：只认 search_kp_parts 检索登记过的料号（服务端索引），
    索引外一律拒绝——大脑无权凭空指定料号。同步 DB 落 pick 走线程池，防慢查询堵死事件循环。
    """
    from app.services.skill_chat import tool_select_kp_parts
    return await asyncio.to_thread(tool_select_kp_parts, args or {})


async def _tool_search_kp_parts(args: dict) -> Any:
    """【任务期工具】kp_reason 配件选配回合专用：按类目+关键词检索配件库真实候选。

    按需检索（progressive disclosure）：大脑上下文只带行清单，候选逐行按需拉取；
    结果由服务端登记进检索索引（select 的接地取值域），价格按数据边界裁剪。
    同步 DB 检索走线程池，防慢查询堵死事件循环（300s/900s 超时兜底依赖循环能跑）。
    """
    from app.services.skill_chat import tool_search_kp_parts
    return await asyncio.to_thread(tool_search_kp_parts, args or {})


async def _tool_ask_user(args: dict) -> Any:
    """【任务期工具】大脑回合专用：把需要客户决策的问题升格为结构化选项卡。

    大脑自由文本提问没有交互通道（2026-09-05 实测：问了但没卡可点）；此工具把
    问题+选项登记进回合上下文，由 skill_chat 在引擎结束后统一弹卡。
    """
    from app.services.skill_chat import tool_ask_user
    return tool_ask_user(args or {})


async def _tool_catalog_search(args: dict) -> Any:
    """在售目录查询（推荐的事实来源）：types / models。"""
    from app.services.skill_chat import tool_catalog_search
    return tool_catalog_search(args or {})
