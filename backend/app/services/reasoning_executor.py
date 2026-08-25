"""推理流图驱动执行器（P2.3）—— 把硬编码线性 pipeline 改成图拓扑执行。

- Handler 注册表：按 node.type 分发（复用 extract/select_models/pick_kp_parts/build_plan）
- 拓扑 BFS：读 graph → 入口（in-degree=0）→ 遍历 → 每节点 broadcast step_start/step_done
- condition 节点：simpleeval 安全求值 → 选 sourceHandle 分支（静默路由，不广播 step_start）
- WS 协议不变（step_start/step_done/candidates_ready/pipeline_done），前端零改

任何异常由调用方（run_pipeline）兜底诚实降级。
"""
import logging
import re
import time
from typing import Any, Awaitable, Callable

from app.api.candidate_search import (select_models, pick_kp_parts, build_plan,
                           kp_categories_for_type, build_variant_signals)

logger = logging.getLogger(__name__)

try:
    from simpleeval import simple_eval
    HAS_SIMPLEEVAL = True
except ImportError:
    HAS_SIMPLEEVAL = False


BroadcastFn = Callable[[dict], Awaitable[None]]

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


def _delegation_terms(config: dict = None) -> tuple:
    """委托判定词：只读节点配置 + 策略中心 delegation_phrases 规则库，不内置默认。

    规则库空缺时返回空 tuple，是否委托完全交给 AI 的 semantic.delegated 判定。
    """
    terms = []
    if config:
        extra = config.get("delegation_phrases") or []
        if isinstance(extra, str):
            extra = [extra]
        terms.extend(str(x).strip().lower() for x in extra if str(x).strip())
    try:
        from app.services import requirement_rule_catalog as _rc
        for r in _rc.delegation_phrases():
            p = r.get("phrase") or r.get("keywords") or []
            if isinstance(p, str):
                p = [p]
            terms.extend(str(x).strip().lower() for x in p if str(x).strip())
    except Exception:
        pass
    return tuple(dict.fromkeys(x for x in terms if x))


def _is_delegation(text: str, config: dict = None, ext: dict = None) -> bool:
    """判断用户是否把决定权委托给系统。

    优先信任 AI 语义层 semantic.delegated；规则词表仅作关键词兜底，不为空则不强判。
    """
    _sem = ((ext or {}).get("semantic") or {})
    if _sem.get("delegated") is True:
        return True
    t = str(text or "").strip().lower()
    if not t:
        return False
    return any(k in t for k in _delegation_terms(config))


def _latest_user_utterance(ctx: dict) -> str:
    """取本轮实际最新用户原话：补答优先（last_user_answer），其次会话里最后一条用户消息，最后需求正文。"""
    ans = str(ctx.get("last_user_answer") or "").strip()
    if ans:
        return ans
    hist = ctx.get("history") or []
    if isinstance(hist, list):
        for m in reversed(hist):
            if isinstance(m, dict) and str(m.get("role") or "") == "user":
                return str(m.get("content") or "")
    return str(ctx.get("requirement_text") or "").strip()


async def _handle_agent_fill(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    # 方案A：agent_fill 不再起独立 LLM（理解/措辞已由外层 AI 角色 extract_requirement_slots 完成）。
    # 本节点只读已抽好的需求槽位，做契约校验 + 缺失反问 + 落表，保证不重复思考、不再套壳。
    try:
        from app.services.slot_contract import _missing_critical, slot_label, slot_spec
        from app.services.slot_state import is_confirmed
        from app.services.capabilities import _has_recommend_signal
    except Exception:
        _missing_critical = lambda ext: []
        slot_label = lambda k: str(k)
        slot_spec = lambda: []
        is_confirmed = lambda ext, k: True
        _has_recommend_signal = lambda ext: True

    ext = dict(ctx.get("ext") or {})
    req_text = str(ctx.get("requirement_text") or "").strip()
    req_keys = {s.get("key") for s in slot_spec() if s.get("src_type") != "kp" and s.get("key") != "server_model"}
    prev_missing = list(ctx.get("missing_fields") or [])
    missing = [m for m in _missing_critical(ext) if m in req_keys and not is_confirmed(ext, m)]

    # 委托兜底：客户明确委托时不再追问缺失字段，交给下游推荐。
    if not ctx.get("delegated") and _is_delegation(_latest_user_utterance(ctx), config, ext=ext):
        ctx["delegated"] = True

    ctx["missing_fields"] = missing
    # 反问收敛：用户答了但缺口完全一致 → 停止机械重复，按 partial 交下游。
    _no_progress = bool(ctx.get("last_user_answer")) and bool(prev_missing) and sorted(missing) == sorted(prev_missing)
    ctx["converged"] = bool(_no_progress)
    need_ask = bool(missing) and not ctx.get("force_complete") and not ctx.get("delegated") and not _no_progress and not _has_recommend_signal(ext)

    # 缺关键槽：触发反问，把外层 AI 角色已生成的自然反问 question 透传；无则用字段名组成中性提示。
    if need_ask:
        question = str(ctx.get("agent_fill_ask") or "").strip()
        if not question:
            question = "还有几个关键信息待确认：" + "、".join([slot_label(m) for m in missing])
        import uuid
        rid = f"agent_{uuid.uuid4().hex[:12]}"
        ctx["awaiting_input"] = True
        ctx["last_reply_id"] = rid
        ctx["last_ask_question"] = question
        _fz = ctx.get("feasibility") or {}
        _fz_lines = [("⚠️ " + w) for w in (_fz.get("warnings") or [])] + [("提示：" + h) for h in (_fz.get("hints") or [])]
        if _fz_lines:
            question = "\n".join(_fz_lines) + "\n" + question
        if broadcast:
            try:
                await broadcast({"type": "need_input", "reply_id": rid, "question": question,
                                 "options": None, "why": "", "missing_fields": missing,
                                 "source": "agent_fill"})
            except Exception:
                pass
        return {"ok": True, "question": question, "options": None, "source": "agent_fill",
                "sufficient": False, "missing_critical": missing}

    # 校验 + 落表：无关键缺口（或已委托/已收敛），固化需求快照并推进下游。
    ctx["awaiting_input"] = False
    _has_model = bool(ext.get("server_model") or ext.get("model"))
    if ctx.get("delegated"):
        ctx["clarity"] = "delegated"
    elif ctx.get("converged"):
        ctx["clarity"] = "partial"
    elif _has_model:
        ctx["clarity"] = "explicit"
    elif missing:
        ctx["clarity"] = "partial"
    else:
        ctx["clarity"] = "explicit" if _has_model else "partial"

    # 固化需求快照（下游只读，不回填）。
    try:
        from app.services.capabilities import _freeze_requirement
        _freeze_requirement(ctx, ext, req_text)
    except Exception:
        pass

    if ctx.get("business_mode") == "opportunity_flow" and ctx.get("opportunity_id"):
        try:
            from app.services.portal_flow_adapter import persist_requirement_from_ctx
            persist_requirement_from_ctx(ctx, str(ctx.get("operator_name") or ""))
        except Exception:
            logger.exception("持久化真实需求草稿失败 opportunity=%s", ctx.get("opportunity_id"))

    return {"ok": True, "source": "agent_fill", "sufficient": bool(not missing),
            "missing_critical": missing, "done": not need_ask}

def _model_selection_intent(answer: str) -> str:
    """识别用户在机型选型节点的意图（关键词兜底，主判定走 LLM resolve_intent）。

    意图词表外置到 rules.requirement_rules 的 model_action_phrases；规则库空缺时不强判，
    只返回默认 choose。型号匹配由 baselines 的确定性字段完成，本函数不承担。
    仅在 LLM 不可用/超时时作为保守兜底，避免断网时把“确认/推荐”误判成自配。
    """
    text = str(answer or "").strip().lower()
    if not text:
        return ""
    try:
        from app.services import requirement_rule_catalog as _rc
        phrases = _rc.model_action_phrases()
    except Exception:
        phrases = {}
    for action in ("self_config", "auto_pick", "reselect", "cancel"):
        if any(k in text for k in phrases.get(action) or []):
            return action
    return ""


async def _resolve_selection_mode(ctx: dict, config: dict, answer: str) -> str:
    """用 LLM 判断当前应走推荐 / AI 智能选配 / 用户自配（决策权交给 AI）。

    返回:
      - recommend  : 出候选卡让用户选（默认，AI 拿不准时）
      - ai_config  : 用户明确委托“你推荐/帮我选好并继续”，自动锁定并推进下游
      - self_config: 用户明确“我自己配”，跳过 BOM 直接进详情页
      抽屉的 selection_mode 只作为兜底偏好，AI 意图优先；py 不写死流程路径。
    """
    # 意图由角色层统一判定；这里只做映射，不再二次调 LLM。
    pi = str(ctx.get("plan_intent") or "").strip().lower()
    if pi == "auto_recommend":
        return "ai_config"
    if pi == "self_config":
        return "self_config"
    if pi in ("confirm_choice", "choose", "refine", "reselect"):
        return "recommend"
    kw = _model_selection_intent(str(answer or "").strip())
    if kw == "auto_pick":
        return "ai_config"
    if kw == "self_config":
        return "self_config"
    return str(config.get("selection_mode") or "recommend").strip().lower()


def _lock_model_from_answer(answer: str, baselines: list) -> dict:
    """把用户回复解析为机型选择；匹配不到返回空 dict。"""
    text = str(answer or "").strip()
    if not baselines or not text:
        return {}
    low = text.lower()
    # 优先“第 1 个 / 1 / 选 2”
    m = re.search(r"(?:第\s*)?([1-9])[、.．\s]*(?:个|台|项)?", text)
    if m:
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(baselines):
            return baselines[idx]
    # 其次型号名/ID 精确包含
    for b in baselines:
        hay = " ".join(str(b.get(k) or "") for k in ("name", "id", "server_model_id")).lower()
        if hay and (low in hay or (hay and len(low) >= 3 and hay in low)):
            return b
    return {}


def _model_reason_matches(baselines: list) -> list:
    return [{
        "config_id": b.get("id"), "name": b.get("name") or "",
        "series": b.get("series") or "", "form": b.get("form") or "",
        "match_stage": b.get("match_stage"), "fallback_note": b.get("fallback_note") or "",
    } for b in baselines]


def _model_reason_display(config: dict) -> dict:
    """机型展示白盒参：按系列分组 / 每组限量 / 介绍字数 / 是否附详情页链接。"""
    cfg = dict(config or {})
    try:
        from app.services import prompt_store
        _defaults = prompt_store.get_prompt_defaults("model_reason")
    except Exception:
        _defaults = {}
    return {
        "group_by_series": bool(cfg.get("group_by_series", True)),
        "per_series_limit": max(1, int(cfg.get("per_series_limit") or 2)),
        "intro_max_chars": max(0, int(cfg.get("intro_max_chars") or 180)),
        "show_detail_link": bool(cfg.get("show_detail_link", True)),
        "model_ask_phrase": str(cfg.get("model_ask_phrase") or "").strip(),
        "detail_link_phrase": str(cfg.get("detail_link_phrase") or "").strip(),
        "candidate_lede": str(cfg.get("candidate_lede") or _defaults.get("candidate_lede") or "").strip(),
        "choice_lede": str(cfg.get("choice_lede") or _defaults.get("choice_lede") or "").strip(),
        "no_exact_lede": str(cfg.get("no_exact_lede") or _defaults.get("no_exact_lede") or "").strip(),
        "no_match_question": str(cfg.get("no_match_question") or _defaults.get("no_match_question") or "").strip(),
        "self_config_lede": str(cfg.get("self_config_lede") or _defaults.get("self_config_lede") or "").strip(),
    }


def _model_intent_from_plan(pi: str, answer: str, llm_enabled: bool) -> str:
    """把角色层 plan_intent 映射成机型节点动作；仅 LLM 不可用时用关键词兜底。"""
    plan = {
        "auto_recommend": "auto_pick",
        "self_config": "self_config",
        "cancel": "cancel",
        "confirm_choice": "choose",
        "choose": "choose",
        "refine": "refine",
        "reselect": "reselect",
    }.get(str(pi or "").strip().lower())
    if plan:
        return plan
    if not llm_enabled:
        return _model_selection_intent(str(answer or "").strip())
    return ""


def _group_baselines(baselines: list, display: dict) -> list:
    """按系列分组、每组限量；保留原排序，去重，不改机型字段。"""
    if not display.get("group_by_series", True):
        return list(baselines or [])
    limit = int(display.get("per_series_limit") or 2)
    order: list[str] = []
    by_series: dict[str, list] = {}
    for b in baselines or []:
        name = str(b.get("name") or "").strip()
        if not name:
            continue
        series = str(b.get("series") or "其他").strip() or "其他"
        if series not in by_series:
            by_series[series] = []
            order.append(series)
        if len(by_series[series]) < limit:
            by_series[series].append(b)
    out: list[dict] = []
    for s in order:
        out.extend(by_series.get(s) or [])
    return out


async def _model_detail_intro(ctx: dict, baseline: dict, display: dict) -> str:
    """从真实目录数据组装机型介绍（字数与是否附链接由节点配置，不写死文案）。"""
    name = str((baseline or {}).get("name") or "")
    series = str((baseline or {}).get("series") or "")
    form = str((baseline or {}).get("form") or "")
    _bc = baseline.get("base_config") or {}
    detail: dict = {}
    try:
        from app.services.catalog_guide import load_catalog
        _types, _models_by_type = load_catalog()
        for _ms in (_models_by_type or {}).values():
            for _m in (_ms or []):
                if str(_m.get("name") or "") == name or str(_m.get("id") or "") == str((baseline or {}).get("id") or ""):
                    detail = _m if isinstance(_m, dict) else {}
                    _bc = detail.get("base_config") or _bc
                    break
            if detail:
                break
    except Exception:
        detail = {}
    _parts = [name]
    if series:
        _parts.append("系列 " + series)
    if form:
        _parts.append("形态 " + form)
    for k in ("cpus", "cpu_model", "max_memory", "max_disk", "drive_bays", "gpu_cnt"):
        _v = _bc.get(k) or detail.get(k)
        if _v:
            _parts.append(f"{k}={_v}")
    _summary = (_bc.get("summary") or detail.get("summary") or "").strip()
    _limit = int(display.get("intro_max_chars") or 180)
    if _summary:
        _parts.append(_summary if len(_summary) <= _limit else _summary[:_limit] + "…")
    out = "；".join(p for p in _parts if p)
    if display.get("show_detail_link", True) and str((baseline or {}).get("id") or ""):
        _lp = str(display.get("detail_link_phrase") or "").strip()
        out += "\n" + (_lp if _lp else "可进入详情页查看完整参数。")
    return out


async def _ask_model_choice_grouped(ctx: dict, baselines: list, rule_res: dict, broadcast: BroadcastFn, display: dict) -> dict:
    """一次性列出候选（按系列分组、每组限量），只广播一次候选卡。"""
    _baselines = _group_baselines(baselines, display)
    if not _baselines:
        return await _ask_model_choice(ctx, baselines, rule_res, broadcast, "")
    grouped: dict[str, list] = {}
    order: list[str] = []
    for b in _baselines:
        s = str(b.get("series") or "其他").strip() or "其他"
        if s not in grouped:
            grouped[s] = []
            order.append(s)
        grouped[s].append(b)
    _lines = []
    for s in order:
        _lines.append(f"{s}：")
        for b in grouped[s]:
            _lines.append("  " + str(b.get("name") or "") + "（" + str(b.get("form") or "") + "）")
    _preamble = str(display.get("candidate_lede") or "")
    body = _preamble + "\n" + "\n".join(_lines)
    question = body
    ctx["awaiting_input"] = True
    ctx["current_target"] = "model_reason"
    ctx["model_phase"] = "await_choice"
    ctx["_locked_baseline"] = {}
    ctx.pop("model_selection", None)
    ctx["last_ask_question"] = question
    ctx["model_reason"] = {"source": "recommend", "baselines": _baselines,
                           "reason": "等待用户确认候选机型"}
    if broadcast:
        try:
            await broadcast({"type": "need_confirm", "step": "model_reason", "question": question,
                             "options": [f"{i + 1}. {b.get('name')}" for i, b in enumerate(_baselines)],
                             "why": "机型选型需要用户确认候选",
                             "candidates": _baselines})
        except Exception:
            pass
    return {**rule_res, "source": "recommend", "matches": _model_reason_matches(_baselines),
            "question": question, "reason": "等待用户确认候选机型"}




async def _handle_model_reason(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """方案A：机型选型节点不再起独立 LLM（run_model_reason 已弃用）。节点只做：
    真实候选（select_models）按系列分组列出 -> 用户确认机型后锁定并继续配件/BOM；
    出口（自配/取消）由角色层 plan_intent 判定，关键词仅在 LLM 不可用时兜底。
    """
    from app.services.capabilities import run_select_baseline_rule, _model_reason_config
    ext = dict(ctx.get("ext") or {})
    answer = str(ctx.get("last_user_answer") or "").strip()
    pi = str(ctx.get("plan_intent") or "").strip().lower()
    cfg = _model_reason_config(config or {})
    display = _model_reason_display(config or {})
    llm_on = bool(ctx.get("llm_enabled", True))
    intent = _model_intent_from_plan(pi, answer, llm_on)

    if intent == "self_config":
        ctx["flow_exit"] = "self_config"
        ctx["awaiting_input"] = False
        ctx["baselines"] = []
        ctx["model_reason"] = {"source": "self_config", "reason": "用户选择自己配置"}
        return {"count": 0, "matches": [], "source": "self_config",
                "reason": "用户选择自己配置"}
    if intent == "cancel":
        ctx["flow_exit"] = "cancelled"
        ctx["awaiting_input"] = False
        ctx["baselines"] = []
        ctx["model_reason"] = {"source": "cancelled", "reason": "用户取消方案配置"}
        return {"count": 0, "matches": [], "source": "cancelled", "reason": "已取消方案配置"}

    # 首次 / 用户明确委托“你推荐/帮我选好并继续”：直接锁首台交下游 BOM。
    if intent == "auto_pick":
        rule_res = run_select_baseline_rule(ctx, config)
        _baselines = _group_baselines(ctx.get("baselines") or [], display)
        if not _baselines:
            return await _ask_model_choice_grouped(ctx, [], rule_res, broadcast, display)
        locked = _baselines[0]
        ctx["baselines"] = [locked]
        ctx["model_selection"] = {"id": locked.get("id"), "name": locked.get("name") or ""}
        ctx["model_reason"] = {"source": "auto_pick", "baseline": locked,
                               "reason": "用户委托智能选配，已锁定推荐机型 " + (locked.get("name") or "")}
        ctx["awaiting_input"] = False
        return {"count": 1, "matches": _model_reason_matches([locked]),
                "source": "auto_pick", "reason": "已按你的委托锁定机型，继续配件选配"}

    if intent == "choose" and pi == "confirm_choice":
        ctx["_confirm_choice"] = True
    rule_res = run_select_baseline_rule(ctx, config)
    _baselines = _group_baselines(ctx.get("baselines") or [], display)
    if _baselines and len(_baselines) == 1 and not answer:
        locked = _baselines[0]
        ctx["baselines"] = [locked]
        ctx["_locked_baseline"] = locked
        ctx["model_selection"] = {"id": locked.get("id"), "name": locked.get("name") or ""}
        ctx["model_reason"] = {"source": "single_pick", "baseline": locked,
                               "reason": "唯一候选，已锁定机型 " + (locked.get("name") or "")}
        ctx["awaiting_input"] = False
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "model_reason",
                                 "question": (str(display.get("candidate_lede") or "") + "\n" +
                                              (locked.get("name") or "")),
                                 "options": [locked.get("name") or ""],
                                 "why": "",
                                 "candidates": _baselines,
                                 "auto_locked": True})
            except Exception:
                pass
        return {"count": 1, "matches": _model_reason_matches([locked]),
                "source": "single_pick", "reason": "已锁定唯一候选机型，继续配件选配"}
    if _baselines:
        # 用户点名具体机型（如“介绍下 ES22V3”/“选第 1 个”）→ 锁定该机型并进入介绍；
        # 仅当明确“确认当前候选”且没给序号时才锁首台；否则按系列重新列候选。
        locked = _lock_model_from_answer(answer, _baselines)
        if not locked and intent == "choose" and ctx.get("_confirm_choice"):
            locked = _baselines[0]
        if locked:
            ctx["baselines"] = [locked]
            ctx["_locked_baseline"] = locked
            ctx["model_selection"] = {"id": locked.get("id"), "name": locked.get("name") or ""}
            ctx["model_reason"] = {"source": "user_pick", "baseline": locked,
                                   "reason": "用户已锁定机型 " + (locked.get("name") or "")}
            ctx["awaiting_input"] = False
            return {"count": 1, "matches": _model_reason_matches([locked]),
                    "source": "user_pick", "reason": "已按你的选择锁定机型，继续配件选配"}

    # 默认：列出候选（按系列分组、每组限量），一次广播候选卡。
    return await _ask_model_choice_grouped(ctx, _baselines, rule_res, broadcast, display)

async def _ask_model_choice(ctx: dict, baselines: list, rule_res: dict, broadcast: BroadcastFn, fallback: str) -> dict:
    """发候选卡，等用户确认。用户能看到的文字由 LLM 生成，py 只留纯数据与流转。"""
    _fz = ctx.get("feasibility") or {}
    _fz_lines = [("⚠️ " + w) for w in (_fz.get("warnings") or [])] + [("提示：" + h) for h in (_fz.get("hints") or [])]
    _fz_block = ("\n".join(_fz_lines) + "\n") if _fz_lines else ""
    if not baselines:
        # 候选为空：从在售目录取真实机型兜底；目录也空则给中性提示，不背固定“自己配置/取消”。
        try:
            from app.services.catalog_guide import load_catalog
            _types, _by_type = load_catalog()
            _browse = []
            for _t in _types or []:
                for _m in (_by_type.get(str(_t.get("name") or "")) or []):
                    _bc = _m.get("base_config") or {}
                    _browse.append({"id": _m.get("id"), "name": _m.get("name") or "",
                                    "series": _bc.get("series") or _m.get("series") or "",
                                    "form": _bc.get("form") or _m.get("form") or ""})
        except Exception:
            _browse = []
        if _browse:
            baselines = _browse
            ctx["baselines"] = baselines
            rule_res = {**rule_res, "count": len(baselines)}
            _preamble = str(display.get("no_exact_lede") or "")
        else:
            question = _fz_block + str(display.get("no_match_question") or "")
            ctx["awaiting_input"] = True
            ctx["current_target"] = "model_reason"
            ctx["last_ask_question"] = question
            ctx["model_reason"] = {"source": "recommend", "baselines": [], "reason": "目录无匹配候选，等待用户选择"}
            if broadcast:
                try:
                    await broadcast({"type": "need_confirm", "step": "model_reason", "question": question,
                                     "options": [], "why": "候选为空"})
                except Exception:
                    pass
            return {**rule_res, "source": "recommend", "matches": [], "question": question,
                    "reason": "等待用户选择处理方式"}

    options = [f"{i + 1}. {b.get('name') or ''}（{b.get('series') or ''}/{b.get('form') or ''}）"
               for i, b in enumerate(baselines[:5])]
    _preamble = fallback or str(display.get("choice_lede") or "")
    body = _preamble + "\n" + "\n".join(options)
    question = _fz_block + body
    ctx["awaiting_input"] = True
    ctx["current_target"] = "model_reason"
    ctx["last_ask_question"] = question
    ctx["model_reason"] = {"source": "recommend", "baselines": baselines,
                           "reason": "等待用户确认候选机型"}
    if broadcast:
        try:
            await broadcast({"type": "need_confirm", "step": "model_reason", "question": question,
                             "options": options + ["重选机型", "取消"],
                             "why": "机型选型需要用户确认候选",
                             "candidates": baselines})
        except Exception:
            pass
    return {**rule_res, "source": "recommend", "matches": _model_reason_matches(baselines),
            "question": question, "reason": "等待用户确认候选机型"}


def _kp_reply_intent(answer: str) -> str:
    """识别用户在配件选配节点的意图（关键词兜底，主判定走 LLM resolve_intent）。"""
    text = str(answer or "").strip().lower()
    if not text:
        return "confirm"
    try:
        from app.services import requirement_rule_catalog as _rc
        phrases = _rc.kp_action_phrases()
    except Exception:
        phrases = {}
    for action in ("cancel", "reselect_model", "confirm"):
        if any(k in text for k in phrases.get(action) or []):
            return action
    return "adjust"


async def _resolve_kp_intent(ctx: dict, answer: str) -> str:
    """配件节点意图映射：角色层已统一判定，这里只按 plan_intent 映射，关键词仅作兜底。"""
    text = str(answer or "").strip()
    pi = str(ctx.get("plan_intent") or "").strip().lower()
    if pi == "cancel":
        return "cancel"
    if pi == "reselect":
        return "reselect_model"
    if pi == "confirm_choice":
        return "confirm"
    if pi == "refine":
        return "adjust"
    if pi in ("self_config", "auto_recommend", "choose"):
        return "confirm"
    if not text:
        return "confirm"
    return _kp_reply_intent(text)


def _kp_part_reason(p: dict) -> str:
    """从真实配件数据构造选择理由（规则/契约/规格），不背固定话术。"""
    for k in ("reason", "unmatched_reason", "matched_spec"):
        _v = str(p.get(k) or "").strip()
        if _v:
            return _v
    _spec = p.get("specs")
    if isinstance(_spec, dict) and _spec:
        return "规格 " + "、".join(f"{k}={v}" for k, v in _spec.items())
    return ""


def _kp_summary_lines(parts: list) -> list:
    out: list = []
    for p in (parts or [])[:12]:
        name = p.get("name") or p.get("model") or p.get("pn") or ""
        qty = p.get("qty")
        line = f"- {name}" + (f" × {qty}" if qty is not None else "")
        _r = _kp_part_reason(p)
        if _r:
            line += f"｜{_r}"
        out.append(line)
    return out


async def _handle_kp_reason(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    # 配件推理（AI 路）：LLM 提议 + 规则校验后先让用户确认；用户可改口、重选机型或取消。
    # 精确执行仍由规则保证（compose 需要完整字段），LLM 输出确认 + 理由。
    from app.services.capabilities import run_kp_reason, run_match_kp_rule
    try:
        from app.services import prompt_store
        _kp_defaults = prompt_store.get_prompt_defaults("kp_reason")
    except Exception:
        _kp_defaults = {}
    answer = str(ctx.get("last_user_answer") or "").strip()
    intent = await _resolve_kp_intent(ctx, answer) if answer else "first"

    if intent == "cancel":
        ctx["flow_exit"] = "cancelled"
        ctx["awaiting_input"] = False
        ctx["kp_reason"] = {"source": "cancelled", "reason": "用户取消方案配置"}
        return {"source": "cancelled", "reason": "已取消方案配置"}
    if intent == "reselect_model":
        # 回到上一节点重新挑机型：本轮先暂停，pending 的 current_target 会保存为 model_reason。
        ctx["awaiting_input"] = True
        ctx["current_target"] = "model_reason"
        ctx["last_ask_question"] = str(_kp_defaults.get("reselect_question") or "")
        ctx["model_selection"] = None
        ctx["baselines"] = []
        ctx["kp_reason"] = {"source": "reselect_model", "reason": "用户要求重新选择机型"}
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "kp_reason",
                                 "question": ctx["last_ask_question"],
                                 "options": [], "why": "用户要求重新选择机型"})
            except Exception:
                pass
        return {"source": "reselect_model", "reason": "用户要求重新选择机型"}

    # 用户要调整配件时，把补充要求并入本轮需求文本，再重新提议/校验。
    if intent == "adjust" and answer:
        old_text = str(ctx.get("requirement_text") or "")
        ctx["requirement_text"] = f"{old_text}\n配件补充要求：{answer}".strip()
        ctx["kp_proposal"] = None

    if intent == "first" or intent == "adjust":
        res = await run_kp_reason(ctx, config, broadcast)
        rule_res = run_match_kp_rule(ctx, config)
        parts = ctx.get("kp_parts") or []
        ctx["kp_reason"] = {**rule_res, "source": "llm+rule" if res.get("ok") else "rule",
                            "proposal_reason": res.get("reason") or ""}
        # 确定性选件完成后直接交给 compose 组装 BOM；只有完全没匹配到、或出现未匹配项时才停下。
        if ctx.get("force_complete") or ctx.get("delegated") or rule_res.get("kp_count"):
            if not rule_res.get("unmatched_count"):
                ctx["kp_reason"] = {**ctx["kp_reason"], "source": "confirmed"}
                ctx["awaiting_input"] = False
                return {**rule_res, "source": "confirmed", "reason": "配件方案已确认", "kp_count": len(parts)}
        lines = _kp_summary_lines(parts)
        question = str(_kp_defaults.get("parts_unmatched_question") or "") + "\n" + ("\n".join(lines) if lines else "")
        ctx["awaiting_input"] = True
        ctx["current_target"] = "kp_reason"
        ctx["last_ask_question"] = question
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "kp_reason", "question": question,
                                 "options": ["重新选机型", "取消"], "why": "配件匹配未完成"})
            except Exception:
                pass
        return {**rule_res, "source": "confirm_parts", "question": question, "reason": "等待用户补充配件要求"}

    # 用户确认/直接继续：用当前已确认的配件结果交给 compose。
    rule_res = run_match_kp_rule(ctx, config)
    parts = ctx.get("kp_parts") or []
    ctx["kp_reason"] = {**rule_res, "source": "confirmed"}
    ctx["awaiting_input"] = False
    return {**rule_res, "source": "confirmed", "reason": "配件方案已确认", "kp_count": len(parts)}

async def _handle_compose(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    from app.services.capabilities import _compose_config, _get_nested
    cfg = _compose_config(config)
    baselines = ctx.get("baselines") or []
    kp_by_model = ctx.get("kp_by_model") or {}
    if not baselines:
        ctx["plans"] = []
        return {"plans_count": 0, "warning": "无匹配的整机基准配置，请调整需求后重试"}
    # 每个机型取自己的 KP（match_kp per-机型配的），fallback 到全局 kp_parts；来源策略由节点配置决定。
    plans = []
    _ext = ctx.get("ext") or {}
    # 电源：需求文本显式瓦数/数量 > build_plan 按负载推断；是否启用和读取路径均由节点配置决定。
    _sig_w = _get_nested(ctx, cfg.get("psu_wattage_source"), None) if cfg.get("psu_override_enabled", True) else None
    _sig_q = _get_nested(ctx, cfg.get("psu_qty_source"), None) if cfg.get("psu_override_enabled", True) else None
    for bl in baselines:
        mid = bl.get("server_model_id") or bl.get("id")
        bl_kp = (ctx.get("kp_parts") or []) if cfg.get("kp_source") == "global" else (kp_by_model.get(mid) or ctx.get("kp_parts") or [])
        # 需求文本功率/数量优先覆盖 build_plan 推断，并让覆盖值在 L6 模板求值前生效（模板行直接显示正确瓦数）。
        _p = build_plan(bl, bl_kp, psu_wattage=_sig_w, psu_qty=_sig_q)
        plans.append(_p)
    ctx["plans"] = plans
    return {"plans_count": len(plans)}


def _ctx_value(ctx: dict, path: str) -> Any:
    """按点分路径读取 ctx 值；路径不存在返回 None。"""
    cur: Any = ctx
    for part in str(path or "").split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _default_output_target(output_kind: str) -> str:
    if output_kind == "requirement_draft":
        return "requirement"
    if output_kind == "bom_scheme_draft":
        return "bom_scheme"
    if output_kind == "data_answer":
        return "conversation_reply"
    return "artifact"


def _apply_payload_map(payload_map: dict, ctx: dict) -> dict:
    payload: dict = {}
    for dest, source in (payload_map or {}).items():
        if not dest:
            continue
        if isinstance(source, str) and source.startswith("ctx."):
            payload[str(dest)] = _ctx_value(ctx, source[4:])
        elif isinstance(source, dict) and isinstance(source.get("source"), str):
            payload[str(dest)] = _ctx_value(ctx, source["source"].removeprefix("ctx."))
        else:
            payload[str(dest)] = source
    return payload

async def _handle_generic_agent(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Generic agent node: LLM decides, calls tools from the global catalog."""
    from app.services.agent_react import run_react_loop
    text = ctx.get("requirement_text") or ctx.get("normalized_text") or ""
    if not str(text).strip():
        return {"ok": False, "answer": "", "reason": "empty_text"}
    result = await run_react_loop(
        requirement_text=str(text),
        config=config,
        max_iterations=int(config.get("max_iterations") or 6),
        system_prompt=config.get("system_prompt") or None,
        history=ctx.get("history") or [],
    )
    ctx["agent_result"] = result
    return {
        "ok": result.get("ok"),
        "answer": result.get("answer") or "",
        "iterations": result.get("iterations") or 0,
        "tool_calls_log": result.get("tool_calls_log") or [],
        "thought_log": result.get("thought_log") or [],
    }

async def _handle_generic_rule(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Generic rule node: load active bodies for referenced rule types from the catalog."""
    from app.services.requirement_rule_catalog import active_bodies
    rule_types = config.get("rule_types") or []
    applied = {str(rt): active_bodies(str(rt)) for rt in rule_types}
    ctx["rule_data"] = applied
    return {"rule_types": list(applied), "matched": sum(len(v) for v in applied.values())}

async def _handle_generic_assemble(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Generic assemble node: preserve structured context for downstream output."""
    assembled = {
        "template": config.get("template") or "",
        "output_schema": config.get("output_schema") or {},
        "plans": ctx.get("plans") or [],
        "ext": ctx.get("ext") or {},
    }
    ctx["assembled"] = assembled
    return {"assembled": True, "plans": len(assembled["plans"])}

async def _handle_generic_output(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Output node = 交接契约：把上游 ctx 结果映射成下游业务实体/对话文本并返回回执。"""
    output_kind = str(config.get("output_kind") or ctx.get("output_kind") or "generic").strip() or "generic"
    target = str(config.get("target") or _default_output_target(output_kind)).strip() or _default_output_target(output_kind)
    payload = _apply_payload_map(config.get("payload_map") or {}, ctx)

    entity = None
    entity_type = ""

    if output_kind == "requirement_draft":
        entity_type = "requirement"
        try:
            from app.services.portal_flow_adapter import persist_requirement_from_ctx
            entity = persist_requirement_from_ctx(ctx, str(ctx.get("operator_name") or ""))
        except Exception:
            logger.exception("输出节点持久化需求草稿失败 opportunity=%s", ctx.get("opportunity_id"))
        if entity:
            payload["requirement"] = entity
    elif output_kind == "bom_scheme_draft":
        entity_type = "bom_scheme"
        try:
            from app.services.portal_flow_adapter import persist_requirement_and_bom_from_ctx, build_preview_bom_scheme
            entity = persist_requirement_and_bom_from_ctx(ctx, str(ctx.get("operator_name") or ""), config)
            if not entity:
                # 会话/无商机模式不落库，但兜底输出可读 BOM 预览（含 configs），保证画布与聊天可点开。
                entity = build_preview_bom_scheme(ctx, config)
        except Exception:
            logger.exception("输出节点持久化需求单/BOM 方案草稿失败 opportunity=%s", ctx.get("opportunity_id"))
        if entity:
            payload["bom_scheme"] = entity
    elif output_kind == "data_answer":
        agent_result = ctx.get("agent_result") if isinstance(ctx.get("agent_result"), dict) else {}
        answer = str(agent_result.get("answer") or "").strip() or str(_ctx_value(ctx, "assembled.answer") or "").strip()
        payload.setdefault("answer", answer)
        payload.setdefault("data", ctx.get("assembled") if isinstance(ctx.get("assembled"), dict) else {})
    else:
        payload.setdefault("result", ctx.get("assembled") if isinstance(ctx.get("assembled"), dict) else {})
        payload.setdefault("template", config.get("template") or "")
        payload.setdefault("output_schema", config.get("output_schema") or {})

    actions = config.get("actions") or []
    handoff = {
        "output_kind": output_kind,
        "target": target,
        "payload": payload,
        "actions": list(actions),
    }
    ctx["output_kind"] = output_kind
    ctx["output_target"] = target
    ctx["output_payload"] = payload
    ctx["output_actions"] = handoff["actions"]
    ctx["handoff"] = handoff

    if entity_type and entity:
        # 只把真实业务实体挂到 ctx，由各通道终端统一补发 business_entity_ready 消息；
        # 避免在 executor 内提前广播一条无 message 的事件，造成前端重复收流。
        ctx["business_entity"] = {
            "entity_type": entity_type,
            "entity": entity,
            "opportunity_id": ctx.get("opportunity_id") or "",
            "target": target,
            "payload": payload,
            "actions": handoff["actions"],
        }
    else:
        await broadcast({
            "type": "handoff_ready",
            "output_kind": output_kind,
            "target": target,
            "payload": payload,
            "actions": handoff["actions"],
        })

    return {
        "output_kind": output_kind,
        "target": target,
        "payload": payload,
        "actions": handoff["actions"],
    }

async def _handle_generic_orchestrator(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Generic orchestrator node: no direct business execution; config is read by run_pipeline."""
    ctx["orchestrator_config"] = config or {}
    return {"configured": True, "config": config or {}}


async def _handle_generic_input(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Generic input node: normalize the user text into the shared skill context."""
    raw = str(ctx.get("requirement_text") or "").strip()
    ctx["input"] = raw
    ctx["skill_input"] = raw
    ctx["normalized_text"] = raw
    return {"input": raw}

_REASONING_HANDLERS: dict[str, Callable[[dict, dict, BroadcastFn], Awaitable[dict]]] = {
    "agent_fill": _handle_agent_fill,
    "model_reason": _handle_model_reason,
    "kp_reason": _handle_kp_reason,
    "compose": _handle_compose,
    "agent": _handle_generic_agent,
    "rule": _handle_generic_rule,
    "assemble": _handle_generic_assemble,
    "output": _handle_generic_output,
    "orchestrator": _handle_generic_orchestrator,
    "input": _handle_generic_input,
}

async def _dispatch(ntype: str, ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """按节点 type 从注册表分发，更新 ctx，返回 step_done payload。"""
    handler = _REASONING_HANDLERS.get(ntype)
    if handler is None:
        ctx.setdefault("exec_trace", []).append({"type": ntype, "status": "skipped_unknown"})
        logger.warning("未知节点类型，跳过执行: %s", ntype)
        return {"skipped": "unknown_node", "node": ntype}
    return await handler(ctx, config, broadcast)


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
    # ⚠️ 兼容含语义回边（反问循环等）的旧图：拓扑 BFS 可能因环停摆
    #（环内节点入度≥1，初始队列可能为空）。这里做「环容忍」：无入度 0 节点时按定义顺序
    # 从首个节点起步；环内节点按定义顺序兜底执行，保证老图/测试仍能跑完整链
    #（orchestrator 主路径不依赖本函数，v12 回边由编排器语义处理）。
    queue = sorted([nid for nid, d in indeg.items() if d == 0])
    visited: set[str] = set()
    _node_order = {nid: i for i, nid in enumerate(nodes.keys())}  # 节点定义顺序（入口在前）
    if not queue and nodes:
        # 全环（反问回边）→ 从定义顺序第一个节点起步，
        # 而不是字母序（否则可能从尾部节点起步，链路乱序）。
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
        ntype = node.get("runtime") or node.get("type") or nid
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
