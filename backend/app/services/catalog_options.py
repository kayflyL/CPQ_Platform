# -*- coding: utf-8 -*-
"""需求分析 Skill 的目录候选与 agent_fill 契约选项源。

这里只提供业务事实（在售目录白名单、填表下拉选项）和 agent_fill JSON 契约；
不调用 LLM，不做模型/配件决策。目录白名单是场景/系列/形态选项的唯一来源。
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services.slot_contract import canonical_get

logger = logging.getLogger(__name__)


def catalog_whitelist(config: Optional[dict] = None, ext: Optional[dict] = None,
                      requirement_text: str = "") -> dict:
    """从在售目录构建与已确认字段一致的候选白名单。

    保留机型与类型/系列/形态的关联（model_meta），后续选项过滤只在此受限集合内进行。
    """
    del config, requirement_text
    ext = ext or {}
    out: dict = {"types": [], "series": [], "forms": [], "models": [], "model_meta": {}}
    try:
        from app.services.catalog_guide import load_catalog
        types, models_by_type = load_catalog()
    except Exception as e:
        logger.warning("读反问候选目录失败: %s", e)
        return out

    confirmed_type = str(canonical_get(ext, "server_type") or "").strip()
    confirmed_series = str(canonical_get(ext, "series") or "").strip()
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


def fill_dropdown_options() -> dict:
    """填表契约的动态下拉选项（类型/系列/形态/KP 大类），实时取自在售目录与规范大类，不硬编码。"""
    wl = catalog_whitelist({}, {}, "")

    def _lines(key: str) -> str:
        vals = [str(v).strip() for v in (wl.get(key) or []) if str(v).strip()]
        return chr(10).join("      - " + v for v in vals) or "      （暂无）"

    kp = []
    try:
        from app.services.requirement_slots import _load_kp_categories
        kp = [str(c).strip() for c in (_load_kp_categories() or []) if str(c).strip()]
    except Exception:
        kp = []
    return {
        "SERVER_TYPE": _lines("types"),
        "SERIES": _lines("series"),
        "FORM": _lines("forms"),
        "KP_CATEGORIES": "、".join(kp) if kp else "（暂无）",
    }