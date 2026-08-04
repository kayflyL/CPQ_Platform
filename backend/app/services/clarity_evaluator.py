"""需求明确度评估器（纯函数，无副作用）。

用 clarity 规则集评估需求明确度，返回 (level, missing_fields, explain)。
- level: explicit / partial / unclear
- missing_fields: 未命中规则要求的缺失字段（供 ask_user 反问）
- explain: {matched_rules, signals} 前端展示 + 未来 LLM 语料

算法可解释、无黑盒：snapshot 信号 → 逐条规则求值 → matched 取 max(weight).level → unmatched 累加 missing。

不依赖 KP spec（库数据稀疏）——只用 ext（jieba 输出）+ budget，spec 校验留给 match_kp 节点。
"""
import re
import logging
from typing import Optional, List, Tuple, Dict, Any

logger = logging.getLogger(__name__)

# 型号 token：含字母且长度>=3 的混合串（EPYC9354 / RTX4090 / DDR5 / H100 等；含单字母+3位数字以匹配 H100/A100/B200）
_MODEL_TOKEN_PATTERN = re.compile(r"^([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[A-Za-z][0-9]{3,})$")

# 型号 token → 品类家族词表（clarity「CPU+GPU 型号双命中→明确」判定的词法分类词表）。
# 数据驱动：权威源 = system_config.model_family_words（可编辑，startup 从 kp 库自动补齐新型号）；
# 以下常量仅为读配置失败时的兜底（与 kp 库常见型号 + 国产卡一致）。
_FALLBACK_FAMILY_WORDS: Dict[str, list] = {
    "CPU": ["epyc", "xeon", "至强", "kh-", "kh50"],
    "GPU": ["h100", "a100", "h200", "h800", "a800", "b200", "b100", "l40", "l20",
            "mi300", "mi250", "mi100", "rtx", "r9700", "w7900", "w7800", "w6600",
            "tesla", "quadro", "radeon", "instinct", "v100", "a30", "a10"],
}


def load_family_words() -> Dict[str, list]:
    """读型号家族词表（system_config.model_family_words），缺失/异常回退常量。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            cfg = repo.get_value("model_family_words")
        finally:
            repo.close()
        if isinstance(cfg, dict) and cfg:
            return {**_FALLBACK_FAMILY_WORDS, **cfg}
    except Exception:
        pass
    return {k: list(v) for k, v in _FALLBACK_FAMILY_WORDS.items()}


def _classify_model_token(tok: str, family_words: Optional[Dict[str, list]] = None) -> set:
    """型号 token → 命中的品类集合（{"CPU","GPU"} 子集）。无匹配返回空集。"""
    t = (tok or "").lower()
    words = family_words if family_words is not None else load_family_words()
    return {cat for cat, kws in words.items() if any(k and k.lower() in t for k in (kws or []))}


def evaluate_clarity(ext: dict, budget: Optional[float], rules: List[dict],
                    family_words: Optional[Dict[str, list]] = None) -> Tuple[str, List[str], dict]:
    """用 clarity 规则集评估需求明确度。

    Args:
        ext: extract 节点输出 {keywords, categories, series, form}
        budget: 预算（None = 未提供）
        rules: clarity 规则列表（每条含 body.signal / body.level / body.missing_if_not / body.weight）

    Returns: (level, missing_fields, explain)
        level ∈ {"explicit", "partial", "unclear"}
    """
    family_words = family_words if family_words is not None else load_family_words()
    signals = _snapshot_signals(ext, budget)
    signals["_family_words"] = family_words  # 型号→品类分类词表（数据驱动，注入求值器）
    matched: List[dict] = []
    unmatched: List[dict] = []
    for r in rules:
        body = r.get("body") or {}
        try:
            if _eval_signal(body.get("signal") or {}, signals):
                matched.append(r)
            else:
                unmatched.append(r)
        except Exception as e:
            logger.warning("clarity 规则求值异常，按 unmatched 处理 rule_id=%s err=%s", r.get("id"), e)
            unmatched.append(r)

    if not matched:
        # 全无 matched：按信号推导真实缺口。
        # 注意：目录驱动引导下「用途」不再是反问字段——类型由客户从真实目录里选（见 catalog_guide），
        # 不再靠关键词猜用途（旧"无用途→不明确"规则已删）。
        missing = []
        if not signals["has_budget"]:
            missing.append("预算")
        if not signals["has_series"]:
            missing.append("系列")
        if not signals["has_form"]:
            missing.append("形态")
        if signals["categories"] and not signals["model_tokens"]:
            missing.append("具体型号")
        if not missing:
            # 标准字段全齐（预算/系列/形态/至少一个具体信号）→ 信息足够出方案
            return "explicit", [], {"matched_rules": [], "signals": signals, "fallback_explicit": True}
        return "partial", missing, {"matched_rules": [], "signals": signals, "fallback": True}

    # 等级优先级：explicit > unclear > partial
    # （最保守判定优先于中间态：避免"无预算"(partial) 压过"无系列无形态"(unclear) 导致漏反问）
    matched_levels = {(r.get("body") or {}).get("level") for r in matched}
    if "explicit" in matched_levels:
        level = "explicit"
    elif "unclear" in matched_levels:
        level = "unclear"
    else:
        level = "partial"

    # missing：从 matched 的非 explicit 规则收集（命中 unclear/partial = 确实缺这些字段）
    missing: List[str] = []
    seen = set()
    for r in matched:
        body = r.get("body") or {}
        if body.get("level") == "explicit":
            continue
        for f in body.get("missing_if_not") or []:
            if f and f not in seen:
                missing.append(f)
                seen.add(f)
    return level, missing, {"matched_rules": [r.get("id") for r in matched], "signals": signals}


def _snapshot_signals(ext: dict, budget: Optional[float]) -> dict:
    keywords = ext.get("keywords") or []
    model_tokens = [k for k in keywords if _MODEL_TOKEN_PATTERN.match(k)]
    usage_inferred = bool(ext.get("usage_inferred"))  # 系统兜底猜的用途（非用户明说）
    has_usage_raw = bool(ext.get("usage"))
    return {
        "_family_words": ext.get("_family_words"),
        "series": ext.get("series"),
        "form": ext.get("form"),
        "has_series": bool(ext.get("series")),
        "has_form": bool(ext.get("form")),
        "usage": ext.get("usage"),
        "has_usage": has_usage_raw and not usage_inferred,  # 用户【明说】的用途（兜底猜的不算）
        "no_usage_inferred": usage_inferred,  # 兼容：是否被系统兜底
        "has_budget": budget is not None and float(budget) > 0,
        "budget": budget,
        "categories": ext.get("categories") or [],
        "category_count": len(ext.get("categories") or []),
        "keywords": keywords,
        "keyword_count": len(keywords),
        "model_tokens": model_tokens,
        "model_token_count": len(model_tokens),
        "has_memory_capacity": bool(ext.get("mem_signal")),  # extract 解析到内存容量信号
    }


def _eval_signal(sig: dict, s: dict) -> bool:
    t = sig.get("type")
    if t == "combined":
        return all(_eval_signal(sub, s) for sub in sig.get("rules") or [])
    if t == "model_token_count":
        return _cmp(s["model_token_count"], sig.get("op", ">="), sig.get("value", 1))
    if t == "category_count":
        return _cmp(s["category_count"], sig.get("op", ">="), sig.get("value", 1))
    if t == "has_budget":
        return s["has_budget"] == sig.get("value", True)
    if t == "no_budget":
        return not s["has_budget"]
    if t == "has_usage":
        return s["has_usage"] == sig.get("value", True)
    if t == "no_usage":
        return not s["has_usage"]
    if t == "series_and_form":
        return s["has_series"] and s["has_form"]
    if t == "no_series_no_form":
        return not s["has_series"] and not s["has_form"]
    if t == "model_token_in_category":
        # 按型号→品类家族词表归类（词表数据驱动：system_config.model_family_words + kp 库自动补齐）
        cat = (sig.get("category") or "").strip().upper()
        fw = s.get("_family_words") or {}
        n = sum(1 for tok in s["model_tokens"] if cat in _classify_model_token(tok, fw))
        return n >= sig.get("min", 1)
    if t == "no_model_in_category":
        # 镜像信号：提到了某品类(在 categories 里)却没给该品类的具体型号 → 适合追问型号
        cat = (sig.get("category") or "").strip().upper()
        cat_present = any(cat and cat.lower() == (c or "").lower() for c in s["categories"])
        fw = s.get("_family_words") or {}
        has_model = any(cat in _classify_model_token(tok, fw) for tok in s["model_tokens"])
        return cat_present and not has_model
    if t == "has_memory_capacity":
        return s["has_memory_capacity"] == sig.get("value", True)
    if t == "no_memory_capacity":
        return not s["has_memory_capacity"]
    logger.warning("未知 signal type: %s", t)
    return False


def _cmp(a, op, b) -> bool:
    try:
        if op == ">=": return a >= b
        if op == ">":  return a > b
        if op == "<=": return a <= b
        if op == "<":  return a < b
        if op in ("=", "=="): return a == b
    except TypeError:
        return False
    return False


# ============================================================
# 槽位覆盖度（2026-08-04 流程重构）：明确度 = 已填槽位 vs 期望清单差距
# 期望清单（requirement_slots）可配置：L0 底线 / L1 重要 / L2 系统推导。
# 替代旧"信号规则猜明确度"——缺多少、缺什么，直接可解释。
# ============================================================

DEFAULT_REQUIREMENT_SLOTS: dict = {
    "version": 1,
    "ask_threshold": 2,  # L0 缺 ≥ N 项 → 反问补全
    "slots": [
        {"key": "scene", "label": "应用场景", "level": "L0"},
        {"key": "series", "label": "所属系列", "level": "L0"},
        {"key": "cpu", "label": "CPU", "level": "L0"},
        {"key": "memory", "label": "内存", "level": "L0"},
        {"key": "storage", "label": "存储", "level": "L0", "default_ok": True},
        {"key": "form", "label": "机箱形态", "level": "L1"},
        {"key": "gpu", "label": "GPU", "level": "L1"},
        {"key": "nic", "label": "网卡", "level": "L1"},
        {"key": "raid", "label": "阵列卡", "level": "L2"},
        {"key": "psu", "label": "电源", "level": "L2"},
    ],
}


def load_requirement_slots() -> dict:
    """读期望槽位清单（system_config.requirement_slots，可配置）；缺失/异常回退默认。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            cfg = repo.get_value("requirement_slots")
        finally:
            repo.close()
        if isinstance(cfg, dict) and cfg.get("slots"):
            return cfg
    except Exception:
        pass
    return DEFAULT_REQUIREMENT_SLOTS


def _slot_filled(key: str, ext: dict) -> bool:
    """槽位是否已填（基于 extract 输出的确定性信号）。缺的不填=False。"""
    if not isinstance(ext, dict):
        return False
    cats = [str(c) for c in (ext.get("categories") or [])]
    qty = ext.get("qty_map") or {}
    if key == "scene":
        # 应用场景：明说用途/类型，或强信号可确定（GPU→AI、存储词→存储）
        if ext.get("usage") or ext.get("server_type_name"):
            return True
        if ext.get("gpu_groups"):
            return True
        low = " ".join(str(k) for k in (ext.get("keywords") or [])).lower()
        if any(w in low for w in ("存储", "nas", "数据库", "ai", "训练", "推理", "大模型", "gpu")):
            return True
        return False
    if key == "series":
        return bool(ext.get("series"))
    if key == "cpu":
        return bool(ext.get("cpu_signal")) or bool(qty.get("CPU")) or "CPU" in cats
    if key == "memory":
        return bool(ext.get("mem_signal")) or bool(ext.get("mem_groups")) or bool(qty.get("Memory")) or "Memory" in cats
    if key == "storage":
        return bool(ext.get("drive_groups")) or bool(qty.get("HDD/SSD")) or "HDD/SSD" in cats
    if key == "form":
        return bool(ext.get("form"))
    if key == "gpu":
        return bool(ext.get("gpu_groups")) or bool(qty.get("GPU"))
    if key == "nic":
        return bool(ext.get("multi_spec_filters") and ext["multi_spec_filters"].get("Network(NIC) requirement")) \
            or "Network(NIC) requirement" in cats
    if key == "raid":
        return bool(ext.get("raid_groups")) or "Raid card" in cats or "阵列" in " ".join(cats)
    if key == "psu":
        return bool(ext.get("psu_signal"))
    return False


def evaluate_slot_coverage(ext: dict, config: Optional[dict] = None) -> tuple:
    """槽位覆盖度主判据 → (level, missing_slots, explain)。

    level ∈ {"explicit", "partial"}：
      • L0 缺 ≥ ask_threshold 项 → partial（反问，missing 列缺的槽位）；
      • AI 场景（有 GPU 信号）缺 GPU → partial（ai_gpu_required，R28 口径）；
      • storage default_ok → 缺存储不计数（系统给默认盘）；
      • 其余（L1/L2 缺）→ explicit（场景分析/系统推导补），不反问。
    explain 带 coverage 明细（白盒：每个槽位 已填/缺失）。
    """
    cfg = load_requirement_slots() if config is None else config
    slots = cfg.get("slots") or DEFAULT_REQUIREMENT_SLOTS["slots"]
    ask_threshold = int(cfg.get("ask_threshold") or 2)

    detail = []
    missing_l0 = []
    ai_scene = bool(ext.get("gpu_groups")) or bool((ext.get("qty_map") or {}).get("GPU"))
    for s in slots:
        key = s.get("key")
        filled = _slot_filled(key, ext)
        default_ok = bool(s.get("default_ok"))
        if not filled and not default_ok:
            detail.append({"key": key, "label": s.get("label") or key, "level": s.get("level"), "filled": False})
            if s.get("level") == "L0":
                missing_l0.append(s.get("label") or key)
        else:
            detail.append({"key": key, "label": s.get("label") or key, "level": s.get("level"), "filled": filled})

    explain = {
        "coverage": f"{sum(1 for d in detail if d['filled'])}/{len(detail)}",
        "slots": detail,
        "missing_l0": missing_l0,
        "ask_threshold": ask_threshold,
    }
    if len(missing_l0) >= ask_threshold:
        return "partial", missing_l0, explain
    if ai_scene and not _slot_filled("gpu", ext):
        explain["ai_gpu_required"] = True
        return "partial", ["GPU"], explain
    return "explicit", [], explain
