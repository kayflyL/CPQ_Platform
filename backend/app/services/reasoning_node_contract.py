"""需求分析节点配置契约（DB-first，无种子文件）。

节点默认值权威源：rules.reasoning_node_default（仅 DB，前端节点抽屉可编辑）。
本模块只负责把「DB 默认值 + 用户覆盖值」合并成生效配置，并在保存时剥掉等于默认值的字段。
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

DEFAULT_SKILL_KEY = "requirement_analysis"


def node_defaults(skill_key: str = DEFAULT_SKILL_KEY) -> dict:
    """需求分析主链节点的默认配置（仅 DB reasoning_node_default；缺失返回空，不回退种子）。"""
    from app.models.base import Rules_SessionLocal
    from app.models.skill_config import ReasoningNodeDefault
    import json
    s = Rules_SessionLocal()
    out: dict = {}
    try:
        rows = s.query(ReasoningNodeDefault).filter(
            ReasoningNodeDefault.skill_key == skill_key
        ).all()
        for r in rows:
            try:
                out[r.node_key] = json.loads(r.config) if r.config else {}
            except Exception:
                out[r.node_key] = {}
    finally:
        s.close()
    return out


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return not value
    return False


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for key, value in (override or {}).items():
        if _is_empty(value):
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def _defaults_for_node(node_key: str) -> dict:
    """节点生效默认值：DB reasoning_node_default 中该节点的配置。"""
    return deepcopy(node_defaults().get(node_key) or {})


def _base_node_key(node_key: str) -> str:
    """兼容 agent_fill_2 这类画布后缀 id，回退到主链节点类型取默认值。"""
    defaults = node_defaults()
    key = str(node_key or "")
    if key in defaults:
        return key
    base = key.rsplit("_", 1)[0]
    return base if base in defaults else key


def effective_config(node_key: str, stored_config: Optional[dict] = None, skill_key: Optional[str] = None) -> dict:
    """返回节点生效配置：DB 默认值 + 用户覆盖值（空值不覆盖默认）。"""
    del skill_key
    base_key = _base_node_key(node_key)
    if base_key not in node_defaults():
        return deepcopy(stored_config or {})
    base = _defaults_for_node(base_key)
    return _merge(base, stored_config or {})


def override_only(node_key: str, config: dict, skill_key: Optional[str] = None) -> dict:
    """保存前把等于默认值或空值的字段剥掉，只留用户真正改过的覆盖值。"""
    del skill_key
    base_key = _base_node_key(node_key)
    defaults = _defaults_for_node(base_key) if base_key in node_defaults() else {}
    out: dict = {}
    for key, value in (config or {}).items():
        if _is_empty(value):
            continue
        if _values_equal(value, defaults.get(key)):
            continue
        out[key] = deepcopy(value)
    return out


def _values_equal(left: Any, right: Any) -> bool:
    try:
        return left == right
    except Exception:
        return False
