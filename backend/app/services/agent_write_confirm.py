# -*- coding: utf-8 -*-
"""agent_write_confirm —— 写操作工具的两阶段确认存证。

协议：高危写工具第一次调用不带 confirm → handler 先算 preview，调 stage() 落一份
待确认记录并把它随 needs_confirmation 结果交回大脑；大脑把 preview 转述用户，
用户点确认卡/回复同意 → 执行。

执行通路（2026-10-22 架构修，用户意图不经过概率组件）：
- 首选【点击直达执行】：轮壳在用户点「确认执行」时直接按 staged 记录调工具，
  结果作为事实注入回合，大脑只陈述结果（见 transaction_turn._execute_pending）；
- 兜底【大脑带 confirm=true 重调】：resolve_confirmed 按（thread, tool, 参数摘要）
  匹配到记录才放行，执行参数一律以 staged 为准（用户批准的是 staged 预览）。

存储：线程 reasoning_state 里的 write_confirm 槽（状态在库——记录必须活得过
--reload / 进程重启 / 并行会话存盘；进程内存版是 2026-10-22「确认卡时好时坏」
的总根源）。测试可切内存后端（_STORAGE = "memory"）。

防自批：消费要求「stage 之后出现过新的用户消息」（seq 闸，随桶落库）；大脑同回合
自问自答吃掉确认被机制拒绝（2026-10-22 实锤）。成功才消费（consume）：执行失败
记录保留，重试直达，不再出现"失败一次就永远只出预览"的死循环。
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Optional

_TTL_SECONDS = 600
_MAX_PENDING_PER_THREAD = 8
_SLOT = "write_confirm:assistant"

# "db"（默认，活过重启）| "memory"（单测后端）
_STORAGE = "db"
_MEM: dict = {}

# {thread_id: {"_seq": int, "records": {tool: {digest, args, preview, seq, expires_at}}}}
# db 模式下这是落库形态（reasoning_state 里的一个 JSON 槽）。


def _sweep(bucket: dict, now: float) -> None:
    for tool in [t for t, e in (bucket.get("records") or {}).items() if e.get("expires_at", 0) <= now]:
        bucket["records"].pop(tool, None)
    for tool in [t for t, e in (bucket.get("deferred") or {}).items() if e.get("expires_at", 0) <= now]:
        bucket["deferred"].pop(tool, None)


def _load_bucket(thread_id: str) -> dict:
    now = time.time()
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
    bucket.setdefault("_seq", 0)
    if not isinstance(bucket.get("records"), dict):
        bucket["records"] = {}
    if not isinstance(bucket.get("deferred"), dict):
        bucket["deferred"] = {}
    _sweep(bucket, now)
    return bucket


def _save_bucket(thread_id: str, bucket: dict) -> None:
    if _STORAGE == "memory":
        _MEM[str(thread_id or "")] = bucket
        return
    from app.repository.assistant_repo import AssistantRepository
    repo = AssistantRepository()
    try:
        repo.update_reasoning_state(str(thread_id or ""), {_SLOT: bucket})
    finally:
        repo.close()


def note_user_message(thread_id: str) -> int:
    """postMessage 入口调用：记下「这个线程又出现过一条用户消息」（seq 闸的计数）。"""
    key = str(thread_id or "")
    bucket = _load_bucket(key)
    bucket["_seq"] = int(bucket.get("_seq") or 0) + 1
    _save_bucket(key, bucket)
    return bucket["_seq"]


def _canonical(value: Any) -> Any:
    """参数归一：数值统一 float（15 与 15.0 等价），bool/字符串保持原样。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (OverflowError, ValueError):
            return value
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in value.items()}
    return value


def _args_digest(args: dict) -> str:
    """参数摘要：确认时重算比对，防记录被挪用到别的参数上（只影响漂移说明，
    执行参数永远以 staged 为准）。confirm/confirm_token 本身不参与摘要。"""
    payload_args = {k: v for k, v in (args or {}).items()
                    if k not in ("confirm", "confirm_token")}
    try:
        payload = json.dumps(_canonical(payload_args), ensure_ascii=False,
                             sort_keys=True, default=str)
    except (TypeError, ValueError):
        payload = repr(payload_args)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stage(thread_id: str, tool: str, args: dict, preview: Optional[dict] = None) -> None:
    """落一份待确认记录（同线程同工具覆盖旧份——重发预览以最后一次为准）。
    preview 随记录存：直达执行补卡/兜底网补卡时的文案数据。记录当时的用户消息序号：
    消费要求 stage 之后出现过新的用户消息。

    carded 标记（2026-10-22 实锤「一口气两张一样的确认卡」）：卡是待确认记录的投影，
    同参数重发（大脑同回合重复调用/跨回合重调）不算新卡——沿用旧记录的 carded；
    参数变了=预览变了，旧卡作废、carded 归零允许发新卡。"""
    key = str(thread_id or "")
    bucket = _load_bucket(key)
    while len(bucket["records"]) >= _MAX_PENDING_PER_THREAD:
        bucket["records"].pop(next(iter(bucket["records"])))
    digest = _args_digest(args)
    tool_key = str(tool or "")
    old = bucket["records"].get(tool_key)
    carded = bool(old.get("query_opened")) if (old and old.get("digest") == digest) else False
    bucket["records"][tool_key] = {
        "digest": digest,
        "expires_at": time.time() + _TTL_SECONDS,
        "args": {k: _canonical(v) for k, v in (args or {}).items() if k != "confirm"},
        "seq": int(bucket.get("_seq") or 0),
        "preview": dict(preview or {}),
        # 授权问询（consent HumanQuery）已发射标记；"carded" 为 2026-10-23 前的旧名
        "query_opened": carded,
    }
    _save_bucket(key, bucket)


def query_opened(thread_id: str, tool: str) -> bool:
    """该工具的待确认记录是否已发起授权问询（发射前去重闸，只读；
    兼容读旧字段 carded——2026-10-23 前的存量记录 10 分钟 TTL 内自然清零）。"""
    bucket = _load_bucket(thread_id)
    entry = (bucket.get("records") or {}).get(str(tool or ""))
    return bool(entry and (entry.get("query_opened") or entry.get("carded")))


def mark_query_opened(thread_id: str, tool: str) -> None:
    """授权问询发射成功后打标记（幂等；记录不存在时静默——记录被并发消费则随事实消亡）。"""
    bucket = _load_bucket(thread_id)
    entry = (bucket.get("records") or {}).get(str(tool or ""))
    if entry and not (entry.get("query_opened") or entry.get("carded")):
        entry["query_opened"] = True
        _save_bucket(thread_id, bucket)


def staged_args(thread_id: str, tool: str) -> Optional[dict]:
    """某工具当前待确认记录的原始参数（案台展示/直达执行用，只读、不消费）。"""
    bucket = _load_bucket(thread_id)
    entry = (bucket.get("records") or {}).get(str(tool or ""))
    return dict(entry.get("args")) if entry else None


def _loose_match(staged: dict, replay: dict) -> bool:
    """宽容匹配：staged 出现过的每个键在重放中都要存在且归一相等——唯一例外是
    staged 里的空值键（None/""/[]/{}），重放未带=等价（空即未提供）。
    字符串/数值互换形态（"345" vs 345）认等价；值真变了仍拒绝——安全性不变。"""
    for k, v in (staged or {}).items():
        if k not in (replay or {}):
            if v in (None, "", [], {}):
                continue
            return False
        cv, cr = _canonical(v), _canonical(replay[k])
        if cv == cr:
            continue
        try:
            if float(cv) != float(cr):
                return False
        except (TypeError, ValueError):
            return False
    return True


def resolve_confirmed(thread_id: str, tool: str, args: dict) -> tuple:
    """confirm=true 时的裁决（确认闸的唯一裁决口；**不销记录**）。

    → (是否放行, 执行参数, 漂移说明)
    - 无 pending / 过期 → (False, None, 原因)；
    - stage 之后没有新的用户消息 → (False, …, "confirm_not_from_user")；
    - 有用户消息：**一律放行，执行参数 = staged（用户看过的预览那份）**。
      记录在工具执行成功后由 consume() 销毁——失败保留，重试直达
      （2026-10-22 实锤：先销后执行，一次落库失败就把用户拖进无限出卡循环）。"""
    bucket = _load_bucket(thread_id)
    entry = (bucket.get("records") or {}).get(str(tool or ""))
    if not entry:
        return False, None, "no_pending"
    if entry.get("expires_at", 0) <= time.time():
        bucket["records"].pop(str(tool or ""), None)
        _save_bucket(thread_id, bucket)
        return False, None, "expired"
    if int(bucket.get("_seq") or 0) <= int(entry.get("seq") or 0):
        return False, None, "confirm_not_from_user"
    staged = dict(entry.get("args") or {})
    strict = entry.get("digest") == _args_digest(args)
    loose = strict or _loose_match(staged, args)
    drift = "" if strict else ("重放参数与预览有出入（含非关键值差异）" if not loose else "")
    return True, staged, drift or None


def consume(thread_id: str, tool: str) -> None:
    """执行成功后销记录（失败保留——重试时 resolve_confirmed 直达放行）。"""
    bucket = _load_bucket(thread_id)
    if bucket["records"].pop(str(tool or ""), None) is not None:
        _save_bucket(thread_id, bucket)


# ── 推迟账本（R3a 跨步记录完备）：写工具因步进纪律自降级（如识别步只解析预览）时
#    记账；调和器在指针推进到写动作所属步后原参数重放。同桶同 TTL，一份数据一份生命周期。


def defer_call(thread_id: str, tool: str, args: dict) -> None:
    """记一笔被推迟的闸调用（同工具同参数幂等——大脑重复调用不重复记账）。"""
    key = str(thread_id or "")
    bucket = _load_bucket(key)
    digest = _args_digest(args)
    old = bucket["deferred"].get(str(tool or ""))
    if old and old.get("digest") == digest:
        return
    bucket["deferred"][str(tool or "")] = {
        "digest": digest,
        "args": {k: _canonical(v) for k, v in (args or {}).items() if k != "confirm"},
        "expires_at": time.time() + _TTL_SECONDS,
    }
    _save_bucket(key, bucket)


def deferred_calls(thread_id: str) -> dict:
    """推迟账本只读视图 {tool: args}（调和器挑可重放项用）。"""
    bucket = _load_bucket(thread_id)
    return {tool: dict(e.get("args") or {})
            for tool, e in (bucket.get("deferred") or {}).items()}


def pop_deferred(thread_id: str, tool: str) -> None:
    """重放消费（一次机会：成败都清——失败由错误事实转述，不死循环）。"""
    bucket = _load_bucket(thread_id)
    if (bucket.get("deferred") or {}).pop(str(tool or ""), None) is not None:
        _save_bucket(thread_id, bucket)


def pending_tools(thread_id: str) -> dict:
    """线程当前待确认记录 {tool: 剩余秒数}（案台展示用，只读、不消费）。"""
    bucket = _load_bucket(thread_id)
    now = time.time()
    return {tool: int(e.get("expires_at", 0) - now)
            for tool, e in (bucket.get("records") or {}).items() if e.get("expires_at", 0) > now}


def pending_previews(thread_id: str) -> dict:
    """线程当前待确认记录的 preview 文案 {tool: preview}（补卡网用，只读、不消费）。"""
    bucket = _load_bucket(thread_id)
    now = time.time()
    return {tool: dict(e.get("preview") or {})
            for tool, e in (bucket.get("records") or {}).items() if e.get("expires_at", 0) > now}


def discard(thread_id: str, tool: str) -> None:
    """用户在确认卡上点了取消：清掉待确认记录（下次要执行须重新走预览）。"""
    bucket = _load_bucket(thread_id)
    if bucket["records"].pop(str(tool or ""), None) is not None:
        _save_bucket(thread_id, bucket)


def pending_count(thread_id: Optional[str] = None) -> int:
    """待确认记录数（测试/诊断用；db 模式只支持单线程查询）。"""
    if thread_id is None:
        if _STORAGE == "memory":
            return sum(len((b or {}).get("records") or {}) for b in _MEM.values())
        return 0
    bucket = _load_bucket(thread_id)
    return len(bucket.get("records") or {})
