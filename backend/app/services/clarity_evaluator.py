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

# 型号 token：含字母且长度>=3 的混合串（EPYC9354 / RTX4090 / DDR5 等）
_MODEL_TOKEN_PATTERN = re.compile(r"^[A-Za-z]{2,}[0-9A-Za-z\-]{2,}$")


def evaluate_clarity(ext: dict, budget: Optional[float], rules: List[dict]) -> Tuple[str, List[str], dict]:
    """用 clarity 规则集评估需求明确度。

    Args:
        ext: extract 节点输出 {keywords, categories, series, form}
        budget: 预算（None = 未提供）
        rules: clarity 规则列表（每条含 body.signal / body.level / body.missing_if_not / body.weight）

    Returns: (level, missing_fields, explain)
        level ∈ {"explicit", "partial", "unclear"}
    """
    signals = _snapshot_signals(ext, budget)
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
        # 全无 matched：兜底 partial
        return "partial", ["需求描述不够具体"], {"matched_rules": [], "signals": signals}

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
    return {
        "series": ext.get("series"),
        "form": ext.get("form"),
        "has_series": bool(ext.get("series")),
        "has_form": bool(ext.get("form")),
        "usage": ext.get("usage"),
        "has_usage": bool(ext.get("usage")),
        "has_budget": budget is not None and float(budget) > 0,
        "budget": budget,
        "categories": ext.get("categories") or [],
        "category_count": len(ext.get("categories") or []),
        "keywords": keywords,
        "keyword_count": len(keywords),
        "model_tokens": model_tokens,
        "model_token_count": len(model_tokens),
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
        # MVP：model_tokens 中任意一个含品类相关字样即算命中（未来可查 KP spec 库精准分类）
        cat = sig.get("category", "")
        n = sum(1 for tok in s["model_tokens"] if cat.lower() in tok.lower())
        return n >= sig.get("min", 1)
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
