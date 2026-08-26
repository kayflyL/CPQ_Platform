# -*- coding: utf-8 -*-
"""需求分析槽位确认工具（唯一真相，无 LLM，可单测）。

is_confirmed：判断某个 slot 是否已被理解/确认填上，供 agent_fill 与进度卡对齐。
（历史逐字段状态机 SlotState 已随节点移除删除。）
"""
from __future__ import annotations

from typing import Any

# 记录字段别名：key -> ext 里可能的取值键（与 slot_contract._slot_filled 一致）
_SLOT_KEYS = {
    "server_type": ["server_type_name", "server_type"],
    "platform_type": ["series", "platform_type"],
    "chassis_form": ["form", "chassis_form"],
    "purchase_qty": ["purchase_qty", "n"],
    "n": ["n", "purchase_qty"],
    "server_model": ["server_model", "model", "baseline_model"],
    "cpu": ["cpu_signal"],
    "memory": ["mem_signal", "mem_groups"],
    "storage": ["drive_groups"],
    "gpu": ["gpu_groups"],
    "nic": ["multi_spec_filters"],
    "raid": ["raid_groups"],
    "psu": ["psu_signal"],
}


def _has(v: Any) -> bool:
    if v is None or v is False:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (int, float)):
        return v > 0
    if isinstance(v, dict):
        return any(_has(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return any(_has(x) for x in v)
    return bool(v)


def is_confirmed(ext: dict, key: str) -> bool:
    """按 ext 结构判断某 slot 是否已被理解/确认填上（与理解节点口径一致）。"""
    from app.services import semantic_contract as _sc
    if _sc.absent_confirmed(ext, key):
        return True
    return any(_has(ext.get(k)) for k in _SLOT_KEYS.get(key, []))
