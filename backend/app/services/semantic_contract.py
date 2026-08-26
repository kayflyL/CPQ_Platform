"""需求语义契约读取器（配置驱动，无业务硬编码）。

契约定义在 system_config.semantic_contract：
- container_key：语义层存放的 ext 子对象键（如 "semantic"）。
- dimensions：维度定义（intent/exclusions/compliance/workload ...），
  每个维度含 key/label/kind/values/fields 等，全部可配。

代码只通过本模块读取契约，不在业务代码里写死维度名、取值枚举或映射。
"""
from __future__ import annotations
from typing import Any, Optional


def _load_contract() -> dict:
    try:
        from app.repository.system_config_repo import SystemConfigRepository
        repo = SystemConfigRepository()
        try:
            raw = repo.get_value("semantic_contract", {})
        finally:
            repo.close()
        if isinstance(raw, dict) and raw:
            return raw
    except Exception:
        pass
    return {}


def container_key() -> str:
    """语义层在 ext 里的子对象键（可配，默认语义命名空间）。"""
    return str(_load_contract().get("container_key") or "semantic")


def dimensions() -> list[dict]:
    return list(_load_contract().get("dimensions") or [])


def dimension_key(logical: str) -> str:
    """按逻辑名返回契约里配置的字段 key；未配置时回退逻辑名。"""
    for d in dimensions():
        if (d.get("key") or "") == logical or (d.get("logical") or "") == logical:
            return str(d.get("key") or logical)
    return str(logical)


def get(ext: dict, logical: str, default: Any = None) -> Any:
    """读 ext 里某语义维度（可配 key）。"""
    ext = ext or {}
    container = ext.get(container_key())
    if not isinstance(container, dict):
        return default
    return container.get(dimension_key(logical), default)


def set_value(ext: dict, logical: str, value: Any) -> None:
    """写 ext 里某语义维度（可配 key）。"""
    ext = ext or {}
    ck = container_key()
    container = ext.get(ck)
    if not isinstance(container, dict):
        container = {}
        ext[ck] = container
    container[dimension_key(logical)] = value


def merge(ext: dict, semantic: Optional[dict]) -> None:
    """把 agent 吐出的 semantic 对象合并进 ext（只保留契约允许的维度名）。"""
    if not isinstance(semantic, dict):
        return
    allowed = {dimension_key(d.get("key")) for d in dimensions() if d.get("key")}
    ck = container_key()
    container = ext.get(ck)
    if not isinstance(container, dict):
        container = {}
        ext[ck] = container
    for k, v in semantic.items():
        if k in allowed or k in {d.get("key") for d in dimensions()}:
            container[k] = v


def exclusions(ext: dict) -> dict:
    v = get(ext, "exclusions")
    return dict(v) if isinstance(v, dict) else {}


def compliance(ext: dict) -> dict:
    v = get(ext, "compliance")
    return dict(v) if isinstance(v, dict) else {}


def workload(ext: dict) -> dict:
    v = get(ext, "workload")
    return dict(v) if isinstance(v, dict) else {}


def intent(ext: dict) -> Optional[str]:
    v = get(ext, "intent")
    return str(v).strip() if v else None


def is_domestic_only(ext: dict) -> bool:
    return bool(compliance(ext).get("domestic_only"))


def exclusion_status(ext: dict, slot_key: str) -> Optional[str]:
    """返回某部件槽位的排除状态：none / self_provided / None。
    若槽位不在契约 value_keys 允许范围内，忽略。"""
    ex = exclusions(ext)
    # 允许的排除键来自契约，避免读未定义键。
    allow = set()
    for d in dimensions():
        if (d.get("key") or "") == "exclusions" or (d.get("logical") or "") == "exclusions":
            allow = set(d.get("value_keys") or [])
    if allow and slot_key not in allow:
        return None
    val = ex.get(slot_key)
    return str(val).strip().lower() if val else None


def absent_confirmed(ext: dict, slot_key: str) -> bool:
    """该槽位是否被明确标记为「无 / 自购」（视为已确认，不再追问、不列入 BOM 供件）。"""
    s = exclusion_status(ext, slot_key)
    return s in ("none", "self_provided")


def _type_blob(ext: dict) -> str:
    typ = str(ext.get("server_type_name") or ext.get("server_type") or "").lower()
    it = (intent(ext) or "").lower()
    return (typ + " " + it).strip()


def is_slot_required(ext: dict, spec_item: dict) -> bool:
    """某 allow_absent 槽位在当前类型/意图下是否必问。

    required_by_type 规则（配置可写死）：{type_key: true/false}。
    - 命中 true 键 → 必问；命中 false 键 → 不必问。
    - 无命中 → 回退槽位自身 required 标志（GPU/NIC 默认 False = 可空，不追问）。
    """
    if not isinstance(spec_item, dict):
        return True
    rbt = spec_item.get("required_by_type")
    if not isinstance(rbt, dict) or not rbt:
        return bool(spec_item.get("required", False))
    blob = _type_blob(ext)
    compact = blob.replace(" ", "").replace("-", "")
    matched = []
    for k, v in rbt.items():
        k = str(k).lower()
        if k in blob or k.replace("_", "") in compact:
            matched.append((k, bool(v)))
    if matched:
        # 命中任一 false → 不必问（如国产化明确排除外卡）；否则命中 true → 必问。
        if any(v is False for _, v in matched):
            return False
        return any(v is True for _, v in matched)
    return bool(spec_item.get("required", False))


def schema() -> dict:
    """把语义契约 dimensions 转成 clean_by_schema 可用的 JSON schema。

    纯配置驱动：维度 kind = single_enum → enum 字符串；map → 对象（子字段可字段）；
    group/struct → 对象（子字段按 type/enum）。用于对模型输出的 semantic 子对象做输出格式收口：
    非法类型/未知字段/非法枚举一律丢弃，不让自由文本污染结构化字段。
    """
    props = {}
    for d in dimensions():
        key = d.get("key")
        if not key:
            continue
        kind = d.get("kind")
        if kind == "single_enum":
            props[key] = {"type": "string", "enum": list(d.get("values") or [])}
        elif kind == "map":
            sub = {}
            for vk in (d.get("value_keys") or []):
                ve = list(d.get("value_enum") or [])
                # value_enum 只含 true/false 语义的开关位 → 以 boolean 收口（模型用 true/false 表达）
                if ve and all(str(x).strip().lower() in ("true", "false") for x in ve):
                    sub[vk] = {"type": "boolean"}
                else:
                    sub[vk] = {"type": "string", "enum": ve} if ve else {"type": "string"}
            props[key] = {"type": "object", "properties": sub}
        elif kind in ("group", "struct"):
            sub = {}
            for f in (d.get("fields") or []):
                fk = f.get("key")
                if not fk:
                    continue
                if f.get("enum"):
                    sub[fk] = {"type": "string", "enum": list(f.get("enum"))}
                else:
                    sub[fk] = {"type": f.get("type") or "string"}
            props[key] = {"type": "object", "properties": sub}
        else:
            props[key] = {"type": "object"}
    return {"type": "object", "properties": props}
