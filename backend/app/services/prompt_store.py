"""统一提示词（话术）存储 —— 需求分析各节点的用户提示词不再混在执行逻辑里。

默认值放在本目录 reasoning_prompt_defaults.json，启动时 seed 进
system_config.reasoning_prompts；节点编辑后从 system_config 覆盖读取，
执行逻辑只从本模块取「默认/用户覆盖」，capabilities.py 等文件不再硬编码提示词。

对外：load_reasoning_prompts()、get_prompt_defaults(node)、merge_node_prompt(node, config)。
"""
import json
import time
from pathlib import Path
from typing import Any, Optional

_DEFAULTS_PATH = Path(__file__).with_name("reasoning_prompt_defaults.json")
_TTL_SECONDS = 5.0
_CACHE: dict = {"ts": 0.0, "value": {}}

_PARSE_KEYS = {
    "kp_reason": ("system_prompt", "user_prompt_template"),
    "model_reason": ("system_prompt",),
    "orchestrator": ("system_prompt",),
}


def _fill(cfg: dict, key: str, default: Any) -> None:
    """仅在缺失或空值时用默认值补齐（避免旧节点已存空串导致回显仍空白）。"""
    val = cfg.get(key)
    if val is None or (isinstance(val, str) and not val.strip()):
        cfg[key] = default
    elif isinstance(val, list) and not val:
        cfg[key] = default


def _seed_file() -> dict:
    """种子默认值（打包文件）。仅作 DB 缺失时的兜底；DB 一旦写入即以其为准。"""
    try:
        return json.loads(_DEFAULTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _db_value() -> dict:
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            value = repo.get_value("reasoning_prompts", {})
        finally:
            repo.close()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def load_reasoning_prompts() -> dict:
    """生效提示词配置：system_config.reasoning_prompts 优先，缺失回退种子文件。"""
    now = time.time()
    if now - _CACHE["ts"] < _TTL_SECONDS:
        return _CACHE["value"]
    value = _db_value()
    if not value:
        value = _seed_file()
    _CACHE["ts"] = now
    _CACHE["value"] = value if isinstance(value, dict) else {}
    return _CACHE["value"]


def _migrate_agent_fill(raw: dict, node: str = "agent_fill") -> dict:
    """旧版碎片字段（tone/intent/fallback_text）迁移为 agent_fill 新 Prompt 结构。

    旧结构含 intent/tone/fallback_text 标志 → 整体替换为文件默认；新结构仅保留用户对
    system_prompt 的覆盖。
    """
    seed = (_seed_file().get(node) or {})
    if not seed:
        return raw
    if ("intent" in raw) or ("tone" in raw) or ("fallback_text" in raw):
        return dict(seed)
    out = dict(seed)
    for k in ("system_prompt",):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v
    return out


def get_prompt_defaults(node: str) -> dict:
    """某节点的提示词默认/用户覆盖 dict（只含提示形态字段）。"""
    raw = load_reasoning_prompts().get(node)
    raw = dict(raw) if isinstance(raw, dict) else {}
    if node == "agent_fill":
        raw = _migrate_agent_fill(raw, node)
    return raw


def merge_node_prompt(node: str, config: Optional[dict]) -> dict:
    """把当前节点的提示词默认值合并进 config（只填空缺字段，不覆盖用户已写值）。

    用途：reasoning_flow 读取时回显，以及 capabilities 归一化时取默认。调用方可用
    返回的 config 直接进入执行链路；用户编辑后存储的 config 仍是它的覆盖值子集。
    """
    cfg = dict(config or {})
    d = get_prompt_defaults(node)
    if node == "agent_fill":
        prompt = dict(cfg.get("prompt") or {})
        _fill(prompt, "system_prompt", str(d.get("system_prompt", "")))
        cfg["prompt"] = prompt
    else:
        for key in _PARSE_KEYS.get(node, ()):
            _fill(cfg, key, d.get(key, ""))
    return cfg


def seed_defaults() -> None:
    """system_config.reasoning_prompts 缺失时写入种子默认值（幂等，不覆盖用户编辑）。"""
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            existing = repo.get_value("reasoning_prompts", None)
            if existing is None:
                repo.set("reasoning_prompts", _seed_file(), type="json",
                         description="需求分析节点提示词/话术默认值（用户可在节点抽屉覆盖）",
                         operator="system")
        finally:
            repo.close()
    except Exception:
        pass


def invalidate_cache() -> None:
    """写入/清理提示词配置后调用，强制下次读取重新加载。"""
    _CACHE["ts"] = 0.0
