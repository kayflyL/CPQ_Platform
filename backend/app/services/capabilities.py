"""能力节点 AI 增强层（2026-08 重构·阶段2）。

每个能力节点 = 一个智能，画布可编排；本模块实现 AI 增强版 handler：
  - agent_fill   智能对话填表 Agent（会对话、会查目录/KP、边答边填线索登记表）
  - model_reason 机型推理（ReAct 调 select_models，失败降级规则）
  - kp_reason    配件推理（ReAct 调 pick_kp_parts，失败降级规则）
  - compose      方案组装（build_plan 生成 BOM）

设计原则（拒绝硬编码、拒绝黑盒）：
  - 反问候选由数据来源 + 规则目录确定性过滤，LLM 只负责措辞；LLM 失败直接返回错误，不再离线兜底；
  - 每个节点输出 evidence/confidence/source/trace，前端逐步展示；
  - 型号/料号/价格/兼容性精确性永远由工具/规则保证，LLM 只做推理与编排。
"""
import json
import logging
import re
from typing import Any, Optional

from app.services import capability_spec
from app.services import prompt_store

logger = logging.getLogger(__name__)



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




# ── model_reason：机型推理（ReAct + select_models）────────────────────


DEFAULT_MODEL_REASON_CONFIG = {
    "grounding_tool": "select_models",
    "grounding_result_key": "candidates",
    "choice_id_pattern": r"id=(\d+)",
    "choice_fields": ["config_id", "server_model_id", "id"],
    "skip_react_when_model_missing": True,
    "model_missing_token_pattern": r"[A-Za-z]{2,}[0-9]{2,}[A-Za-z0-9\-]*",
}

DEFAULT_COMPOSE_CONFIG = {
    "kp_source": "per_baseline",
    "psu_override_enabled": True,
    "psu_wattage_source": "ext.psu_signal.wattage",
    "psu_qty_source": "ext.psu_signal.qty",
}

def _compose_config(config: Optional[dict]) -> dict:
    """归一化 compose 节点配置；配件来源与电源覆盖策略不再写死。"""
    cfg = dict(config or {})
    for key, value in DEFAULT_COMPOSE_CONFIG.items():
        cfg.setdefault(key, value)
    return cfg
def _get_nested(data: dict, path: str, default=None):
    """按点分路径读取嵌套字典值；路径非法返回 default。"""
    cur = data
    for part in str(path or "").split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _model_reason_config(config: Optional[dict]) -> dict:
    """归一化 model_reason 节点配置；默认值集中在这里，不在执行逻辑中散落业务常量。"""
    cfg = dict(config or {})
    for key, value in DEFAULT_MODEL_REASON_CONFIG.items():
        if isinstance(value, list):
            cfg.setdefault(key, list(value))
        else:
            cfg.setdefault(key, value)
    d = prompt_store.get_prompt_defaults("model_reason")
    cur = cfg.get("system_prompt")
    if cur is None or (isinstance(cur, str) and not cur.strip()):
        cfg["system_prompt"] = d.get("system_prompt", "")
    return cfg


def _extract_grounding_from_react(tool_calls_log: list, config: Optional[dict] = None) -> list:
    """从 ReAct 工具轨迹收集候选清单；工具名与结果字段由节点配置指定。"""
    cfg = _model_reason_config(config)
    candidates = []
    for c in tool_calls_log or []:
        if c.get("name") != cfg.get("grounding_tool"):
            continue
        res = c.get("result")
        if not isinstance(res, dict):
            continue
        result_key = str(cfg.get("grounding_result_key") or "candidates")
        values = res.get(result_key)
        if isinstance(values, list):
            candidates.extend(values)
    return candidates


def _parse_model_choice(answer: str, candidates: list, config: Optional[dict] = None) -> Optional[dict]:
    """从 LLM final.answer 解析选中的机型；id 正则与候选字段由节点配置指定。"""
    cfg = _model_reason_config(config)
    if not answer:
        return None
    # 显式 id=xxx（正则与候选字段可配）
    try:
        pattern = str(cfg.get("choice_id_pattern") or DEFAULT_MODEL_REASON_CONFIG["choice_id_pattern"])
        m = re.search(pattern, answer, re.I)
        if m:
            raw = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
            cid = int(raw) if str(raw).isdigit() else raw
            fields = [str(f) for f in (cfg.get("choice_fields") or []) if f]
            for c in candidates:
                if any(c.get(field) == cid for field in fields):
                    return c
    except re.error:
        pass
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
        cfg = _model_reason_config(config)
        # 用户可在 model_reason 抽屉用 model_missing_token_pattern 覆盖（空=用默认特征）。
        pat = cfg.get("model_missing_token_pattern") or DEFAULT_MODEL_REASON_CONFIG["model_missing_token_pattern"]
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
    cfg = _model_reason_config(config)
    text = ctx.get("requirement_text") or ""
    ext = ctx.get("ext") or {}
    scene = ctx.get("scene") or {}
    if not _ai_enabled(ctx, cfg):
        return {"ok": False, "source": "rule"}
    if ctx.get("delegated"):
        # 客户已委托推荐 → 不再反问（编排层已拦截，这里兜底）
        return {"ok": False, "source": "delegated"}
    # 短路（可配 skip_react_when_model_missing，默认开）：需求点名了不在在售目录的具体机型
    # （如 联想 WA5480 G3）→ ReAct 只会反复确认"目录里没有"然后烧 30s 降级，不如直走规则
    # 降级（select_models 已有 fallback_order 多级放宽 + 白盒说明），省时且更透明。
    if bool(cfg.get("skip_react_when_model_missing", True)) and \
            _named_model_not_in_catalog(text, cfg, ctx):
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
    persona = (ctx.get("colleague_system_prompt") or "").strip()
    base_prompt = str(cfg.get("system_prompt") or "")
    if persona:
        base_prompt = persona + "\n\n" + base_prompt
    agent_cfg = {
        "enabled_tools": cfg.get("enabled_tools") or [str(cfg.get("grounding_tool"))],
        "system_prompt": base_prompt,
    }
    try:
        react = await run_react_loop(text, agent_cfg, extra_context=extra,
                                     max_iterations=int(cfg.get("max_iterations") or 2),
                                     allowed_tool_ids=ctx.get("colleague_tool_ids"),
                                     model=ctx.get("colleague_model_override"),
                                     event_sink=broadcast)
        candidates = _extract_grounding_from_react(react.get("tool_calls_log") or [], cfg)
        chosen = _parse_model_choice(react.get("answer") or "", candidates, cfg)
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


KP_FINAL_CONTRACT = (
    "\n\n【任务】只输出一个 JSON 对象，不要 Markdown 代码块，不调用工具、不分步。"
    "你已完成信息处理，直接给配件提议。"
    '必须是：{"action":"final","answer":{"memory":{"per_stick_gb":32,"qty":8,"type":"DDR5","speed_mt":6400,"total_gb":256,"reason":"..."},'
    '"raid":{"model":"RAID卡型号","qty":1,"reason":"..."},'
    '"nic":[{"speed_g":10,"ports":2,"qty":1,"with_optical_module":false,"reason":"..."}],'
    '"psu":{"wattage":3000,"qty":4,"reason":"..."},"notes":["..."]}}'
    "\n- memory/raid/nic/psu 按上面键给；没把握的键省略（置空），绝不编造不在机型能力目录内的型号/料号/瓦数。"
    "\n- 型号/料号/价格/兼容性由后端库校验，你只给建议；最终以库为准。"
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


def _kp_proposal_reason(data: dict, config: Optional[dict] = None) -> str:
    """提议的白盒说明（给 step_done payload / 用户看）；摘要规则由 proposal_mapping 驱动。"""
    cfg = _kp_config(config)
    notes = []
    mapping = cfg.get("proposal_mapping") or {}
    for target, spec in mapping.items():
        if not isinstance(spec, dict):
            continue
        source = data.get(target)
        if isinstance(source, list):
            if source:
                notes.append(f"{target} {len(source)} 项")
            continue
        if not isinstance(source, dict):
            continue
        fields = [str(f) for f in (spec.get("fields") or []) if f]
        required = [str(f) for f in (spec.get("required_any") or fields) if f]
        if not any(source.get(f) is not None for f in required):
            continue
        parts = []
        for f in fields:
            if source.get(f) is not None:
                parts.append(f"{f}={source[f]}")
        if parts:
            notes.append(f"{target} {'，'.join(parts)}")
    summary = "、".join(notes)
    template = str(cfg.get("reason_template") or "{{items}}")
    return template.replace("{{items}}", summary) if summary else ""


def _apply_kp_proposal(ext: dict, data: dict, requirement_text: str, config: Optional[dict] = None) -> None:
    """把 LLM 提议合并进 ext（复用 merge_into_ext 的确定性收口：只补缺、规则赢）。
    哪个字段合入、哪些字段必填，全部由 proposal_mapping 配置决定。"""
    from app.services.llm_extract_enhance import merge_into_ext
    cfg = _kp_config(config)
    slots: dict = {}
    for target, spec in (cfg.get("proposal_mapping") or {}).items():
        if not isinstance(spec, dict):
            continue
        source = data.get(target)
        fields = [str(f) for f in (spec.get("fields") or []) if f]
        required = [str(f) for f in (spec.get("required_any") or fields) if f]
        if isinstance(source, list):
            cleaned_items = []
            for item in source or []:
                if not isinstance(item, dict):
                    continue
                if not any(item.get(f) is not None for f in required):
                    continue
                cleaned_items.append({f: item.get(f) for f in fields if item.get(f) is not None})
            if cleaned_items:
                slots[target] = cleaned_items
            continue
        if not isinstance(source, dict):
            continue
        if not any(source.get(f) is not None for f in required):
            continue
        slots[target] = {f: source.get(f) for f in fields if source.get(f) is not None}
    if slots:
        try:
            merge_into_ext(ext, slots, requirement_text=requirement_text)
        except Exception as e:
            logger.warning("kp 提议合并失败（丢弃提议，规则赢）: %s", e)


async def _kp_llm_propose(ctx: dict, config: dict, broadcast=None) -> dict:
    """KP LLM 提议（单次流式）：读需求+理解摘要+机型通道 → 一次流式输出配件提议 JSON。
    与 agent_fill 同构：不再多轮 ReAct/工具，模型只输出最终 JSON；schema 收口与事实落地交给
    clean_by_schema + _apply_kp_proposal（规则赢）。失败返回 {ok:False}，上层降级规则。"""
    from app.services import llm_client
    from app.services.agent_react import run_react_loop
    cfg = _kp_config(config)
    ext = ctx.get("ext") or {}
    baseline = ctx.get("baseline") or (ctx.get("baselines") or [None])[0]
    mem_cfg = ""
    if baseline:
        mc = baseline.get("mem_channels")
        md = baseline.get("max_dimm")
        mem_cfg = f"机型 {baseline.get('name') or '?'}：内存通道={mc or '未知'}，最大插槽={md or '未知'}"
    text = ctx.get("requirement_text") or ""
    user_template = str(cfg.get("user_prompt_template") or "")
    user = user_template
    for key, value in {
        "requirement_text": text,
        "understood": _ext_digest_for_kp(ext),
        "baseline_capability": mem_cfg or "（未选机型）",
    }.items():
        user = user.replace("{{" + key + "}}", str(value))

    async def _sink(ev: dict) -> None:
        if not broadcast:
            return
        try:
            await broadcast({"type": "step_progress", "step": "kp_reason",
                             "sub": ev.get("sub") or {}})
        except Exception:
            pass

    try:
        result = await run_react_loop(
            requirement_text=text or "（无需求原文）",
            config={**cfg, "enabled_tools": []},
            system_prompt=str(cfg.get("system_prompt") or ""),
            history=[],
            extra_context=user,
            max_iterations=min(int(cfg.get("max_iterations") or 3), 2),
            event_sink=_sink,
            final_only=True,
            final_only_contract=KP_FINAL_CONTRACT,
        )
    except Exception as e:
        logger.warning("kp LLM 提议失败: %s", e)
        return {"ok": False, "error": str(e)[:200]}
    raw_answer = result.get("answer") or ""
    if not result.get("ok") or not raw_answer:
        err = str(result.get("error") or (raw_answer if isinstance(raw_answer, str) else "empty"))[:200]
        logger.warning("kp LLM 提议未返回有效 JSON: %s", err)
        return {"ok": False, "error": err or "empty"}
    text_ans = raw_answer if isinstance(raw_answer, str) else json.dumps(raw_answer, ensure_ascii=False)
    try:
        parsed = llm_client._parse_json_content(text_ans) if isinstance(text_ans, str) else raw_answer
    except Exception:
        parsed = None
    if not isinstance(parsed, dict) or not parsed:
        return {"ok": False, "error": "empty"}
    data, _ = llm_client.clean_by_schema(parsed, cfg.get("proposal_schema") or KP_PROPOSE_SCHEMA)
    if not isinstance(data, dict) or not data:
        return {"ok": False, "error": "empty_schema"}
    _apply_kp_proposal(ext, data, text, cfg)
    return {"ok": True, "proposal": data, "reason": _kp_proposal_reason(data, cfg)}


async def run_kp_reason(ctx: dict, config: dict, broadcast=None) -> dict:
    """配件推理（改革版·Phase1）：LLM 提议（内存条数/RAID/网卡/电源）→ pick_kp_parts 库校验执行。

    AI-first：固定走 LLM 提议（内存条数/RAID/网卡/电源）→ pick_kp_parts 库校验执行。
    返回 {ok, kp_parts, kp_count, reason, trace, source}。LLM 提议失败 → run_match_kp_rule 规则兜底。
    """
    cfg = _kp_config(config)
    if not _ai_enabled(ctx, cfg):
        return {"ok": False, "source": "rule"}
    proposal_note = ""
    if bool(cfg.get("proposal_enabled", True)):
        prop = await _kp_llm_propose(ctx, cfg, broadcast)
        if prop.get("ok"):
            proposal_note = prop.get("reason") or ""
            ctx["kp_proposal"] = prop.get("proposal")
        else:
            logger.warning("kp LLM 提议失败(%s)，降级规则匹配", prop.get("error"))
    rule_res = run_match_kp_rule(ctx, cfg)
    ok = bool(rule_res.get("kp_count"))
    return {**rule_res, "ok": ok, "source": "llm+rule" if proposal_note else "rule",
            "reason": proposal_note, "trace": [], "kp_parts": ctx.get("kp_parts") or []}




DEFAULT_KP_REASON_CONFIG = {
    "proposal_enabled": True,
    "proposal_schema": KP_PROPOSE_SCHEMA,
    "temperature": 0.2,
    "timeout": 60,
    "max_attempts": 1,
    "proposal_mapping": {
        "memory": {
            "fields": ["per_stick_gb", "qty", "type", "speed_mt", "comparison", "total_gb"],
            "required_any": ["per_stick_gb", "total_gb"],
        },
        "raid": {
            "fields": ["model", "qty"],
            "required_any": ["model"],
        },
        "nic": {
            "fields": ["speed_g", "ports", "qty", "with_optical_module"],
            "required_any": ["speed_g", "ports", "qty"],
        },
    },
    "reason_template": "配件规划：已确认 {{items}}",
}


def _kp_config(config: Optional[dict]) -> dict:
    """归一化 kp_reason 节点配置；LLM 提议的 schema/提示词/映射全部可编辑。"""
    cfg = dict(config or {})
    for key, value in DEFAULT_KP_REASON_CONFIG.items():
        if isinstance(value, dict):
            cfg.setdefault(key, dict(value))
        elif isinstance(value, list):
            cfg.setdefault(key, list(value))
        else:
            cfg.setdefault(key, value)
    d = prompt_store.get_prompt_defaults("kp_reason")
    for key in ("system_prompt", "user_prompt_template"):
        cur = cfg.get(key)
        if cur is None or (isinstance(cur, str) and not cur.strip()):
            cfg[key] = d.get(key, "")
    return cfg




def _ask_config(config: Optional[dict]) -> dict:
    """归一化 agent_fill/model_reason 等节点配置：数据来源与规则目录可配，不再含反问状态机字段。"""
    cfg = dict(config or {})
    cfg.setdefault("data_sources", ["server_catalog"])
    cfg.setdefault("rule_types", ["platform_series_map"])
    return cfg

def _infer_series_from_requirement(text: str, config: Optional[dict] = None) -> Optional[str]:
    """按 platform_series_map 把 AMD/兆芯/Intel 等平台词归一为系列。"""
    low = (text or "").lower()
    try:
        from app.services.requirement_rule_catalog import platform_series_map
        rules = platform_series_map(enabled_types=_ask_config(config).get("rule_types"))
    except Exception:
        return None
    for rule in rules:
        series = str(rule.get("series") or "").strip()
        keywords = [str(k).strip().lower() for k in (rule.get("keywords") or []) if str(k).strip()]
        if series and any(k in low for k in keywords):
            return series
    return None


def _catalog_whitelist(config: Optional[dict] = None, ext: Optional[dict] = None,
                       requirement_text: str = "") -> dict:
    """从在售目录构建与已确认字段一致的候选白名单。

    保留机型与类型/系列/形态的关联（model_meta），后续选项过滤只在此受限集合内进行。
    """
    cfg = _ask_config(config)
    ext = ext or {}
    out: dict = {"types": [], "series": [], "forms": [], "models": [], "model_meta": {}}
    try:
        from app.services.catalog_guide import load_catalog
        types, models_by_type = load_catalog()
    except Exception as e:
        logger.warning("读反问候选目录失败: %s", e)
        return out

    confirmed_type = (ext.get("server_type_name") or "").strip()
    confirmed_series = (ext.get("series") or "").strip() or _infer_series_from_requirement(requirement_text, cfg) or ""
    confirmed_form = (ext.get("form") or "").strip()
    type_names = [str(t.get("name") or "") for t in (types or []) if t.get("name")]
    type_names = [tn for tn in type_names if (models_by_type or {}).get(tn)]

    type_set: set = set()
    series_order: list = []
    form_order: list = []
    model_order: list = []
    model_meta: dict = {}

    def _add_unique(lst: list, value: str) -> None:
        value = str(value or "").strip()
        if value and value not in lst:
            lst.append(value)

    for tn in type_names:
        if confirmed_type and tn != confirmed_type:
            continue
        for m in (models_by_type or {}).get(tn) or []:
            base = m.get("base_config") or {}
            model_series = (base.get("series") or m.get("series") or "").strip()
            model_form = (base.get("form") or m.get("form") or "").strip()
            if confirmed_series and model_series != confirmed_series:
                continue
            if confirmed_form and model_form != confirmed_form:
                continue
            name = str(m.get("name") or "").strip()
            if not name:
                continue
            type_set.add(tn)
            _add_unique(series_order, model_series)
            _add_unique(form_order, model_form)
            if name not in model_order:
                model_order.append(name)
            model_meta[name] = {"type": tn, "series": model_series, "form": model_form}

    out["types"] = [tn for tn in type_names if tn in type_set]
    if not out["types"] and confirmed_type:
        out["types"] = [confirmed_type]
    out["series"] = series_order
    out["forms"] = form_order
    out["models"] = model_order
    out["model_meta"] = model_meta
    out["inferred_series"] = confirmed_series or None
    return out


def _slot_now_filled(ext: dict, key: str) -> bool:
    """反问回填后判断某 slot 是否已确认（与理解节点 slot 填充口径一致）。"""
    from app.services import semantic_contract as _sc
    if _sc.absent_confirmed(ext, key):
        return True
    def _has(v) -> bool:
        if v is None or v is False:
            return False
        if isinstance(v, str):
            return v.strip() != ""
        if isinstance(v, (int, float)):
            return v > 0
        if isinstance(v, dict):
            return any(_has(x) for x in v.values())
        if isinstance(v, (list, tuple)):
            return any(_has(x) for x in v)
        return bool(v)
    mapping = {
        "server_type": ["server_type_name", "server_type"],
        "platform_type": ["series", "platform_type"],
        "chassis_form": ["form", "chassis_form"],
        "purchase_qty": ["purchase_qty", "n"],
        "n": ["n", "purchase_qty"],
        "server_model": ["server_model", "model", "baseline_model"],
        "cpu": ["cpu_signal", "cpu"],
        "memory": ["mem_signal", "mem_groups", "memory"],
        "storage": ["drive_groups", "drives", "storage"],
        "gpu": ["gpu_groups", "gpu"],
        "nic": ["nic_groups", "nic_signal", "nic", "multi_spec_filters"],
        "raid": ["raid_groups", "raid_signal", "raid"],
        "psu": ["psu_signal", "psu"],
    }
    return any(_has(ext.get(k)) for k in mapping.get(key, []))




def _infer_series_from_selected_model(ext: dict, whitelist: dict, cfg: dict,
                                      requirement_text: str = "") -> None:
    """机型已选但系列/类型/形态空 → 从 model_meta 反推，避免「机型定了却问系列」。"""
    model = str(ext.get("server_model") or "").strip()
    if not model:
        return
    meta = (whitelist.get("model_meta") or {}).get(model) or {}
    if not ext.get("server_type_name") and meta.get("type"):
        ext["server_type_name"] = meta["type"]
    if not (ext.get("series") or ext.get("platform_type")) and meta.get("series"):
        ext["series"] = meta["series"]
        ext["platform_type"] = meta["series"]
    if not (ext.get("form") or ext.get("chassis_form")) and meta.get("form"):
        ext["form"] = meta["form"]
        ext["chassis_form"] = meta["form"]


def _confirmed_text(ext: dict) -> str:
    """把已确认的选型要点拼成一行（只做状态展示，不做话术）。"""
    parts = []
    if ext.get("server_type_name"):
        parts.append(f"服务器类型={ext['server_type_name']}")
    if ext.get("series"):
        parts.append(f"平台系列={ext['series']}")
    if ext.get("form"):
        parts.append(f"机箱形态={ext['form']}")
    if ext.get("server_model"):
        parts.append(f"机型={ext['server_model']}")
    if ext.get("purchase_qty"):
        parts.append(f"数量={ext['purchase_qty']}")
    return "；".join(parts) or "（暂无明确约束）"

def _apply_extracted_slots(ext: dict, slots: dict, allow_overwrite: bool = False) -> bool:
    """把 LLM 抽取的需求层 slots 应用到 ext（信任模型语义）。

    allow_overwrite=True 用于 edit 意图：允许覆盖已确认值；默认只填空槽。
    目录/部件结构槽不在此落（由 slot_extractor / 下游负责）。仅拒绝 None 与明显空值。
    """
    if not isinstance(slots, dict):
        return False
    changed = False
    for key, value in (slots or {}).items():
        if value is None:
            continue
        if isinstance(value, bool) and not value:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        key = str(key).strip()
        if not key:
            continue
        if isinstance(value, (dict, list)):
            continue
        if key in ("server_type", "server_type_name"):
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "server_type"):
                ext["server_type"] = ext["server_type_name"] = v
                changed = True
        elif key in ("platform_type", "series"):
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "platform_type"):
                ext["platform_type"] = ext["series"] = v
                changed = True
        elif key in ("chassis_form", "form"):
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "chassis_form"):
                ext["chassis_form"] = ext["form"] = v
                changed = True
        elif key in ("server_model", "model", "baseline_model"):
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "server_model"):
                ext["server_model"] = v
                ext.pop("model", None)
                changed = True
        elif key in ("purchase_qty", "n"):
            try:
                qty = int(float(value))
            except Exception:
                continue
            if allow_overwrite or (not _slot_now_filled(ext, "n") and not _slot_now_filled(ext, "purchase_qty")):
                ext["n"] = ext["purchase_qty"] = qty
                changed = True
        else:
            if allow_overwrite or not _slot_now_filled(ext, key):
                ext[key] = value
                changed = True
    return changed
def _extract_agent_fill_json(text: str) -> dict:
    """从 agent final 消息里抽取含 fill/ask/done/edit 的 JSON 对象（取键最全的那个）。"""
    s = str(text or "")
    import json

    def balanced_end(start: int) -> int:
        depth = 0
        in_str = False
        esc = False
        for j in range(start, len(s)):
            ch = s[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return j
        return -1

    best: dict = {}
    best_score = -1
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        end = balanced_end(i)
        if end == -1:
            continue
        try:
            obj = json.loads(s[i:end + 1])
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if not any(k in obj for k in ("fill", "ask", "done", "edit")):
            continue
        score = sum(1 for k in ("fill", "ask", "done", "edit") if k in obj)
        if score > best_score:
            best = obj
            best_score = score
    return best


def _ground_fill_from_tools(answer: str, tool_calls_log: list, ext: dict,
                            config: dict, req_text: str) -> None:
    """模型未给 fill 时，用 agent 已调工具返回的真实目录候选落地机型，再反推系列/形态/类型。"""
    ans = str(answer or "")
    cands: dict = {}
    for call in (tool_calls_log or []):
        if not isinstance(call, dict) or call.get("name") not in (
                "select_models", "get_server_model", "list_server_models"):
            continue
        result = call.get("result")
        items = []
        if isinstance(result, dict):
            items = result.get("matches") or result.get("candidates") or result.get("models") or [result]
        elif isinstance(result, list):
            items = result
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name") or it.get("model") or it.get("model_name") or "").strip()
            if name:
                cands.setdefault(name, it)
    if not cands:
        return
    picks = [name for name in cands if name in ans]
    if not picks:
        return
    picks.sort(key=len, reverse=True)
    name = picks[0]
    meta = cands[name]
    ext.setdefault("server_model", name)
    if meta.get("type") and not ext.get("server_type_name"):
        ext["server_type_name"] = meta["type"]
    if meta.get("series") and not ext.get("series"):
        ext["series"] = meta["series"]
        ext.setdefault("platform_type", meta["series"])
    if meta.get("form") and not ext.get("form"):
        ext["form"] = meta["form"]
        ext.setdefault("chassis_form", meta["form"])
    whitelist = _catalog_whitelist(config, ext=ext, requirement_text=req_text)
    _infer_series_from_selected_model(ext, whitelist, config, requirement_text=req_text)


def _semantic_ref_text(config: Optional[dict], req_text: Optional[str]) -> str:
    """把语义契约参考（workload_map/compliance_map/gpu_form_map）注入 agent 上下文，供它按规则推断。"""
    from app.services import requirement_rule_catalog as _rc
    rule_types = (config or {}).get("rule_types")
    chunks = []
    # 真实在售目录（数据源）：模型只按目录里实际存在的类型/系列/形态归一化，禁用死词表。
    try:
        from app.services.catalog_guide import load_catalog
        _c_types, _c_by_type = load_catalog()
    except Exception:
        _c_types, _c_by_type = [], {}
    if _c_types:
        _tnames = [str(t.get("name") or "").strip() for t in _c_types if str(t.get("name") or "").strip()]
        if _tnames:
            chunks.append("在售服务器类型目录（只能填这些 server_type_name）：\n" + "\n".join("  - " + n for n in _tnames))
        _series_order: list = []
        _form_order: list = []
        for _tn, _ms in (_c_by_type or {}).items():
            for _m in _ms or []:
                _b = _m.get("base_config") or {}
                for _s in (_b.get("series"), _m.get("series")):
                    _s = str(_s or "").strip()
                    if _s and _s not in _series_order:
                        _series_order.append(_s)
                for _f in (_b.get("form"), _m.get("form")):
                    _f = str(_f or "").strip()
                    if _f and _f not in _form_order:
                        _form_order.append(_f)
        if _series_order:
            chunks.append("在售平台系列目录（只能填这些 series/platform_type）：\n" + "\n".join("  - " + s for s in _series_order))
        if _form_order:
            chunks.append("在售机箱形态目录（只能填这些 form/chassis_form）：\n" + "\n".join("  - " + f for f in _form_order))
    ta = _rc.type_alias(rule_types)
    if ta:
        lines = ["  %s → %s" % (r.get("keyword"), r.get("type_name")) for r in ta if r.get("keyword") and r.get("type_name")]
        chunks.append("类型别名等价参考（客户说左侧词，按右侧目录类型登记 server_type_name）：\n" + "\n".join(lines))
    psm = _rc.platform_series_map(rule_types)
    if psm:
        lines = []
        for r in psm:
            kws = "、".join(str(k) for k in (r.get("keywords") or []) if str(k).strip())
            if kws:
                lines.append("  " + kws + " → " + str(r.get("series") or ""))
        if lines:
            chunks.append("平台系列别名等价参考（客户说左侧平台词 → 按右侧系列登记 series/platform_type）：\n" + "\n".join(lines))
    wl = _rc.workload_map(rule_types)
    if wl:
        lines = []
        for r in wl:
            lines.append("  %s → 意图=%s 总显存=%sG 卡数=%s" % (
                r.get("workload_keyword"), r.get("intent"), r.get("total_vram_gb"), r.get("gpu_count")))
        chunks.append("工作负载等价参考（命中关键词即按此填 total_vram_gb/gpu_count）：\n" + "\n".join(lines))
    cm = _rc.compliance_map(rule_types)
    if cm:
        c = cm[0]
        chunks.append("国产化参考：系列=%s 排除厂商=%s 允许厂商=%s GPU策略=%s" % (
            c.get("platform_series"), c.get("excluded_manufacturers"),
            c.get("allowed_manufacturers"), c.get("gpu_policy")))
    gm = _rc.gpu_form_map(rule_types)
    if gm:
        lines = ["  %s-%s卡 → %s" % (r.get("gpu_count_min"), r.get("gpu_count_max"), r.get("form")) for r in gm]
        chunks.append("GPU卡数→机箱形态：\n" + "\n".join(lines))
    return "\n\n" + "\n".join(chunks) if chunks else ""


def _enrich_agent_semantic(ext: dict, config: Optional[dict], req_text: Optional[str]) -> None:
    """agent 吐出的语义契约后处理：按规则补齐 workload/国产化/GPU 卡数，不硬编码业务。"""
    from app.services import semantic_contract as _sc
    from app.services import requirement_rule_catalog as _rc
    rule_types = (config or {}).get("rule_types")
    rtext = str(req_text or "").lower()
    # 模型输出的 semantic 已经过 schema 收口，此处作为 advisor；侧重在“事实确定性”。
    # 量化事实（gpu_count/total_vram_gb）来源：模型 semantic > 规则库 workload_map（规则赢模型的数值）。
    wl = dict(_sc.workload(ext))
    # 2) 规则库 workload_map：命中关键词即按规则补总显存/卡数/意图（规则赢模型的数值）。
    for r in _rc.workload_map(rule_types):
        kw = str(r.get("workload_keyword") or "").lower()
        if kw and kw in rtext:
            if r.get("intent"):
                wl["kind"] = str(r.get("intent"))
            if r.get("total_vram_gb") is not None and "total_vram_gb" not in wl:
                wl["total_vram_gb"] = r.get("total_vram_gb")
            if r.get("gpu_count") is not None and "gpu_count" not in wl:
                wl["gpu_count"] = r.get("gpu_count")
            break
    if wl:
        _sc.set_value(ext, "workload", wl)
        if wl.get("kind") and _sc.intent(ext) in (None, "general"):
            _sc.set_value(ext, "intent", str(wl.get("kind")))
    comp = dict(_sc.compliance(ext))
    if comp.get("domestic_only"):
        if _sc.intent(ext) in (None, "general"):
            _sc.set_value(ext, "intent", "domestic_compliance")
    # GPU 卡数保存到 gpu_groups：量化事实来自模型 semantic 与规则库 workload_map。
    gc = int(wl.get("gpu_count") or 0)
    if gc > 0 and not _sc.absent_confirmed(ext, "gpu") and not ext.get("gpu_groups") and not ext.get("gpu"):
        ext["gpu_groups"] = [{"qty": gc}]

def _freeze_requirement(ctx: dict, ext: dict, req_text: str = "") -> None:
    """把 agent_fill 落地的需求事实固化为「线索登记表」快照 ctx.requirement。

    下游（机型/KP/组装）只读该快照，绝不回写；后续持久化与运行面板都以它为准。
    机型字段只在客户原话真实点名时才保留（否则从 ext 与快照一并剔除，
    避免 LLM 臆造或下游选型结果污染“原始需求”，也不误导下游当作客户指定机型）。
    """
    import copy as _copy
    import re as _re
    model = str(ext.get("server_model") or ext.get("model") or "").strip()
    if model:
        norm_model = _re.sub(r"\s+", "", model)
        norm_text = _re.sub(r"\s+", "", str(req_text or ""))
        if norm_model not in norm_text:
            ext.pop("server_model", None)
            ext.pop("model", None)
    ctx["requirement"] = _copy.deepcopy(ext)
    ctx["requirement_text_snapshot"] = str(req_text or "")

async def run_agent_fill(ctx: dict, config: dict, broadcast=None, step_id: str = "agent_fill") -> dict:
    """智能对话填表 Agent（ReAct 形态，不再兼容旧槽位状态机）。

    - 完整会话历史 + 目录/KP 工具 + 当前草稿/缺口一起交给 agent。
    - agent 调工具查证（是否在售、系列归属、配件），可一次批量填多槽，可改口。
    - 最后输出结构化 {fill, ask, done, edit}；执行器落地并决定是否反问。
    - LLM 不可用时不回退白名单正则，直接返回 error 交给调用方。
    """
    from app.services.slot_contract import _missing_critical, slot_label
    from app.services.slot_state import is_confirmed
    from app.services import prompt_store
    from app.services.agent_react import run_react_loop
    config = prompt_store.merge_node_prompt("agent_fill", config or {})

    req_text = str(ctx.get("requirement_text") or ctx.get("normalized_text") or "").strip()
    ext = dict(ctx.get("ext") or {})
    from app.services.slot_contract import slot_spec
    req_keys = {s.get("key") for s in slot_spec() if s.get("src_type") != "kp" and s.get("key") != "server_model"}
    prev_missing = list(ctx.get("missing_fields") or [])
    missing = [m for m in _missing_critical(ext) if m in req_keys and not is_confirmed(ext, m)]
    confirmed_text = _confirmed_text(ext)
    missing_labels = [slot_label(m) for m in missing]
    extra = (
        "当前线索登记表草稿：\n" + (confirmed_text or "（尚未填写）") +
        "\n\n还缺（参考，不必按顺序问）：" + ("、".join(missing_labels) or "无") +
        "\n\n任务：只登记客户已明确表达的需求层字段；缺的只反问“必填且未委托”的字段；客户委托（你随便/都行）就留空交下游，不要编造具体值；客户改口就覆盖草稿。"
    )
    extra += _semantic_ref_text(config, req_text)
    _prompt = config.get("prompt") or {}
    sys_prompt = str(_prompt.get("system_prompt") or "").strip() or str(
        prompt_store.get_prompt_defaults("agent_fill").get("system_prompt") or "")
    tools = list(config.get("enabled_tools") or capability_spec.default_tools("agent_fill"))

    async def _sink(ev: dict) -> None:
        if not broadcast:
            return
        try:
            await broadcast({"type": "step_progress", "step": step_id,
                             "sub": ev.get("sub") or {}})
        except Exception:
            pass

    # 单次流式：agent_fill 不再是多轮工具调用循环。模型只负责正常情况下一次输出最终 JSON（fill/ask/done/edit/semantic）；
    # 事实冲地由下游确定性层（_apply_extracted_slots/_enrich_agent_semantic/check_feasibility）完成。
    # 安全余量：限制最多 2 轮（正常 1 轮，非 JSON 时一次轻量纠正），不再无限滚大。
    result = await run_react_loop(
        requirement_text=req_text or "（无需求原文）",
        config={**config, "enabled_tools": tools},
        system_prompt=sys_prompt,
        history=ctx.get("history") or [],
        extra_context=extra,
        max_iterations=min(int(config.get("max_iterations") or 3), 2),
        event_sink=_sink,
        final_only=True,
    )
    raw_answer = result.get("answer") or ""
    agent_answer = raw_answer if isinstance(raw_answer, str) else (
        json.dumps(raw_answer, ensure_ascii=False)
        if isinstance(raw_answer, (dict, list)) else str(raw_answer))
    if not result.get("ok"):
        error = str(result.get("error") or (agent_answer if agent_answer else "agent_fill 不可用"))[:200]
        return {"ok": False, "error": error, "source": step_id,
                "sufficient": False, "missing_critical": missing}

    parsed = agent_answer if isinstance(agent_answer, dict) else _extract_agent_fill_json(agent_answer)
    fill = parsed.get("fill") if isinstance(parsed.get("fill"), dict) else {}
    ask = str(parsed.get("ask") or "").strip()
    done = bool(parsed.get("done", True))
    edit = bool(parsed.get("edit", False))

    from app.services import semantic_contract as _sc
    # 输出格式收口：模型回的 semantic 子对象按契约 schema 验证，
    # 非法类型/未知字段/非法枚举一律丢弃（如 workload 被写成字符串 → 丢弃，保留已有结构化值）。
    _sem_raw = parsed.get(_sc.container_key())
    if isinstance(_sem_raw, dict):
        from app.services.llm_client import clean_by_schema
        _sem_raw, _sem_dropped = clean_by_schema(_sem_raw, _sc.schema())
    _sc.merge(ext, _sem_raw)

    if fill:
        _apply_extracted_slots(ext, fill, allow_overwrite=edit)
        try:
            from app.services.slot_extractor import apply_structured_slots
            apply_structured_slots(ext, fill, req_text)
        except Exception:
            pass
    _enrich_agent_semantic(ext, config, req_text)
    # 可行性护栏在理解阶段即触发，冲突不等到机型选型才提示。
    try:
        from app.services.feasibility_guard import check_feasibility
        _fz = check_feasibility(ext, config)
        if _fz.get("warnings") or _fz.get("hints"):
            ctx["feasibility"] = _fz
    except Exception:
        pass
    ctx["ext"] = ext
    _freeze_requirement(ctx, ext, req_text)
    ctx["agent_fill_trace"] = result.get("tool_calls_log") or []

    missing = [m for m in _missing_critical(ext) if m in req_keys and not is_confirmed(ext, m)]
    ctx["missing_fields"] = missing
    # 反问收敛：这是对上一个追问的补充回答，且缺口集合与上一轮完全一致（用户答了但没填上该字段）
    # → 停止机械重复追问，带着“可默认”的 partial 清晰度交给下游，由下游按目录默认/放宽处理。
    _no_progress = bool(ctx.get("last_user_answer")) and bool(prev_missing) and sorted(missing) == sorted(prev_missing)
    ctx["converged"] = bool(_no_progress)
    need_ask = bool(missing) and not ctx.get("force_complete") and not ctx.get("delegated") and not _no_progress
    _fz_block = ""
    _fz = ctx.get("feasibility") or {}
    _fz_lines = [("⚠️ " + w) for w in (_fz.get("warnings") or [])] + [("提示：" + h) for h in (_fz.get("hints") or [])]
    if _fz_lines:
        _fz_block = chr(10).join(_fz_lines) + chr(10)
    if need_ask:
        question = ask or ("还有几个关键信息待确认：" + "、".join(
            [slot_label(m) for m in missing]))
        if _fz_block:
            question = _fz_block + question
        import uuid
        rid = f"agent_{uuid.uuid4().hex[:12]}"
        ctx["awaiting_input"] = True
        ctx["last_reply_id"] = rid
        ctx["last_ask_question"] = question
        if broadcast:
            try:
                await broadcast({"type": "need_input", "reply_id": rid, "question": question,
                                 "options": None, "why": "", "missing_fields": missing,
                                 "source": "agent_fill"})
            except Exception:
                pass
        return {"ok": True, "question": question, "options": None, "source": step_id,
                "sufficient": False, "missing_critical": missing, "agent_answer": agent_answer}

    has_model = bool(ext.get("server_model") or ext.get("model"))
    ctx["customer_specified_model"] = has_model
    if ctx.get("delegated"):
        # 客户已委托（你推荐/都行）→ 需求“模糊”不再等同于“无法下手”，交给下游推荐，不判 unclear。
        ctx["clarity"] = "delegated"
    elif ctx.get("converged"):
        # 客户反复没答上同个字段 → 不再卡住，按“已有信息可下沉”继续，由下游给默认/放宽。
        ctx["clarity"] = "partial"
    elif missing:
        ctx["clarity"] = "unclear"
    else:
        ctx["clarity"] = "explicit" if has_model else "partial"
    return {"ok": True, "source": step_id, "sufficient": bool(not missing),
            "missing_critical": missing, "agent_answer": agent_answer, "done": done}


def run_select_baseline_rule(ctx: dict, config: dict) -> dict:
    """机型选型规则本体：四级兜底（exact/same_series/same_form/all，fallback_order 可配）+ model_recommend 标注。"""
    from app.api.candidate_search import select_models, build_variant_signals
    from app.services.requirement_rule_catalog import fallback_order as _catalog_fallback_order
    cfg = config or {}
    _fb = _catalog_fallback_order(enabled_types=cfg.get("rule_types"))
    _fallback_order = _fb.get("order") or ["exact", "same_series", "same_form", "all"]
    _no_signal_strategy = _fb.get("no_signal_strategy") or "return_empty"
    if ctx.get("awaiting_input"):
        ctx["baselines"] = []
        return {"count": 0, "matches": [], "skipped": "awaiting_input"}
    ext = ctx.get("ext") or {}
    scene = ctx.get("scene") or {}
    _type_name = (ctx.get("catalog_type_name")
                  or (scene.get("scene_name") if scene.get("determined") else None)
                  or ext.get("server_type_name"))
    from app.services import semantic_contract as _sc
    from app.services.requirement_rule_catalog import compliance_map as _compliance_map, gpu_form_map as _gpu_form_map
    _series = scene.get("series") or ext.get("series") or None
    _form = scene.get("form") or ext.get("form") or None
    # 客户已委托（你推荐/随便/都行）且完全没给类型/系列/形态线索 → 默认到目录里排序第一的
    # “通用”类型，让推荐有抓手，而不是返回“找不到机型”。数据来自目录 sort_order，非硬编码词。
    if not _type_name and not _series and not _form and ctx.get("delegated"):
        try:
            from app.repository.server_catalog_repo import ServerCatalogRepository
            _cts = ServerCatalogRepository().list_types()
            if _cts:
                _def_type = min(_cts, key=lambda t: int(t.get("sort_order") or 1 << 30))
                _type_name = str(_def_type.get("name") or "")
                ctx["delegated_default_type"] = _type_name
        except Exception:
            logger.exception("委托默认类型解析失败，交回空候选")
    _domestic_only = bool(_sc.is_domestic_only(ext))
    _domestic_series = set()
    if _domestic_only:
        _cms = _compliance_map(enabled_types=cfg.get("rule_types")) or [{}]
        _domestic_series = set(_cms[0].get("platform_series") or ["Polaris"])
        if _series not in _domestic_series:
            _series = next(iter(_domestic_series), _series)
    # GPU 数量（来自 workload/exclusion 卡数）→ 机箱形态约束
    _gpu_count = int((_sc.gpu_requirement(ext) or {}).get("gpu_count") or 0)
    if _gpu_count > 0:
        for _rule in _gpu_form_map(enabled_types=cfg.get("rule_types")):
            _lo = int(_rule.get("gpu_count_min") or 0)
            _hi = int(_rule.get("gpu_count_max") or (1 << 31))
            if _lo <= _gpu_count <= _hi and _rule.get("form"):
                _form = str(_rule.get("form") or _form)
                break
    from app.api.candidate_search import MAX_PLANS
    baselines = select_models(
        ext.get("usage"), _type_name, _series, _form,
        limit=cfg.get("max_plans") or MAX_PLANS,
        recommend_strategy_id=cfg.get("recommend_strategy_id"),
        no_signal_strategy=_no_signal_strategy,
        variant_signals=build_variant_signals(ext, ctx.get("requirement_text")),
        # 多级放宽（用户可配 fallback_order；未配则读规则目录）：
        # 库内无 {系列} 平台 {类型} 机型时按配置顺序逐级放宽，白盒标注放宽维度
        fallback_order=_fallback_order,
    )
    if _domestic_only and _domestic_series:
        baselines = [b for b in baselines if b.get("series") in _domestic_series]
        if not baselines and _series in _domestic_series:
            # 放宽被过滤后无结果：保留系列但标注
            baselines = [b for b in select_models(
                ext.get("usage"), _type_name, _series, _form,
                limit=cfg.get("max_plans") or MAX_PLANS,
                recommend_strategy_id=cfg.get("recommend_strategy_id"),
                no_signal_strategy=_no_signal_strategy,
                variant_signals=build_variant_signals(ext, ctx.get("requirement_text")),
                fallback_order=_fallback_order,
            ) if b.get("series") in _domestic_series]
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
            selected = None
            for r in rules:
                rng = (r.get("body") or {}).get("range") or {}
                mn, mx = rng.get("min"), rng.get("max")
                if budget is None:
                    if mn is None and mx is None:
                        selected = r
                        break
                    continue
                if (mn is None or budget >= mn) and (mx is None or budget < mx):
                    selected = r
                    break
            if selected:
                try:
                    repo.record_hits([selected.get("id")])
                except Exception:
                    pass
                return (selected.get("body") or {}).get("strategy", {}).get("representative_pick", "min_price")
        finally:
            repo.close()
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
    from app.services import requirement_rule_catalog as _rule_catalog
    cfg = config or {}
    ext = ctx.get("ext") or {}
    baselines = ctx.get("baselines") or []
    cfg_pick = cfg.get("representative_pick")
    _rule_types = cfg.get("rule_types") or []
    _type_packages = _rule_catalog.type_packages(_rule_types or None)
    _category_aliases = _rule_catalog.category_aliases(_rule_types or None)
    _spec_rules = _rule_catalog.spec_rules(_rule_types or None)
    _cpu_mem_rules = _rule_catalog.cpu_mem_type_rules(_rule_types or None)
    _capacity_match = _rule_catalog.capacity_match(_rule_types or None)
    _raid_level_rules = _rule_catalog.raid_level_map(_rule_types or None)
    pick = cfg_pick if (cfg_pick and cfg_pick != "auto") else _resolve_budget_strategy(ctx.get("budget"))
    from app.services import semantic_contract as _sc
    _ex_gpu = str((_sc.exclusions(ext) or {}).get("gpu") or "").lower()
    _domestic_only = bool(_sc.is_domestic_only(ext))
    _excl_mfr = set()
    _dom_series = set()
    if _domestic_only:
        _cm = (_rule_catalog.compliance_map(_rule_types or None) or [{}])[0]
        _excl_mfr = {str(x).lower() for x in (_cm.get("excluded_manufacturers") or [])}
        _dom_series = {str(x).lower() for x in (_cm.get("platform_series") or [])}
    kp_by_model: dict = {}
    all_kp: list = []
    for bl in baselines:
        type_cats = kp_categories_for_type(bl.get("server_type_name") or "", _type_packages, ext.get("categories"))
        eff_cats = list(dict.fromkeys(type_cats + (ext.get("categories") or [])))
        _eff_gpu_groups = ext.get("gpu_groups")
        if _ex_gpu in ("none", "self_provided"):
            eff_cats = [c for c in eff_cats if c not in ("GPU", "GPU card", "GPU Card")]
            _eff_gpu_groups = []
        bl_kp = pick_kp_parts(
            eff_cats, ext.get("keywords", []),
            category_aliases=_category_aliases,
            representative_pick=pick,
            spec_rules=_spec_rules,
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
            gpu_groups=_eff_gpu_groups,
            mem_groups=ext.get("mem_groups"),
            platform_series=bl.get("series"),
            drive_spec_substitute=cfg.get("drive_spec_substitute", True),
            default_mem_speed=_base_config_std_mem_speed(bl.get("id")),
            default_mem_channels=bl.get("mem_channels"),
            default_max_dimm=bl.get("max_dimm"),
            cpu_mem_type_rules=_cpu_mem_rules,
            capacity_match=_capacity_match or {"strategy": "tolerance", "tolerance": 10},
            raid_level_rules=_raid_level_rules,
        )
        mid = bl.get("server_model_id") or bl.get("id")
        _bl_kp = bl_kp
        if _excl_mfr:
            _bl_kp = [kp for kp in _bl_kp
                      if str(kp.get("brand") or kp.get("manufacturer") or "").lower() not in _excl_mfr]
        if _dom_series:
            _bs = str(bl.get("series") or "").lower()
            if _bs and _bs not in _dom_series:
                _bl_kp = []
        # 去重（per-机型）：同 pn 因别名分类（Raid Card/Raid card）重复命中 → 保留 qty 最大一条（9361-8i×2 → ×1）
        kp_by_model[mid] = _dedup_kp_by_pn(_bl_kp)
        all_kp.extend(kp_by_model[mid])
    ctx["kp_by_model"] = kp_by_model
    ctx["kp_parts"] = all_kp
    by_category: dict[str, int] = {}
    for kp in all_kp:
        c = kp.get("category") or "其他"
        by_category[c] = by_category.get(c, 0) + 1
    unmatched_count = sum(1 for kp in all_kp if kp.get("unmatched"))
    return {"kp_count": len(all_kp), "by_category": by_category, "unmatched_count": unmatched_count}
