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
from app.services.slot_contract import canonical_get, canonical_key, canonical_set

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




def _compose_config(config: Optional[dict]) -> dict:
    """归一化 compose 节点配置；配件来源与电源覆盖策略不再写死。"""
    cfg = dict(config or {})
    from app.services import reasoning_node_contract
    defaults = reasoning_node_contract.node_defaults().get("compose", {})
    for key, value in defaults.items():
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
    _st = canonical_get(ext, "server_type")
    if _st:
        parts.append(f"类型={_st}")
    _series = canonical_get(ext, "series")
    if _series:
        parts.append(f"系列={_series}")
    _form = canonical_get(ext, "form")
    if _form:
        parts.append(f"形态={_form}")
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
    rs_groups = ext.get("raid_groups") or []
    _raid_labels = [str(g.get("model") or "/".join(g.get("raid_levels") or []) or "") for g in rs_groups if isinstance(g, dict)]
    if _raid_labels:
        parts.append("RAID=" + "、".join(x for x in _raid_labels if x))
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
            max_iterations=min(int(cfg.get("max_iterations") or 2), 1),
            event_sink=_sink,
            final_only=True,
            final_only_contract=KP_FINAL_CONTRACT,
            llm_timeout=45.0,
            llm_max_attempts=1,
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
    # 默认走规则库：仅当用户明确说了配件诉求（内存/RAID/网卡/电源等）才让 LLM 提议，
    # 否则纯规则由 pick_kp_parts 按类型/形态补齐，避免每次配件选型都等数十秒的 LLM 流式。
    _kp_ext = ctx.get("ext") or {}
    # 只在客户用自然语言提住真正模糊的配件诉求（吐需更多内存/架 raid/万兆网卡）时才让 LLM 提议；
    # 结构化 gpu_groups/mem_groups/raid_groups/drive_groups 等是事实，由 pick_kp_parts 规则直接利用，不再走慢 LLM，避免 GPU/内存场景卡数十秒。
    _need_llm = any(_kp_ext.get(k) for k in ("mem_signal", "psu_signal"))
    if _need_llm:
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




def _kp_config(config: Optional[dict]) -> dict:
    """归一化 kp_reason 节点配置；只暴露业务策略，不再让前端手写 schema/映射黑盒。"""
    cfg = dict(config or {})
    from app.services import reasoning_node_contract
    defaults = reasoning_node_contract.node_defaults().get("kp_reason", {})
    for key, value in defaults.items():
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
    """归一化 agent_fill/model_reason 等节点配置：规则目录可配，不再含反问状态机字段。"""
    cfg = dict(config or {})
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

    confirmed_type = str(canonical_get(ext, "server_type") or "").strip()
    confirmed_series = str(canonical_get(ext, "series") or "").strip() or _infer_series_from_requirement(requirement_text, cfg) or ""
    confirmed_form = str(canonical_get(ext, "form") or "").strip()
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
    """反问回填后判断某 slot 是否已确认（统一走 slot_contract 契约口径，避免重复映射）。"""
    from app.services.slot_contract import _slot_filled
    return _slot_filled(ext, key)




def _infer_series_from_selected_model(ext: dict, whitelist: dict, cfg: dict,
                                      requirement_text: str = "") -> None:
    """机型已选但系列/类型/形态空 → 从 model_meta 反推，避免「机型定了却问系列」。"""
    model = str(ext.get("server_model") or "").strip()
    if not model:
        return
    meta = (whitelist.get("model_meta") or {}).get(model) or {}
    if not canonical_get(ext, "server_type") and meta.get("type"):
        canonical_set(ext, "server_type", meta["type"])
    if not canonical_get(ext, "series") and meta.get("series"):
        canonical_set(ext, "series", meta["series"])
    if not canonical_get(ext, "form") and meta.get("form"):
        canonical_set(ext, "form", meta["form"])


def _confirmed_text(ext: dict) -> str:
    """把已确认的选型要点拼成一行（只做状态展示，不做话术）。"""
    parts = []
    _st = canonical_get(ext, "server_type")
    if _st:
        parts.append(f"服务器类型={_st}")
    _series = canonical_get(ext, "series")
    if _series:
        parts.append(f"平台系列={_series}")
    _form = canonical_get(ext, "form")
    if _form:
        parts.append(f"机箱形态={_form}")
    _model = canonical_get(ext, "server_model")
    if _model:
        parts.append(f"机型={_model}")
    _qty = canonical_get(ext, "purchase_qty")
    if _qty:
        parts.append(f"数量={_qty}")
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
        if canonical_key(key) == "server_type":
            v = str(value).strip()
            if not v:
                continue
            if v.isdigit():
                continue
            if allow_overwrite or not _slot_now_filled(ext, "server_type"):
                canonical_set(ext, "server_type", v)
                changed = True
        elif canonical_key(key) == "series":
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "series"):
                canonical_set(ext, "series", v)
                changed = True
        elif canonical_key(key) == "form":
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "form"):
                canonical_set(ext, "form", v)
                changed = True
        elif canonical_key(key) == "server_model":
            v = str(value).strip()
            if not v:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "server_model"):
                canonical_set(ext, "server_model", v)
                changed = True
        elif canonical_key(key) == "purchase_qty":
            try:
                qty = int(float(value))
            except Exception:
                continue
            if allow_overwrite or not _slot_now_filled(ext, "purchase_qty"):
                canonical_set(ext, "purchase_qty", qty)
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
    if not canonical_get(ext, "server_model"):
        canonical_set(ext, "server_model", name)
    if meta.get("type") and not canonical_get(ext, "server_type"):
        canonical_set(ext, "server_type", meta["type"])
    if meta.get("series") and not canonical_get(ext, "series"):
        canonical_set(ext, "series", meta["series"])
    if meta.get("form") and not canonical_get(ext, "form"):
        canonical_set(ext, "form", meta["form"])
    whitelist = _catalog_whitelist(config, ext=ext, requirement_text=req_text)
    _infer_series_from_selected_model(ext, whitelist, config, requirement_text=req_text)


def _semantic_ref_text(config: Optional[dict], req_text: Optional[str]) -> str:
    """把语义契约参考（workload_map/compliance_map）注入 agent 上下文，供它按规则推断。"""
    from app.services import requirement_rule_catalog as _rc
    rule_types = (config or {}).get("rule_types")
    chunks = []
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
    return "\n\n" + "\n".join(chunks) if chunks else ""


def _enrich_agent_semantic(ext: dict, config: Optional[dict], req_text: Optional[str]) -> None:
    """agent 吐出的语义契约后处理：按规则补齐 workload/国产化/GPU 卡数，不硬编码业务。"""
    from app.services import semantic_contract as _sc
    from app.services import requirement_rule_catalog as _rc
    rule_types = (config or {}).get("rule_types")
    rtext = str(req_text or "").lower()
    # 模型输出的 semantic 已经过 schema 收口，此处作为 advisor；侧重在“事实确定性”。
    # GPU 卡数唯一真值源 = ext.gpu_groups；此处只用规则库 workload_map 的数值做归一，
    # 不再把 semantic.workload.gpu_count 当作第二真值源。
    wl = dict(_sc.workload(ext))
    rule_gpu_count = 0
    # 规则库 workload_map：命中关键词即按规则补意图/显存/卡数（规则赢模型的数值）。
    for r in _rc.workload_map(rule_types):
        kw = str(r.get("workload_keyword") or "").lower()
        if kw and kw in rtext:
            if r.get("intent"):
                wl["kind"] = str(r.get("intent"))
            if r.get("total_vram_gb") is not None and "total_vram_gb" not in wl:
                wl["total_vram_gb"] = r.get("total_vram_gb")
            if r.get("gpu_count") is not None and rule_gpu_count <= 0:
                rule_gpu_count = int(r.get("gpu_count"))
            break
    if wl:
        _sc.set_value(ext, "workload", wl)
        if wl.get("kind") and _sc.intent(ext) in (None, "general"):
            _sc.set_value(ext, "intent", str(wl.get("kind")))
    comp = dict(_sc.compliance(ext))
    if comp.get("domestic_only"):
        if _sc.intent(ext) in (None, "general"):
            _sc.set_value(ext, "intent", "domestic_compliance")
    # GPU 卡数只落 gpu_groups（模型 semantic / 规则 workload_map 的卡数统一在此归一）。
    if rule_gpu_count > 0 and not _sc.absent_confirmed(ext, "gpu") and not ext.get("gpu_groups"):
        ext["gpu_groups"] = [{"qty": rule_gpu_count}]

def _freeze_requirement(ctx: dict, ext: dict, req_text: str = "") -> None:
    """把 agent_fill 落地的需求事实固化为「线索登记表」快照 ctx.requirement。

    下游（机型/KP/组装）只读该快照，绝不回写；后续持久化与运行面板都以它为准。
    机型字段只在客户原话真实点名时才保留（否则从 ext 与快照一并剔除，
    避免 LLM 臆造或下游选型结果污染“原始需求”，也不误导下游当作客户指定机型）。
    """
    import copy as _copy
    import re as _re
    model = str(canonical_get(ext, "server_model") or "").strip()
    if model:
        norm_model = _re.sub(r"\s+", "", model)
        norm_text = _re.sub(r"\s+", "", str(req_text or ""))
        if norm_model not in norm_text:
            ext.pop("server_model", None)
            ext.pop("model", None)
            ext.pop("baseline_model", None)
    ctx["requirement"] = _copy.deepcopy(ext)
    ctx["requirement_text_snapshot"] = str(req_text or "")

def _has_recommend_signal(ext: dict) -> bool:
    """编排层判断：客户是否已给足【机型/机箱/任一硬件】信号，足以让下游给候选，无需再反向补问。
    单独的 server_type_name（类型）不算足够——它只是第一层粗筛，还缺系列/形态/预算等关键字段；
    只有「系列+形态齐全」「点名机型」「已填任一硬件」「用户明确委托」才算足够。这样缺关键字段时
    agent_fill 会继续自然追问，而不是过早下沉出卡。"""
    if not ext:
        return False
    # 类型 + （系列 或 形态 任一）：已能选型，缺的维度由下游 select_models 逐级放宽补齐，
    # 不因缺单个维度在 agent_fill 反复反问（否则给“2U+预算”也会被问缺系列）。
    has_type = bool(canonical_get(ext, "server_type"))
    has_form_or_series = bool(canonical_get(ext, "series") or canonical_get(ext, "form"))
    if has_type and has_form_or_series:
        return True
    # 点名机型：强信号，交给下游按名称确认/找最近似
    if canonical_get(ext, "server_model"):
        return True
    try:
        from app.services.slot_contract import _slot_filled
        return any(_slot_filled(ext, k) for k in ("cpu", "memory", "storage", "gpu",
                                                   "nic", "raid", "psu"))
    except Exception:
        return False


AGENT_FILL_FINAL_CONTRACT = (
    "\n\n【输出要求：只输出一个 JSON 对象，不要 Markdown 代码块，不要调用任何工具，不要分步。"
    "基于客户原话与下方《在售目录参考/草稿/缺口》把客户已明确表达的字段登记为结构化需求\u3002\n"
    "JSON 顶层字段\uff1a\n"
    '  - "fill"\uff1a对象，只含客户已明确表达的字段（键使用给定字段名，如 server_type_name/series/form/cpu/memory/gpu_count），未提到的不要填\u3002\n'
    '  - "ask"\uff1a字符串。若缺“必填且客户未委托”的关键字段，用一句自然中文只问最关键的那个；已足够则给空字符串\u3002\n'
    '  - "done"\uff1a布尔。客户已委托、点名机型、或关键字段足够时为 true，否则 false\u3002\n'
    '  - "edit"\uff1a布尔。客户在改口/覆盖之前需求时为 true，否则 false\u3002\n'
    '  - "semantic"\uff1a对象。仅当客户提到 workload 时填结构化对象（kind/gpu_count/total_vram_gb 等），不要写成字符串\u3002\n'
    "不得编造客户没说的型号/规格/数量/预算；数值只取客户原话明确给出的\u3002"
)


async def extract_requirement_slots(ctx: dict, config: dict, broadcast=None) -> dict:
    """外层 AI 角色抽槽（方案A）：把用户原话理解成结构化需求槽位。

    仅做一次 LLM 结构化抽取（无工具调用），不负责措辞/节点后续判定。
    结果落进 ctx.ext / ctx.requirement，并返回 {fill, missing_critical, done, ask}。
    这是「AI 角色填表 + 节点纯工具/契约/校验」的填表层。
    """
    from app.services.slot_contract import _missing_critical, slot_label, slot_spec
    from app.services import prompt_store
    from app.services.agent_react import run_react_loop
    from app.services.capability_spec import default_tools as _default_tools

    config = prompt_store.merge_node_prompt("agent_fill", config or {})
    if isinstance(config.get("enabled_tools"), list):
        node_tools = [str(t) for t in config.get("enabled_tools") if str(t)]
    else:
        node_tools = list(_default_tools("agent_fill"))
    req_text = str(ctx.get("requirement_text") or ctx.get("normalized_text") or "").strip()
    ext = dict(ctx.get("ext") or {})

    req_keys = {s.get("key") for s in slot_spec() if s.get("src_type") != "kp" and s.get("key") != "server_model"}
    prev_missing = list(ctx.get("missing_fields") or [])
    missing = [m for m in _missing_critical(ext) if m in req_keys and not _slot_now_filled(ext, m)]
    missing_labels = [slot_label(m) for m in missing]

    confirmed_text = _confirmed_text(ext)
    extra = (
        "当前线索登记表草稿：\n" + (confirmed_text or "（尚未填写）") +
        "\n\n还缺（参考，不必按顺序问）：" + ("、".join(missing_labels) or "无") +
        "\n\n任务：只登记客户已明确表达的需求层字段；缺的只反问“必填且未委托”的字段；客户委托（你随便/都行）就留空交下游；客户改口就覆盖草稿。"
    )
    extra += _semantic_ref_text(config, req_text)

    _prompt = config.get("prompt") or {}
    sys_prompt = str(_prompt.get("system_prompt") or "").strip() or str(
        prompt_store.get_prompt_defaults("agent_fill").get("system_prompt") or "")

    async def _sink(ev: dict) -> None:
        if not broadcast:
            return
        try:
            await broadcast({"type": "step_progress", "step": "agent_fill", "sub": ev.get("sub") or {}})
        except Exception:
            pass

    result = await run_react_loop(
        requirement_text=req_text or "（无需求原文）",
        config={**config, "enabled_tools": node_tools},
        system_prompt=sys_prompt,
        history=ctx.get("history") or [],
        extra_context=extra,
        max_iterations=min(int(config.get("max_iterations") or 4), 6),
        event_sink=_sink,
        allowed_tool_ids=ctx.get("allowed_tool_ids"),
        allowed_data_sources=ctx.get("allowed_data_sources"),
        prefer_text_react=True,
        final_only=False,
        final_only_contract=AGENT_FILL_FINAL_CONTRACT,
    )
    raw_answer = result.get("answer") or ""
    agent_answer = raw_answer if isinstance(raw_answer, str) else (
        json.dumps(raw_answer, ensure_ascii=False)
        if isinstance(raw_answer, (dict, list)) else str(raw_answer))
    if not result.get("ok"):
        return {"ok": False, "error": str(result.get("error") or (agent_answer if agent_answer else "需求抽取不可用"))[:200],
                "missing_critical": missing, "sufficient": False, "source": "agent_fill"}

    parsed = agent_answer if isinstance(agent_answer, dict) else _extract_agent_fill_json(agent_answer)
    fill = parsed.get("fill") if isinstance(parsed.get("fill"), dict) else {}
    ask = str(parsed.get("ask") or "").strip()
    done = bool(parsed.get("done", True))
    edit = bool(parsed.get("edit", False))

    from app.services import semantic_contract as _sc
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
    _freeze_requirement(ctx, ext, req_text)
    ctx["ext"] = ext

    new_missing = [m for m in _missing_critical(ext) if m in req_keys and not _slot_now_filled(ext, m)]
    return {
        "ok": True, "source": "agent_fill", "done": done, "ask": ask,
        "fill": fill, "missing_critical": new_missing, "sufficient": not new_missing,
        "delegated": bool((ext.get("semantic") or {}).get("delegated")),
    }


async def run_agent_fill(ctx: dict, config: dict, broadcast=None, step_id: str = "agent_fill") -> dict:
    """兼容壳（方案A）：节点不再起独立 LLM，委托外层 AI 角色抽槽（extract_requirement_slots）。

    保留签名以兼容既有调用方/测试；理解与措辞已收归外层角色层。
    """
    from app.services.capabilities import extract_requirement_slots
    return await extract_requirement_slots(ctx, config, broadcast)


def _gpu_qty_from_ext(ext: dict) -> int:
    """GPU 卡数唯一真值源：汇总 ext.gpu_groups 的 qty。不读 semantic.workload.gpu_count（已收口删除）。"""
    total = 0
    for g in (ext.get("gpu_groups") or []):
        if isinstance(g, dict):
            try:
                total += int(g.get("qty") or 0)
            except (TypeError, ValueError):
                pass
    return total


def _mem_groups_from_signal(mem_signal: Optional[dict]) -> list:
    """从单真值源 mem_signal 确定性派生候选内存组（不写回 ext，避免双真值源）。"""
    if not isinstance(mem_signal, dict):
        return []
    per = mem_signal.get("per_stick_gb")
    try:
        per = int(per) if per is not None else None
    except (TypeError, ValueError):
        per = None
    if not per or not (4 <= per <= 1024):
        return []
    qty = mem_signal.get("qty")
    try:
        qty = int(qty) if qty is not None else 1
    except (TypeError, ValueError):
        qty = 1
    if not (1 <= qty <= 64):
        qty = 1
    group = {"term": f"{per}G", "qty": qty}
    if mem_signal.get("comparison") in ("gte", "lte"):
        group["comparison"] = mem_signal["comparison"]
    return [group]


def filter_models_by_gpu_capacity(baselines: list, gpu_count: int):
    """按 GPU 槽位统一过滤候选机型，唯一能力过滤点（事实源 = base_config.gpu_slots）。

    能装下的机型全部保留；一个都装不下时保留原候选并给每条打 gpu_capacity_note，
    由上层决定是否自动升级/询问，不再静默锁机型。
    """
    if not gpu_count or not baselines:
        return list(baselines or []), []
    _capable = [b for b in baselines
                if int((b.get("base_config") or {}).get("gpu_slots") or 0) >= gpu_count]
    if _capable:
        return _capable, []
    notes = []
    for b in baselines:
        note = f"当前候选机型 GPU 槽位不足 {gpu_count} 卡"
        b.setdefault("gpu_capacity_note", note)
        notes.append(note)
    return list(baselines), notes


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
                  or canonical_get(ext, "server_type"))
    from app.services import semantic_contract as _sc
    from app.services.requirement_rule_catalog import compliance_map as _compliance_map
    _series = scene.get("series") or canonical_get(ext, "series") or None
    _form = scene.get("form") or canonical_get(ext, "form") or None
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
    # GPU 卡数：唯一真值源 = ext.gpu_groups（需求侧结构化事实）。不再读 semantic.workload.gpu_count，
    # 也不再按 gpu_form_map 死区间猜形态；真实槽位能力由 base_config.gpu_slots 在选型后过滤。
    _gpu_count = _gpu_qty_from_ext(ext)
    baselines = select_models(
        canonical_get(ext, "server_type"), _type_name, _series, _form,
        limit=None,
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
                canonical_get(ext, "server_type"), _type_name, _series, _form,
                limit=None,
                no_signal_strategy=_no_signal_strategy,
                variant_signals=build_variant_signals(ext, ctx.get("requirement_text")),
                fallback_order=_fallback_order,
            ) if b.get("series") in _domestic_series]
    # 真实 GPU 槽位能力过滤（事实源 = base_config.gpu_slots，非死区间）：卡数需求>0 时只保留能装下的机型；
    # 一个能装的都没有则保留原候选并白盒标注槽位不足，交下游说明，不静默丢卡。
    if _gpu_count > 0:
        baselines, _gpu_capacity_notes = filter_models_by_gpu_capacity(baselines, _gpu_count)

    _cat_model_id = ctx.get("catalog_model_id")
    if _cat_model_id:
        _keep = [b for b in baselines
                 if b.get("server_model_id") == _cat_model_id or b.get("id") == _cat_model_id]
        if _keep:
            baselines = _keep
    # 每个系列最多保留 N 台（可配），避免“用户说 Orion 却把 Polaris 也一起铺出来”：
    # 收敛只作用于候选展示；确定性匹配精度仍由 match_stage 负责。
    try:
        series_limit = int(cfg.get("series_limit") or 3)
    except (TypeError, ValueError):
        series_limit = 3
    if series_limit > 0 and baselines:
        _seen_series: dict = {}
        _limited = []
        for _b in baselines:
            _s = str(_b.get("series") or "")
            if _seen_series.get(_s, 0) >= series_limit:
                continue
            _seen_series[_s] = _seen_series.get(_s, 0) + 1
            _limited.append(_b)
        baselines = _limited
    ctx["baselines"] = baselines
    ctx["model_reason_cfg"] = {
        "series_limit": series_limit,
        "detail_link_enabled": bool(cfg.get("detail_link_enabled", True)),
        "intro_length": str(cfg.get("intro_length") or "medium"),
        "sort_by": str(cfg.get("sort_by") or "match_stage"),
    }
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
            mem_groups=_mem_groups_from_signal(ext.get("mem_signal")),
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
