"""需求分析节点配置契约（DB-first）。

节点默认值权威源：system_config.reasoning_node_defaults（缺失时回退
reasoning_node_defaults.json 种子）。提示词/话术默认值来自
system_config.reasoning_prompts；规则词表默认值来自 rules.requirement_rules。
本模块只负责把「默认值 + 用户覆盖值」合并成生效配置，并在保存时剥掉等于默认值的字段。
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional


_SEED_PATH = Path(__file__).with_name("reasoning_node_defaults.json")

MODEL_REASON_PROMPT_KEYS = (
    "candidate_lede",
    "choice_lede",
    "no_exact_lede",
    "no_match_question",
)


def _load_seed() -> dict:
    try:
        return json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _db_value(key: str) -> Any:
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            return repo.get_value(key, None)
        finally:
            repo.close()
    except Exception:
        return None


def _node_defaults_from_value(value: Any) -> dict:
    if not isinstance(value, dict):
        return {}
    nodes = value.get("requirement_analysis")
    if isinstance(nodes, dict):
        return deepcopy(nodes)
    if value.get("nodes") and isinstance(value["nodes"], dict):
        return deepcopy(value["nodes"])
    return deepcopy(value)


def node_defaults() -> dict:
    """需求分析主链节点的默认配置（DB 优先，种子兜底）。"""
    value = _db_value("reasoning_node_defaults")
    if value is not None:
        return _node_defaults_from_value(value)
    seed = _load_seed()
    return _node_defaults_from_value(seed)


def node_defaults_seed() -> dict:
    """直接从打包种子读取需求分析主链节点默认配置（不读 DB）。"""
    return _node_defaults_from_value(_load_seed())


def _prompt_defaults(node_key: str) -> dict:
    try:
        from app.services import prompt_store
        return dict(prompt_store.get_prompt_defaults(node_key) or {})
    except Exception:
        return {}


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
    defaults = node_defaults()
    base = dict(defaults.get(node_key) or {})
    if node_key == "agent_fill":
        prompt_defaults = _prompt_defaults("agent_fill")
        base.setdefault("prompt", {})
        base["prompt"] = _merge(base["prompt"], {"system_prompt": prompt_defaults.get("system_prompt", "")})
    elif node_key == "kp_reason":
        prompt_defaults = _prompt_defaults("kp_reason")
        if prompt_defaults.get("system_prompt"):
            base["system_prompt"] = prompt_defaults["system_prompt"]
        if prompt_defaults.get("user_prompt_template"):
            base["user_prompt_template"] = prompt_defaults["user_prompt_template"]
    elif node_key == "model_reason":
        prompt_defaults = _prompt_defaults("model_reason")
        for key in MODEL_REASON_PROMPT_KEYS:
            if prompt_defaults.get(key):
                base[key] = prompt_defaults[key]
    return base


def _base_node_key(node_key: str) -> str:
    """兼容 agent_fill_2 这类画布后缀 id，回退到主链节点类型取默认值。"""
    defaults = node_defaults()
    key = str(node_key or "")
    if key in defaults:
        return key
    base = key.rsplit("_", 1)[0]
    return base if base in defaults else key


def effective_config(node_key: str, stored_config: Optional[dict] = None, skill_key: Optional[str] = None) -> dict:
    """返回节点生效配置：默认值 + 用户覆盖值（空值不覆盖默认）。"""
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
