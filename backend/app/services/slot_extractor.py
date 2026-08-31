"""配件多槽落位：把结构化配件槽位（agent_fill LLM 契约输出 / 选项结构化直传载荷）
合并进 ext。

与理解节点共用 llm_extract_enhance.merge_into_ext，保证「一句话能抽多槽」口径一致。
本模块只做类型守卫与容量单位换算——**不做任何自然语言解析**：语义理解归理解通道
（LLM），选项点击归结构化直传（option.signal）。字符串形态的信号槽由理解通道（LLM）负责结构化；本模块只处理已结构化的载荷。
"""
from __future__ import annotations

import re
from typing import Any

_STRUCTURED_KEYS = {"cpu", "memory", "drives", "storage", "gpu", "nic", "raid", "psu"}


def _parse_gb(text: str) -> int | None:
    """从容量/容量描述抽出 GB 数值（1T 按 1024G；支持 1.92T 小数盘容）。单位换算，非词表。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*(G|GB|T|TB)", (text or "").upper())
    if not m:
        return None
    val = float(m.group(1))
    if m.group(2) in ("T", "TB"):
        val *= 1024
    val = int(round(val))
    return val if 1 <= val <= 65536 else None


def _as_dicts(value: Any) -> list[dict]:
    """类型守卫：只收对象形态；字符串/标量不解析（语义归 LLM/选项直传），直接丢弃。"""
    if isinstance(value, list):
        return [x for x in value[:16] if isinstance(x, dict)]
    return [value] if isinstance(value, dict) else []


def apply_structured_slots(ext: dict, slots: dict, requirement_text: str = "") -> list:
    """把结构化配件槽位（对象/数组形态）合并进 ext，返回变更说明。

    ext 只存一张契约表（cpu/memory/drives/gpu/nic/raid/psu），不再有第二套信号键名。
    """
    if not isinstance(slots, dict):
        return []
    from app.services.llm_extract_enhance import merge_into_ext

    notes: list = []
    # 逐组问的跳过登记（「先跳过这组」逃生项）：数组形态直传，非配件信号不入槽位合并
    if isinstance(slots.get("scenario_skips"), list):
        pre = [str(s).strip() for s in (ext.get("scenario_skips") or []) if str(s).strip()]
        merged = list(pre)
        for s in slots["scenario_skips"]:
            v = str(s).strip()
            if v and v not in merged:
                merged.append(v)
        if merged != pre:
            notes.append("scenario_skips=" + ",".join(merged))
        ext["scenario_skips"] = merged

    cleaned: dict[str, Any] = {}
    for key in _STRUCTURED_KEYS:
        if key not in slots:
            continue
        val = _as_dicts(slots[key])
        if not val:
            continue
        cleaned[key] = val if key in ("drives", "storage", "gpu", "nic", "raid") else val[0]
    # storage 别名 → drives（merge_into_ext 认 drives）
    if "storage" in cleaned and "drives" not in cleaned:
        cleaned["drives"] = cleaned.pop("storage")
    if not cleaned:
        return notes
    return notes + merge_into_ext(ext, cleaned, requirement_text or "")
