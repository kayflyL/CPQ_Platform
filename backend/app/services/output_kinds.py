# -*- coding: utf-8 -*-
"""output_kinds —— 输出物种类唯一注册表（ABI 节点契约 kind 分册）。

输出节点 output_kind 的合法值前后端同源：本表是唯一权威，前端画布抽屉经
GET /api/reasoning-flow/output-kinds 拉取渲染（不再前端硬编码清单）。新增输出
种类 = 这里加一行 + 消费方（渲染器/分发器）接线，机制零改动。
"""

OUTPUT_KINDS = {
    "bom_scheme_draft": {"label": "BOM 方案草稿"},
    "requirement_draft": {"label": "需求单草稿"},
    "plans": {"label": "方案 / BOM"},
    "data_answer": {"label": "数据结论"},
    "generic": {"label": "通用 JSON"},
}


def list_output_kinds() -> dict:
    return {k: dict(v) for k, v in OUTPUT_KINDS.items()}


def is_valid_output_kind(kind: str) -> bool:
    return str(kind or "").strip() in OUTPUT_KINDS
