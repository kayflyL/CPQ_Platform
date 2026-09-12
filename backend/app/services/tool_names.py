# -*- coding: utf-8 -*-
"""工具名共享归一（单一来源）。

全链路工具名唯一权威：AI 工具目录（agent_tool_specs）里注册的名字。
本模块只维护「历史旧名 → 现行名」映射与「已退役工具」集合，供所有
读取工具名配置的地方归一，避免每个消费者各自维护一份词表（DB 配置漂移）。

TODO: 一旦 DB 里旧名清零，rename/retired 两张表可整体退役。
"""
from __future__ import annotations

from typing import Iterable, List

# 历史旧名 → 现行名（只在此处维护，禁止散落双写）
TOOL_RENAME_MAP: dict[str, str] = {
    "select_models": "choose_model",
    "select_model": "choose_model",
    "search_kp_parts": "query_parts",
    "select_kp_parts": "select_parts",
    "pick_kp_parts": "select_parts",
    "choose_parts": "select_parts",
    "open_part": "inspect_parts",
    "open_row": "inspect_parts",
    "open_category": "inspect_parts",
    "grep_parts": "inspect_parts",
}

# 已退役工具（直接剔除，不映射）：旧服务器浏览三件套 + 旧节点机制工具
RETIRED_TOOL_IDS: set[str] = {
    "list_server_types",
    "list_server_models",
    "get_server_model",
    "resolve_part_alias",
    "compose_memory",
    "list_kp_categories",
    "begin_step",
    "end_step",
    "compose_plan",
    "build_plan",
    "cost_breakdown",
    "quote_draft",
    "suggest_parts",
}


def normalize_tool_ids(ids: Iterable[str]) -> List[str]:
    """归一工具名列表：旧名→现行名、剔除退役项、去空去重，保持原相对顺序。

    - 入参为 None/不可迭代 → 返回 []。
    - 每一项先 strip；空串跳过。
    - 后缀截断后匹配 rename；退役工具直接丢弃。
    - 幂等：对已归一的名字重复调用无副作用。
    """
    if ids is None:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        t = str(raw or "").strip()
        if not t:
            continue
        t = TOOL_RENAME_MAP.get(t, t)
        if t in RETIRED_TOOL_IDS:
            continue
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
