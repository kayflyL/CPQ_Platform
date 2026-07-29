"""推理流图驱动执行器（P2.3）—— 把硬编码线性 pipeline 改成图拓扑执行。

- Handler 注册表：按 node.type 分发（复用 extract_keywords/select_baselines/pick_kp_parts/build_plan）
- 拓扑 BFS：读 graph → 入口（in-degree=0）→ 遍历 → 每节点 broadcast step_start/step_done
- condition 节点：simpleeval 安全求值 → 选 sourceHandle 分支（静默路由，不广播 step_start）
- WS 协议不变（step_start/step_done/candidates_ready/pipeline_done），前端零改

任何异常由调用方（run_pipeline）兜底回退 _run_linear_fallback。
"""
import logging
from typing import Any, Awaitable, Callable

from app.api.candidate_search import select_baselines, select_models, pick_kp_parts, build_plan, kp_categories_for_type

logger = logging.getLogger(__name__)

try:
    from simpleeval import simple_eval
    HAS_SIMPLEEVAL = True
except ImportError:
    HAS_SIMPLEEVAL = False


BroadcastFn = Callable[[dict], Awaitable[None]]

# 死循环防护：反问最多 N 轮，超限强制 partial 走选型
MAX_CLARIFY_ROUNDS = 3

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
_FALLBACK_REBUTTAL = [
    {"body": {"trigger_field": "具体型号", "priority": 90,
      "question": "您提到 {series} {form}，方便告诉我具体型号吗？",
      "options": [], "fallback": "请补充型号。"}},
    {"body": {"trigger_field": "预算", "priority": 50,
      "question": "这次采购的大致预算范围是？",
      "options": ["5万以内", "5-10万", "10-30万", "30万以上"], "fallback": "请补充预算。"}},
    {"body": {"trigger_field": "用途", "priority": 80,
      "question": "这套配置主要用于什么场景？",
      "options": ["AI训练/推理", "虚拟化", "数据库", "存储"], "fallback": "请描述用途。"}},
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


def _load_rebuttal_templates() -> list:
    """读 rebuttal 话术（三层兜底）。"""
    try:
        from app.repository.requirement_rule_repo import RequirementRuleRepository
        repo = RequirementRuleRepository()
        try:
            return repo.list_by_type("rebuttal", status="active") or _FALLBACK_REBUTTAL
        finally:
            repo.close()
    except Exception:
        return list(_FALLBACK_REBUTTAL)


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


def _compose_question(missing: list, templates: list, ctx: dict) -> tuple:
    """按 missing_fields 挑 rebuttal 话术，渲染问句。返回 (question, options, reply_id)。
    按话术 priority 排序——有话术的字段（型号/用途/预算）优先问；没话术的用 fallback 兜底。"""
    import uuid
    reply_id = f"clr_{uuid.uuid4().hex[:12]}"
    if not missing:
        return ("您的需求已收到，但还有些细节需要确认，方便补充更多规格信息吗？", [], reply_id)
    by_field = {(t.get("body") or {}).get("trigger_field"): t for t in templates}

    def field_priority(f):
        t = by_field.get(f)
        return (t.get("body") or {}).get("priority", 0) if t else 0

    sorted_missing = sorted(missing, key=field_priority, reverse=True)
    parts, options = [], []
    for f in sorted_missing[:2]:  # 一轮最多问 2 个，避免轰炸
        t = by_field.get(f)
        if t:
            body = t.get("body") or {}
            tpl = body.get("question", body.get("fallback", f"请补充{f}。"))
            ext = ctx.get("ext") or {}
            example_default = body.get("example_default", "具体型号")
            example_by_series = body.get("example_by_series") or {}
            series = str(ext.get("series") or "")
            example = example_by_series.get(series) or example_default
            tpl = (tpl.replace("{series}", series)
                      .replace("{form}", str(ext.get("form") or ""))
                      .replace("{example}", example))
            parts.append(tpl)
            if body.get("options"):
                options.extend(body["options"])
        else:
            parts.append(f"请补充{f}。")
    question = " ".join(parts)
    return question, options[:6], reply_id


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

    if ntype == "extract":
        text = ctx.get("requirement_text", "")
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
        return {
            "keywords": ext["keywords"], "categories": ext["categories"],
            "series": ext["series"], "form": ext["form"],
            "usage": ext.get("usage"), "server_type_name": ext.get("server_type_name"),
            "chassis_categories": ext.get("chassis_categories", []),
            "budget": ext.get("budget"),
        }

    if ntype == "select_baseline":
        ext = ctx.get("ext") or {}
        baselines = select_models(
            ext.get("usage"),
            ext.get("server_type_name"),
            ext.get("series"), ext.get("form"),
            limit=config.get("max_plans") or 3,
            recommend_strategy_id=config.get("recommend_strategy_id"),
            no_signal_strategy=config.get("no_signal_strategy"),
        )
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
            type_cats = kp_categories_for_type(bl.get("server_type_name") or "", config.get("type_packages"))
            eff_cats = list(dict.fromkeys(type_cats + (ext.get("categories") or [])))
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
        for bl in baselines:
            mid = bl.get("server_model_id") or bl.get("id")
            bl_kp = kp_by_model.get(mid) or ctx.get("kp_parts") or []
            plans.append(build_plan(bl, bl_kp))
        ctx["plans"] = plans
        return {"plans_count": len(plans)}

    if ntype == "review":
        plans = ctx.get("plans") or []
        ext = ctx.get("ext") or {}
        await broadcast({
            "type": "candidates_ready",
            "plans": plans,
            "keywords": ext.get("keywords", []),
            "series": ext.get("series"),
            "form": ext.get("form"),
        })
        return {}

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
        rules = _load_clarity_rules()
        try:
            from app.services.clarity_evaluator import evaluate_clarity
            level, missing, explain = evaluate_clarity(ext, budget, rules)
        except Exception as e:
            logger.exception("clarity 评估异常，回退 partial: %s", e)
            level, missing, explain = "partial", ["需求描述不够具体"], {}
        # 死循环防护：超轮次上限且非 explicit → 强制 partial
        if ctx.get("clarify_round", 0) >= MAX_CLARIFY_ROUNDS and level != "explicit":
            level = "partial"
            ctx["clarity_capped"] = True
        else:
            ctx["clarity_capped"] = False
        ctx["clarity"] = level
        ctx["missing_fields"] = missing
        ctx["clarity_explain"] = explain
        return {"level": level, "missing_fields": missing, "explain": explain}

    if ntype == "ask_user":
        # 叶子节点：按 missing_fields 挑话术 → broadcast need_input → 标记暂停
        missing = ctx.get("missing_fields") or []
        templates = _load_rebuttal_templates()
        question, options, reply_id = _compose_question(missing, templates, ctx)
        await broadcast({
            "type": "need_input",
            "reply_id": reply_id,
            "question": question,
            "missing_fields": missing,
            "options": options,
            "round": ctx.get("clarify_round", 1),
            "clarity_capped": ctx.get("clarity_capped", False),
        })
        ctx["awaiting_input"] = True
        ctx["last_reply_id"] = reply_id
        return {"question": question, "reply_id": reply_id}

    if ntype == "budget_check":
        # 给 plans 注 over_budget / underspend 标注（共享函数，线性 fallback 也用）
        from app.services.requirement_intel_service import apply_budget_check
        plans = ctx.get("plans") or []
        over_count = apply_budget_check(plans, ctx.get("budget"),
                                         float(config.get("underspend_threshold") or 0.5))
        under_count = sum(1 for p in plans if p.get("underspend"))
        return {"checked": True, "over_budget_count": over_count, "underspend_count": under_count}

    # 未知 type（llm 等 P2.3 预留）静默通过
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
    ctx: dict[str, Any] = {"requirement_text": requirement_text}
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
