# -*- coding: utf-8 -*-
"""workflow_ask —— 节点反问原语（公共件）：工作流节点向用户要一个决定。

与聊天的 ask_user 两轨不混：ask_user 是会话语义（依赖 task_active 的对话脑）；
本原语是流程语义——节点暂停等用户拍板，服务端留底（问题/选项/所属节点），
用户点选/回答按 (run_id, node) 匹配消费。

进程内 TTL 存储（与 agent_write_confirm 同款纪律）：只存技术态不存业务事实；
重启丢失 = 反问卡重新出。消费者：交付工作流的反问节点；需求分析后续迁移时同源。
"""
from __future__ import annotations

import time
from typing import Any, Optional

_TTL_SECONDS = 1800  # 反问挂 30 分钟：足够用户离开再回来，不长到误导

# {run_id: {node: {question, options, created_at}}}
_pending: dict = {}


def _sweep(now: float) -> None:
    for run in list(_pending.keys()):
        bucket = _pending[run]
        for node in [n for n, item in bucket.items() if item["created_at"] + _TTL_SECONDS <= now]:
            bucket.pop(node, None)
        if not bucket:
            _pending.pop(run, None)


def ask(run_id: str, node: str, question: str,
        options: list, *, extra: Optional[dict] = None) -> dict:
    """登记一次反问（同 run 同 node 覆盖旧份），返回可直接渲染的卡 payload。"""
    now = time.time()
    _sweep(now)
    run = str(run_id or "")
    bucket = _pending.setdefault(run, {})
    opts = [{"label": str(o.get("label") if isinstance(o, dict) else o),
             **({"value": o["value"]} if isinstance(o, dict) and o.get("value") else {})}
            for o in (options or [])]
    item = {"question": str(question or ""), "options": opts,
            "created_at": now, **(extra or {})}
    bucket[str(node or "")] = item
    return {"kind": "input_options", "question": item["question"], "options": opts}


def answer(run_id: str, node: str, value: str) -> Optional[dict]:
    """用户拍板：按 (run, node) 匹配并消费，返回命中的 option（含 value）；无匹配= None。"""
    now = time.time()
    _sweep(now)
    bucket = _pending.get(str(run_id or "")) or {}
    item = bucket.pop(str(node or ""), None)
    if not item or item["created_at"] + _TTL_SECONDS <= now:
        return None
    for o in item["options"]:
        if str(o.get("label")) == str(value) or str(o.get("value")) == str(value):
            return o
    return {"label": str(value), "value": str(value)}  # 自由文本回答也算数（原样带回）


def pending(run_id: Optional[str] = None) -> dict:
    """当前挂着的反问（测试/诊断用）。"""
    _sweep(time.time())
    if run_id is None:
        return {r: {n: i["question"] for n, i in b.items()} for r, b in _pending.items()}
    return {n: i["question"] for n, i in (_pending.get(str(run_id)) or {}).items()}
