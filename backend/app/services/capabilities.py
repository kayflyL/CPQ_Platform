"""需求分析 skill 的能力/契约辅助层。

- 只负责：需求抽槽、字段契约、规则检索、确定性组装输入。
- 不做：固定选料兜底、节点内独立 ReAct、模型/配件决策。
- 决策由 AI 角色主循环完成；工具（select_models/select_parts）负责事实落地。
"""
import logging
from typing import Any, Optional

from app.services.slot_contract import canonical_get, canonical_key, canonical_set

logger = logging.getLogger(__name__)


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

def _ground_fill_from_tools(answer: str, tool_calls_log: list, ext: dict,
                            config: dict, req_text: str) -> None:
    """模型未给 fill 时，用 agent 已调工具返回的真实目录候选落地机型，再反推系列/形态/类型。"""
    ans = str(answer or "")
    cands: dict = {}
    for call in (tool_calls_log or []):
        if not isinstance(call, dict) or call.get("name") not in ("select_models",):
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
    # GPU 卡数唯一真值源 = ext.gpu；此处只用规则库 workload_map 的数值做归一，
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
    # GPU 卡数只落 gpu（模型 semantic / 规则 workload_map 的卡数统一在此归一）。
    if rule_gpu_count > 0 and not _sc.absent_confirmed(ext, "gpu") and not ext.get("gpu"):
        ext["gpu"] = [{"qty": rule_gpu_count}]

def _apply_domestic_by_cpu(ext: dict, config: Optional[dict] = None) -> list:
    """确定性规则：登记到的 CPU 是国产 → 产品=国产化/信创（compliance.domestic_only）。词表来自规则库 compliance_map。"""
    from app.services import semantic_contract as _sc
    from app.services import requirement_rule_catalog as _rc
    rule_types = (config or {}).get("rule_types")
    cpu = ext.get("cpu") if isinstance(ext.get("cpu"), dict) else {}
    cpu_text = " ".join(str(cpu.get(k) or "") for k in ("model", "brand")).lower()
    if not cpu_text and isinstance(ext.get("cpu"), dict):
        cpu_text = str((ext.get("cpu") or {}).get("model") or "").lower()
    if not cpu_text:
        return []
    kws = _rc.domestic_cpu_keywords(rule_types)
    if not any(k and k in cpu_text for k in kws if k):
        return []
    comp = dict(_sc.compliance(ext))
    changed: list = []
    if not comp.get("domestic_only"):
        comp["domestic_only"] = True
        _sc.set_value(ext, "compliance", comp)
        changed.append("compliance.domestic_only=True(国产CPU)")
    if _sc.intent(ext) in (None, "general"):
        _sc.set_value(ext, "intent", "domestic_compliance")
        changed.append("intent=domestic_compliance")
    return changed

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


AGENT_FILL_FINAL_CONTRACT = (
    "\n\n【输出要求】只输出一个 JSON 对象，不要 Markdown 代码块，不要调用任何工具，不要分步。"
    "基于客户原话与下方《在售目录参考/草稿/缺口》，把客户已明确表达的字段登记为结构化需求。\n"
    "JSON 顶层字段：\n"
    '  - "fill"：对象，只含客户已明确表达的字段（键名用：server_type_name/series/form/purchase_qty/cpu/memory/drives/gpu/nic/raid/psu；采购数量一律用 purchase_qty，禁止 qty/quantity/n 等变体）；客户没提到的不要填。\n'
    '  - "fill" 中配件用结构化对象/数组，不要只写一句话：\n'
    '      cpu{model,cores,tdp_w,qty}、memory{per_stick_gb,qty,type,speed_mt,total_gb}\n'
    '      drives[{capacity,capacity_gb,interface,qty,type,comparison}]：capacity 是带单位的原文容量串（写 "1.92T"/"48T"/"960G"，禁止写纯数字 1.92）；capacity_gb 可选（数字 GB）；type 必填 "SSD" 或 "HDD"（固态→SSD，机械→HDD）；comparison 用 "gte"（≥）/ "lte"（≤）；客户提到硬盘/固态/机械/存储/SSD/HDD 时，必须逐条登记进 drives，不要漏\n'
    '      gpu[{model,qty,capacity_gb}]、nic[{speed_g,ports,qty,with_optical_module}]\n'
    '      raid[{model,qty,cache}]（只给 RAID 级别时用 raid_levels:["0","1","10"]，不要写成 model）\n'
    '      psu{wattage,qty}：电源必须写瓦数 wattage（数字 W）+ 数量 qty；客户提到电源（如 3000W*2）就要登记\n'
    '  - "ask"：字符串。若缺"必填且客户未委托"的关键字段，用一句自然中文只问最关键的那个；已足够则给空字符串。\n'
    '  - "done"：布尔。客户已委托、点名机型、或关键字段足够时为 true，否则 false。\n'
    '  - "edit"：布尔。客户在改口/覆盖之前需求时为 true，否则 false。\n'
    '  - "semantic"：对象。仅当客户提到 workload 时填结构化对象（kind/gpu_count/total_vram_gb 等），不要写成字符串。\n'
    "不得编造客户没说的型号/规格/数量/预算；数值只取客户原话明确给出的。"
    "server_type_name 必须从《在售目录参考》里选（未给出时留空并向客户确认），不要自己造类型名；"
    "内存 speed_mt、盘 interface 与数量、RAID 级别、硬盘容量单位这类规格原样保留客户给出的值，不得改数字/单位。"
)



async def extract_requirement_slots(ctx: dict, config: dict, broadcast=None) -> dict:
    """外层 AI 角色抽槽（方案A）：把用户原话理解成结构化需求槽位。

    仅做一次 LLM 结构化抽取（无工具调用），不负责措辞/节点后续判定。
    结果落进 ctx.ext / ctx.requirement，并返回 {fill, missing_critical, done, ask}。
    这是「AI 角色填表 + 节点纯工具/契约/校验」的填表层。
    """
    from app.services.slot_contract import _missing_critical, slot_label, slot_spec

    config = dict(config or {})
    config["rule_types"] = []
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

    _prompt = config.get("prompt") or {}
    sys_prompt = str(_prompt.get("system_prompt") or "").strip()
    if not sys_prompt:
        from app.services import reasoning_node_contract
        default_prompt = (reasoning_node_contract.node_defaults_seed().get("agent_fill") or {}).get("prompt") or {}
        sys_prompt = str(default_prompt.get("system_prompt") or "").strip()

    if broadcast:
        try:
            await broadcast({"type": "step_progress", "step": "agent_fill", "sub": {"phase": "fill"}})
        except Exception:
            pass

    from app.services.llm_client import chat_json as _chat_json
    user_content = (req_text or "（无需求原文）") + "\n\n" + extra + AGENT_FILL_FINAL_CONTRACT
    try:
        parsed = await _chat_json(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_content},
            ],
            schema=None,
            model=ctx.get("llm_model"),
            temperature=0.0,
            reasoning_effort="low",
            max_tokens=int(config.get("max_tokens") or 8192),
            timeout=float(config.get("llm_timeout") or 90.0),
        )
    except Exception as e:
        return {"ok": False, "error": str(e)[:200], "missing_critical": missing,
                "sufficient": False, "source": "agent_fill"}

    if not isinstance(parsed, dict):
        return {"ok": False, "error": "LLM 返回 JSON 非对象", "missing_critical": missing,
                "sufficient": False, "source": "agent_fill"}
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

    _slot_notes: list = []
    if fill:
        _apply_extracted_slots(ext, fill, allow_overwrite=edit)
        try:
            from app.services.slot_extractor import apply_structured_slots
            _slot_notes = apply_structured_slots(ext, fill, req_text) or []
        except Exception as _e:
            logger.warning("agent_fill 结构化槽位合并失败: %s", _e, exc_info=True)
            _slot_notes = []
    _enrich_agent_semantic(ext, config, req_text)
    _slot_notes.extend(_apply_domestic_by_cpu(ext, config))
    _freeze_requirement(ctx, ext, req_text)
    ctx["ext"] = ext

    new_missing = [m for m in _missing_critical(ext) if m in req_keys and not _slot_now_filled(ext, m)]
    return {
        "ok": True, "source": "agent_fill", "done": done, "ask": ask,
        "fill": fill, "missing_critical": new_missing, "sufficient": not new_missing,
        "delegated": bool((ext.get("semantic") or {}).get("delegated")),
        "audit": _slot_notes,
    }


async def run_agent_fill(ctx: dict, config: dict, broadcast=None, step_id: str = "agent_fill") -> dict:
    """兼容壳（方案A）：节点不再起独立 LLM，委托外层 AI 角色抽槽（extract_requirement_slots）。

    保留签名以兼容既有调用方/测试；理解与措辞已收归外层角色层。
    """
    from app.services.capabilities import extract_requirement_slots
    return await extract_requirement_slots(ctx, config, broadcast)


def _gpu_qty_from_ext(ext: dict) -> int:
    """GPU 卡数唯一真值源：汇总 ext.gpu 的 qty。不读 semantic.workload.gpu_count（已收口删除）。"""
    total = 0
    for g in (ext.get("gpu") or []):
        if isinstance(g, dict):
            try:
                total += int(g.get("qty") or 0)
            except (TypeError, ValueError):
                pass
    return total


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
    # GPU 卡数：唯一真值源 = ext.gpu（需求侧结构化事实）。不再读 semantic.workload.gpu_count，
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
