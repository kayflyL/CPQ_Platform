# -*- coding: utf-8 -*-
"""slots_backfill —— 槽位回填器（公共件）：部分槽位值按契约校验回填，产出缺口清单。

消费者：交付工作流的「线索登记回填」节点（喂解析 meta）、需求分析的理解节点（喂模型
抽取值）——回填器只有一个实现，谁也不许复制第二套。

原则（对齐既有体系）：
- 只认槽位契约（combined_slot_spec）里的 key，多余值进 ignored（防脏写）；
- 契约带默认值的槽位未提供时按默认兜底（source=「默认兜底」），流程可通；
- 其余未提供的进 missing——那就是反问卡的数据源（逐个问，一次一卡）；
- 回填值全部带 source 标记（表格解析/用户确认/默认兜底），无隐藏状态。
"""
from __future__ import annotations

from typing import Any, Optional


def _spec(spec: Optional[list]) -> list:
    if spec:
        return spec
    from app.services.requirement_slots import combined_slot_spec
    return combined_slot_spec()


def _empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return v.strip() == ""
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def backfill(values: dict, *, source: str = "表格解析",
             spec: Optional[list] = None) -> dict:
    """确定性回填：values = {槽位key: 值}（来源统一标 source）。
    返回 {ok, filled, missing, draft_slots, ignored}——draft_slots 可直接喂
    save_requirement_draft；missing 按契约顺序排列，是反问卡的队列。"""
    provided = {k: v for k, v in (values or {}).items() if not _empty(v)}
    filled: dict = {}
    missing: list = []
    draft_slots: dict = {}

    for slot in _spec(spec):
        key = slot.get("key")
        if not key:
            continue
        if key in provided:
            value = provided.pop(key)
            filled[key] = {"value": value, "source": source}
            draft_slots[key] = value
            continue
        # 缺省兜底（数据驱动，沿用契约语义）：保证流程可通，允许后续规则层扭转
        default = slot.get("default_value")
        if default is None and key == "purchase_qty":
            default = 1
        if default is not None and not _empty(default):
            filled[key] = {"value": default, "source": "默认兜底"}
            draft_slots[key] = default
            continue
        missing.append(key)

    ignored = dict(provided)  # 契约外的键：不写草稿，原样告知调用方
    return {"ok": True, "filled": filled, "missing": missing,
            "draft_slots": draft_slots, "ignored": ignored}


def question_for(missing: list) -> Optional[dict]:
    """缺口 → 一张反问卡（一次一卡原则：只返回第一个缺口）。
    返回 {key, question} 或 None（无缺口=直接放行）。"""
    if not missing:
        return None
    key = missing[0]
    return {"key": key,
            "question": f"还需要确认一项：{key} 是多少？（不填可选「已知悉」跳过）"}
