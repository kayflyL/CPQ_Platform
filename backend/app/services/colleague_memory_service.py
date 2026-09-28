"""同事结构化记忆服务（2026-09-27 重构：代理自管 + 双时间轴 + 空闲整理）。

架构（对应调研四机制）：
- memory_block：注入层不变——钉死集（置顶 ∪ 手工）恒注入 + 非置顶按相关性召回
  （本地向量，fastembed 不可用回退最新序）；命中条目刷新 last_accessed_at（老化排序）。
- tool_memory_action：写入层=记忆工具（Anthropic memory tool 形）。正在对话的模型在轮内
  自决 write/retire（写入者=对话者，上下文最全），每次写入是可见 tool call（观测免费）。
  旧 fire-and-forget 抽取器已退役。
- consolidate_role：整理层=空闲期归并（Letta sleep-time lite）。LLM 全量看一遍某角色的
  活跃记忆提归并案（merge/retype/retire），确定性校验后才落库；管理面可手动触发。
- 数据模型：失效打戳不删除（retired_at/superseded_by），矛盾=新条目 supersede 旧条目。
- 记忆域（多用户隔离，2026-09-28）：对话写入一律落用户私有域（user_id=写入者，仅本人
  注入/可 retire）；公共域（user_id NULL）只由治理面维护，全员可见。确定性规则，
  不靠 LLM 判断某条该不该共享。
"""
import logging
from typing import Optional

from app.models.colleague_memory import MEMORY_TYPES, TYPE_LABELS
from app.repository.colleague_memory_repo import ColleagueMemoryRepository

logger = logging.getLogger(__name__)

PROMPT_LIMIT = 30
MAX_PER_ROLE = 100


def _is_durable(row: dict) -> bool:
    """钉死集：管理员置顶或手工录入的记忆（员工页「管理记忆」手写的即长期事实）。"""
    return bool(row.get("pinned")) or str(row.get("source") or "") == "manual"


def _ordered_rows(repo: ColleagueMemoryRepository, role_key: str, user_id: str = "") -> list:
    uid = str(user_id or "").strip()
    if uid:
        return repo.list_by_role(role_key, limit=1000, visible_to=uid)
    # 无用户上下文=只看公共域（fail-safe：绝不注入他人私有记忆）
    return repo.list_by_role(role_key, limit=1000, public_only=True)


def memory_block(role_key: str, limit: int = PROMPT_LIMIT, user_text: str = "",
                 user_id: Optional[str] = None) -> str:
    """同事记忆 → system prompt 注入块；钉死集恒在、其余按与当前消息的相关性召回。
    user_id 定域：公共 ∪ 该用户私有；缺省只注入公共域（多用户不串）。"""
    repo = ColleagueMemoryRepository()
    rows = _ordered_rows(repo, role_key, str(user_id or "").strip())
    if not rows:
        return ""
    durable = [r for r in rows if _is_durable(r)][:PROMPT_LIMIT]
    rest_rows = [r for r in rows if not _is_durable(r)]
    rest: list = []
    if rest_rows:
        if str(user_text or "").strip():
            from app.services import colleague_memory_search
            ranked = colleague_memory_search.rank_by_relevance(
                role_key, rest_rows, user_text, limit)
            rest = ranked if ranked is not None else rest_rows[:limit]
        else:
            rest = rest_rows[:limit]
    selected = durable + rest
    if selected:
        try:
            repo.touch_access([int(r["id"]) for r in selected if r.get("id")])
        except Exception:
            logger.exception("记忆 last_accessed 刷新失败 role=%s", role_key)
    grouped: dict = {}
    for r in selected:
        grouped.setdefault(r.get("type") or "business_fact", []).append(r.get("content") or "")
    lines = []
    for t in MEMORY_TYPES:
        items = grouped.get(t)
        if not items:
            continue
        label = TYPE_LABELS.get(t, t)
        for text in items:
            lines.append(f"- [{label}] {text}")
    if not lines:
        return ""
    return "同事长期记忆（长期有效的事实与偏好，优先级高于默认习惯）：\n" + "\n".join(lines)


# ── 记忆工具实现（写入层：对话者自决，agent_tool_handlers 薄壳委托到这里）─────────

def tool_memory_action(args: dict, tool_ctx: Optional[dict] = None) -> dict:
    """colleague_memory 工具的确定性实现：list/view/write/retire 四动作。

    权属=调用它的同事（TOOL_CTX.role_key），跨角色读写一律拒绝。
    域规则（2026-09-28）：write 一律落当前用户私有域（TOOL_CTX.user_id 必须存在）；
    list/view=公共 ∪ 本人私有；retire 仅本人私有条目，公共域归治理面。
    确定性校验：类型枚举、内容去重（可见集精确串）、钉死集禁 retire、容量封顶。
    """
    if isinstance(tool_ctx, dict):
        ctx = tool_ctx
    else:
        from app.services.skill_tool_context import TOOL_CTX
        ctx = TOOL_CTX.get() or {}
    role_key = str(ctx.get("role_key") or "").strip()
    if not role_key:
        return {"ok": False, "error": "缺少角色上下文，记忆工具不可用"}
    uid = str(ctx.get("user_id") or "").strip()
    action = str((args or {}).get("action") or "").strip().lower()
    repo = ColleagueMemoryRepository()

    if action == "list":
        rows = _ordered_rows(repo, role_key, uid)[:100]
        return {"ok": True, "count": len(rows), "memories": [
            {"id": r["id"], "type": r["type"], "type_label": r.get("type_label") or r["type"],
             "content": r["content"], "pinned": r.get("pinned") or False,
             "source": r.get("source") or "auto"}
            for r in rows]}

    if action == "view":
        try:
            mid = int((args or {}).get("id") or 0)
        except (TypeError, ValueError):
            mid = 0
        row = repo.get(mid) if mid > 0 else None
        if not row or row.get("role_key") != role_key:
            return {"ok": False, "error": f"记忆 #{mid} 不存在或不属于本角色"}
        owner = str(row.get("user_id") or "").strip()
        if owner and uid and owner != uid:
            return {"ok": False, "error": f"记忆 #{mid} 不存在或不属于本角色"}
        return {"ok": True, "memory": row}

    if action == "write":
        content = str((args or {}).get("content") or "").strip()
        type_ = str((args or {}).get("type") or "").strip()
        if not content:
            return {"ok": False, "error": "content 不能为空"}
        if type_ not in MEMORY_TYPES:
            return {"ok": False, "error": "type 必须是：" + "、".join(MEMORY_TYPES)}
        if not uid:
            return {"ok": False, "error": "缺少用户上下文：对话写入的记忆归属当前用户，无法确定用户时不写入"}
        active = _ordered_rows(repo, role_key, uid)
        for r in active:
            if str(r.get("content") or "").strip() == content:
                return {"ok": False, "error": f"已有相同记忆 #{r['id']}，无需重复写入",
                        "duplicate_of": r["id"]}
        row = repo.add(role_key, type_, content, source="auto", user_id=uid, provenance={
            "via": "memory_tool", "thread_id": str(ctx.get("thread_id") or "")[:120],
            "user": uid[:120],
        })
        if not row:
            return {"ok": False, "error": "写入失败"}
        repo.enforce_cap(role_key, MAX_PER_ROLE, user_id=uid)
        return {"ok": True, "memory": {"id": row["id"], "type": row["type"], "content": row["content"]}}

    if action == "retire":
        try:
            mid = int((args or {}).get("id") or 0)
        except (TypeError, ValueError):
            mid = 0
        row = repo.get(mid) if mid > 0 else None
        if not row or row.get("role_key") != role_key:
            return {"ok": False, "error": f"记忆 #{mid} 不存在或不属于本角色"}
        if not str(row.get("user_id") or "").strip():
            return {"ok": False, "error": f"记忆 #{mid} 属公共域，由管理面维护（对话中不可失效）"}
        owner = str(row.get("user_id") or "").strip()
        if owner != uid:
            return {"ok": False, "error": f"记忆 #{mid} 不存在或不属于本角色"}
        retired = repo.retire(mid)
        if retired is None:
            return {"ok": False, "error": f"记忆 #{mid} 是置顶/手工条目，工具无权失效（管理面处理）"}
        return {"ok": True, "retired": mid,
                "reason": str((args or {}).get("reason") or "")[:200]}

    return {"ok": False, "error": "action 必须是：list、view、write、retire"}


# ── 空闲期整理（sleep-time lite：低频归并，管理面触发/一次性清洗）─────────────

async def consolidate_role(role_key: str) -> dict:
    """对某角色**公共域**的活跃记忆跑一次 LLM 归并案 + 确定性落库。

    只整理公共域（治理面视角）；用户私有域靠容量封顶+对话内 retire 自然代谢。
    ops 契约：merge（多条合一，旧条目打戳 superseded_by 新条）/ retype（改分型）/
    retire（过时/一次性污染打戳）。钉死集条目只读不改；LLM 失败返回 {"ok": False}。
    """
    role_key = str(role_key or "").strip()
    if not role_key:
        return {"ok": False, "error": "role_key 不能为空"}
    repo = ColleagueMemoryRepository()
    rows = repo.list_by_role(role_key, limit=1000, public_only=True)
    if not rows:
        return {"ok": True, "applied": 0, "note": "无活跃记忆"}

    from app.services import llm_client
    from app.services.ai_colleague_service import get_colleague
    system_prompt = str((get_colleague(role_key) or {}).get("system_prompt") or "").strip()
    if not system_prompt:
        return {"ok": False, "error": f"同事 {role_key} 无 system_prompt，跳过整理"}
    type_options = "、".join(f"{key}={label}" for key, label in TYPE_LABELS.items())
    listing = "\n".join(
        f"- #{m['id']} [{m.get('type')}] {m.get('content')}"
        + ("（置顶/手工，勿动）" if _is_durable(m) else "")
        for m in rows)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": (
            f"以下是你（role_key={role_key}）的长期记忆公共域清单（全员共享，不含用户私有记忆）。请做卫生整理：\n"
            f"1) 语义重复/可合并的条目提 merge（ids=旧条目 id 列表，content=合并后的一句话，type=分型）；\n"
            f"2) 分型错误的提 retype；\n"
            f"3) 一次性任务、会话态残留、已过时的提 retire（附 reason）。\n"
            f"标记「置顶/手工勿动」的条目不得出现在任何 op 里。\n"
            f"记忆类型取值：{type_options}。\n\n{listing}\n\n"
            '只输出 JSON：{"ops": [{"op": "merge|retype|retire", ...}]}；无需整理输出 {"ops": []}。'
        )},
    ]
    try:
        result = await llm_client.chat_json(
            messages, temperature=0.1, timeout=60.0, max_attempts=1, reasoning_effort="low")
    except Exception as e:
        logger.warning("记忆整理 LLM 调用失败 role=%s: %s", role_key, e)
        return {"ok": False, "error": f"LLM 调用失败：{e}"}
    ops = result.get("ops") if isinstance(result, dict) else None
    if not isinstance(ops, list):
        return {"ok": False, "error": "LLM 未返回合法 ops"}

    active = {int(m["id"]): m for m in rows}
    durable_ids = {mid for mid, m in active.items() if _is_durable(m)}
    applied: list = []
    skipped: list = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op") or "").strip().lower()
        ids = [int(i) for i in (op.get("ids") or []) if str(i).isdigit()]
        try:
            single = int(op.get("id") or 0)
        except (TypeError, ValueError):
            single = 0
        targets = [i for i in (ids or ([single] if single else [])) if i in active]
        bad = [i for i in (ids or ([single] if single else [])) if i not in active]
        if bad:
            skipped.append(f"unknown:{bad}")
        if not targets:
            continue
        if any(i in durable_ids for i in targets):
            skipped.append(f"durable:{targets}")
            continue
        if kind == "merge" and len(targets) >= 2:
            content = str(op.get("content") or "").strip()
            type_ = str(op.get("type") or "").strip()
            if content and type_ in MEMORY_TYPES:
                new_row = repo.add(role_key, type_, content, source="auto", provenance={
                    "via": "consolidation", "merged_ids": targets})
                if new_row:
                    for i in targets:
                        repo.retire(i, superseded_by=new_row["id"])
                    applied.append(f"merge{targets}->#{new_row['id']}")
        elif kind == "retype" and len(targets) == 1:
            type_ = str(op.get("type") or "").strip()
            if type_ in MEMORY_TYPES:
                repo.update(targets[0], {"type": type_})
                applied.append(f"retype#{targets[0]}->{type_}")
        elif kind == "retire":
            for i in targets:
                if repo.retire(i) is not None:
                    applied.append(f"retire#{i}")
    repo.enforce_cap(role_key, MAX_PER_ROLE)
    if applied:
        logger.info("记忆整理 role=%s applied=%s skipped=%s", role_key, applied, skipped)
    return {"ok": True, "applied": len(applied), "ops": applied, "skipped": skipped,
            "total_before": len(rows)}
