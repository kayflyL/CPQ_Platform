# -*- coding: utf-8 -*-
"""human_query —— 问答协议：向人提问的一等公民（human-as-tool）。

把系统里散落的"向人要信息"收敛为一个契约、两个发起者、三种类型：

    HumanQuery  = {query_id, kind: choice|form|consent, question{title,hint,detail},
                   options?[{label,description,recommended}], fields?[{key,label,type,placeholder}],
                   action?{tool}}                     # consent：绑定的授权动作
    HumanAnswer = {query_id, selections?[label], values?{key:value}, note, answered_by}

- 大脑发起（ask_user 工具，choice/form）与系统发起（调和器，consent）走同一协议；
- 渲染由**载荷形状**决定（有 options=单选卡+Other、有 fields=表单），大脑不选模板；
- 答案按 **query_id** 路由（结构化回流），文本"确认"只是兜底——匹配范围被
  开放问题收窄，不再是全局字符串比对（2026-10-23 实锤：答案路由曾是
  `user_text in ("确认执行","确认","取消")` 全局串比对）；
- **每线程至多一个开放问题**：任务规则 12"一回合一卡"从行为规则降维成协议不变量——
  机制保证，不靠大脑自觉。旧问题未答时再问 = 契约错误。

存储：线程 reasoning_state 的 human_query 槽（状态在库——开放问题/答案活过重启，
与 write_confirm 同一纪律）；问题与答案的**展示副本**落消息流（重放可见）。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)

_SLOT = "human_query:assistant"
_TTL_SECONDS = 1800  # 开放问题 30 分钟无人答自动关（consent 记录另有 write_confirm 的 10 分钟闸）

_MEM: dict = {}
_STORAGE = "db"  # "db"（默认）| "memory"（单测）


def _sweep(bucket: dict, now: float) -> None:
    for qid in [q for q, e in (bucket.get("open") or {}).items() if e.get("expires_at", 0) <= now]:
        bucket["open"].pop(qid, None)


def _load(thread_id: str) -> dict:
    if _STORAGE == "memory":
        bucket = _MEM.get(str(thread_id or "")) or {}
    else:
        from app.repository.assistant_repo import AssistantRepository
        repo = AssistantRepository()
        try:
            raw = repo.get_reasoning_state(str(thread_id or ""))
        finally:
            repo.close()
        data = json.loads(raw or "{}") if raw else {}
        bucket = data.get(_SLOT) or {}
    bucket = bucket if isinstance(bucket, dict) else {}
    bucket.setdefault("open", {})
    bucket.setdefault("answer", None)
    _sweep(bucket, time.time())
    return bucket


def _save(thread_id: str, bucket: dict) -> None:
    if _STORAGE == "memory":
        _MEM[str(thread_id or "")] = bucket
        return
    from app.repository.assistant_repo import AssistantRepository
    repo = AssistantRepository()
    try:
        repo.update_reasoning_state(str(thread_id or ""), {_SLOT: bucket})
    finally:
        repo.close()


# ── 契约校验（形状即类型：options→choice，fields→form；都不给=纯文本问，不立问题）──

def validate_payload(title: str, options: Any, fields: Any) -> tuple[Optional[str], str]:
    """→ (kind, error)。kind=None 表示载荷不构成一个可渲染的问题。"""
    t = str(title or "").strip()
    if not t:
        return None, "question.title 缺失：问题必须有正文"
    opts = options if isinstance(options, list) else None
    flds = fields if isinstance(fields, list) else None
    if opts and flds:
        return None, "options 与 fields 二选一：一次只问一种形状（单选/表单）"
    if opts is not None:
        if not (2 <= len(opts) <= 4):
            return None, f"options 需要 2~4 个（当前 {len(opts)}）：少于 2 个不构成选择"
        for o in opts:
            if not isinstance(o, dict) or not str(o.get("label") or "").strip():
                return None, "options[].label 缺失：每个选项必须有可点选的名字"
        return "choice", ""
    if flds is not None:
        if not (1 <= len(flds) <= 8):
            return None, f"fields 需要 1~8 个（当前 {len(flds)}）"
        for f in flds:
            if not isinstance(f, dict) or not str(f.get("key") or "").strip() \
                    or not str(f.get("label") or "").strip():
                return None, "fields[] 的 key/label 缺失"
        return "form", ""
    return None, "options 与 fields 至少给一个：纯文本反问不需要工具"


# ── 开放 / 回答 / 路由 ────────────────────────────────────────────────────

def open_query(thread_id: str, *, kind: str, title: str, hint: str = "", detail: str = "",
               options: Optional[list] = None, fields: Optional[list] = None,
               action: Optional[dict] = None, role_key: Optional[str] = None) -> dict:
    """立一个开放问题。每线程至多一个——已有开放问题时抛 ContractError（不变量，
    调用方把错误转述给大脑/发起者，绝不排队第二个问题）。"""
    bucket = _load(thread_id)
    if bucket["open"]:
        qid, old = next(iter(bucket["open"].items()))
        raise ContractError(f"已有开放的问题未回答（{old.get('question', {}).get('title') or qid}）："
                            "一次只问一个问题，等它被回答或超时")
    qid = uuid.uuid4().hex[:12]
    entry = {
        "query_id": qid, "kind": kind,
        "question": {"title": str(title or "").strip(), "hint": str(hint or ""),
                     "detail": str(detail or "")},
        "options": options or None, "fields": fields or None,
        "action": action or None,
        "role_key": role_key,
        "opened_at": time.time(), "expires_at": time.time() + _TTL_SECONDS,
    }
    bucket["open"][qid] = entry
    _save(thread_id, bucket)
    return entry


def open_query_of(thread_id: str) -> Optional[dict]:
    """当前唯一的开放问题（过期自动关；无=None）。"""
    bucket = _load(thread_id)
    if not bucket["open"]:
        return None
    qid, entry = next(iter(bucket["open"].items()))
    return entry


def answer_query(thread_id: str, *, query_id: str, selections: Optional[list] = None,
                 values: Optional[dict] = None, note: str = "", answered_by: str = "") -> dict:
    """回答开放问题（结构化回流）。答完即关（一回合一答）。→ {query, answer}"""
    bucket = _load(thread_id)
    entry = bucket["open"].get(str(query_id or ""))
    if not entry:
        raise ContractError("问题不存在或已关闭：以当前对话下方的卡片为准")
    answer = {"query_id": entry["query_id"], "kind": entry["kind"],
              "selections": [str(s) for s in (selections or []) if str(s).strip()] or None,
              "values": {str(k): v for k, v in (values or {}).items()} or None,
              "note": str(note or ""), "answered_by": str(answered_by or ""),
              "answered_at": time.time()}
    bucket["answer"] = answer
    bucket["open"].pop(str(query_id or ""), None)
    _save(thread_id, bucket)
    return {"query": entry, "answer": answer}


def take_answer(thread_id: str) -> Optional[dict]:
    """轮壳取走当前回答（取出即清）——{query, answer}；无=None。"""
    bucket = _load(thread_id)
    ans = bucket.get("answer")
    if not ans:
        return None
    bucket["answer"] = None
    _save(thread_id, bucket)
    query = None
    # 问题正文随答案走（跨回合断层由协议补偿：答案自带问题上下文）
    for e in _recent_queries(thread_id):
        if e.get("query_id") == ans.get("query_id"):
            query = e
            break
    return {"query": query, "answer": ans}


def _recent_queries(thread_id: str) -> list:
    """消息流里最近的 query 展示副本（答案配对正文用；协议状态本体在槽里）。"""
    try:
        from app.repository.assistant_repo import AssistantRepository
        repo = AssistantRepository()
        try:
            msgs = repo.list_messages(str(thread_id or ""), limit=40)
        finally:
            repo.close()
        out = []
        for m in msgs or []:
            if m.get("kind") != "query" or not m.get("data"):
                continue
            try:
                d = json.loads(m["data"])
            except (TypeError, ValueError):
                continue
            if isinstance(d, dict):
                out.append(d)
        return out
    except Exception:
        logger.exception("recent queries read failed")
        return []


def close_stale(thread_id: str) -> None:
    """显式关掉过期问题（装载时已自动清扫，这里供回合壳兜底调用）。"""
    _load(thread_id)


async def open_query_and_announce(thread_id: str, *, kind: str, title: str, hint: str = "",
                                  detail: str = "", options: Optional[list] = None,
                                  fields: Optional[list] = None, action: Optional[dict] = None,
                                  role_key: Optional[str] = None) -> dict:
    """立开放问题 + 落展示副本（消息流，重放可见）+ 广播。纯文本回退正文一并生成
    （介质无关：无 JS 渲染器时问题仍是完整可读可答的）。"""
    entry = open_query(thread_id, kind=kind, title=title, hint=hint, detail=detail,
                       options=options, fields=fields, action=action, role_key=role_key)
    lines = [str(title or "").strip()]
    if detail:
        lines.append(str(detail))
    if options:
        labels = []
        for o in options:
            lbl = str(o.get("label") or "").strip()
            labels.append(lbl + ("（推荐）" if o.get("recommended") else ""))
        lines.append("・" + " / ".join(labels))
    if hint:
        lines.append(f"（{hint}）")
    from app.repository.assistant_repo import AssistantRepository
    from app.services.assistant_hub import assistant_hub
    repo = AssistantRepository()
    try:
        msg = repo.add_message(
            thread_id=str(thread_id or ""), role="assistant",
            content="\n".join(x for x in lines if x),
            kind="query", data=json.dumps(entry, ensure_ascii=False, default=str),
            colleague_role_key=role_key)
    finally:
        repo.close()
    if msg:
        entry["message_id"] = msg.get("message_id")
        await assistant_hub.broadcast(str(thread_id or ""), {"type": "done", "message": msg})
    return entry


def render_answer_text(query: Optional[dict], answer: dict) -> str:
    """答案的人类可读文本（展示副本/【客户消息】用）：「问题」选项A；字段=值。"""
    title = str(((query or {}).get("question") or {}).get("title") or "问题")
    parts = []
    for s in (answer.get("selections") or []):
        parts.append(str(s))
    for k, v in (answer.get("values") or {}).items():
        parts.append(f"{k}={v}")
    if answer.get("note"):
        parts.append(f"备注：{answer['note']}")
    return f"「{title}」" + ("；".join(parts) if parts else "（已回答）")


class ContractError(Exception):
    """问答协议的契约错误（已有开放问题/问题已关闭）——调用方原样转述，不重试。"""
