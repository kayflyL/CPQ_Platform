"""配件多槽抽取/归一化：把 agent_fill LLM 输出的结构化配件槽位落进 ext。

与理解节点共用 llm_extract_enhance.merge_into_ext，保证「一句话能抽多槽」在理解/反问两条路
口径一致。代码不做关键词意图判断，只做最小收敛（字符串→对象/数组）与范围校验，语义由 LLM 负责。
"""
from __future__ import annotations

import re
from typing import Any


_STRUCTURED_KEYS = {"cpu", "memory", "drives", "storage", "gpu", "nic", "raid", "psu"}
_MB_SUFFIX = {"G", "GB", "T", "TB"}


def _parse_gb(text: str) -> int | None:
    """从容量/容量描述抽出 GB 数值（1T 按 1024G）。"""
    m = re.search(r"(\d+)\s*(G|GB|T|TB)", (text or "").upper())
    if not m:
        return None
    val = int(m.group(1))
    if m.group(2) in ("T", "TB"):
        val *= 1024
    return val if 1 <= val <= 65536 else None


def _coerce_single(key: str, value: Any) -> Any:
    """把单个字符串/裸值收敛为 merge_into_ext 可接受的结构。"""
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    if key == "cpu":
        return {"model": s, "qty": 1}
    if key == "raid":
        qty = 1
        qm = re.search(r"[×*x]\s*(\d+)", s, re.I)
        if qm:
            qty = int(qm.group(1))
        # 只写级别没写卡型号（RAID 0,1,10 / RAID0/1/10）：留级别信号，不臆造型号。
        levels = re.findall(r"\d+", s) if re.search(r"raid", s, re.I) else []
        if levels:
            return {"raid_levels": [str(int(x)) for x in levels], "qty": qty}
        return {"model": s, "qty": qty}
    if key == "memory":
        v: dict[str, Any] = {"qty": 1}
        gb = _parse_gb(s)
        if gb:
            v["per_stick_gb"] = gb
        m = re.search(r"DDR\d", s, re.I)
        if m:
            v["type"] = m.group(0)
        sp = re.search(r"DDR\d\s*-?\s*(\d{4})", s, re.I)
        if sp:
            v["speed_mt"] = int(sp.group(1))
        qm = re.search(r"[×*x]\s*(\d+)\s*(?:条|根)?", s, re.I)
        if qm:
            v["qty"] = int(qm.group(1))
        if not gb and not m:
            v["term"] = s
        return v
    if key == "psu":
        m = re.search(r"(\d+)\s*W", s, re.I)
        if m:
            return {"wattage": int(m.group(1)), "qty": 1}
        return {"model": s, "qty": 1}
    if key in ("drives", "storage"):
        d: dict[str, Any] = {"term": s, "qty": 1}
        gb = _parse_gb(s)
        if gb:
            d["capacity_gb"] = gb
        mi = re.search(r"NVMe|SAS|SATA|U\\.2|U\\.3", s, re.I)
        if mi:
            d["interface"] = mi.group(0)
        return d
    if key in ("gpu", "nic"):
        return {"model": s, "qty": 1}
    return None


def _coerce_list_value(key: str, value: Any) -> list:
    """列表键：统一收敛为 list[dict]。"""
    if isinstance(value, list):
        out = []
        for item in value[:16]:
            if isinstance(item, dict):
                out.append(item)
            else:
                c = _coerce_single(key, item)
                if c:
                    out.append(c)
        return out
    if isinstance(value, dict):
        return [value]
    c = _coerce_single(key, value)
    return [c] if c else []


def apply_structured_slots(ext: dict, slots: dict, requirement_text: str = "") -> list:
    """把 agent_fill LLM 抽到的结构化配件槽位合并进 ext，返回变更说明。"""
    if not isinstance(slots, dict):
        return []
    from app.services.llm_extract_enhance import merge_into_ext

    cleaned: dict[str, Any] = {}
    for key in _STRUCTURED_KEYS:
        if key not in slots:
            continue
        raw = slots[key]
        if key in ("drives", "storage", "gpu", "nic"):
            val = _coerce_list_value(key, raw)
            if val:
                cleaned[key] = val
        elif key == "raid":
            if isinstance(raw, list):
                val = _coerce_list_value(key, raw)
            else:
                val = _coerce_single(key, raw) or {}
            if val:
                cleaned[key] = val
        else:
            val = _coerce_single(key, raw)
            if val:
                cleaned[key] = val
    # storage 别名 → drives（merge_into_ext 认 drives）
    if "storage" in cleaned and "drives" not in cleaned:
        cleaned["drives"] = cleaned.pop("storage")
    if not cleaned:
        return []
    return merge_into_ext(ext, cleaned, requirement_text or "")
