# -*- coding: utf-8 -*-
"""工具执行期的线程上下文（contextvar）。全局唯一 owner：所有工具模块共用同一个对象。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
"""
from __future__ import annotations

import contextvars

# 工具执行期的线程上下文（react 循环内 handler 读取；run 侧每轮注入）
TOOL_CTX: contextvars.ContextVar[dict] = contextvars.ContextVar("skill_chat_tool_ctx", default={})
