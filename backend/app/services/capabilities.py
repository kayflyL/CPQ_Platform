"""能力节点 AI 增强层（2026-08 重构·阶段2）。

每个能力节点 = 一个智能，画布可编排；本模块实现 AI 增强版 handler：
  - understand   需求理解（LLM 填表 + 领域知识注入 + 内部校验）
  - gap_analyze  缺口分析（槽位覆盖度 + LLM 可选解释）
  - scene_decide 场景判定（规则判定 + LLM 可选增强）
  - model_reason 机型推理（ReAct 调 select_models，失败降级规则）
  - kp_reason    配件推理（ReAct 调 pick_kp_parts，失败降级规则）
  - llm_ask      智能反问（LLM 基于完整上下文策略提问，失败降级目录引导）
  - llm_confirm  决策确认（推荐 + 理由汇总，供用户确认/调整）

设计原则（拒绝硬编码、拒绝黑盒）：
  - AI 优先、确定性兜底：LLM 失败/关闭/超轮 → 自动降级到节点内置规则实现，白盒标注 source；
  - 每个节点输出 evidence/confidence/source/trace，前端逐步展示；
  - 型号/料号/价格/兼容性精确性永远由工具/规则保证，LLM 只做推理与编排。
"""
import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── 领域知识注入：词表(触发词→品类/系列/类型/形态) → LLM 可读文本 ────────

_KIND_LABEL = {
    "kp": "配件品类", "chassis": "机箱底盘件",
    "server_type": "服务器类型", "series": "平台系列", "form": "机箱形态",
}


def _lexicon_mapping_map(lexicons: Optional[list], match_text: Optional[str] = None,
                         kinds: Optional[list] = None) -> dict:
    """词表 → {kind: 领域知识文本}（understand 分步子任务按 kind 按需注入用）。

    例：系列映射「兆芯/开胜/zhaoxin → Polaris」；类型映射「AI训练/深度学习 → AI / 加速计算服务器」。
    这些是产品领域知识，LLM 不知道，必须查词表——用户可配（原 extract 节点抽屉）。

    match_text（按需检索）：给定时只保留「触发词命中需求原文」的条目——与本次需求无关的条目
    是噪音，全量灌既拖慢 reasoning 模型（空回/超时主因之一），也稀释关键事实。
    kinds：限定只返回这些种类的词表（子任务各取所需，避免跨种类噪音）。
    """
    if not lexicons:
        return {}
    text = (match_text or "").strip().lower()
    kinds = set(kinds or [])
    out: dict = {}
    for lex in lexicons:
        kind = lex.get("kind")
        if kind not in _KIND_LABEL:
            continue
        if kinds and kind not in kinds:
            continue
        entries = []
        for e in lex.get("entries") or []:
            key = e.get("key") or ""
            trigs = [str(t) for t in (e.get("triggers") or []) if str(t).strip()]
            if key and trigs:
                if text and not any(t.lower() in text for t in trigs):
                    continue
                entries.append(f"{key}：{'/'.join(trigs)}")
        if entries:
            out[kind] = f"【领域知识·{_KIND_LABEL[kind]}】" + "；".join(entries[:40])
    return out


def build_domain_knowledge_map(flow_configs: Optional[dict] = None, lexicons: Optional[list] = None,
                               match_text: Optional[str] = None, kinds: Optional[list] = None) -> dict:
    """构建领域知识 map（{kind: 文本}），供 understand 分步子任务按需注入。失败静默降级空 map。"""
    try:
        if lexicons is None:
            extract_cfg = (flow_configs or {}).get("extract") or {}
            lexicons = extract_cfg.get("lexicons")
        return _lexicon_mapping_map(lexicons, match_text=match_text, kinds=kinds)
    except Exception as e:
        logger.warning("构建领域知识失败: %s", e)
        return {}




def _ai_enabled(ctx: dict, config: Optional[dict]) -> bool:
    """AI 是否启用：跟随全局 AI 开关（设置→AI 设置→启用 AI）。（Phase3 清理：ai_mode 逐节点开关已删——
    AI-first，规则只作失败兜底，不再有"纯规则/强制 LLM"独立模式。）"""
    return bool(ctx.get("llm_enabled", True))


def _safe_broadcast(broadcast, step_id: Optional[str], kind: str, text: str) -> None:
    try:
        if broadcast and step_id:
            import asyncio
            if asyncio.iscoroutinefunction(broadcast) or True:
                import asyncio as _a
                try:
                    _a.get_event_loop()
                except Exception:
                    pass
        if broadcast and step_id:
            # broadcast 可能是 async 函数，这里同步调用方一般传 async；失败静默
            res = broadcast({"type": "step_progress", "step": step_id, "sub": {"kind": kind, "text": text}})
            if hasattr(res, "__await__"):
                import asyncio
                try:
                    asyncio.get_event_loop()
                except Exception:
                    pass
    except Exception:
        pass


# ── understand：需求理解 ─────────────────────────────────────────────

async def run_understand(ctx: dict, config: dict, broadcast=None, step_id: str = "understand") -> dict:
    """需求理解：LLM 填表 + 领域知识注入 + 目录白名单；抽不全 → sufficient=False 触发反问。

    复用 agent_understand（填表→resolver→extract 兜底），新增领域知识注入。
    返回 {ok, ext, source, sufficient, missing_critical, changes, error}。
    """
    from app.services.agent_understand import run_agent_understand
    text = ctx.get("normalized_text") or ctx.get("requirement_text") or ""
    flow_cfgs = ctx.get("flow_configs") or {}
    legacy = flow_cfgs.get("extract") or {}
    # 领域知识：understand 节点自身 config（v11 单路无 extract 节点）优先，旧图 fallback extract
    extract_cfg = {}
    for _k in ("lexicons", "spec_aliases", "qty_units", "qty_multipliers",
               "model_token_regex", "keyword_limit", "category_lexicon", "parse_rules"):
        if config.get(_k) is not None:
            extract_cfg[_k] = config[_k]
    for _k, _v in legacy.items():
        extract_cfg.setdefault(_k, _v)
    # agent 化·按需检索：只注入命中需求原文的词表条目（轻 prompt，防空回/提速）
    # 领域知识 map（按 kind 分桶）：分步子任务各取所需（S1 类型/系列/形态、S2~S4 KP/底盘）。
    # 按需检索：只注入命中需求原文的词表条目（轻 prompt，防空回/提速）。
    domain_map = build_domain_knowledge_map(flow_cfgs, lexicons=extract_cfg.get("lexicons"), match_text=text)
    # 工作负载→类型映射（llm_ask 节点可配）：AI 反问首问给工作负载选项，客户选了标签后，
    # 这里让理解节点把「AI / 机器学习」这类标签确定性映射到在售类型（如 AI / 加速计算服务器），
    # 不依赖 LLM 猜。来源 = llm_ask 节点 config.workload_categories（画布可配，非硬编码）。
    wl_cats = ((ctx.get("flow_configs") or {}).get("llm_ask") or {}).get("workload_categories") or []
    wl_lines = [f"- {c.get('label')}（{c.get('desc') or ''}）→ {c.get('type') or ''}"
                for c in wl_cats if c.get("label") and c.get("type")]
    if wl_lines:
        _wl = ("【工作负载 → 服务器类型映射（AI 反问选项与理解共用）】\n"
               + "\n".join(wl_lines)
               + "\n客户说的工作负载名称按此映射到 server_type_name，类型只能选在售类型。")
        domain_map["server_type"] = ((domain_map.get("server_type") or "") + "\n\n" + _wl).strip()
    res = await run_agent_understand(
        text, config, extract_config=extract_cfg,
        broadcast=broadcast, step_id=step_id,
        domain_knowledge="\n".join(domain_map.values()),
        domain_map=domain_map,
    )
    # AI 失效（LLM 关/报错/空表/resolver 失败）→ 不在此内联兜底：
    # 返回 ai_failed，编排器据此走诚实降级（目录手动选型 + 明确告知用户 AI 不可用）。
    if not res.get("ok"):
        ctx["ext"] = {}
        return {"called": False, "source": "ai_failed", "sufficient": False,
                "missing_critical": res.get("missing_critical") or [],
                "changes": [], "error": res.get("error") or "ai_failed"}
    ext = res.get("ext") or {}
    ctx["ext"] = ext
    ctx["model_token_regex"] = extract_cfg.get("model_token_regex") or config.get("model_token_regex")
    if ctx.get("budget") is None and ext.get("budget") is not None:
        ctx["budget"] = ext["budget"]
    # Phase2：理解节点自带「专家分析 / 场景 / 缺口」——默认链可不再经过 gap_analyze/scene_decide。
    # 场景：由已理解类型/系列/形态确定性给出（与 scene_decide 输出同构，模型/选型消费端兼容）。
    _issues = res.get("analysis_issues") or []
    if _issues:
        ctx["analysis_issues"] = _issues
    ctx["scene"] = {
        "scene_name": ext.get("server_type_name"),
        "series": ext.get("series"),
        "form": ext.get("form"),
        "determined": bool(ext.get("server_type_name")),
        "source": "understand",
    }
    # 缺口/明确度：理解充分→explicit，否则 partial（与 gap_analyze 判定同向，供反问门控）
    if not bool(res.get("sufficient")) and not ctx.get("delegated"):
        ctx["understand_insufficient"] = True
        for m in (res.get("missing_critical") or []):
            if m and m not in ctx.setdefault("missing_fields", []):
                ctx["missing_fields"].append(m)
        ctx["clarity"] = "partial"
    else:
        ctx["clarity"] = "explicit"
    return {
        "called": bool(res.get("ok")),
        "source": res.get("source"),
        "sufficient": bool(res.get("sufficient")),
        "missing_critical": res.get("missing_critical") or [],
        "changes": res.get("changes") or [],
        "error": res.get("error"),
        "issues": _issues,
    }


def run_gap_analyze(ctx: dict, config: Optional[dict] = None) -> dict:
    """缺口分析：已填槽位 vs 期望清单 → level + missing_fields + 原因。

    确定性：槽位覆盖度（clarity_evaluator）；LLM 可选解释（config.llm_explain，异步由上层调）。
    期望槽位来源：节点 config 显式覆盖（slots/ask_threshold）> system_config.requirement_slots
    （全局，前端 SlotListEditor 编辑）——不能把整包节点 config（含 llm_explain）传进去，
    否则 evaluate_slot_coverage 会因 config 非 None 而跳过全局读取（2026-08 重构修复）。
    """
    from app.services.clarity_evaluator import evaluate_slot_coverage, load_requirement_slots
    ext = ctx.get("ext") or {}
    try:
        if config and (config.get("slots") or config.get("ask_threshold") is not None):
            slots_cfg = {"slots": config.get("slots") or [], "ask_threshold": config.get("ask_threshold")}
        else:
            slots_cfg = load_requirement_slots()
        level, missing, explain = evaluate_slot_coverage(ext, slots_cfg)
    except Exception as e:
        logger.exception("槽位覆盖度评估异常，回退 partial: %s", e)
        level, missing, explain = "partial", ["需求描述不够具体"], {}
    # 目录引导已完成 → 视为信息足够
    if (ctx.get("catalog_stage") or "") == "done":
        level, missing = "explicit", []
        explain = {**(explain or {}), "catalog_complete": True}
    # 客户已委托推荐（"你推荐/不确定/随便"）→ 信息视为足够，不再反问（AI 路等价目录引导 delegate 特判）
    if ctx.get("delegated"):
        level, missing = "explicit", []
        explain = {**(explain or {}), "delegated": True}
    # understand 抽不全（无类型/无配置信号）→ 强制不足，合并缺失项（交给 llm_ask 智能反问）。
    # 客户已委托推荐（delegated）时不覆盖：委托 = 不再反问，直接按推荐默认出方案。
    if ctx.get("understand_insufficient") and not ctx.get("delegated"):
        level = "partial"
        for m in (ctx.get("missing_fields") or []):
            if m and m not in missing:
                missing.append(m)
        explain = {**(explain or {}), "understand_insufficient": True}
    ctx["clarity"] = level
    ctx["missing_fields"] = missing
    ctx["clarity_explain"] = explain
    # cond_gap 条件用：反问封顶标志（orchestrator 有循环上限，此处默认未封顶）
    ctx["clarity_capped"] = bool(ctx.get("clarity_capped") or ctx.get("force_complete"))
    return {"level": level, "missing_fields": missing, "explain": explain, "capped": ctx["clarity_capped"]}


# ── scene_decide：场景判定 ───────────────────────────────────────────

def run_scene_decide(ctx: dict, config: Optional[dict] = None) -> dict:
    """场景判定：需求信号 → AI/存储/通用 × 系列 × 形态（带证据白盒）。

    规则判定（scene_analyzer）为确定性本体；LLM 增强在 model_reason/kp_reason 阶段体现。
    """
    from app.services.scene_analyzer import analyze_scene
    ext = ctx.get("ext") or {}
    scene = analyze_scene(
        ext,
        ctx.get("requirement_text") or "",
        config=config,
        opportunity=ctx.get("opportunity"),
        catalog_type_name=ctx.get("catalog_type_name"),
        force_complete=bool(ctx.get("force_complete")),
    )
    ctx["scene"] = scene
    ctx["scene_determined"] = bool(scene.get("determined"))
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
    }


# ── model_reason：机型推理（ReAct + select_models）────────────────────

_MODEL_REASON_PROMPT = (
    "你是 CPQ 平台的服务器机型选型智能体（ReAct：推理→行动→观察）。\n"
    "【每轮只输出一个 json 对象（JSON 格式）】，包含 action 字段；禁止输出任何多余文字。\n"
    "目标：根据已理解的需求，为整机方案选定 1-N 个候选机型。\n"
    "【必须用 select_models 工具查真实在售机型】，禁止编造机型名/型号。\n"
    "流程：先调 select_models（传 server_type_name/form/series/usage），观察返回的候选清单，\n"
    "从中选出满足需求的最优机型（可多选，但宁缺毋滥），然后 final 收敛。\n"
    "【final.answer 必须严格用以下格式】：\n"
    "选型：<机型名>（id=<config_id>）；理由：<一句话，只能引用工具返回字段>\n"
    "若工具返回无匹配机型，final.answer 写：选型：无；理由：<原因>"
)


def _extract_grounding_from_react(tool_calls_log: list) -> list:
    """从 ReAct 工具轨迹收集 select_models 返回的候选清单（含完整字段）。"""
    candidates = []
    for c in tool_calls_log or []:
        if c.get("name") != "select_models":
            continue
        res = c.get("result")
        if isinstance(res, dict) and res.get("candidates"):
            candidates.extend(res["candidates"])
    return candidates


def _parse_model_choice(answer: str, candidates: list) -> Optional[dict]:
    """从 LLM final.answer 解析选中的机型（匹配候选 name/config_id；禁编）。"""
    if not answer:
        return None
    # 显式 id=xxx
    m = re.search(r"id=(\d+)", answer)
    if m:
        cid = int(m.group(1))
        for c in candidates:
            if c.get("config_id") == cid or c.get("server_model_id") == cid or c.get("id") == cid:
                return c
    # 名称匹配（精确/包含）
    low = answer.lower()
    best = None
    for c in candidates:
        nm = str(c.get("name") or "")
        if nm and (nm.lower() in low or low in nm.lower()):
            if best is None or len(nm) > len(str(best.get("name") or "")):
                best = c
    return best


def _named_model_not_in_catalog(text: str, config: dict, ctx: dict) -> bool:
    """需求是否点名了「不在在售目录的具体机型」（如 联想 WA5480 G3）。

    判定（纯检测，不涉及业务判断）：
      - 文本命中任一在售机型名 → False（ReAct 有意义：选它）；
      - 否则用可配的 model_token_regex 提取机型 token（WA5480/R760/5090 等），有 token 且
        无一命中在售机型 → True（用户点名了库外机型，ReAct 只会反复确认"没有"然后烧时间降级，
        不如直走规则降级 + 白盒说明）。
    任何异常降级 False（保守：不短路，保持原 ReAct 行为）。
    """
    try:
        from app.services.catalog_guide import load_catalog
        _, models_by_type = load_catalog()
        catalog_names = [str(m.get("name") or "").lower()
                         for ms in (models_by_type or {}).values() for m in (ms or [])]
        low = (text or "").lower()
        if any(n and n in low for n in catalog_names):
            return False
        import re
        # 机型代码特征（纯检测，非业务规则）：2+ 字母后跟 2+ 数字（可带 -/字母后缀）——
        # 命中「点名了具体型号」如 WA5480 / ES22V3-P / R760；排除纯数字与带单位规格（32G/5090/5600/2700）。
        # 用户可在 model_reason 抽屉用 model_missing_token_pattern 覆盖（空=用默认特征）。
        pat = config.get("model_missing_token_pattern") or r"[A-Za-z]{2,}[0-9]{2,}[A-Za-z0-9\-]*"
        try:
            parts = re.split(r"[\s,，、;；:：()（）×*]+", low)
            hit = [t for t in parts if t and re.fullmatch(pat, t, re.I)]
            return bool(hit)
        except Exception:
            return False
    except Exception as e:
        logger.warning("model_reason 短路判定失败（不短路）: %s", e)
        return False


async def run_model_reason(ctx: dict, config: dict, broadcast=None) -> dict:
    """机型推理：AI 开 → ReAct 调 select_models 选机型 + 理由；AI 关/失败 → {ok:False} 由上层降级规则。

    返回 {ok, baseline, reason, trace, source}。ok=False 时上层走 select_baseline 规则。
    """
    from app.services.agent_react import run_react_loop
    text = ctx.get("requirement_text") or ""
    ext = ctx.get("ext") or {}
    scene = ctx.get("scene") or {}
    if not _ai_enabled(ctx, config):
        return {"ok": False, "source": "rule"}
    if ctx.get("delegated"):
        # 客户已委托推荐 → 不再反问（编排层已拦截，这里兜底）
        return {"ok": False, "source": "delegated"}
    # 短路（可配 skip_react_when_model_missing，默认开）：需求点名了不在在售目录的具体机型
    # （如 联想 WA5480 G3）→ ReAct 只会反复确认"目录里没有"然后烧 30s 降级，不如直走规则
    # 降级（select_models 已有 fallback_order 多级放宽 + 白盒说明），省时且更透明。
    if bool(config.get("skip_react_when_model_missing", True)) and \
            _named_model_not_in_catalog(text, config, ctx):
        logger.info("model_reason 短路：需求点名机型不在在售目录，直走规则降级")
        ctx["model_reason_shortcut"] = True
        return {"ok": False, "source": "rule", "reason": "需求点名机型不在在售目录，按最接近在售机型给出"}
    # 构建检索意图上下文（已理解槽位 + 场景判定）
    intent = {
        "server_type_name": ctx.get("catalog_type_name") or scene.get("scene_name") or ext.get("server_type_name"),
        "series": scene.get("series") or ext.get("series"),
        "form": scene.get("form") or ext.get("form"),
        "usage": ext.get("usage"),
    }
    extra = "已理解需求意图：" + json.dumps({k: v for k, v in intent.items() if v}, ensure_ascii=False)
    agent_cfg = {
        "enabled_tools": config.get("enabled_tools") or ["select_models"],
        "system_prompt": config.get("system_prompt") or _MODEL_REASON_PROMPT,
    }
    try:
        react = await run_react_loop(text, agent_cfg, extra_context=extra,
                                     max_iterations=int(config.get("max_iterations") or 4))
        candidates = _extract_grounding_from_react(react.get("tool_calls_log") or [])
        chosen = _parse_model_choice(react.get("answer") or "", candidates)
        if react.get("ok") and chosen:
            return {
                "ok": True, "baseline": chosen, "reason": react.get("answer") or "",
                "trace": react.get("tool_calls_log") or [], "source": "llm",
            }
        logger.warning("model_reason LLM 未收敛/未选中机型，降级规则（answer=%r）", react.get("answer"))
    except Exception as e:
        logger.exception("model_reason 失败，降级规则: %s", e)
    return {"ok": False, "source": "rule"}


# ── KP「LLM 提议 + 库校验」（2026-08 改革·Phase1 核心）──────────────────
# 方案助手（纯 LLM）比规则匹配聪明（256GB→8×32G、2GB缓存8口→9361-8i、双口网卡、电源按 GPU 功耗）。
# 改革：kp_reason = LLM 提议（读需求+理解摘要+机型通道，产出需领域知识才能定的项）→
#        pick_kp_parts 库校验执行（用真实配件库精确匹配，防幻觉）。
# AI-first：固定 LLM 提议 + 库校验（proposal_mode/react/rule 旧模式已删）。
KP_PROPOSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "memory": {"type": "object", "properties": {
            "per_stick_gb": {"type": "integer"}, "qty": {"type": "integer"},
            "type": {"type": "string"}, "speed_mt": {"type": "integer"},
            "total_gb": {"type": "integer"}, "reason": {"type": "string"},
        }},
        "raid": {"type": "object", "properties": {
            "model": {"type": "string"}, "qty": {"type": "integer"}, "reason": {"type": "string"},
        }},
        "nic": {"type": "array", "items": {"type": "object", "properties": {
            "speed_g": {"type": "integer"}, "ports": {"type": "integer"},
            "qty": {"type": "integer"}, "with_optical_module": {"type": "boolean"},
            "reason": {"type": "string"},
        }}},
        "psu": {"type": "object", "properties": {
            "wattage": {"type": "integer"}, "qty": {"type": "integer"}, "reason": {"type": "string"},
        }},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
}

KP_PROPOSE_SYSTEM_PROMPT = (
    "你是 CPQ 服务器配件规划智能体。输入：客户需求原文 + 已理解摘要 + 机型内存通道能力。\n"
    "任务：把「只有总量没单条/条数」的内存、RAID 型号、网卡口数、电源瓦数这些**需要领域知识才能定**的项确认下来，输出 JSON。\n"
    "规则：\n"
    "1) 内存：给了总量没给单条/条数时，按机型通道数拆条（如 256GB、12 通道 → 8×32G 填 8 通道；"
    "优先 32G/64G 常见条，别用 16G 凑 16 条），给出 per_stick_gb/qty/total_gb；\n"
    "2) RAID：需求给了缓存/接口数等规格（如 2GB缓存+8口）但没型号 → 推断常见型号（如 LSI 9361-8i）；不确定写 null；\n"
    "3) 网卡：按需求口数与速率确认（双口/单口、是否含光模块），产出每张卡的 speed_g/ports/qty/with_optical_module；\n"
    "4) 电源：按需求 GPU/CPU 数量粗估满载功耗（如 8×300W GPU + 双路 ≈ >4000W → 4×2700W 或 3000W 冗余），"
    "给 wattage/qty + reason；需求已明确瓦数则沿用；\n"
    "5) 一切以需求与给定事实为准，没把握的字段留 null，绝不编造具体料号。\n"
    "只输出 JSON：{memory:{per_stick_gb,qty,type,speed_mt,total_gb,reason}, raid:{model,qty,reason}, "
    "nic:[{speed_g,ports,qty,with_optical_module,reason}], psu:{wattage,qty,reason}, notes:[...]}"
)


def _ext_digest_for_kp(ext: dict) -> str:
    """理解摘要（紧凑，给 KP 提议 LLM 看）。"""
    parts = []
    if ext.get("server_type_name"):
        parts.append(f"类型={ext['server_type_name']}")
    if ext.get("series"):
        parts.append(f"系列={ext['series']}")
    if ext.get("form"):
        parts.append(f"形态={ext['form']}")
    cs = ext.get("cpu_signal") or {}
    if cs.get("model"):
        parts.append(f"CPU={cs['model']}×{cs.get('qty') or 1}")
    ms = ext.get("mem_signal") or {}
    if ms.get("total_gb"):
        parts.append(f"内存总量={ms['total_gb']}GB")
    if ms.get("per_stick_gb"):
        parts.append(f"内存单条={ms['per_stick_gb']}GB×{ms.get('qty') or '?'}")
    dgs = ext.get("drive_groups") or []
    if dgs:
        parts.append("盘=" + ",".join(f"{g.get('term')}×{g.get('qty')}" for g in dgs[:4]))
    ggs = ext.get("gpu_groups") or []
    if ggs:
        parts.append("GPU=" + ",".join(f"{(g.get('tokens') or ['?'])[0]}×{g.get('qty')}({g.get('cap')}G)" for g in ggs[:4]))
    mf = ext.get("multi_spec_filters") or {}
    nics = mf.get("Network(NIC) requirement") or []
    if nics:
        parts.append(f"网卡规格{len(nics)}组")
    rs = ext.get("raid_signal") or {}
    if rs.get("model"):
        parts.append(f"RAID={rs['model']}")
    return "；".join(parts) or "（空）"


def _kp_proposal_reason(data: dict) -> str:
    """提议的白盒说明（给 step_done payload / 用户看）。"""
    notes = []
    mem = data.get("memory") or {}
    if mem.get("per_stick_gb") and mem.get("qty"):
        notes.append(f"内存 {mem['per_stick_gb']}G×{mem['qty']}")
    raid = data.get("raid") or {}
    if raid.get("model"):
        notes.append(f"RAID {raid['model']}")
    nics = data.get("nic") or []
    if nics:
        notes.append(f"网卡 {len(nics)} 张")
    psu = data.get("psu") or {}
    if psu.get("wattage"):
        notes.append(f"电源 {psu['wattage']}W×{psu.get('qty') or '?'}")
    return "配件规划：已确认 " + "、".join(notes) if notes else ""


def _apply_kp_proposal(ext: dict, data: dict, requirement_text: str) -> None:
    """把 LLM 提议合并进 ext（复用 merge_into_ext 的确定性收口：只补缺、规则赢）。
    理解已抽到的（per_stick/mem_groups/raid 型号/nic 过滤器/psu 瓦数）不覆盖；只补缺口。"""
    from app.services.llm_extract_enhance import merge_into_ext
    slots: dict = {}
    mem = data.get("memory") or {}
    if mem.get("per_stick_gb") or mem.get("total_gb"):
        slots["memory"] = {k: mem.get(k) for k in ("per_stick_gb", "qty", "type", "speed_mt", "comparison", "total_gb")
                           if mem.get(k) is not None}
    raid = data.get("raid") or {}
    if raid.get("model"):
        slots["raid"] = {"model": str(raid["model"]), "qty": int(raid.get("qty") or 1)}
    nics = data.get("nic") or []
    if nics:
        slots["nic"] = [{"speed_g": n.get("speed_g"), "ports": n.get("ports"), "qty": n.get("qty"),
                         "with_optical_module": n.get("with_optical_module")} for n in nics]
    # psu 不合并：电源瓦数由 compose 的确定性 GPU-TDP 计算（_infer_psu_wattage，数据驱动）给出，
    # 需求显式瓦数由理解抽取（S4）→ merge；LLM 提议的口算常偏低（如 8×R9700 给了 2000W），不采用。
    if slots:
        try:
            merge_into_ext(ext, slots, requirement_text=requirement_text)
        except Exception as e:
            logger.warning("kp 提议合并失败（丢弃提议，规则赢）: %s", e)


async def _kp_llm_propose(ctx: dict, config: dict) -> dict:
    """KP LLM 提议：读需求+理解摘要+机型通道 → 确认内存条数/RAID/网卡/电源（领域知识）。
    产出结构化信号合并进 ext；pick_kp_parts 随后做库校验执行。失败返回 {ok:False}，上层降级规则。"""
    from app.services import llm_client
    ext = ctx.get("ext") or {}
    baseline = ctx.get("baseline") or (ctx.get("baselines") or [None])[0]
    mem_cfg = ""
    if baseline:
        mc = baseline.get("mem_channels")
        md = baseline.get("max_dimm")
        mem_cfg = f"机型 {baseline.get('name') or '?'}：内存通道={mc or '未知'}，最大插槽={md or '未知'}"
    text = ctx.get("requirement_text") or ""
    user = (
        f"客户需求原文：\n{text}\n\n"
        f"已理解摘要：\n{_ext_digest_for_kp(ext)}\n\n"
        f"机型能力：{mem_cfg or '（未选机型）'}\n\n"
        "请确认内存/RAID/网卡/电源（没把握留空）。"
    )
    try:
        data = await llm_client.chat_json(
            [{"role": "system", "content": KP_PROPOSE_SYSTEM_PROMPT},
             {"role": "user", "content": user}],
            schema=KP_PROPOSE_SCHEMA, temperature=0.2, timeout=60, max_attempts=1,
        )
    except Exception as e:
        logger.warning("kp LLM 提议失败: %s", e)
        return {"ok": False, "error": str(e)[:200]}
    if not isinstance(data, dict) or not data:
        return {"ok": False, "error": "empty"}
    _apply_kp_proposal(ext, data, text)
    return {"ok": True, "proposal": data, "reason": _kp_proposal_reason(data)}


async def run_kp_reason(ctx: dict, config: dict, broadcast=None) -> dict:
    """配件推理（改革版·Phase1）：LLM 提议（内存条数/RAID/网卡/电源）→ pick_kp_parts 库校验执行。

    AI-first：固定走 LLM 提议（内存条数/RAID/网卡/电源）→ pick_kp_parts 库校验执行。
    返回 {ok, kp_parts, kp_count, reason, trace, source}。LLM 提议失败 → run_match_kp_rule 规则兜底。
    """
    ext = ctx.get("ext") or {}
    baseline = ctx.get("baseline") or (ctx.get("baselines") or [None])[0]
    if not _ai_enabled(ctx, config):
        return {"ok": False, "source": "rule"}
    # AI-first：LLM 提议 → 库校验执行（proposal_mode 旧开关已删）
    proposal_note = ""
    prop = await _kp_llm_propose(ctx, config)
    if prop.get("ok"):
        proposal_note = prop.get("reason") or ""
        ctx["kp_proposal"] = prop.get("proposal")
    else:
        logger.warning("kp LLM 提议失败(%s)，降级规则匹配", prop.get("error"))
    rule_res = run_match_kp_rule(ctx, config)
    ok = bool(rule_res.get("kp_count"))
    return {**rule_res, "ok": ok, "source": "llm+rule" if proposal_note else "rule",
            "reason": proposal_note, "trace": [], "kp_parts": ctx.get("kp_parts") or []}


# ── 智能反问（llm_ask）与决策确认（llm_confirm）─────────────────────────
# （2026-08 Phase1 误删后按原契约重建：选项白名单过滤禁塔式/空选项目录兜底/工作负载放行 由
#   tests/test_llm_ask_catalog.py 约束；run_llm_ask 主逻辑与原实现一致。）
_FORM_WHITELIST = ["1U", "2U", "4U", "5U", "6U", "8U"]

_LLM_ASK_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "why": {"type": "string"},
    },
    "required": ["question", "options"],
}

_LLM_ASK_PROMPT = (
    "你是 CPQ 平台的服务器配置顾问，负责在信息不足时向客户提出最关键的一个问题。\n"
    "要求：\n"
    "1) 一次只问一个最关键的问题，简短、口语化；\n"
    "2) options 只能从给定白名单/工作负载选项里选，禁止编造（如目录没有塔式，就不能给塔式）；\n"
    "3) 每个问题给 why（一句话说明为什么问这个）；\n"
    "4) 只输出 JSON：{question, options, why}。"
)


def _catalog_whitelist() -> dict:
    """从目录派生反问白名单：类型/系列/形态/机型。形态从机型 base_config.form 去重 + 顶层 form 兜底；
    目录空 → 回退 _FORM_WHITELIST（不崩）。"""
    out: dict = {"types": [], "series": [], "forms": [], "models": []}
    try:
        from app.services.catalog_guide import load_catalog
        types, models_by_type = load_catalog()
        out["types"] = [str(t.get("name") or "") for t in (types or []) if t.get("name")]
        for tn, ms in (models_by_type or {}).items():
            for m in (ms or []):
                nm = m.get("name")
                if nm and str(nm) not in out["models"]:
                    out["models"].append(str(nm))
                f = (m.get("base_config") or {}).get("form") or m.get("form")
                if f and str(f) not in out["forms"]:
                    out["forms"].append(str(f))
    except Exception as e:
        logger.warning("读反问白名单失败（回退形态常量）: %s", e)
    if not out["forms"]:
        out["forms"] = list(_FORM_WHITELIST)
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            series = repo.get_value("server_series", [])
            if isinstance(series, list):
                out["series"] = [str(x.get("value")) for x in series if isinstance(x, dict) and x.get("value")]
        finally:
            repo.close()
    except Exception:
        pass
    if not out["series"]:
        out["series"] = ["Orion", "Polaris", "Intel", "工作站"]
    return out


def _filter_catalog_options(opts: list, whitelist: dict) -> list:
    """LLM 反问选项白名单过滤：禁塔式/卧式/刀片/桌面；保留机架式(别名)、白名单项、委托选项。"""
    out = []
    wl: list = []
    for lst in (whitelist.get("types") or [], whitelist.get("series") or [],
                whitelist.get("forms") or [], whitelist.get("models") or [],
                whitelist.get("workload") or []):
        wl.extend(str(x) for x in lst if x)
    for o in opts or []:
        s = str(o or "").strip()
        if not s:
            continue
        if any(k in s for k in ("塔式", "卧式", "刀片", "桌面")):
            continue
        if any(k in s for k in ("不确定", "你推荐", "随便", "委托")):
            out.append(s)
            continue
        if "机架式" in s or any(x and (x in s or s in x) for x in wl):
            out.append(s)
    return out


def _catalog_fallback_options(missing: list, whitelist: dict) -> list:
    """缺失项关键词 → 对应目录维度合法选项：形态→形态、系列→系列、其余→类型。"""
    missing = missing or []
    if any("形态" in str(m) or "form" in str(m).lower() for m in missing):
        return list(whitelist.get("forms") or [])
    if any("系列" in str(m) for m in missing):
        return list(whitelist.get("series") or [])
    return list(whitelist.get("types") or [])


async def run_llm_ask(ctx: dict, config: dict, broadcast=None) -> dict:
    """智能反问：LLM 基于完整上下文生成策略性问题；AI 关/失败 → 由上层走目录引导兜底。

    返回 {ok, question, options, why}。ok=False 时上层走 _ask_catalog_question。
    """
    from app.services import llm_client
    from app.services.agent_understand import _understood_summary
    if not _ai_enabled(ctx, config):
        return {"ok": False, "source": "rule"}
    text = ctx.get("requirement_text") or ""
    ext = ctx.get("ext") or {}
    missing = ctx.get("missing_fields") or []
    strategy = (config or {}).get("strategy") or "one"  # one=问最关键1个 / all=列全
    whitelist = _catalog_whitelist()
    workload_cats = (config or {}).get("workload_categories") or []
    need_workload = any(("场景" in str(m)) or ("用途" in str(m)) or ("workload" in str(m).lower()) for m in missing) \
        or not ext.get("server_type_name")
    scale_tiers = (config or {}).get("scale_tiers") or {}
    scale_note = ""
    for m in missing:
        key = None
        if "CPU" in m or "处理" in m:
            key = "CPU"
        elif "内存" in m:
            key = "内存"
        elif "存储" in m or "硬盘" in m or "盘" in m:
            key = "存储"
        tiers = scale_tiers.get(key) if key else None
        if tiers:
            scale_note += f"\n【{key}按规模分档（选项/推荐参考，禁止编造）】\n" + "\n".join(
                f"- {t.get('label')}（{t.get('desc') or ''}）：推荐 {t.get('recommend') or ''}"
                for t in tiers if t.get("label"))
    for _key in ("CPU", "内存", "存储"):
        for _t in (scale_tiers.get(_key) or []):
            if _t.get("label"):
                whitelist.setdefault("workload", []).append(str(_t["label"]))

    if need_workload and workload_cats:
        wl_labels = [str(c.get("label") or "").strip() for c in workload_cats if c.get("label")]
        wl_desc = "\n".join(
            f"- {c.get('label')}（{c.get('desc') or ''}）→ {c.get('type') or ''}"
            for c in workload_cats if c.get("label"))
        user = (
            f"客户需求原文：\n{text}\n\n"
            f"已理解：{_understood_summary(ext)}\n"
            f"还缺的关键信息：{'、'.join(missing) if missing else '（无明确缺失，但可确认关键选型点）'}\n"
            f"【当前需要确定客户的工作负载/用途】可选工作负载（选项只能从这里选，禁止编造）：\n{wl_desc}\n\n"
            + (scale_note + "\n\n" if scale_note else "")
            + "请输出一个问工作负载的问题，options 用上面的工作负载名称。"
        )
    else:
        user = (
            f"客户需求原文：\n{text}\n\n"
            f"已理解：{_understood_summary(ext)}\n"
            f"还缺的关键信息：{'、'.join(missing) if missing else '（无明确缺失，但可确认关键选型点）'}\n"
            f"追问策略：{'一次问最关键的一个问题' if strategy != 'all' else '一次列全缺失项（每项带选项）'}\n"
            f"在售目录（选项只能从这里选，禁止编造）：\n"
            f"  类型：{'、'.join(whitelist.get('types') or []) or '（无）'}\n"
            f"  系列：{'、'.join(whitelist.get('series') or []) or '（无）'}\n"
            f"  形态（全部机架式，无塔式）：{'、'.join(whitelist.get('forms') or [])}\n"
            f"  机型：{'、'.join((whitelist.get('models') or [])[:10]) or '（无）'}\n\n"
            + (scale_note + "\n\n" if scale_note else "")
            + "请输出策略性问题。"
        )
    try:
        messages = [{"role": "system", "content": (config or {}).get("system_prompt") or _LLM_ASK_PROMPT},
                    {"role": "user", "content": user}]
        data = await llm_client.chat_json(messages, schema=_LLM_ASK_SCHEMA, temperature=0.4)
        q = (data or {}).get("question") or ""
        if not q:
            return {"ok": False, "source": "empty"}
        opts = (data or {}).get("options") or []
        if need_workload and workload_cats:
            wl_labels = [str(c.get("label") or "").strip() for c in workload_cats if c.get("label")]
            ok_opts = _filter_catalog_options(opts, {**whitelist, "workload": wl_labels})
        else:
            ok_opts = _filter_catalog_options(opts, whitelist)
        if not ok_opts:
            ok_opts = _catalog_fallback_options(missing, whitelist)
        show_why = (config or {}).get("show_why", True)
        return {"ok": True, "question": q, "options": ok_opts,
                "why": ((data or {}).get("why") or "") if show_why else "", "source": "llm"}
    except Exception as e:
        logger.warning("llm_ask LLM 失败，走目录引导兜底: %s", e)
        return {"ok": False, "source": "error"}


def run_llm_confirm(ctx: dict, config: Optional[dict] = None) -> dict:
    """决策确认：汇总机型/配件推荐 + 理由，供前端确认面板展示（可调整后重跑）。

    确定性汇总（不额外调 LLM）：reason 来自 model_reason/kp_reason 的 trace。
    """
    items = []
    mr = ctx.get("model_reason") or {}
    if mr.get("baseline"):
        b = mr["baseline"]
        items.append({
            "id": "baseline",
            "type": "机型",
            "value": b.get("name") or "",
            "series": b.get("series") or "",
            "form": b.get("form") or "",
            "reason": mr.get("reason") or "",
        })
    kps = ctx.get("kp_parts") or []
    for kp in kps[:30]:
        items.append({
            "id": f"kp-{kp.get('pn') or kp.get('name') or kp.get('category')}",
            "type": kp.get("category") or "配件",
            "value": kp.get("name") or "",
            "qty": kp.get("qty") or 1,
            "unit_price": kp.get("unit_price"),
            "currency": kp.get("currency") or "RMB",
            "matched_spec": kp.get("matched_spec") or "",
        })
    return {"ok": True, "items": items, "count": len(items)}


def run_select_baseline_rule(ctx: dict, config: Optional[dict] = None) -> dict:
    """机型选型规则本体：四级兜底（exact/same_series/same_form/all，fallback_order 可配）+ model_recommend 标注。"""
    from app.api.candidate_search import select_models, build_variant_signals
    cfg = config or {}
    if ctx.get("awaiting_input"):
        ctx["baselines"] = []
        return {"count": 0, "matches": [], "skipped": "awaiting_input"}
    ext = ctx.get("ext") or {}
    scene = ctx.get("scene") or {}
    _type_name = (ctx.get("catalog_type_name")
                  or (scene.get("scene_name") if scene.get("determined") else None)
                  or ext.get("server_type_name"))
    _series = scene.get("series") or ext.get("series") or None
    _form = scene.get("form") or ext.get("form") or None
    from app.api.candidate_search import MAX_PLANS
    baselines = select_models(
        ext.get("usage"), _type_name, _series, _form,
        limit=cfg.get("max_plans") or MAX_PLANS,
        recommend_strategy_id=cfg.get("recommend_strategy_id"),
        no_signal_strategy=cfg.get("no_signal_strategy"),
        variant_signals=build_variant_signals(ext, ctx.get("requirement_text")),
        # 多级放宽（用户可配 fallback_order，见 model_reason 节点抽屉）：
        # 库内无 {系列} 平台 {类型} 机型时按配置顺序逐级放宽，白盒标注放宽维度
        fallback_order=cfg.get("fallback_order") or ["exact", "same_series", "same_form", "all"],
    )
    _cat_model_id = ctx.get("catalog_model_id")
    if _cat_model_id:
        _keep = [b for b in baselines
                 if b.get("server_model_id") == _cat_model_id or b.get("id") == _cat_model_id]
        if _keep:
            baselines = _keep
    ctx["baselines"] = baselines
    return {
        "count": len(baselines),
        "match_stage": (baselines[0].get("match_stage") if baselines else None),
        "fallback_note": (baselines[0].get("fallback_note") if baselines else ""),
        "matches": [{
            "config_id": b.get("id"), "name": b.get("name") or "",
            "series": b.get("series") or "", "form": b.get("form") or "",
            "match_stage": b.get("match_stage"), "fallback_note": b.get("fallback_note") or "",
        } for b in baselines],
    }


def _resolve_budget_strategy(budget) -> str:
    """按 budget 规则返回 representative_pick（min_price/max_price）。给 match_kp 用。
    （本地副本，避免与 reasoning_executor 循环导入；语义同源。）"""
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


def _dedup_kp_by_pn(kp_list: list) -> list:
    """同 pn 去重：别名分类（Raid Card/Raid card）会导致同件重复命中 → 保留 qty 最大的一条。"""
    out: list = []
    seen: dict = {}
    for kp in kp_list or []:
        pn = kp.get("pn") or kp.get("name") or ""
        if not pn:
            out.append(kp)
            continue
        prev = seen.get(pn)
        if prev is None:
            seen[pn] = kp
            out.append(kp)
        elif int(kp.get("qty") or 1) > int(prev.get("qty") or 1):
            prev["qty"] = kp.get("qty")
    return out


def run_match_kp_rule(ctx: dict, config: Optional[dict] = None) -> dict:
    """配件匹配规则本体：型号/规格/品类代表件三级匹配（per-机型各配 KP）。"""
    from app.api.candidate_search import pick_kp_parts, kp_categories_for_type, _base_config_std_mem_speed
    cfg = config or {}
    ext = ctx.get("ext") or {}
    baselines = ctx.get("baselines") or []
    cfg_pick = cfg.get("representative_pick")
    pick = cfg_pick if (cfg_pick and cfg_pick != "auto") else _resolve_budget_strategy(ctx.get("budget"))
    kp_by_model: dict = {}
    all_kp: list = []
    for bl in baselines:
        type_cats = kp_categories_for_type(bl.get("server_type_name") or "", cfg.get("type_packages"), ext.get("categories"))
        eff_cats = list(dict.fromkeys(type_cats + (ext.get("categories") or [])))
        bl_kp = pick_kp_parts(
            eff_cats, ext.get("keywords", []),
            category_aliases=cfg.get("category_aliases"),
            representative_pick=pick,
            spec_rules=cfg.get("spec_rules"),
            fallback_strategy=cfg.get("fallback_strategy") or "fallback_representative",
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
            drive_spec_substitute=cfg.get("drive_spec_substitute", True),
            default_mem_speed=_base_config_std_mem_speed(bl.get("id")),
            default_mem_channels=bl.get("mem_channels"),
            default_max_dimm=bl.get("max_dimm"),
            cpu_mem_type_rules=cfg.get("cpu_mem_type_rules"),
            capacity_match=cfg.get("capacity_match") or {"strategy": "tolerance", "tolerance": 10},
        )
        mid = bl.get("server_model_id") or bl.get("id")
        # 去重（per-机型）：同 pn 因别名分类（Raid Card/Raid card）重复命中 → 保留 qty 最大一条（9361-8i×2 → ×1）
        kp_by_model[mid] = _dedup_kp_by_pn(bl_kp)
        all_kp.extend(kp_by_model[mid])
    ctx["kp_by_model"] = kp_by_model
    ctx["kp_parts"] = all_kp
    by_category: dict[str, int] = {}
    for kp in all_kp:
        c = kp.get("category") or "其他"
        by_category[c] = by_category.get(c, 0) + 1
    unmatched_count = sum(1 for kp in all_kp if kp.get("unmatched"))
    return {"kp_count": len(all_kp), "by_category": by_category, "unmatched_count": unmatched_count}


# ── spec_compliance：规格合规校验（v12 新增，确定性红线前）──────────────────

_CPU_MODEL_RE = re.compile(
    r"(?:EPYC|Xeon|霄龙|至强|开胜|开先|zhaoxin|兆芯|海光|KH[- ]?\d+|KX[- ]?\d+)\s*[- ]?[0-9][0-9A-Za-z]*",
    re.IGNORECASE,
)


def _req_cpu_tokens(text: str) -> list:
    """从需求原文提取 CPU 型号 token（归一去空格/连字符，如 "EPYC 9654" → EPYC9654）。"""
    out = []
    for m in _CPU_MODEL_RE.finditer(text or ""):
        tok = re.sub(r"[\s\-]+", "", m.group(0)).upper()
        if tok and tok not in out:
            out.append(tok)
    return out


def _merge_retry(ctx: dict, caps: list) -> list:
    """合并 retry_caps（去重保序），供 orchestrator 重跑链。"""
    cur = list(ctx.get("retry_caps") or [])
    for c in caps:
        if c not in cur:
            cur.append(c)
    return cur


def _expected_mem_type_from_cpu_parts(kp_parts: list, rules: Optional[list]) -> Optional[str]:
    """按实配 CPU 件型号推内存代际（复用 candidate_search._default_mem_type_for_cpu）。"""
    try:
        from app.api.candidate_search import _default_mem_type_for_cpu
        return _default_mem_type_for_cpu(kp_parts, rules)
    except Exception:
        return None


def run_spec_compliance(ctx: dict, config: Optional[dict] = None) -> dict:
    """规格合规校验（确定性）：kp_reason 之后、compose 之前。

    检查需求规格 vs 实配：
      - AI 类型缺 GPU → auto_fix 追加 GPU 品类并请求重跑（gpu_required_for_ai，默认开）；
      - 存储类型缺盘 → auto_fix 追加 HDD/SSD（兜底，正常 mandatory_storage 已在品类层处理）；
      - 需求明确 CPU 型号但实配不同 → 标 issue（strict_model_match，默认开，不自动造件）；
      - CPU 代际 → 内存代际不符 → auto_fix 重设 mem_signal.type 并请求重跑（cpu_mem_generation）。
    返回 {issues, fixed, server_type, mode}；auto_fix 改 ctx 并置 retry_caps（orchestrator 重跑链）。
    """
    cfg = config or {}
    if not cfg.get("enabled", True):
        return {"issues": [], "fixed": 0, "skipped": "disabled"}
    ext = ctx.get("ext") or {}
    scene = ctx.get("scene") or {}
    server_type = (ext.get("server_type_name") or scene.get("scene_name")
                   or ctx.get("catalog_type_name") or "")
    kp_parts = ctx.get("kp_parts") or []
    mode = cfg.get("mode") or "auto_fix"
    fix_budget = int(ctx.get("spec_fix_count") or 0) < int(cfg.get("max_fix_rounds") or 2)
    issues: list = []
    fixed = 0

    def _request_retry():
        ctx["retry_caps"] = _merge_retry(
            ctx, ["kp_reason", "spec_compliance", "compose", "budget_check", "llm_audit", "audit_fix"])
        ctx["spec_fix_count"] = int(ctx.get("spec_fix_count") or 0) + 1

    # 1) AI 类型缺 GPU（配件库有 GPU，2026-08 修：AI 默认带卡）
    if cfg.get("gpu_required_for_ai", True) and "AI" in server_type:
        has_gpu = any("GPU" in (k.get("category") or "") for k in kp_parts)
        if not has_gpu:
            issues.append("AI/加速计算服务器未配置 GPU 加速卡")
            if mode == "auto_fix" and fix_budget:
                cats = list(ext.get("categories") or [])
                if "GPU" not in cats:
                    ext["categories"] = cats + ["GPU"]
                    ctx["ext"] = ext
                _request_retry()
                fixed += 1
    # 2) 存储类型缺盘（兜底；正常 mandatory_storage 已在品类层保证）
    if "存储" in server_type:
        has_drive = any("HDD/SSD" in (k.get("category") or "") for k in kp_parts)
        if not has_drive:
            issues.append("存储服务器未配置任何硬盘/SSD")
            if mode == "auto_fix" and fix_budget:
                cats = list(ext.get("categories") or [])
                if "HDD/SSD" not in cats:
                    ext["categories"] = cats + ["HDD/SSD"]
                    ctx["ext"] = ext
                _request_retry()
                fixed += 1
    # 3) CPU 型号严格匹配（需求明确型号 → 实配必须命中；不自动造件，标 issue 交审计/人工）
    if cfg.get("strict_model_match", True):
        req_cpus = _req_cpu_tokens(ctx.get("requirement_text") or "")
        if req_cpus:
            picked = [str(k.get("name") or k.get("description") or "") for k in kp_parts
                      if "CPU" in (k.get("category") or "")]
            picked_text = re.sub(r"[\s\-]+", "", " ".join(picked)).upper()
            miss = [t for t in req_cpus if t not in picked_text]
            if miss:
                issues.append(f"需求指定 CPU 型号 {'、'.join(miss)} 未命中（实配 {'/'.join(picked) or '无'}）")
    # 4) CPU 代际 → 内存代际（auto_fix 重设 mem_signal.type 重跑）
    mem_rules = cfg.get("cpu_mem_generation") or []
    if mem_rules:
        expected = _expected_mem_type_from_cpu_parts(kp_parts, mem_rules)
        if expected:
            mem_text = " ".join(str(k.get("description") or k.get("name") or "") for k in kp_parts
                                if "内存" in (k.get("category") or "") or "Memory" in (k.get("category") or ""))
            if mem_text and expected not in mem_text.upper():
                issues.append(f"内存代际不匹配：CPU 需 {expected}，实配 {mem_text[:40]}")
                if mode == "auto_fix" and fix_budget:
                    ms = dict(ext.get("mem_signal") or {})
                    ms["type"] = expected
                    ext["mem_signal"] = ms
                    ctx["ext"] = ext
                    _request_retry()
                    fixed += 1
    ctx["spec_issues"] = issues
    return {"issues": issues, "fixed": fixed, "server_type": server_type, "mode": mode}


# ── audit_fix：审计自纠（v12 新增，执行中自我修正闭环）────────────────────

def _collect_audit_issues(ctx: dict) -> list:
    """汇总可自纠的问题：llm_audits（LLM 意图级）+ spec_issues（规则级，最新一次）。"""
    issues: list = []
    for la in (ctx.get("llm_audits") or []):
        for i in (la.get("issues") or []):
            if str(i).strip():
                issues.append(str(i))
    for i in (ctx.get("spec_issues") or []):
        if str(i).strip():
            issues.append(str(i))
    return list(dict.fromkeys(issues))


def _memory_upgrade_target(ctx: dict, cfg: dict) -> Optional[int]:
    """内存不足时抬到「标准档」可解析总量（llm_ask.scale_tiers.内存 配置驱动）。
    优先取 label 含「标准」的档（如 "32G*8条" → 256）；无标准档取最大值；解析失败 None（不硬编码）。"""
    try:
        tiers = ((ctx.get("flow_configs") or {}).get("llm_ask") or {}).get("scale_tiers") or {}
        mem_tiers = tiers.get("内存") or []
        targets = []
        std_target = None
        for t in mem_tiers:
            rec = str(t.get("recommend") or "")
            m = re.search(r"(\d+)\s*[Gg]\s*[*×]\s*(\d+)", rec)
            if m:
                total = int(m.group(1)) * int(m.group(2))
                targets.append(total)
                if "标准" in str(t.get("label") or ""):
                    std_target = total
        if not targets:
            return None
        return std_target if std_target is not None else max(targets)
    except Exception:
        return None


def run_audit_fix(ctx: dict, config: Optional[dict] = None) -> dict:
    """审计自纠（确定性）：llm_audit 检出问题 → 用确定性动作（补 GPU / 抬内存）改需求信号，
    并请求 orchestrator 重跑 retry_scope 链（默认到 llm_audit 再审计一次）；仍不过 → review 标人工复核。

    这是把 llm_audit 从「纯事后审计」升级为「执行中自我修正」的闭环，上限 max_retry（默认 1）。
    """
    cfg = config or {}
    if not cfg.get("enabled", True):
        return {"retry": False, "issues": [], "skipped": "disabled"}
    issues = _collect_audit_issues(ctx)
    if not issues:
        return {"retry": False, "issues": [], "reason": "no_issues"}
    retried = int(ctx.get("audit_retry_count") or 0)
    max_retry = int(cfg.get("max_retry") or 1)
    if retried >= max_retry:
        return {"retry": False, "issues": issues, "reason": "retry_capped", "retried": retried}
    ext = ctx.get("ext") or {}
    action = False
    # 补 GPU（"未配置 GPU / 缺少 GPU"）
    if any(("GPU" in str(i)) and ("未配置" in str(i) or "缺少" in str(i) or "无 GPU" in str(i)) for i in issues):
        cats = list(ext.get("categories") or [])
        if "GPU" not in cats:
            ext["categories"] = cats + ["GPU"]
            ctx["ext"] = ext
            action = True
    # 抬内存目标（"内存不足/严重/无法支撑"）
    if any(("内存" in str(i)) and ("不足" in str(i) or "严重" in str(i) or "无法支撑" in str(i) or "远低于" in str(i)) for i in issues):
        target = _memory_upgrade_target(ctx, cfg)
        if target:
            ms = dict(ext.get("mem_signal") or {})
            cur = int(ms.get("total_gb") or 0)
            if cur < target:
                ms["total_gb"] = target
                ext["mem_signal"] = ms
                ctx["ext"] = ext
                action = True
    if not action:
        return {"retry": False, "issues": issues, "reason": "no_action", "retried": retried}
    ctx["audit_retry_count"] = retried + 1
    scope = cfg.get("retry_scope") or ["kp_reason", "spec_compliance", "compose", "budget_check", "llm_audit", "audit_fix"]
    ctx["retry_caps"] = _merge_retry(ctx, scope)
    return {"retry": True, "issues": issues, "retried": retried + 1}


# ── result_check：方案自检（确定性，2026-08 新增）─────────────────────────
# 与 spec_compliance（规格合规：配置是否符合目录/兼容规则）分工：
# 本节点查「结果完整性」——方案有没有缺漏/自洽，纯确定性，画布可见可配。

def run_result_check(ctx: dict, config: Optional[dict] = None) -> dict:
    """方案自检：结果非空 + 必填核心件 + 数量合理性。

    确定性规则（不调 LLM）；检查项由节点 config.checks 勾选（前端抽屉可配）。
    返回 {checks:[{name,passed,detail}], failed, on_fail}。
    """
    cfg = config or {}
    checks_cfg = cfg.get("checks") or {}
    plans = ctx.get("plans") or []
    baselines = ctx.get("baselines") or []
    kp_parts = ctx.get("kp_parts") or []
    results: list[dict] = []

    def _cat(p) -> str:
        return str(p.get("category") or p.get("part_category") or p.get("catalogue") or "").lower()

    # 1) 方案非空：有方案、有机型、有配件
    if checks_cfg.get("plan_not_empty", True):
        ok = bool(plans) and bool(baselines) and bool(kp_parts)
        detail = f"方案 {len(plans)} 张 / 机型 {len(baselines)} / 配件 {len(kp_parts)} 件"
        results.append({"name": "方案非空", "passed": ok, "detail": detail})

    # 2) 必填核心件：CPU / 内存 / 盘 至少各一（存储类/AI 类同理要有核心件）
    if checks_cfg.get("required_fields", True):
        cats = {_cat(p) for p in kp_parts}
        has_cpu = any("cpu" in c for c in cats)
        has_mem = any("mem" in c for c in cats)
        has_disk = any(("hdd" in c) or ("ssd" in c) or ("disk" in c) or ("盘" in c) or ("storage" in c) for c in cats)
        ok = has_cpu and has_mem and has_disk
        results.append({"name": "核心件齐全（CPU/内存/盘）", "passed": ok,
                        "detail": f"CPU={has_cpu} 内存={has_mem} 盘={has_disk}"})

    # 3) 数量合理性：内存有量、配了 GPU 则有 GPU 供电线/数量匹配
    if checks_cfg.get("qty_reasonable", True):
        issues: list[str] = []
        mem_count = sum(int(p.get("qty") or 0) for p in kp_parts if "mem" in _cat(p))
        gpu_qty = sum(int(p.get("qty") or 0) for p in kp_parts
                      if (("gpu" in _cat(p) or "显卡" in _cat(p)) and "power" not in _cat(p) and "cord" not in _cat(p)))
        gpu_cord = sum(int(p.get("qty") or 0) for p in kp_parts if "gpu power" in _cat(p) or "gpu_cord" in _cat(p) or "显卡电源线" in _cat(p))
        if mem_count <= 0:
            issues.append("无内存条")
        if gpu_qty > 0 and gpu_cord <= 0:
            issues.append(f"配了 {gpu_qty} 张 GPU 但无 GPU 供电线")
        ok = not issues
        results.append({"name": "数量合理性", "passed": ok,
                        "detail": ("；".join(issues) if issues else f"GPU={gpu_qty} 内存条={mem_count}")})

    failed = any(not r["passed"] for r in results)
    on_fail = cfg.get("on_fail") or "mark"
    ctx["result_check"] = {"checks": results, "failed": failed, "on_fail": on_fail}
    return {"checks": results, "failed": failed, "on_fail": on_fail}
