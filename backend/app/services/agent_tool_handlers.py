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


async def _tool_suggest_workflow(args: dict) -> Any:
    """suggest_workflow → 记录一次工作流发起建议（卡面数据随回合消息落库，用户点击确认后才发起）。

    可发起清单由回合层摆进 TOOL_CTX（workflow_offers，来自该角色的 workflow skill 绑定）；
    建议写回 TOOL_CTX（workflow_suggestion），由 colleague_turn_runners 在回合收尾随消息落库。
    """
    from app.services.skill_tool_context import TOOL_CTX
    ctx = TOOL_CTX.get() if isinstance(TOOL_CTX.get(), dict) else {}
    offers = ctx.get("workflow_offers") if isinstance(ctx.get("workflow_offers"), list) else []
    key = str((args or {}).get("workflow_key") or "").strip()
    requirement = str((args or {}).get("requirement_text") or "").strip()
    offer = next((o for o in offers if isinstance(o, dict) and str(o.get("key") or "").strip() == key), None)
    if not offer:
        return {"ok": False, "error": "workflow_key 不在当前角色可发起的工作流清单内",
                "available": [str(o.get("key") or "") for o in offers if isinstance(o, dict)]}
    if not requirement:
        return {"ok": False, "error": "requirement_text 缺失：填对话中用户需求的原文整理"}
    suggestion = {
        "workflow_key": key,
        "name": str(offer.get("name") or key),
        "requirement_text": requirement[:2000],
        "reason": str((args or {}).get("reason") or "").strip()[:200],
    }
    ctx["workflow_suggestion"] = suggestion
    return {"ok": True, **suggestion}


# ── 写操作工具：方案助手/同事代办业务事务（身份=TOOL_CTX.user，高危走两阶段确认）──

async def _with_consent_query(result: Any, tool: str) -> Any:
    """写动作的授权问询（consent）：needs_confirmation 结果由调和器/本包装立一个
    consent 型 HumanQuery（问题=待确认操作，选项=确认执行/取消，action 绑定工具）。

    用户点选=结构化 HumanAnswer 按 query_id 回流；确认直达执行（transaction_turn
    _execute_pending）。TOOL_CTX.defer_user_emission=true 时（事务工作流轮壳）此处
    只返回不发射——问询由轮壳在**大脑答案落库之后**统一发射（先解释后问；
    工具瞬间发射会跑到解释文本前面，2026-10-22 用户实测顺序颠倒）。
    去重：待确认记录的 query_opened 标记（R1 投影幂等，同参重发只发一次问）。"""
    if not isinstance(result, dict) or not result.get("needs_confirmation"):
        return result

    from app.services.skill_tool_context import TOOL_CTX
    ctx = TOOL_CTX.get() if isinstance(TOOL_CTX.get(), dict) else {}
    thread_id = str(ctx.get("thread_id") or "")
    if not thread_id:
        return result
    if ctx.get("defer_user_emission"):
        return result
    if not tool:
        return result
    from app.services.agent_write_confirm import mark_query_opened, query_opened
    if query_opened(thread_id, tool):
        return result
    from app.services import human_query as hq
    try:
        await hq.open_query_and_announce(
            thread_id, kind="consent",
            title="待确认操作",
            detail=_preview_detail(result.get("preview")),
            options=[{"label": "确认执行", "description": "按上述内容执行"},
                     {"label": "取消", "description": "不执行，可继续调整"}],
            action={"tool": tool}, role_key=ctx.get("role_key"))
        mark_query_opened(thread_id, tool)
    except hq.ContractError:
        pass  # 已有开放问题：调和器末扫会补发，这里不挤第二个
    return result


def _preview_detail(preview: Any) -> str:
    """preview 字典 → 问题正文明细行（宽列表走大脑的文本回复，不挤进问询）。"""
    if not isinstance(preview, dict):
        return ""
    return "\n".join(f"{k}：{v}" for k, v in preview.items()
                     if not isinstance(v, (list, dict)))


async def _tool_create_opportunity(args: dict) -> Any:
    """create_opportunity → 建商机（与商机列表页「新建」同一路由函数，权限/归属同源）。"""
    from app.services.skill_tools_write import tool_create_opportunity
    return await asyncio.to_thread(tool_create_opportunity, args or {})


async def _tool_save_requirement_draft(args: dict) -> Any:
    """save_requirement_draft → 需求草稿落库（与门户需求草稿端点同一路由函数）。"""
    from app.services.skill_tools_write import tool_save_requirement_draft
    return await asyncio.to_thread(tool_save_requirement_draft, args or {})


async def _tool_import_cost_sheet(args: dict) -> Any:
    """import_cost_sheet → 商机附件里的成本表解析成成本核算草稿（解析/落库/流程卡与页面上传同源）。
    落库段有两阶段确认（先看后落）：needs_confirmation 经 _with_confirm_card 落卡，
    事务轮壳 defer 时由轮壳在答案后统一落。"""
    from app.services.skill_tools_write import tool_import_cost_sheet
    return await _with_consent_query(
        await asyncio.to_thread(tool_import_cost_sheet, args or {}), tool="import_cost_sheet")


async def _tool_submit_cost_sheet(args: dict) -> Any:
    """submit_cost_sheet → 提交成本表并转报价草稿（提交/影子建单/推进/通知全走页面同一路由函数）。"""
    from app.services.skill_tools_write import tool_submit_cost_sheet
    return await _with_consent_query(
        await asyncio.to_thread(tool_submit_cost_sheet, args or {}), tool="submit_cost_sheet")


async def _tool_set_quote_margin(args: dict) -> Any:
    """set_quote_margin → 报价单统一加价（价格门控 TOOL_CTX.price_ok，重算口径与工作台一致）。"""
    from app.services.skill_tools_write import tool_set_quote_margin
    return await _with_consent_query(
        await asyncio.to_thread(tool_set_quote_margin, args or {}), tool="set_quote_margin")


async def _tool_ask_user(args: dict) -> Any:
    """ask_user → 向人提问（human-as-tool）：载荷即问题形状，系统渲染等待回答。
    事务轮壳 defer 时问题由壳在答案后统一发射（先解释后问）。"""
    from app.services.skill_tools_write import tool_ask_user
    return await _with_user_query(
        await asyncio.to_thread(tool_ask_user, args or {}))


async def _with_user_query(result: Any) -> Any:
    """向人提问发射（choice/form）：user_query 载荷立一个开放问题（human_query 协议）。
    TOOL_CTX.defer_user_emission=true（事务轮壳）时只返回不发射——问题由轮壳在
    答案落库之后统一发射（先解释后问）。每线程至多一个开放问题（协议不变量），
    已有开放问题时把契约错误作为工具结果还给大脑转述。"""
    if not isinstance(result, dict) or not result.get("user_query"):
        return result
    from app.services.skill_tool_context import TOOL_CTX
    ctx = TOOL_CTX.get() if isinstance(TOOL_CTX.get(), dict) else {}
    thread_id = str(ctx.get("thread_id") or "")
    if not thread_id or ctx.get("defer_user_emission"):
        return result
    from app.services import human_query as hq
    try:
        await hq.open_query_and_announce(thread_id, role_key=ctx.get("role_key"),
                                         **result["user_query"])
    except hq.ContractError as exc:
        return {"ok": False, "error": str(exc)}
    return result


async def _tool_share_quote(args: dict) -> Any:
    """share_quote → 生成报价单分享链接（服务端渲染 xlsx，customer 视角一律拒绝）。"""
    from app.services.skill_tools_write import tool_share_quote
    return await asyncio.to_thread(tool_share_quote, args or {})


async def _tool_import_bom_scheme(args: dict) -> Any:
    """import_bom_scheme → 方案表落位（解析结构表落方案草稿，不要求价格列）。"""
    from app.services.skill_tools_write import tool_import_bom_scheme
    return await asyncio.to_thread(tool_import_bom_scheme, args or {})


async def _tool_derive_cost_from_scheme(args: dict) -> Any:
    """derive_cost_from_scheme → 由方案表推导成本表草稿（库价填充，方案推进到成本核算）。"""
    from app.services.skill_tools_write import tool_derive_cost_from_scheme
    return await asyncio.to_thread(tool_derive_cost_from_scheme, args or {})


async def _tool_set_cost_prices(args: dict) -> Any:
    """set_cost_prices → 聊天补价回写成本草稿行（页面同源保存；缺价闸的回价通道之一）。"""
    from app.services.skill_tools_write import tool_set_cost_prices
    return await asyncio.to_thread(tool_set_cost_prices, args or {})
