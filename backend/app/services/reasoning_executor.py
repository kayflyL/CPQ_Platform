"""推理流图驱动执行器（P2.3）—— 把硬编码线性 pipeline 改成图拓扑执行。

- Handler 注册表：按 node.type 分发（复用 normalize_text/extract_keywords/select_models/pick_kp_parts/build_plan）
- 拓扑 BFS：读 graph → 入口（in-degree=0）→ 遍历 → 每节点 broadcast step_start/step_done
- condition 节点：simpleeval 安全求值 → 选 sourceHandle 分支（静默路由，不广播 step_start）
- WS 协议不变（step_start/step_done/candidates_ready/pipeline_done），前端零改

任何异常由调用方（run_pipeline）兜底回退 _run_linear_fallback。
"""
import logging
import re
from typing import Any, Awaitable, Callable, Optional

from app.api.candidate_search import (select_models, pick_kp_parts, build_plan,
                           kp_categories_for_type, build_variant_signals)

logger = logging.getLogger(__name__)

try:
    from simpleeval import simple_eval
    HAS_SIMPLEEVAL = True
except ImportError:
    HAS_SIMPLEEVAL = False


BroadcastFn = Callable[[dict], Awaitable[None]]

# 死循环防护：反问最多 N 轮，超限强制 partial 走选型。
# 目录驱动引导正常 3 步（类型→机型→KP 格式）即可走完，6 是兜底保险（含反复改答案的情况）。
MAX_CLARIFY_ROUNDS = 6

def _resolve_budget_strategy(budget) -> str:
    """按 budget 规则返回 representative_pick（min_price/max_price）。给 match_kp 用。"""
    try:
        from app.repository.requirement_rule_repo import RequirementRuleRepository
        repo = RequirementRuleRepository()
        try:
            rules = repo.list_by_type("budget", status="active")
        finally:
            repo.close()
        for r in rules:
            rng = (r.get("body") or {}).get("range") or {}
            mn, mx = rng.get("min"), rng.get("max")
            if budget is None:
                if mn is None and mx is None:
                    return (r.get("body") or {}).get("strategy", {}).get("representative_pick", "min_price")
                continue
            if (mn is None or budget >= mn) and (mx is None or budget < mx):
                return (r.get("body") or {}).get("strategy", {}).get("representative_pick", "min_price")
    except Exception as e:
        logger.warning("读 budget 规则失败，回退 min_price: %s", e)
    return "min_price"


# ── 用户"放弃指定/用默认"类回答 ─────────────────────────
# chip 常见值：不确定 / 你推荐 / 还没定 / 越大越好 / 不限 …。命中视为该字段已按
# 默认处理，不再重复追问（目录驱动引导里也用它：答"你推荐"→ 走推荐类型/代表性机型）。
# 词表是业务内容，数据驱动：system_config.requirement_guide_words（可编辑，拒绝硬编码）。


def _is_default_reply(text: str) -> bool:
    """单条回答是否为"放弃指定/用默认"（不确定/你推荐/还没定/越大越好/不限…）。
    词表读 system_config.requirement_guide_words，读失败由 catalog_guide 回退常量。"""
    if not (text or "").strip():
        return False
    from app.services.catalog_guide import is_default_reply
    return is_default_reply(text)


def _llm_questions(ctx: dict) -> list:
    """取 LLM 主理解产出的一次性追问（缺失项列全）。LLM 未开/失败返回空。"""
    report = ctx.get("llm_report") or {}
    if report.get("reason") != "ok":
        return []
    return report.get("questions") or []


async def _ask_catalog_question(ctx: dict, broadcast: BroadcastFn,
                               extra_questions: Optional[list] = None) -> dict:
    """目录驱动引导的 ask_user / llm_ask（旧 workload/rebuttal 思路已删除，见 catalog_guide）。

    按会话 stage 生成问题：选项 100% 来自产品目录（l6.server_types / l6.server_models /
    该类型支持的 KP 品类套餐），不猜、不臆造。stage 推进由 run_pipeline 在每轮开始消费
    supplement 完成；这里只负责「发问 + 记录本轮推给客户的选项」。

    extra_questions：LLM 主理解（llm_understand）产出的一次性缺失项追问，追加到问题里
    （2026-08 P2：一次列出所有缺失项，不逐个问）。
    """
    import uuid
    from app.services.catalog_guide import build_question_with_catalog, load_ask_config
    stage = ctx.get("catalog_stage") or ""
    if stage == "done":  # 防御：正常 clarity_check 已放行，不会走到
        ctx["awaiting_input"] = False
        return {"question": "信息已足够，正在生成方案…", "skip": True}
    ask_cfg = load_ask_config(ctx.get("flow_configs"))
    question, options, offered, fmt = build_question_with_catalog(
        stage, ctx.get("catalog_state") or {}, ask_cfg, ctx.get("flow_configs"),
    )
    if extra_questions:
        qs = list(dict.fromkeys(str(q) for q in extra_questions if str(q).strip()))[:6]
        if qs:
            question = f"{question}\n\n请一并确认：{'；'.join(qs)}"
    reply_id = f"clr_{uuid.uuid4().hex[:12]}"
    # 记录本轮推给客户的选项 + 当前 stage（下轮选项匹配用）。
    # 首问（stage=""）落成 "type"：否则 run_pipeline 的「仅目录引导会话才推进」守卫
    # 因 stage 空而跳过推进，AI 关时目录引导会卡在第一问（2026-08 修）。
    _persist_stage = stage or "type"
    oid = ctx.get("opportunity_id")
    if oid:
        from app.services.requirement_intel_service import _persist_catalog_offer
        # 必须与会话读端同一 store（thread 会话/商机），否则目录 offer 写错地方、下轮推进读不到
        _persist_catalog_offer(oid, _persist_stage, offered, store=ctx.get("_session"))
    await broadcast({
        "type": "need_input",
        "reply_id": reply_id,
        "question": question,
        "missing_fields": ctx.get("missing_fields") or [],
        "options": options,
        "asked_fields": [],  # 目录引导不再按字段追问（旧 clarify_defaults 机制保留兼容）
        "round": ctx.get("clarify_round", 1),
        "clarity_capped": ctx.get("clarity_capped", False),
        "stage": stage,
        "format": fmt,  # KP 填写格式模板，前端展示引导
    })
    ctx["awaiting_input"] = True
    ctx["last_reply_id"] = reply_id
    return {"question": question, "reply_id": reply_id}


def _eval_condition(expr: str, ctx: dict) -> bool:
    """条件表达式安全求值（simpleeval 受限 AST，禁 import/attr）。
    变量白名单：series/form/categories/keywords。异常或无表达式默认 True。"""
    if not expr or not HAS_SIMPLEEVAL:
        return True
    ext = ctx.get("ext") or {}
    budget_val = ctx.get("budget")
    names = {
        "series": ext.get("series") or "",
        "form": ext.get("form") or "",
        "categories": ext.get("categories") or [],
        "keywords": ext.get("keywords") or [],
        # v3：明确度 + 预算（cond_clarity 等条件节点用）
        "clarity": ctx.get("clarity") or "partial",
        "clarity_capped": ctx.get("clarity_capped", False),
        "budget": budget_val if budget_val is not None else 0,
        "has_budget": budget_val is not None,
        "missing_fields": ctx.get("missing_fields") or [],
        # R29 流程重构：场景是否确定 + 系列是否已确认（confirm_series 产出）
        "scene_determined": bool(ctx.get("scene_determined")),
        "series_ready": bool(ctx.get("series_ready")),
        "confirmed_series": ctx.get("confirmed_series") or "",
        # 双路线分叉（route_fork 头部 / cond_audit 尾部）：全局 AI 开关 true→AI 路、false→本地路
        "llm_enabled": bool(ctx.get("llm_enabled")),
    }
    try:
        return bool(simple_eval(expr, names=names))
    except Exception as e:
        logger.warning("condition 求值失败（默认 True）expr=%r err=%s", expr, e)
        return True


def _extract_grounding(tool_calls_log: list) -> dict:
    """从 ReAct 工具调用日志提取 server_type/form/series 接地值。

    取【最后一次成功匹配（count>0）的 select_models 调用】的 args——agent 可能多轮试探
    （先宽后窄），最后一次成功的最准；全失败返回 {}（上层用 extract 的确定性 server_type 兜底）。
    """
    grounding: dict = {}
    for c in tool_calls_log or []:
        if c.get("name") != "select_models":
            continue
        result = c.get("result")
        count = result.get("count", 0) if isinstance(result, dict) else 0
        if not count:
            continue
        args = c.get("args") or {}
        if args.get("server_type_name"):
            grounding["server_type_name"] = args["server_type_name"]
        if args.get("form"):
            grounding["form"] = args["form"]
        if args.get("series"):
            grounding["series"] = args["series"]
    return grounding


async def _dispatch(ntype: str, ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """按节点 type 执行 handler，更新 ctx，返回 step_done payload。"""
    # 延迟 import 避免循环
    if ntype == "text_clean":
        # 文本清洗（2026-08 重构·合并单路）：轻量归一（去噪音/全角/表格行），AI 与规则共用前置；规则可配、白盒 report。
        from app.services.requirement_normalizer import normalize_text
        raw = ctx.get("requirement_text") or ""
        text, report = normalize_text(raw, config)
        ctx["normalized_text"] = text
        ctx["normalize_report"] = report
        return {"normalized": text, "report": report}

    if ntype == "normalize_input":
        # 需求输入规范化：格式归一 + 噪音过滤（规则来自节点 config，数据驱动）。
        # 输出 normalized_text 给 extract；report 白盒展示"归一了什么"。
        from app.services.requirement_normalizer import normalize_text
        raw = ctx.get("requirement_text") or ""
        text, report = normalize_text(raw, config)
        ctx["normalized_text"] = text
        ctx["normalize_report"] = report
        return {"normalized": text, "report": report}

    if ntype == "extract":
        # extract 正则理解路径已随 AI-first 改革删除（CHANGELOG [0.1.55-56]）。
        # 图里残留的 extract 节点静默跳过（不执行、不广播），兼容旧图数据。
        return None

    if ntype == "llm_agent":
        # P1：AI 路「需求理解」主节点（LLM 接管理解，替代 regex extract）。
        # = run_agent_understand：需求原文 → catalog 白名单锚定 → LLM 出 RequirementSlots
        #   （EXTRACT_ENHANCE_SCHEMA 收口）→ merge_into_ext 确定性合并 → ctx["ext"]。
        # 三道可靠性闸：catalog 白名单锚定 + merge 校验 + extract 确定性兜底（离线可跑）。
        # 取代旧版「确定性 extract + ReAct 接地」——需求理解不再是 regex，打地鼠从根上消失。
        # ReAct 接地降级为可选 escalation（config.escalate_grounding 默认关）：仅在 server_type 缺/弱时
        # 调 select_models 工具锁机型；catalog 白名单直抽够用时不动它（P1 靠白名单直抽）。
        text = ctx.get("normalized_text") or ctx.get("requirement_text") or ""
        flow_cfgs = ctx.get("flow_configs") or {}
        extract_cfg = flow_cfgs.get("extract") or {}
        from app.services.agent_understand import run_agent_understand
        res = await run_agent_understand(text, config, extract_config=extract_cfg,
                                         broadcast=broadcast, step_id="llm_agent")
        ext = res.get("ext") or {}
        ctx["ext"] = ext
        ctx["model_token_regex"] = extract_cfg.get("model_token_regex") or config.get("model_token_regex")
        if ctx.get("budget") is None and ext.get("budget") is not None:
            ctx["budget"] = ext["budget"]

        # 抽不全且非 force_complete → 反问最关键的缺口（SAGE 门控：够就推进、不够才问一件）
        # select_baseline 见 awaiting_input 会跳过选型；run_pipeline 收尾发 paused 等用户补充
        if not res.get("sufficient") and not ctx.get("force_complete"):
            import uuid
            missing = res.get("missing_critical") or []
            q = (("请补充更多配置信息，便于精确选型：" + "、".join(missing)) if missing
                 else "请补充更多配置信息（服务器用途/类型，CPU/内存/硬盘/GPU 规格）")
            rid = f"understand_{uuid.uuid4().hex[:12]}"
            await broadcast({"type": "need_input", "reply_id": rid, "question": q,
                             "options": [], "round": ctx.get("clarify_round", 1),
                             "source": "llm_agent", "missing_fields": missing})
            ctx["awaiting_input"] = True
            ctx["last_reply_id"] = rid
            ctx["llm_agent"] = {"ok": res.get("ok"), "source": res.get("source"),
                                "sufficient": False, "missing_critical": missing}
            return {"called": bool(res.get("ok")), "source": res.get("source"),
                    "sufficient": False, "missing_critical": missing,
                    "server_type_name": ext.get("server_type_name"), "question": q}

        # 可选接地升级（默认关）：server_type 缺/弱 → ReAct 调 select_models 锁机型（catalog 直抽够用则跳过）
        grounding: dict = {}
        react_res: dict = {"ok": False, "tool_calls_log": [], "iterations": 0}
        if bool(config.get("escalate_grounding")) and not ext.get("server_type_name"):
            try:
                from app.services.agent_react import run_react_loop
                agent_cfg = {
                    "enabled_tools": config.get("enabled_tools") or ["select_models"],
                    "system_prompt": None,  # 接地专用，不复用理解 prompt
                    "case_source": config.get("case_source", "internal"),
                    "case_top_k": config.get("case_top_k", 2),
                    "case_match": config.get("case_match", "tags_keyword"),
                }
                react = await run_react_loop(
                    text, agent_cfg, max_iterations=int(config.get("max_iterations") or 5))
                react_res = react
                grounding = _extract_grounding(react.get("tool_calls_log") or [])
            except Exception as e:
                logger.exception("llm_agent 接地升级失败（不阻塞，保留理解的 server_type）: %s", e)
                react_res["reason"] = f"node_error: {e}"
            if grounding.get("server_type_name"):
                ext["server_type_name"] = grounding["server_type_name"]
                ext["form"] = grounding.get("form") or ext.get("form")
                ext["series"] = grounding.get("series")

        ctx["catalog_type_name"] = ext.get("server_type_name")  # 桥接 select_baseline
        ctx["llm_agent"] = {
            "ok": res.get("ok"), "source": res.get("source"), "error": res.get("error"),
            "sufficient": True, "changes": res.get("changes") or [],
            "grounding": grounding, "iterations": react_res.get("iterations"),
            "tool_calls": [(c.get("name"), c.get("args")) for c in react_res.get("tool_calls_log") or []],
        }
        _trace = [
            {"tool": c.get("name"), "args": c.get("args") or {},
             "result_count": (c.get("result") or {}).get("count")
                             if isinstance(c.get("result"), dict) else None}
            for c in (react_res.get("tool_calls_log") or [])
        ] or None
        return {
            "called": bool(res.get("ok")),
            "source": res.get("source"),  # llm / extract_only_* —— 白盒看走主理解还是离线兜底
            "sufficient": True,
            "server_type_name": ext.get("server_type_name"),
            "series": ext.get("series"), "form": ext.get("form"),
            "keywords": ext.get("keywords") or [], "categories": ext.get("categories") or [],
            "changes": res.get("changes") or [],
            # 接地升级轨迹（仅 escalate_grounding 开时有值，否则 None）
            "grounding": grounding, "iterations": react_res.get("iterations"), "tool_trace": _trace,
        }

    # llm_guide 节点已溶解（P3）：反问/放行并入 llm_agent（抽不全→need_input 反问），对话阶段机移除。
    # llm_guide dispatch 分支、llm_guide_prompt.py、run_pipeline 的 dialog_state 持久化均已删。

    if ntype == "slot_validate":
        # 槽位语义校验节点（2026-08 LLM 重构 P1）：结构 + 业务语义的最终确定性闸门。
        # 白名单外值丢弃（记 issues）；LLM vs 规则冲突 / 低置信度 → confirm_items（P2 confirm 面板）。
        ext = ctx.get("ext") or {}
        llm_slots = ctx.get("llm_slots") or {}
        from app.services.requirement_slots import validate_pipeline_slots
        v = validate_pipeline_slots(ext, llm_slots,
                                    ctx.get("requirement_text") or ctx.get("normalized_text") or "",
                                    config)
        ctx["slot_validation"] = v
        return {
            "ok": v.get("ok"), "issues": v.get("issues") or [],
            "confirm_items": v.get("confirm_items") or [],
            "coverage": v.get("coverage"),
            "catalog_count": v.get("catalog_count"),
        }

    if ntype == "scene_analysis":
        # 场景分析：需求信号 + 商机上下文 → AI/存储/通用 × 系列 × 形态（带证据、白盒）。
        # 无法确定（真·无信号）→ missing_fields 加"场景"，由 cond_scene 路由到 ask_user 反问。
        from app.services.scene_analyzer import analyze_scene
        ext = ctx.get("ext") or {}
        opp = ctx.get("opportunity")
        oid = ctx.get("opportunity_id")
        if opp is None and oid and oid != "test-run":
            try:
                from app.repository.opportunity_repo import OpportunityRepository
                _or = OpportunityRepository()
                try:
                    opp = _or.get_opportunity(oid)
                finally:
                    _or.close()
            except Exception as e:
                logger.warning("读商机上下文失败 opp=%s err=%s", oid, e)
        scene = analyze_scene(
            ext,
            ctx.get("requirement_text") or "",
            config=config,
            opportunity=opp,
            catalog_type_name=ctx.get("catalog_type_name"),
            force_complete=bool(ctx.get("force_complete")),
        )
        ctx["scene"] = scene
        ctx["opportunity"] = opp
        ctx["scene_determined"] = bool(scene.get("determined"))
        # 2026-08 LLM 重构 P1：scene_analysis 的散装 LLM 增强已下线。系列/场景推断统一交给
        # llm_understand（LLM 主理解）与 slot_validate（语义校验），本节点保持规则兜底确定性。
        if not scene.get("determined"):
            for _f in scene.get("missing") or []:
                if _f not in ctx.setdefault("missing_fields", []):
                    ctx["missing_fields"].append(_f)
        return {
            "scene_name": scene.get("scene_name"),
            "series": scene.get("series"),
            "form": scene.get("form"),
            "determined": scene.get("determined"),
            "confidence": scene.get("confidence"),
            "evidence": scene.get("evidence"),
            "missing": scene.get("missing"),
            "candidates": scene.get("candidates"),
        }

    if ntype == "understand":
        # AI 路需求理解主节点（2026-08 重构）：LLM 填表 + 领域知识注入 + 内部校验；
        # 抽不全且非 force_complete → 反问最关键缺口；失败 → extract 兜底（source=extract_only_*）。
        from app.services.capabilities import run_understand
        res = await run_understand(ctx, config, broadcast, step_id="understand")
        if not res.get("called") and res.get("error") == "empty_text":
            return {"called": False, "source": "empty"}
        if not res.get("sufficient") and not ctx.get("force_complete"):
            # 2026-08 重构：抽不全不再硬编码反问话术，标记不足并交给 gap_analyze/llm_ask
            # （智能反问：LLM 基于完整上下文生成策略性问题）统一处理，杜绝绕过硬编码话术。
            missing = res.get("missing_critical") or []
            ctx["understand_insufficient"] = True
            for m in missing:
                if m not in ctx.setdefault("missing_fields", []):
                    ctx["missing_fields"].append(m)
            return {"called": True, "source": res.get("source"), "sufficient": False,
                    "missing_critical": missing}
        return {
            "called": True, "source": res.get("source"), "sufficient": True,
            "server_type_name": (ctx.get("ext") or {}).get("server_type_name"),
            "series": (ctx.get("ext") or {}).get("series"), "form": (ctx.get("ext") or {}).get("form"),
            "changes": res.get("changes") or [], "error": res.get("error"),
            "issues": res.get("issues") or [],
        }

    if ntype == "gap_analyze":
        # 缺口分析：已填槽位 vs 期望清单 → level + missing_fields + 原因（白盒）
        from app.services.capabilities import run_gap_analyze
        return run_gap_analyze(ctx, config)

    if ntype == "scene_decide":
        # 场景判定：需求信号 → AI/存储/通用 × 系列 × 形态（带证据白盒）
        from app.services.capabilities import run_scene_decide
        return run_scene_decide(ctx, config)

    if ntype == "model_reason":
        # 机型推理（AI 路）：LLM ReAct 调 select_models 选机型 + 理由；失败降级规则本体。
        # LLM 决定"选哪个"，完整数据由规则补全（型号/料号精确性永远规则保证）。
        from app.services.capabilities import run_model_reason, run_select_baseline_rule
        res = await run_model_reason(ctx, config, broadcast)
        if res.get("ok") and res.get("baseline"):
            rule_res = run_select_baseline_rule(ctx, config)
            cid = (res.get("baseline") or {}).get("config_id") or (res.get("baseline") or {}).get("id")
            keep = [b for b in (ctx.get("baselines") or [])
                    if b.get("id") == cid or b.get("server_model_id") == cid]
            if keep:
                ctx["baselines"] = keep
                ctx["model_reason"] = res
                return {"count": 1,
                        "matches": [{"config_id": keep[0].get("id"), "name": keep[0].get("name") or "",
                                     "series": keep[0].get("series") or "", "form": keep[0].get("form") or ""}],
                        "source": "llm", "reason": res.get("reason") or "",
                        "trace": res.get("trace") or []}
        return run_select_baseline_rule(ctx, config)

    if ntype == "select_baseline":
        # 机型选型规则本体（AI 增强在 model_reason 节点；本节点为确定性降级）
        from app.services.capabilities import run_select_baseline_rule
        return run_select_baseline_rule(ctx, config)

    if ntype == "kp_reason":
        # 配件推理（AI 路）：LLM ReAct 调 pick_kp_parts 探查/确认配件；精确执行仍由规则保证
        # （compose 需要完整字段），LLM 输出确认 + 理由。
        from app.services.capabilities import run_kp_reason, run_match_kp_rule
        res = await run_kp_reason(ctx, config, broadcast)
        if res.get("ok") and res.get("kp_parts"):
            rule_res = run_match_kp_rule(ctx, config)
            ctx["kp_reason"] = {**res, "kp_count": rule_res.get("kp_count")}
            return {**rule_res, "source": "llm+rule", "reason": res.get("reason") or "",
                    "trace": res.get("trace") or []}
        return run_match_kp_rule(ctx, config)

    if ntype == "match_kp":
        # 配件匹配规则本体（AI 增强在 kp_reason 节点；本节点为确定性降级）
        from app.services.capabilities import run_match_kp_rule
        return run_match_kp_rule(ctx, config)

    if ntype == "compose":
        baselines = ctx.get("baselines") or []
        kp_by_model = ctx.get("kp_by_model") or {}
        if not baselines:
            ctx["plans"] = []
            return {"plans_count": 0, "warning": "未找到匹配的基准配置，请手填或调整需求"}
        # 每个机型取自己的 KP（match_kp per-机型配的），fallback 到全局 kp_parts
        plans = []
        _ext = ctx.get("ext") or {}
        # 电源：需求文本显式瓦数/数量 > build_plan 按负载推断（既有逻辑，compose 为确定性红线不暴露开关）
        _sig_w = (_ext.get("psu_signal") or {}).get("wattage")
        _sig_q = (_ext.get("psu_signal") or {}).get("qty")
        for bl in baselines:
            mid = bl.get("server_model_id") or bl.get("id")
            bl_kp = kp_by_model.get(mid) or ctx.get("kp_parts") or []
            _p = build_plan(bl, bl_kp)
            if _sig_w or _sig_q:  # 需求文本功率/数量优先覆盖 build_plan 推断（前端 deriveVars 读 psu_wattage/psu_qty）
                # 合并而非整体替换：保留 build_plan 已派生的 bp_type / cable_qty_by_kind（选型配置规则）
                _cs = _p.get("chassis_signals") or {}
                if _sig_w:
                    _cs = {**_cs, "psu_wattage": _sig_w}
                if _sig_q:
                    _cs = {**_cs, "psu_qty": int(_sig_q)}
                _p["chassis_signals"] = _cs
            plans.append(_p)
        ctx["plans"] = plans
        return {"plans_count": len(plans)}

    if ntype == "llm_audit":
        # LLM 方案校对节点（2026-08 P3）：bom_cases 同平台 few-shot + 一次调用校对全部方案。
        # 规则硬校验（缺件/平台/超预算）仍在 review 节点兜底；本节点只报意图级问题。
        # 默认关 = 纯规则（review 纯规则校对）；失败静默降级，绝不阻塞。
        plans = ctx.get("plans") or []
        try:
            from app.services.llm_audit import run_llm_audit
            res = await run_llm_audit(ctx.get("requirement_text") or ctx.get("normalized_text") or "",
                                      plans, config,
                                      opportunity_id=ctx.get("opportunity_id") or "",
                                      pipeline_id=ctx.get("pipeline_id") or "",
                                      ext=ctx.get("ext"))
        except Exception as e:
            logger.exception("llm_audit 未预期异常（降级规则校对，不阻塞）: %s", e)
            res = {"called": True, "reason": "node_error", "error": str(e)[:300],
                   "audits": [], "plans_checked": 0, "issue_plans": 0,
                   "duration_ms": 0, "references": []}
        ctx["llm_audits"] = res.get("audits") or []
        ctx["llm_audit_report"] = res
        return {
            "called": res.get("called"), "reason": res.get("reason"),
            "error": res.get("error"),
            "plans_checked": res.get("plans_checked") or 0,
            "issue_plans": res.get("issue_plans") or 0,
            "duration_ms": res.get("duration_ms") or 0,
            "references": res.get("references") or [],
            "audits": res.get("audits") or [],
        }

    if ntype == "spec_compliance":
        # 规格合规校验（v12，确定性）：AI 缺卡自动补 / 型号降级·内存代际标 issue / 请求重跑链
        from app.services.capabilities import run_spec_compliance
        return run_spec_compliance(ctx, config)

    if ntype == "audit_fix":
        # 审计自纠（v12）：llm_audit 检出问题 → 确定性动作 + 请求重跑链（执行中自我修正闭环）
        from app.services.capabilities import run_audit_fix
        return run_audit_fix(ctx, config)

    if ntype == "result_check":
        # 方案自检（2026-08 新增，确定性）：结果完整性 + 必填核心件 + 数量合理性。
        # 与 spec_compliance（规格合规）分工：本节点查「结果有没有缺漏/自洽」，检查项抽屉可配。
        from app.services.capabilities import run_result_check
        return run_result_check(ctx, config)

    if ntype == "review":
        plans = ctx.get("plans") or []
        ext = ctx.get("ext") or {}
        # 方案校对（2026-08-04 流程重构 R29）：阻塞式通过/不通过 + 必改项（≤2），
        # 替代了原 requirement_check 的"全量差异报告"（实测警告泛滥）。挂 plan.audit。
        from app.services.requirement_checker import audit_plan
        _audits = []
        for _p in plans:
            try:
                _audit = audit_plan(_p, ctx.get("requirement_text") or "", ext)
            except Exception as _e:
                logger.warning("audit_plan 失败 plan=%s err=%s", _p.get("name"), _e)
                _audit = {"status": "ok", "issues": [], "issue_count": 0, "error": str(_e)}
            _p["audit"] = _audit
            _audits.append(_audit)
        # 2026-08 P3：review 的散装 LLM 校对已移出，收拢到独立 llm_audit 节点
        # （bom_cases few-shot 意图级校对，一次调用校对全部方案）。这里只做规则校对 +
        # 把 llm_audit 产出的意图级问题合并进 plan.audit：规则通过但 LLM 存疑 → review。
        _llm_audits = ctx.get("llm_audits") or []
        for _i, _la in enumerate(_llm_audits):
            if _i >= len(plans):
                break
            _p = plans[_i]
            _audit = _p.get("audit") or {}
            _issues = _la.get("issues") or []
            if _issues:
                _audit = {**_audit,
                          "issues": list(dict.fromkeys((_audit.get("issues") or []) + _issues))[:2]}
                if _audit.get("status") == "ok" and _la.get("passed") is False:
                    _audit["status"] = "review"  # 规则通过但 LLM 存疑 → 需人工确认
                _p["audit"] = _audit
        _audits = [_p.get("audit") or {} for _p in plans]
        _llm = None
        _llm_report = ctx.get("llm_audit_report") or {}
        if _llm_report:
            _llm = {"called": _llm_report.get("called", False),
                    "reason": _llm_report.get("reason"),
                    "plans_checked": _llm_report.get("plans_checked") or 0,
                    "issue_plans": _llm_report.get("issue_plans") or 0,
                    "duration_ms": _llm_report.get("duration_ms") or 0,
                    "error": _llm_report.get("error")}
        _blocked = sum(1 for a in _audits if a.get("status") == "blocked")
        await broadcast({
            "type": "candidates_ready",
            "plans": plans,
            "keywords": ext.get("keywords", []),
            "series": ext.get("series"),
            "form": ext.get("form"),
            # BOM 明细输出配置（review 节点可配：是否显示/走模板/字段）——方案助手/企微收尾转文本用
            "bom_output": config.get("bom_output") or {},
            # 推荐输出配置（review 节点可配：是否附推荐语+理由+下一步引导）——方案助手收尾生成
            "recommendation": config.get("recommendation") or {},
        })
        # BOM案例库在线防偏差（P2）已下线（2026-08-04 用户实测）：跨平台/跨机型最相似案例
        # 的规格级对照全是误报噪音（如 AMD 案例对照海光需求满屏差异）——与已删的
        # requirement_check 同类问题。案例库对照保留在训练（bom_compare/重放），不挂方案卡；
        # 在线"重大偏差"由上方 audit_plan 硬校验兜底（缺件/平台冲突/严重超预算）。
        return {"plans": len(plans), "blocked": _blocked, "audits": _audits, "llm": _llm}

    if ntype == "clarity_check":
        # force_complete（用户点跳过）：强制走选型，不反问
        if ctx.get("force_complete"):
            ctx["clarity"] = "partial"
            ctx["missing_fields"] = []
            ctx["clarity_capped"] = True
            ctx["clarity_explain"] = {"force_complete": True}
            return {"level": "partial", "missing_fields": [], "explain": {"force_complete": True}}
        ext = ctx.get("ext") or {}
        budget = ctx.get("budget")
        # 2026-08-04 流程重构：明确度 = 槽位覆盖度（已填槽位 vs 期望清单 L0/L1/L2 的差距）。
        # 期望清单 requirement_slots 可配置；比旧"信号规则猜明确度"更可解释、更贴近选型实际。
        try:
            from app.services.clarity_evaluator import evaluate_slot_coverage
            level, missing, explain = evaluate_slot_coverage(ext)
        except Exception as e:
            logger.exception("clarity 槽位覆盖度评估异常，回退 partial: %s", e)
            level, missing, explain = "partial", ["需求描述不够具体"], {}
        # 2026-08 P2：明确度主判据 = 槽位覆盖度 + 目录校验结果；LLM 置信度仅辅助。
        # ① slot_validate 目录校验 issues（白名单外值被丢弃）→ 并入缺失项；
        # ② LLM 主理解的缺失项追问（一次列全）→ 并入 missing_fields 供 ask_user/llm_ask 发问。
        sv = ctx.get("slot_validation") or {}
        sv_issues = list(sv.get("issues") or [])
        for issue in sv_issues:
            _label = issue.split("「")[0].replace("规则抽取", "").strip()
            if _label and _label not in missing:
                missing.append(_label)
        llm_missing = (ctx.get("llm_report") or {}).get("missing") or []
        for m in llm_missing:
            m = str(m).strip()
            if m and m not in missing:
                missing.append(m)
        if sv_issues or llm_missing:
            explain = {**(explain or {}), "slot_validation_issues": sv_issues[:5],
                       "llm_missing": llm_missing[:8]}
        # 目录驱动引导已完成（类型/机型/规格都已确认）→ 视为信息足够，直接出方案。
        # 旧 M1.6 delegate 特判已删除：委托（你推荐/随便）由 run_pipeline 消费 supplement
        # 推进目录 stage 到 done，不再在 clarity 里猜。
        if (ctx.get("catalog_stage") or "") == "done":
            ctx["clarity"] = "explicit"
            ctx["missing_fields"] = []
            ctx["clarity_capped"] = False
            ctx["clarity_explain"] = {**(explain or {}), "catalog_complete": True}
            return {"level": "explicit", "missing_fields": [], "explain": ctx["clarity_explain"]}
        # M1 1.3b：答"还没定/你推荐"跳过的字段（clarify_defaults）从缺失列表剔除，
        # 只跳过已答默认的字段，其余字段继续引导（不因单个"还没定"直接出方案）。
        defaults = ctx.get("clarify_defaults") or []
        if defaults:
            missing = [f for f in missing if f not in defaults]
            if not missing and level != "explicit":
                level = "explicit"  # 所有缺失字段均已答/默认 → 信息足够
                explain = {**(explain or {}), "defaults_satisfied": True}
        # 死循环防护：超轮次上限且非 explicit → 强制 partial（上限优先取 ask_user 配置，缺省常量）
        _round_cap = int(ctx.get("max_clarify_rounds") or MAX_CLARIFY_ROUNDS)
        if ctx.get("clarify_round", 0) >= _round_cap and level != "explicit":
            level = "partial"
            ctx["clarity_capped"] = True
        else:
            ctx["clarity_capped"] = False
        ctx["clarity"] = level
        ctx["missing_fields"] = missing
        ctx["clarity_explain"] = explain
        return {"level": level, "missing_fields": missing, "explain": explain}

    if ntype == "ask_user":
        # 目录驱动引导（类型 → 机型 → KP 格式）：选项来自产品目录，回复解析靠选项匹配 + extract 信号。
        # P2：LLM 主理解的缺失项追问（一次性列全）注入问题文案；LLM 关则纯目录问题。
        return await _ask_catalog_question(ctx, broadcast, extra_questions=_llm_questions(ctx))

    if ntype == "llm_ask":
        # 智能反问（2026-08 重构）：LLM 基于完整上下文生成策略性问题（带选项/理由）；
        # AI 关/失败 → 目录引导兜底（选项来自产品目录）。
        # v12 单路图无 cond_gap 门控，节点直连 gap_analyze；force_complete（跳过）时不反问。
        if ctx.get("force_complete") or ctx.get("delegated"):
            return {"skipped": "force_complete"}
        from app.services.capabilities import run_llm_ask
        res = await run_llm_ask(ctx, config, broadcast)
        if res.get("ok"):
            import uuid
            rid = f"llm_{uuid.uuid4().hex[:12]}"
            ctx["awaiting_input"] = True
            ctx["last_reply_id"] = rid
            await broadcast({"type": "need_input", "reply_id": rid, "question": res["question"],
                             "options": res.get("options") or [], "why": res.get("why") or "",
                             "missing_fields": ctx.get("missing_fields") or [], "source": "llm_ask"})
            return {"question": res["question"], "options": res.get("options") or [],
                    "source": "llm", "why": res.get("why") or ""}
        # AI 关/失败 → 目录引导兜底；llm_ask 节点 config 可带 ask_user 子配置（引导文案/选项）
        if config.get("ask_user") and isinstance(config["ask_user"], dict):
            from app.services.catalog_guide import load_ask_config
            merged = {**load_ask_config(ctx.get("flow_configs")), **config["ask_user"]}
            ctx.setdefault("flow_configs", {})["ask_user"] = merged
        return await _ask_catalog_question(ctx, broadcast, extra_questions=_llm_questions(ctx))

    if ntype == "confirm_series":
        # 系列确认/补全（2026-08-04 流程重构 R29）：
        #   scene.series_source == explicit（需求明说/词表命中系列）→ 无需确认直接过；
        #   inferred（系统推断系列）→ 问「是否 XX 系列？」（先给方向，用户纠正）；
        #   推不出系列（None）→ 列在售系列让用户选。
        # 答复（是/不是/系列名）由 run_pipeline 消费 supplement 解析存 extra_fields，
        # 下一轮经 ctx.confirmed_series 注入；确认后 series_ready=True，cond_scene 放行选型。
        scene = ctx.get("scene") or {}
        series = scene.get("series")
        source = scene.get("series_source")
        confirmed = ctx.get("confirmed_series") or ""
        if confirmed and confirmed != "__ask__":
            ctx["series_ready"] = True
            ctx["confirmed_series"] = confirmed
            return {"skip": True, "series": confirmed}
        if source == "explicit" and series:
            ctx["series_ready"] = True
            ctx["confirmed_series"] = series
            return {"skip": True, "series": series}
        if ctx.get("force_complete"):
            # 用户点跳过/训练重放：不反问系列，直接放行选型（select_baseline 仍按场景/形态推候选）
            ctx["series_ready"] = True
            return {"skip": True, "series": series or ""}
        # 需要交互：推断未确认 → 确认问题；无系列 → 补全问题
        from app.services.requirement_intel_service import _load_series_values
        import uuid
        if series and source == "inferred":
            question = f"根据需求推断所属系列为「{series}」，是否按这个系列选型？"
            options = ["是", "不是，换系列"]
            offered = {"series": series, "mode": "confirm"}
        else:
            _vals = _load_series_values() or []
            question = "请选择所属系列（以下均为在售系列）："
            options = list(_vals) or []
            offered = {"mode": "ask", "series": _vals or []}
        reply_id = f"cf_{uuid.uuid4().hex[:12]}"
        ctx["awaiting_input"] = True
        ctx["last_reply_id"] = reply_id
        oid = ctx.get("opportunity_id")
        if oid:
            try:
                from app.services.requirement_intel_service import _persist_series_offer
                _persist_series_offer(oid, offered)
            except Exception as e:
                logger.warning("写 series_offer 失败 opp=%s err=%s", oid, e)
        return {"question": question, "reply_id": reply_id, "options": options,
                "asked_fields": ["系列"], "mode": "series_confirm"}

    if ntype == "budget_check":
        # 给 plans 注 over_budget / underspend 标注（共享函数，线性 fallback 也用）
        from app.services.requirement_intel_service import apply_budget_check
        plans = ctx.get("plans") or []
        over_count = apply_budget_check(plans, ctx.get("budget"),
                                         float(config.get("underspend_threshold") or 0.5))
        under_count = sum(1 for p in plans if p.get("underspend"))
        # v12：超预算自动降配（确定性，不改 LLM）—— 换 min_price 代表件 → 请求重跑 compose/budget_check。
        # 只降一轮（budget_downgraded 防重复）；downgrade_axis.model（换机型）预留。
        if over_count > 0 and config.get("auto_downgrade") and not ctx.get("budget_downgraded"):
            try:
                from app.services.capabilities import run_match_kp_rule
                run_match_kp_rule(ctx, {**config, "representative_pick": "min_price"})
                ctx["budget_downgraded"] = True
                ctx["budget_downgrade_reason"] = "超预算，已按最低价代表件降配一轮"
                from app.services.capabilities import _merge_retry
                ctx["retry_caps"] = _merge_retry(ctx, ["compose", "budget_check"])
            except Exception as e:
                logger.warning("budget_check 自动降配失败: %s", e)
        return {"checked": True, "over_budget_count": over_count, "underspend_count": under_count,
                "downgraded": bool(ctx.get("budget_downgraded"))}

    if ntype == "llm_confirm":
        # 决策确认（可选节点）：汇总机型/配件推荐 + 理由，供前端确认面板展示
        from app.services.capabilities import run_llm_confirm
        return run_llm_confirm(ctx, config)

    # 未知 type 静默通过
    logger.info("未知节点类型，跳过执行: %s", ntype)
    return {}


async def run_graph_executor(opportunity_id: str, requirement_text: str, flow: dict,
                             broadcast: BroadcastFn, initial_ctx: dict = None) -> dict:
    """图驱动执行。读 graph（v2）→ 拓扑 BFS → 每节点 broadcast step_start/step_done。
    condition 静默路由。异常抛出，调用方 fallback。
    返回 ctx（调用方检查 awaiting_input 决定发 pipeline_paused/done）。"""
    graph = flow.get("graph") or {}
    raw_nodes = graph.get("nodes") or []
    raw_edges = graph.get("edges") or []
    nodes: dict[str, dict] = {}
    for n in raw_nodes:
        nid = n.get("id")
        if nid:
            nodes[nid] = n

    # 邻接 + 入度
    adj: dict[str, list[dict]] = {nid: [] for nid in nodes}
    indeg: dict[str, int] = {nid: 0 for nid in nodes}
    for e in raw_edges:
        s, t = e.get("source"), e.get("target")
        if s in nodes and t in nodes:
            adj[s].append(e)
            indeg[t] = indeg.get(t, 0) + 1

    node_configs = flow.get("node_configs") or {}
    ctx: dict[str, Any] = {
        "requirement_text": requirement_text,
        "opportunity_id": opportunity_id,
        "flow_configs": node_configs,
    }
    if initial_ctx:
        ctx.update(initial_ctx)
    # 全局 AI 开关（设置→AI 设置→启用 AI），每次推理读最新值；route_fork/cond_audit 分叉用。
    # 放在 initial_ctx.update 之后，确保不被请求参数覆盖（系统状态，非请求输入）。
    from app.services import llm_client
    ctx["llm_enabled"] = llm_client.is_llm_enabled()

    # 入口（in-degree=0），按 id 排序保证 WS 序确定。
    # ⚠️ v12 画布含语义回边（llm_ask→understand 反问循环等），拓扑 BFS 会因环停摆
    #（环内节点入度≥1，初始队列可能为空）。这里做「环容忍」：无入度 0 节点时按定义顺序
    # 从首个节点起步；环内节点按定义顺序兜底执行，保证老图/测试仍能跑完整链
    #（orchestrator 主路径不依赖本函数，v12 回边由编排器语义处理）。
    queue = sorted([nid for nid, d in indeg.items() if d == 0])
    visited: set[str] = set()
    _node_order = {nid: i for i, nid in enumerate(nodes.keys())}  # 节点定义顺序（入口在前）
    if not queue and nodes:
        # 全环（v12 反问回边）→ 从定义顺序第一个节点起步（如 understand），
        # 而不是字母序（否则可能从 audit_fix 这种尾节点起步，链路乱序）。
        queue = [min(nodes.keys(), key=lambda n: _node_order[n])]

    def _enqueue(ts: list):
        for t in ts:
            if t in nodes and t not in visited and t not in queue:
                queue.append(t)

    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes[nid]
        ntype = node.get("type") or nid
        config = node_configs.get(nid) or {}

        # extract 节点已废弃（AI-first），图里残留则静默跳过。
        if ntype == "extract":
            continue

        # condition 静默路由（不广播 step_start）
        if ntype == "condition":
            branch = _eval_condition(config.get("expr", ""), ctx)
            handle = "true" if branch else "false"
            next_edges = [e for e in adj[nid] if (e.get("source_handle") or "true") == handle]
            if not next_edges:
                next_edges = list(adj[nid])  # 无匹配 handle 兜底全走
            _enqueue([e.get("target") for e in next_edges])
            continue

        # 普通节点：广播 step_start → 执行 → step_done
        label = node.get("label") or ntype
        await broadcast({"type": "step_start", "step": nid, "label": label})
        payload = await _dispatch(ntype, ctx, config, broadcast)
        await broadcast({"type": "step_done", "step": nid, "payload": payload})

        # 后继入队
        _enqueue([e.get("target") for e in adj[nid]])

        # 环容忍：主队列走完仍有未访问节点（回边环）→ 按节点定义顺序补执行一次（visited 防重入）
        if not queue:
            for nid2 in sorted(nodes.keys(), key=lambda n: _node_order[n]):
                if nid2 not in visited:
                    queue.append(nid2)
                    break

    return ctx
