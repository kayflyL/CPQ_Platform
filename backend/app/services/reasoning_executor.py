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

# 三层兜底最底层（DB 读失败时用）—— 与 requirement_rule_repo.DEFAULT_RULES 结构一致
_FALLBACK_CLARITY_RULES = [
    {"id": "fb_c1", "body": {"signal": {"type": "combined", "rules": [
        {"type": "model_token_in_category", "category": "CPU", "min": 1},
        {"type": "model_token_in_category", "category": "GPU", "min": 1}]},
      "level": "explicit", "missing_if_not": [], "weight": 100}},
    {"id": "fb_c2", "body": {"signal": {"type": "series_and_form"},
      "level": "partial", "missing_if_not": ["具体型号"], "weight": 50}},
    {"id": "fb_c3", "body": {"signal": {"type": "no_series_no_form"},
      "level": "unclear", "missing_if_not": ["系列", "形态", "用途"], "weight": 30}},
    {"id": "fb_c4", "body": {"signal": {"type": "no_budget"},
      "level": "partial", "missing_if_not": ["预算"], "weight": 40}},
]


def _load_clarity_rules() -> list:
    """读 clarity 规则（三层兜底：DB → 模块常量）。"""
    try:
        from app.repository.requirement_rule_repo import RequirementRuleRepository
        repo = RequirementRuleRepository()
        try:
            rules = repo.list_by_type("clarity", status="active")
        finally:
            repo.close()
        return rules or _FALLBACK_CLARITY_RULES
    except Exception as e:
        logger.warning("读 clarity rules 失败，用 fallback: %s", e)
        return _FALLBACK_CLARITY_RULES



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


async def _confirm_llm_items(ctx: dict, broadcast: BroadcastFn, config: dict) -> dict:
    """confirm 节点（P2）：LLM 与规则冲突项 / 低置信度项的人工确认。

    策略：默认采纳 LLM 补充项（accept）+ 前端高亮可改。
      - 无确认项 → 直接跳过；
      - 有确认项且已带决策（用户改过 / force_complete）→ 应用决策并写反馈样本；
      - 有确认项且未决策、非 force_complete → 标记 confirm_pending（不阻塞图执行），
        run_pipeline 在收尾时广播 need_confirm + pipeline_paused 等用户确认。
    """
    sv = ctx.get("slot_validation") or {}
    items = list(sv.get("confirm_items") or [])
    if not items:
        ctx["confirm_applied"] = []
        return {"skip": True, "confirmed": []}
    decisions = ctx.get("confirm_decisions") or {}
    oid = ctx.get("opportunity_id")
    if not decisions and not ctx.get("confirm_answered"):
        if ctx.get("force_complete"):
            # 快速模式（试运行/跳过）：默认全采纳，不暂停
            decisions = {it.get("id"): "accept" for it in items}
        else:
            import uuid
            reply_id = f"cfm_{uuid.uuid4().hex[:12]}"
            ctx["confirm_pending"] = True
            ctx["confirm_items"] = items
            ctx["confirm_reply_id"] = reply_id
            ctx["awaiting_input"] = True
            ctx["last_reply_id"] = reply_id
            return {"reply_id": reply_id, "items": items, "default": "accept", "awaiting": True}
    from app.services.requirement_slots import apply_confirm_decisions
    applied = apply_confirm_decisions(ctx.get("ext") or {}, items, decisions)
    ctx["confirm_applied"] = applied
    ctx["confirm_consumed"] = True
    if oid and applied:
        try:
            from app.services.requirement_intel_service import _write_llm_feedback_sample
            _write_llm_feedback_sample(oid, ctx.get("requirement_text") or "", applied)
        except Exception as e:
            logger.warning("写 llm_feedback 样本失败: %s", e)
    return {"confirmed": applied, "count": len(applied)}


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
    # 记录本轮推给客户的选项 + 当前 stage（下轮选项匹配用）
    oid = ctx.get("opportunity_id")
    if oid:
        from app.services.requirement_intel_service import _persist_catalog_offer
        _persist_catalog_offer(oid, stage, offered)
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
    }
    try:
        return bool(simple_eval(expr, names=names))
    except Exception as e:
        logger.warning("condition 求值失败（默认 True）expr=%r err=%s", expr, e)
        return True


async def _dispatch(ntype: str, ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """按节点 type 执行 handler，更新 ctx，返回 step_done payload。"""
    # 延迟 import 避免循环
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons

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
        text = ctx.get("normalized_text") or ctx.get("requirement_text", "")
        # 新结构 lexicons 折叠成 4 个 dict；旧结构（category_lexicon）兼容直传
        if config.get("lexicons"):
            _cat_lex, _chassis_lex, _usage_map, _series_map, _form_map = _fold_lexicons(config["lexicons"])
        else:
            _cat_lex = config.get("category_lexicon")
            _chassis_lex, _usage_map, _series_map, _form_map = None, None, None, None
        ext = extract_keywords(
            text,
            lexicon=_cat_lex,
            keyword_limit=config.get("keyword_limit") or 12,
            series_keyword_map=_series_map,
            usage_keyword_map=_usage_map,
            form_keyword_map=_form_map,
            chassis_lexicon=_chassis_lex,
            spec_aliases=config.get("spec_aliases"),
            qty_units=config.get("qty_units"),
            qty_multipliers=config.get("qty_multipliers"),
            model_token_regex=config.get("model_token_regex"),
        )
        ctx["ext"] = ext
        ctx["model_token_regex"] = config.get("model_token_regex")  # 给 match_kp 同源用
        # extract 抽到的预算兜底注入 ctx（若 initial_ctx 未显式给预算）
        if ctx.get("budget") is None and ext.get("budget") is not None:
            ctx["budget"] = ext["budget"]
        # 2026-08 LLM 重构 P1：extract 的散装 LLM 增强已下线，收拢到独立 llm_understand 节点
        # （需求原文 + 目录白名单 → RequirementSlots 契约，见 llm_understand 分支）。规则抽取保持
        # 100% 确定性，绝不让 LLM 掺入词表/分词。
        return {
            "keywords": ext["keywords"], "categories": ext["categories"],
            "series": ext["series"], "form": ext["form"],
            "usage": ext.get("usage"), "server_type_name": ext.get("server_type_name"),
            "chassis_categories": ext.get("chassis_categories", []),
            "budget": ext.get("budget"),
        }

    if ntype == "llm_understand":
        # LLM 主理解节点（2026-08 LLM 重构 P1）：需求原文 + 目录白名单 → RequirementSlots 契约。
        # 开启 enable_llm 才调 LLM（受「设置→AI 设置→启用 AI」总开关约束）；默认关 = 纯规则透传。
        # 合并规则赢、只补缺（apply_llm_merge）；任何失败静默降级，绝不阻塞主流程。
        ext = ctx.get("ext") or {}
        text = ctx.get("requirement_text") or ctx.get("normalized_text") or ""
        try:
            from app.services.llm_understand import run_llm_understand
            res = await run_llm_understand(text, ext, config,
                                           opportunity_id=ctx.get("opportunity_id") or "",
                                           pipeline_id=ctx.get("pipeline_id") or "")
        except Exception as e:
            # 最终兜底：任何未预期异常（脏配置/DB/序列化）都降级该节点，绝不拖垮整条图。
            logger.exception("llm_understand 未预期异常（降级规则，不阻塞）: %s", e)
            res = {
                "called": True, "reason": "node_error", "error": str(e)[:300],
                "slots": {}, "changes": [], "merged": False, "retried": False,
                "errors": [], "warnings": [],
                "coverage": None, "intent_summary": None,
                "missing": [], "questions": [], "catalog": None,
            }
        ctx["llm_understand"] = res
        ctx["llm_slots"] = res.get("slots") or {}
        ctx["llm_report"] = {
            "reason": res.get("reason"),
            "error": res.get("error"),
            "changes": res.get("changes") or [],
            "errors": res.get("errors") or [],
            "warnings": res.get("warnings") or [],
            "retried": res.get("retried"),
            "coverage": res.get("coverage"),
            "intent_summary": res.get("intent_summary"),
            "missing": res.get("missing") or [],
            "questions": res.get("questions") or [],
        }
        return {
            "called": res.get("called"), "reason": res.get("reason"),
            "error": res.get("error"),
            "merged": res.get("merged"), "changes": res.get("changes") or [],
            "retried": res.get("retried"), "errors": res.get("errors") or [],
            "warnings": res.get("warnings") or [],
            "coverage": res.get("coverage"), "intent_summary": res.get("intent_summary"),
            "missing": res.get("missing") or [], "questions": res.get("questions") or [],
            "slots": res.get("slots") or {},
            "catalog": res.get("catalog"),
        }

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

    if ntype == "confirm":
        # LLM 确认面板（P2）：冲突项/低置信度默认采纳 LLM 补充，高亮让用户改。
        # 无确认项直接跳过；有确认项未决策 → confirm_pending（run_pipeline 收尾发 need_confirm）。
        return await _confirm_llm_items(ctx, broadcast, config)

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

    if ntype == "select_baseline":
        ext = ctx.get("ext") or {}
        scene = ctx.get("scene") or {}
        # 场景分析（scene_analysis）结果优先：目录引导选型 > 场景判定 > extract 词表猜测
        _type_name = (ctx.get("catalog_type_name")
                      or (scene.get("scene_name") if scene.get("determined") else None)
                      or ext.get("server_type_name"))
        _series = scene.get("series") or ext.get("series") or None
        _form = scene.get("form") or ext.get("form") or None
        baselines = select_models(
            ext.get("usage"),
            _type_name,
            _series, _form,
            limit=config.get("max_plans") or 3,
            recommend_strategy_id=config.get("recommend_strategy_id"),
            no_signal_strategy=config.get("no_signal_strategy"),
            variant_signals=build_variant_signals(ext, ctx.get("requirement_text")),
        )
        # 用户明确选了机型 → 只保留该机型（防同类型多机型混推）
        _cat_model_id = ctx.get("catalog_model_id")
        if _cat_model_id:
            _keep = [b for b in baselines
                     if b.get("server_model_id") == _cat_model_id or b.get("id") == _cat_model_id]
            if _keep:
                baselines = _keep
        ctx["baselines"] = baselines
        return {
            "count": len(baselines),
            "matches": [{
                "config_id": b.get("id"), "name": b.get("name") or "",
                "series": b.get("series") or "", "form": b.get("form") or "",
            } for b in baselines],
        }

    if ntype == "match_kp":
        ext = ctx.get("ext") or {}
        baselines = ctx.get("baselines") or []
        # representative_pick：config 显式 > 按预算自动(auto) > min_price
        cfg_pick = config.get("representative_pick")
        pick = cfg_pick if (cfg_pick and cfg_pick != "auto") else _resolve_budget_strategy(ctx.get("budget"))
        # per-机型各配 KP：每个机型按自己的 server_type 套餐 ∪ 需求品类
        # 避免"多类型机型混推时被 baselines[0] 代表"——AI 机型配 GPU、存储机型配 Raid 各得其所
        kp_by_model: dict = {}
        all_kp: list = []
        for bl in baselines:
            type_cats = kp_categories_for_type(bl.get("server_type_name") or "", config.get("type_packages"), ext.get("categories"))
            eff_cats = list(dict.fromkeys(type_cats + (ext.get("categories") or [])))
            # I47：需求未指定内存速率 → 按机型标准速率（base_config.config_content.standard_mem_speed）
            from app.api.candidate_search import _base_config_std_mem_speed
            bl_kp = pick_kp_parts(
                eff_cats, ext.get("keywords", []),
                category_aliases=config.get("category_aliases"),
                representative_pick=pick,
                spec_rules=config.get("spec_rules"),
                fallback_strategy=config.get("fallback_strategy") or "fallback_representative",
                requirement_text=ctx.get("requirement_text"),
                qty_map=ext.get("qty_map"),
                qty_per_token=ext.get("qty_per_token"),
                spec_search_terms=ext.get("spec_search_terms"),
                model_token_regex=ctx.get("model_token_regex"),
                mem_signal=ext.get("mem_signal"),
                cpu_signal=ext.get("cpu_signal"),
                multi_spec_filters=ext.get("multi_spec_filters"),
                drive_groups=ext.get("drive_groups"),
                raid_groups=ext.get("raid_groups"),
                gpu_groups=ext.get("gpu_groups"),
                mem_groups=ext.get("mem_groups"),
                platform_series=bl.get("series"),
                drive_spec_substitute=config.get("drive_spec_substitute", True),
                default_mem_speed=_base_config_std_mem_speed(bl.get("id")),
            )
            mid = bl.get("server_model_id") or bl.get("id")
            kp_by_model[mid] = bl_kp
            all_kp.extend(bl_kp)
        ctx["kp_by_model"] = kp_by_model
        ctx["kp_parts"] = all_kp  # 兼容汇总（step 报数 / 旧消费方）
        by_category: dict[str, int] = {}
        for kp in all_kp:
            c = kp.get("category") or "其他"
            by_category[c] = by_category.get(c, 0) + 1
        unmatched_count = sum(1 for kp in all_kp if kp.get("unmatched"))
        return {"kp_count": len(all_kp), "by_category": by_category, "unmatched_count": unmatched_count}

    if ntype == "compose":
        baselines = ctx.get("baselines") or []
        kp_by_model = ctx.get("kp_by_model") or {}
        if not baselines:
            ctx["plans"] = []
            return {"plans_count": 0, "warning": "未找到匹配的基准配置，请手填或调整需求"}
        # 每个机型取自己的 KP（match_kp per-机型配的），fallback 到全局 kp_parts
        plans = []
        _ext = ctx.get("ext") or {}
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
                                      pipeline_id=ctx.get("pipeline_id") or "")
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
        # LLM 反问节点（P2）：复用 ask_user 目录状态机，但问题文案由 LLM 生成（一次列全缺失项）；
        # LLM 未开/无追问时回落纯目录问题。图里可把 cond_clarity(true) 接到本节点替代 ask_user。
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
        return {"checked": True, "over_budget_count": over_count, "underspend_count": under_count}

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

    # 入口（in-degree=0），按 id 排序保证 WS 序确定
    queue = sorted([nid for nid, d in indeg.items() if d == 0])
    visited: set[str] = set()

    while queue:
        nid = queue.pop(0)
        if nid in visited:
            continue
        visited.add(nid)
        node = nodes[nid]
        ntype = node.get("type") or nid
        config = node_configs.get(nid) or {}

        # condition 静默路由（不广播 step_start）
        if ntype == "condition":
            branch = _eval_condition(config.get("expr", ""), ctx)
            handle = "true" if branch else "false"
            next_edges = [e for e in adj[nid] if (e.get("source_handle") or "true") == handle]
            if not next_edges:
                next_edges = list(adj[nid])  # 无匹配 handle 兜底全走
            for e in next_edges:
                t = e.get("target")
                if t in nodes:
                    queue.append(t)
            continue

        # 普通节点：广播 step_start → 执行 → step_done
        label = node.get("label") or ntype
        await broadcast({"type": "step_start", "step": nid, "label": label})
        payload = await _dispatch(ntype, ctx, config, broadcast)
        await broadcast({"type": "step_done", "step": nid, "payload": payload})

        # 后继入队
        for e in adj[nid]:
            t = e.get("target")
            if t in nodes:
                queue.append(t)

    return ctx
