# -*- coding: utf-8 -*-
"""constitution_lint —— 「对大脑说怎么做」祈使/流程词表（宪法守卫的判定核心）。

唯一出处：tests/test_constitution.py 的扫描与 /api/assistant/tools 文案保存口共用，
两边不允许各自维护一份词表（词表分叉 = 守卫失效）。
"""

PROSE_MARKERS = [
    "先调", "优先调", "先对", "先问", "先查", "才调", "再调", "然后调",
    "无需再", "不用再", "不再要求", "不必再",
    "不许", "严禁", "不得", "必须调", "必须用", "禁止",
    "不要", "别把", "别当成", "别再",
    "应当", "应该", "建议", "请先", "请把", "请注意", "请据此", "请据",
    "可据此", "由系统", "交由", "交客户", "交回客户", "让客户", "如实告诉", "如实说明", "如实向",
    "才能", "即可锁定", "会有", "会自动",
]


def find_prose_markers(text: str) -> list:
    """返回文本里命中的祈使/流程词（按词表顺序去重）。空文本/非字符串按无命中处理。"""
    if not text or not isinstance(text, str):
        return []
    hits: list = []
    for marker in PROSE_MARKERS:
        if marker in text and marker not in hits:
            hits.append(marker)
    return hits
