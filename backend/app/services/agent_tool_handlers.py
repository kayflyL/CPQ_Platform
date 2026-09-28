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
                "note": "无匹配机型（收窄条件：server_type/form/usage 关键词）"}
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
    from app.services.skill_tools_misc import tool_query_data
    return await asyncio.to_thread(tool_query_data, args or {})


async def _tool_opportunity_stats(args: dict) -> Any:
    """opportunity_stats → 商机统计口径工具（与商机线索页同一实现，报告数字唯一来源）。"""
    from app.services.opp_stats import compute_opp_stats
    _args = args or {}
    return await asyncio.to_thread(
        compute_opp_stats, str(_args.get("start") or ""), str(_args.get("end") or ""))


async def _tool_fill_requirement(args: dict) -> Any:
    """【需求分析流程工具】agent_fill 登记回合专用：大脑亲自把客户需求逐项落进线索登记表。

    普通对话回合不挂载这个工具（进任务前不填表）；落表语义确定性（默认只填空槽）。
    """
    from app.services.skill_tools_fill import tool_fill_requirement
    return tool_fill_requirement(args or {})


async def _tool_choose_model(args: dict) -> Any:
    """【统一模型工具】需求分析流程内锁定候选机，或浏览在售机型候选。

    需求分析流程内 model_reason：带 model/model_id 从引擎候选池锁定一个机型（接地，池外拒绝）。
    同事对话/参考：带 usage/server_type_name/series/form 浏览在售机型候选 digest。
    """
    if (args or {}).get("model") or (args or {}).get("model_id"):
        from app.services.skill_tools_model import tool_select_model
        return tool_select_model(args or {})
    return await _tool_select_models(args or {})


async def _tool_query_parts(args: dict) -> Any:
    """【需求分析流程工具】query_parts → 配件库候选精确检索（按类目+结构化规格/关键词收窄，或多行批量召回）。"""
    from app.services.skill_tools_kp import tool_query_parts
    return await asyncio.to_thread(tool_query_parts, args or {})


async def _tool_inspect_parts(args: dict) -> Any:
    """【需求分析流程工具】inspect_parts → 统一只读钻取入口（action=part/row/category/grep）。"""
    from app.services.skill_tools_open import tool_inspect_parts
    return await asyncio.to_thread(tool_inspect_parts, args or {})


async def _tool_select_parts(args: dict) -> Any:
    """【需求分析流程工具】select_parts → 把大脑点名的料号按「类目+料号名」回库核对后锁定（核对不上就拒）。"""
    from app.services.skill_tools_select import tool_select_parts
    return await asyncio.to_thread(tool_select_parts, args or {})


async def _tool_ask_user(args: dict) -> Any:
    """【需求分析流程工具】大脑回合专用：把需要客户决策的问题升格为结构化选项卡。

    大脑自由文本提问没有交互通道（2026-09-05 实测：问了但没卡可点）；此工具把
    问题+选项登记进回合上下文，由 skill_chat 在引擎结束后统一弹卡。
    """
    from app.services.skill_tools_misc import tool_ask_user
    return tool_ask_user(args or {})


async def _tool_catalog_search(args: dict) -> Any:
    """在售目录查询（推荐的事实来源）：types / models。"""
    from app.services.skill_tools_misc import tool_catalog_search
    return tool_catalog_search(args or {})


async def _tool_colleague_memory(args: dict) -> Any:
    """同事长期记忆自管（写入者=对话者）：list / view / write / retire 四动作。"""
    from app.services.colleague_memory_service import tool_memory_action
    return await asyncio.to_thread(tool_memory_action, args or {})
