"""推理流图驱动执行器（P2.3）—— 把硬编码线性 pipeline 改成图拓扑执行。

- Handler 注册表：按 node.type 分发（复用 extract/select_models/pick_kp_parts/build_plan）
- 拓扑 BFS：读 graph → 入口（in-degree=0）→ 遍历 → 每节点 broadcast step_start/step_done
- condition 节点：simpleeval 安全求值 → 选 sourceHandle 分支（静默路由，不广播 step_start）
- WS 协议不变（step_start/step_done/candidates_ready/pipeline_done），前端零改

任何异常由调用方（run_pipeline）兜底诚实降级。
"""
import json
import logging
import re
import time
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
    # 智能对话填表 Agent：会对话、会查目录/KP、边答边填线索登记表。
    # 复用 run_agent_fill；信息不足时内部自然反问（need_input）。
    # 用户委托（你推荐/随便/都行/我不太懂/帮我推荐）时不再追问缺失字段，交给下游。
    # 注意：last_user_answer 只在“回答上一个追问”时才有值；首轮/自由输入时必须看最新用户原话，
    # 否则托管式需求会被机械反问（这正是“AI 已判断委托、本地状态机却再问一次”的根因）。
    if not ctx.get("delegated") and _is_delegation(_latest_user_utterance(ctx), config, ext=ctx.get("ext")):
        ctx["delegated"] = True
    from app.services.capabilities import run_agent_fill
    res = await run_agent_fill(ctx, config, broadcast)
    # 信任 LLM 在 semantic=delegated 中给出的委托判定，兜底覆盖关键词漏判的场景。
    _sem = (ctx.get("ext") or {}).get("semantic") or {}
    if _sem.get("delegated") and not ctx.get("delegated"):
        ctx["delegated"] = True
    if ctx.get("business_mode") == "opportunity_flow" and ctx.get("opportunity_id"):
        try:
            from app.services.portal_flow_adapter import persist_requirement_from_ctx
            persist_requirement_from_ctx(ctx, str(ctx.get("operator_name") or ""))
        except Exception:
            logger.exception("持久化真实需求草稿失败 opportunity=%s", ctx.get("opportunity_id"))
    if res.get("error"):
        ctx["agent_fill_error"] = res.get("error")
    return {**res, "source": res.get("source") or "agent_fill"}

def _model_selection_intent(answer: str) -> str:
    """识别用户在机型选型节点的意图。

    意图词表外置到 rules.requirement_rules 的 model_action_phrases；规则库空缺时不强判，
    只返回默认 choose。型号匹配由 baselines 的确定性字段完成，本函数不承担。
    """
    text = str(answer or "").strip().lower()
    if not text:
        return "choose"
    try:
        from app.services import requirement_rule_catalog as _rc
        phrases = _rc.model_action_phrases()
    except Exception:
        phrases = {}
    for action in ("self_config", "auto_pick", "reselect", "cancel"):
        if any(k in text for k in phrases.get(action) or []):
            return action
    return "choose"


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


async def _handle_model_reason(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    # 机型选型三态：
    # - recommend：从服务器目录推荐 1-N 台候选机型，发卡片并等待用户选择或“自己配置”
    # - ai_config：按线索登记 + 规则/文档库智能选配，锁定一台进入下游
    # - self_config：用户自己去服务器详情页配置，跳过下游 BOM 节点
    from app.services.capabilities import run_model_reason, run_select_baseline_rule
    ext = ctx.get("ext") or {}
    agent_model = str(ext.get("server_model") or "").strip()
    selection_mode = str(config.get("selection_mode") or "recommend").strip().lower()
    answer = str(ctx.get("last_user_answer") or "").strip()
    intent = _model_selection_intent(answer) if answer else ""
    clarity = str(ctx.get("clarity") or "partial").strip().lower()

    if selection_mode == "self_config" or intent == "self_config":
        ctx["flow_exit"] = "self_config"
        ctx["baselines"] = []
        ctx["model_reason"] = {"source": "self_config", "reason": "用户选择自己配置"}
        return {"count": 0, "matches": [], "source": "self_config",
                "reason": "用户选择自己配置，下游 BOM 节点已跳过"}

    if intent == "cancel":
        ctx["flow_exit"] = "cancelled"
        ctx["awaiting_input"] = False
        ctx["baselines"] = []
        ctx["model_reason"] = {"source": "cancelled", "reason": "用户取消方案配置"}
        return {"count": 0, "matches": [], "source": "cancelled", "reason": "已取消方案配置"}

    _existing = list(ctx.get("baselines") or [])
    # 多轮续跑时（用户在等候选确认、回答“1/型号/你推荐吧”），候选人已在 slot_state.baselines 里，
    # 绝不能在这里重新 select_models——委托场景下信号未回写，重新查询会清空候选导致“找不到机型”。
    _preserve = bool(_existing) and intent in ("choose", "auto_pick")
    if _preserve:
        rule_res = {"count": len(_existing), "matches": _model_reason_matches(_existing), "preserved": True}
    else:
        rule_res = run_select_baseline_rule(ctx, config)
    baselines = list(ctx.get("baselines") or [])
    try:
        from app.services.feasibility_guard import check_feasibility
        _fz = check_feasibility(ext, config)
        if _fz.get("warnings") or _fz.get("hints"):
            ctx["feasibility"] = _fz
    except Exception:
        pass

    if clarity == "unclear" and not ctx.get("delegated"):
        ctx["awaiting_input"] = True
        ctx["current_target"] = "model_reason"
        ctx["baselines"] = []
        ctx["model_reason"] = {"source": "unclear", "reason": "需求信息不足，暂不硬猜机型"}
        question = ("需求信息还不足，我先不硬猜机型。你可以补充场景/类型/系列/形态等关键信息；"
                    "或回复“我自己配置”去详情页；或回复“取消”。")
        ctx["last_ask_question"] = question
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "model_reason",
                                 "question": question, "options": ["我自己配置", "取消"],
                                 "why": "需求信息不足，无法精确推荐"})
            except Exception:
                pass
        return {**rule_res, "source": "unclear", "matches": [],
                "question": question, "reason": "等待用户补充信息或选择自己配置"}

    if intent == "auto_pick":
        ctx["delegated"] = True
    if intent == "auto_pick" and baselines:
        locked = baselines[0]
        ctx["baselines"] = [locked]
        ctx["model_selection"] = {"id": locked.get("id"), "name": locked.get("name") or ""}
        ctx["model_reason"] = {"source": "auto_pick", "baseline": locked,
                               "reason": "按用户委托锁定推荐机型 " + (locked.get("name") or "")}
        return {"count": 1, "matches": _model_reason_matches([locked]),
                "source": "auto_pick", "reason": "已按你的委托锁定推荐机型"}

    # 客户指定型号 → 不再自动锁定：在售就放到候选首位，仍让用户确认/自配/重选；
    # 不在售则推最接近候选，绝不硬猜。
    if agent_model and not ctx.get("awaiting_input") and not ctx.get("delegated"):
        idx = next((i for i, b in enumerate(baselines)
                    if (b.get("name") or "") == agent_model
                    or str(b.get("id") or "") == agent_model
                    or str(b.get("server_model_id") or "") == agent_model), None)
        if idx is not None:
            locked = baselines[idx]
            ordered = [locked] + [b for i, b in enumerate(baselines) if i != idx]
            ctx["baselines"] = ordered
            ctx["model_reason"] = {"source": "customer_specified", "baseline": locked,
                                   "reason": "客户指定机型在售，已放入候选首位等待确认"}
            return await _ask_model_choice(
                ctx, ordered, rule_res, broadcast,
                f"你指定的机型 {locked.get('name')} 在售，已放在候选首位。请回复序号/型号确认，" +
                "或回复“我自己配置”去详情页自配，或回复“重选机型”。")
        if baselines:
            return await _ask_model_choice(ctx, baselines, rule_res, broadcast,
                                           "你指定的机型暂不在在售目录，以下是最接近的候选；也可回复“我自己配置”或“重选机型”。")
        ctx["awaiting_input"] = True
        ctx["current_target"] = "model_reason"
        ctx["baselines"] = []
        ctx["model_reason"] = {"source": "customer_specified_missing",
                               "reason": "客户指定机型不在目录，且无接近候选"}
        question = "你指定的机型暂不在在售目录，我可以帮你推荐接近机型，或你回复“我自己配置”去详情页，或回复“取消”。"
        ctx["last_ask_question"] = question
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "model_reason",
                                 "question": question, "options": ["我自己配置", "取消"],
                                 "why": "客户指定机型不在目录"})
            except Exception:
                pass
        return {**rule_res, "source": "customer_specified_missing", "matches": [],
                "question": question, "reason": "等待用户选择处理方式"}

    if selection_mode == "ai_config":
        # AI 智能选配：没有明确回复时走 LLM/规则锁定一台；有回复则按回复锁定。
        if answer and intent == "choose":
            locked = _lock_model_from_answer(answer, baselines)
            if locked:
                ctx["baselines"] = [locked]
                ctx["model_selection"] = {"id": locked.get("id"), "name": locked.get("name") or ""}
                ctx["model_reason"] = {"source": "user_pick", "baseline": locked,
                                       "reason": f"已按用户选择锁定机型 {locked.get('name') or ''}"}
                return {"count": 1, "matches": _model_reason_matches([locked]),
                        "source": "user_pick", "reason": "已按用户选择锁定机型"}
        res = await run_model_reason(ctx, config, broadcast)
        if res.get("ok") and res.get("baseline"):
            cid = (res.get("baseline") or {}).get("config_id") or (res.get("baseline") or {}).get("id")
            keep = [b for b in baselines if b.get("id") == cid or b.get("server_model_id") == cid]
            if keep:
                ctx["baselines"] = keep
                ctx["model_selection"] = {"id": keep[0].get("id"), "name": keep[0].get("name") or ""}
                ctx["model_reason"] = res
                return {"count": 1, "matches": _model_reason_matches(keep),
                        "source": "llm", "reason": res.get("reason") or "",
                        "trace": res.get("trace") or []}
        # 规则兜底锁定第一台
        if baselines:
            ctx["baselines"] = baselines[:1]
            ctx["model_selection"] = {"id": baselines[0].get("id"), "name": baselines[0].get("name") or ""}
            ctx["model_reason"] = {"source": "rule_lock", "baseline": baselines[0],
                                   "reason": "AI 智能选配降级规则，已锁定首台候选"}
        return {**rule_res, "source": "ai_config", "matches": _model_reason_matches(ctx.get("baselines") or []),
                "reason": "已按线索登记完成机型智能选配"}

    # recommend 默认：给候选卡片，等待用户确认；无候选时直接交给下游。
    if answer and intent == "choose":
        locked = _lock_model_from_answer(answer, baselines)
        if locked:
            ctx["baselines"] = [locked]
            ctx["model_selection"] = {"id": locked.get("id"), "name": locked.get("name") or ""}
            ctx["model_reason"] = {"source": "user_pick", "baseline": locked,
                                   "reason": f"已按用户选择锁定机型 {locked.get('name') or ''}"}
            return {"count": 1, "matches": _model_reason_matches([locked]),
                    "source": "user_pick", "reason": "已按用户选择锁定机型"}
        if not ctx.get("force_complete"):
            # 用户本轮提供了补充信息而非有效型号：不误报“没识别到机型”，直接给出目录候选卡片。
            return await _ask_model_choice(ctx, baselines, rule_res, broadcast, "")

    if not baselines:
        # 空候选：绝不静默放行到下游（否则会自由编造/产出假 BOM），改为暂停并给兜底选项。
        return await _ask_model_choice(ctx, baselines, rule_res, broadcast, "")

    ctx["baselines"] = baselines
    ctx["model_reason"] = {"source": "recommend", "baselines": baselines,
                           "reason": "已从服务器目录生成候选机型"}
    if not ctx.get("force_complete"):
        return await _ask_model_choice(ctx, baselines, rule_res, broadcast, "")
    return {**rule_res, "source": "recommend", "matches": _model_reason_matches(baselines),
            "reason": "已从服务器目录生成候选机型"}


async def _ask_model_choice(ctx: dict, baselines: list, rule_res: dict, broadcast: BroadcastFn, fallback: str) -> dict:
    _fz = ctx.get("feasibility") or {}
    _fz_lines = [("⚠️ " + w) for w in (_fz.get("warnings") or [])] + [("提示：" + h) for h in (_fz.get("hints") or [])]
    _fz_block = ("\n".join(_fz_lines) + "\n") if _fz_lines else ""
    if not baselines:
        # 候选为空：绝不空转，给兜底“我自己配置/取消/先补充需求”。
        question = _fz_block + (fallback or "服务器目录暂未找到匹配机型。") + "\n" + (
            "你可以：\n"
            "· 回复“我自己配置”去服务器详情页自配；\n"
            "· 补充场景/类型/系列/形态等需求，我再重新筛；\n"
            "· 回复“取消”结束方案配置。")
        ctx["awaiting_input"] = True
        ctx["current_target"] = "model_reason"
        ctx["last_ask_question"] = question
        ctx["model_reason"] = {"source": "recommend", "baselines": [], "reason": "目录无匹配候选，等待用户选择"}
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "model_reason", "question": question,
                                 "options": ["我自己配置", "重新选机型", "取消"], "why": "候选为空",
                                 "candidates": []})
            except Exception:
                pass
        return {**rule_res, "source": "recommend", "matches": [], "question": question,
                "reason": "等待用户选择处理方式"}

    options = [f"{i + 1}. {b.get('name') or ''}（{b.get('series') or ''}/{b.get('form') or ''}）"
               for i, b in enumerate(baselines[:5])]
    body = ("我按需求从服务器目录筛出了以下机型，回复序号/型号确认：\n" +
            "\n".join(options) + "\n" +
            "也可以回复“我自己配置”去服务器详情页自配，或“重选机型”/“取消”。")
    question = _fz_block + ((fallback + "\n" + body) if fallback else body)
    ctx["awaiting_input"] = True
    ctx["current_target"] = "model_reason"
    ctx["last_ask_question"] = question
    ctx["model_reason"] = {"source": "recommend", "baselines": baselines,
                           "reason": "等待用户确认候选机型"}
    if broadcast:
        try:
            await broadcast({"type": "need_confirm", "step": "model_reason", "question": question,
                             "options": options + ["我自己配置", "重选机型", "取消"],
                             "why": "机型选型需要用户确认或选择自己配置",
                             "candidates": baselines})
        except Exception:
            pass
    return {**rule_res, "source": "recommend", "matches": _model_reason_matches(baselines),
            "question": question, "reason": "等待用户确认候选机型"}

def _kp_reply_intent(answer: str) -> str:
    """识别用户在配件选配节点的意图；词表外置到 kp_action_phrases。"""
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


def _kp_summary_lines(parts: list) -> list:
    out: list = []
    for p in (parts or [])[:8]:
        name = p.get("name") or p.get("model") or p.get("pn") or ""
        qty = p.get("qty")
        out.append(f"- {name}" + (f" × {qty}" if qty is not None else ""))
    return out


async def _handle_kp_reason(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    # 配件推理（AI 路）：LLM 提议 + 规则校验后先让用户确认；用户可改口、重选机型或取消。
    # 精确执行仍由规则保证（compose 需要完整字段），LLM 输出确认 + 理由。
    from app.services.capabilities import run_kp_reason, run_match_kp_rule
    answer = str(ctx.get("last_user_answer") or "").strip()
    intent = _kp_reply_intent(answer) if answer else "first"

    if intent == "cancel":
        ctx["flow_exit"] = "cancelled"
        ctx["awaiting_input"] = False
        ctx["kp_reason"] = {"source": "cancelled", "reason": "用户取消方案配置"}
        return {"source": "cancelled", "reason": "已取消方案配置"}
    if intent == "reselect_model":
        # 回到上一节点重新挑机型：本轮先暂停，pending 的 current_target 会保存为 model_reason。
        ctx["awaiting_input"] = True
        ctx["current_target"] = "model_reason"
        ctx["last_ask_question"] = "好的，我们重新选机型。请描述新的机型要求，或等待我重新给出候选。"
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
        if ctx.get("force_complete") or ctx.get("delegated"):
            return {**rule_res, "source": "confirmed", "reason": "配件方案已确认", "kp_count": len(parts)}
        lines = _kp_summary_lines(parts)
        question = ("我按需求配了这些配件：\n" + ("\n".join(lines) if lines else "（未匹配到明确配件）") +
                    "\n回复“确认”继续生成 BOM；要改就直接说要怎么改；也可以“重新选机型”或“取消”。")
        ctx["awaiting_input"] = True
        ctx["current_target"] = "kp_reason"
        ctx["last_ask_question"] = question
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "kp_reason", "question": question,
                                 "options": ["确认", "重新选机型", "取消"], "why": "生成 BOM 前请确认配件方案"})
            except Exception:
                pass
        return {**rule_res, "source": "confirm_parts", "question": question, "reason": "等待用户确认配件方案"}

    # 用户确认/直接继续：用当前已确认的配件结果交给 compose。
    rule_res = run_match_kp_rule(ctx, config)
    parts = ctx.get("kp_parts") or []
    ctx["kp_reason"] = {**rule_res, "source": "confirmed"}
    return {**rule_res, "source": "confirmed", "reason": "配件方案已确认", "kp_count": len(parts)}

async def _handle_compose(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    from app.services.capabilities import _compose_config, _get_nested
    cfg = _compose_config(config)
    baselines = ctx.get("baselines") or []
    kp_by_model = ctx.get("kp_by_model") or {}
    if not baselines:
        ctx["plans"] = []
        return {"plans_count": 0, "warning": "未找到匹配的基准配置，请手填或调整需求"}
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

def _extract_json_object(text: str) -> Optional[dict]:
    """从 final answer 里抽取 JSON 对象（允许前后有说明文字）。"""
    if not text:
        return None
    t = str(text).strip()
    try:
        v = json.loads(t)
        return v if isinstance(v, dict) else None
    except Exception:
        pass
    s = t.find("{")
    e = t.rfind("}")
    if s != -1 and e != -1 and e > s:
        try:
            v = json.loads(t[s:e + 1])
            return v if isinstance(v, dict) else None
        except Exception:
            return None
    return None


def _dig_path(obj: Any, dotted: str, default: Optional[Any] = None):
    """按点分路径从 dict 取值，缺失返回 default。"""
    if not dotted:
        return default
    cur = obj
    for part in str(dotted).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return default
        if cur is None:
            return default
    return cur


def _resolve_pre_args(args: Any, ctx: dict) -> Any:
    """解析 pre_tools 参数模板：ctx.<path> 取 ctx，req.<path> 取 requirement。"""
    if isinstance(args, str):
        if args.startswith("ctx."):
            return _dig_path(ctx, args[4:])
        if args.startswith("req."):
            return _dig_path(ctx.get("requirement") or {}, args[4:])
        return args
    if isinstance(args, dict):
        return {k: _resolve_pre_args(v, ctx) for k, v in args.items()}
    if isinstance(args, list):
        return [_resolve_pre_args(x, ctx) for x in args]
    return args


async def _run_pre_tools(config: dict, ctx: dict) -> list[str]:
    """执行节点配置的确定性前置工具，收集事实供 LLM 单次决策（AI 只编排，事实从工具来）。"""
    specs = config.get("pre_tools") or []
    if not specs:
        return []
    from app.services.agent_tools import build_tool_registry
    names = []
    for spec in specs:
        t = spec.get("tool") if isinstance(spec, dict) else spec
        if t:
            names.append(str(t))
    if not names:
        return []
    reg = build_tool_registry({"enabled_tools": names})
    out: list[str] = []
    for spec in specs:
        tool = spec.get("tool") if isinstance(spec, dict) else spec
        if not tool:
            continue
        args = spec.get("args") if isinstance(spec, dict) else {}
        args = _resolve_pre_args(args, ctx)
        try:
            res = await reg.execute(str(tool), args)
        except Exception as exc:
            logger.exception("pre_tool failed tool=%s", tool)
            res = {"error": str(exc)}
        try:
            txt = json.dumps(res, ensure_ascii=False, default=str)
        except Exception:
            txt = str(res)
        out.append(f"[工具 {tool} 结果]\n{txt[:3000]}")
    return out


def _apply_agent_effects(structured: dict, ctx: dict, config: dict) -> dict:
    """执行 Agent 结构化答案里的确定性副作用（编排胶水，非业务硬编码）。

    仅当 config.allowed_effects 声明时才触发对应动作：
      - build_bom:   用 baseline+parts 跑真实 build_plan，写 ctx.plans/bom_scheme；
      - self_config: 用户选择自配→冻结流程并退出主线（推送机型卡片由交互层处理）。
    """
    allowed = set(config.get("allowed_effects") or [])
    action = str(structured.get("action") or "").strip()
    if not action or action not in allowed:
        return {}
    effects: dict = {}
    if action == "self_config":
        ctx["flow_exit"] = "self_config"
        ctx["current_target"] = "model_choice"
        effects["self_config"] = True
    elif action == "build_bom":
        baseline = structured.get("baseline") or {}
        parts = structured.get("parts") or []
        if isinstance(baseline, dict) and isinstance(parts, list) and parts:
            try:
                from app.api.candidate_search import build_plan
                plan = build_plan(baseline, parts)
            except Exception as exc:
                logger.exception("build_bom effect failed")
                plan = {"error": str(exc)}
            if isinstance(plan, dict) and plan.get("error") is None:
                ctx["plans"] = [plan]
                ctx["bom_scheme"] = {"plans": [plan], "baseline": baseline, "parts": parts}
                effects["build_bom"] = True
            else:
                ctx["bom_error"] = plan.get("error") if isinstance(plan, dict) else "build_plan 失败"
                effects["build_bom"] = {"error": ctx.get("bom_error")}
        else:
            ctx["bom_error"] = "build_bom 缺 baseline 或 parts"
            effects["build_bom"] = {"error": ctx.get("bom_error")}
    return effects

async def _run_single_shot(text: str, config: dict, extra_context: str) -> dict:
    """final_only 节点的单发决策：走 chat_json（非流式，快），模型一次给契约 JSON。

    返回与 run_react_loop 兼容的 {ok, answer, iterations, tool_calls_log, thought_log}。
    """
    from app.services import llm_client
    from app.services.agent_react import REACT_SYSTEM_PROMPT, FINAL_ONLY_CONTRACT
    base: dict = {"ok": False, "answer": "", "iterations": 0, "tool_calls_log": [], "thought_log": []}
    if not llm_client.is_llm_enabled():
        base["answer"] = "AI 未启用"
        return base
    sys_prompt = (config.get("system_prompt") or REACT_SYSTEM_PROMPT) \
        + (config.get("final_only_contract") or FINAL_ONLY_CONTRACT) \
        + "\n\n一次输出，只输出一个 JSON 对象，不要 Markdown 代码块，不要复述需求。"
    messages = [{"role": "system", "content": sys_prompt}]
    user_content = f"需求：{text or ''}".strip()
    if extra_context:
        user_content += f"\n\n参考：{extra_context}"
    messages.append({"role": "user", "content": user_content})
    try:
        data = await llm_client.chat_json(llm_client._ensure_json_instruction(messages))
    except Exception as exc:
        logger.warning("single_shot chat_json failed: %s", exc)
        base["answer"] = ""
        return base
    if not isinstance(data, dict):
        base["answer"] = ""
        return base
    action = str(data.get("action") or "").strip()
    if action == "final" and isinstance(data.get("answer"), dict):
        base["answer"] = json.dumps(data.get("answer"), ensure_ascii=False)
        base["ok"] = True
    elif action == "final":
        base["answer"] = str(data.get("answer") or "").strip()
        base["ok"] = True
    else:
        base["answer"] = json.dumps(data, ensure_ascii=False) if data else ""
        base["ok"] = True
    base["iterations"] = 1
    return base


async def _handle_generic_agent(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Generic agent node: LLM decides, calls tools from the global catalog.

    config 可配（节点抽屉）：
      - context_map: [{key,label}] 把上游 ctx 序列化进 extra_context；
      - result_key:  把最终结构化答案写回 ctx 的键（默认沿用 agent_result）；
      - result_mapping: {ctx_key: path} 把答案里的子字段再复制到 ctx 顶层。
    结构化答案取 final answer（JSON 对象），非 JSON 则仅保留 agent_result。
    """
    from app.services.agent_react import run_react_loop
    text = ctx.get("requirement_text") or ctx.get("normalized_text") or ""
    if not str(text).strip():
        return {"ok": False, "answer": "", "reason": "empty_text"}

    extra = []
    for item in config.get("context_map") or []:
        k = str((item or {}).get("key") or "")
        label = str((item or {}).get("label") or k)
        val = ctx.get(k)
        if val is None:
            val = _dig_path(ctx, k)
        if val not in (None, "", [], {}):
            try:
                extra.append(f"[{label}]\n{json.dumps(val, ensure_ascii=False, default=str)[:2000]}")
            except Exception:
                extra.append(f"[{label}]\n{str(val)[:2000]}")
    pre = await _run_pre_tools(config, ctx)
    extra_context = "\n\n".join(pre + extra)

    if config.get("final_only"):
        result = await _run_single_shot(text, config, extra_context)
    else:
        result = await run_react_loop(
            requirement_text=str(text),
            config=config,
            extra_context=extra_context,
            max_iterations=int(config.get("max_iterations") or 6),
            system_prompt=config.get("system_prompt") or None,
            history=ctx.get("history") or [],
            final_only=False,
        )
    ctx["agent_result"] = result

    answer = str(result.get("answer") or "").strip()
    structured: Optional[dict] = None
    if answer:
        parsed = _extract_json_object(answer)
        if isinstance(parsed, dict):
            structured = parsed

    result_key = str(config.get("result_key") or "agent_result")
    effects: dict = {}
    if structured is not None:
        ctx[result_key] = structured
        for ck, path in (config.get("result_mapping") or {}).items():
            val = _dig_path(structured, str(path))
            if val is not None:
                ctx[str(ck)] = val
        effects = _apply_agent_effects(structured, ctx, config)

    return {
        "ok": result.get("ok"),
        "answer": answer,
        "iterations": result.get("iterations") or 0,
        "tool_calls_log": result.get("tool_calls_log") or [],
        "thought_log": result.get("thought_log") or [],
        "structured": structured,
        "effects": effects,
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
