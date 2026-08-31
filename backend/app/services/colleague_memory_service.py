"""同事结构化记忆服务（Claude Code 式分型记忆 + Mem0 式抽取归并）。

- memory_block：按类型分组注入 system prompt（置顶优先，有条数上限）
- extract_and_reconcile：每轮回复后 fire-and-forget，LLM 从本轮对话抽候选
  事实并对存量做 ADD/UPDATE/DELETE 归并；失败静默（记忆是增强不是依赖）
"""
import asyncio
import logging
from typing import Optional

from app.models.colleague_memory import MEMORY_TYPES, TYPE_LABELS
from app.repository.colleague_memory_repo import ColleagueMemoryRepository

logger = logging.getLogger(__name__)

PROMPT_LIMIT = 30
MAX_PER_ROLE = 100

_EXTRACT_SYSTEM = """你是同事记忆管理员。从一段对话里判断是否产生了值得长期记住的信息，并对该同事现有的记忆清单做归并。

只记（分四类）：
- user_profile 用户画像：客户/用户是谁、角色、公司、团队结构等稳定事实
- preference 偏好反馈：用户明确表达的喜好或纠正（如"以后方案默认按国产化平台配"、"别再推荐8T盘"）
- business_fact 业务事实：业务规则/约束/背景（如"报价默认含三年质保"、"主力推 Orion 系列"）
- guide 行为指引：对该同事行为方式的要求（如"先给结论再展开"）

不记：闲聊、寒暄、一次性的过程信息（本轮在配什么型号）、对话里已存在的重复信息。

归并规则：新信息与现有条目语义相同→noop 或 update（改写得更准）；矛盾→update 旧条目；用户明确收回/否定→delete。
输出只能是 JSON：{"ops": [{"op": "add|update|delete|noop", "id": 现有条目id(update/delete必填), "type": 四类之一, "content": "一句压缩事实(≤80字)"}]}，无值得记的输出 {"ops": []}。"""


def memory_block(role_key: str, limit: int = PROMPT_LIMIT) -> str:
    """同事记忆 → system prompt 注入块；置顶优先、按类型分组。"""
    rows = ColleagueMemoryRepository().list_by_role(role_key, limit=limit)
    if not rows:
        return ""
    grouped: dict = {}
    for r in rows:
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


async def extract_and_reconcile(role_key: str, user_name: str,
                                user_text: str, assistant_text: str) -> None:
    """后台抽取归并一轮对话。调用方用 asyncio.create_task fire-and-forget。"""
    role_key = str(role_key or "").strip()
    u = str(user_text or "").strip()
    a = str(assistant_text or "").strip()
    if not role_key or (not u and not a):
        return
    repo = ColleagueMemoryRepository()
    existing = repo.list_by_role(role_key, limit=200)
    try:
        from app.services import llm_client
        existing_lines = "\n".join(
            f"- #{m['id']} [{m.get('type')}] {m.get('content')}" for m in existing
        ) or "（暂无）"
        messages = [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {"role": "user", "content": (
                f"同事 role_key={role_key}\n用户：{user_name or '未知用户'}\n\n"
                f"现有记忆清单：\n{existing_lines}\n\n"
                f"本轮对话：\n用户说：{u[:2000]}\n同事回复：{a[:2000]}\n\n请输出归并 ops。"
            )},
        ]
        result = await llm_client.chat_json(
            messages, temperature=0.1, timeout=30.0, max_attempts=1,
            reasoning_effort="low",
        )
        ops = result.get("ops") if isinstance(result, dict) else None
        if not isinstance(ops, list):
            return
        applied = _apply_ops(repo, role_key, ops, existing)
        if applied:
            repo.enforce_cap(role_key, MAX_PER_ROLE)
            logger.info("同事记忆归并 role=%s ops=%s", role_key, applied)
    except Exception:
        logger.exception("同事记忆抽取失败 role=%s（静默，不影响主流程）", role_key)


def _apply_ops(repo: ColleagueMemoryRepository, role_key: str,
               ops: list, existing: list) -> list:
    known_ids = {int(m["id"]) for m in existing}
    known_contents = {str(m.get("content") or "").strip() for m in existing}
    applied: list = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        kind = str(op.get("op") or "").strip().lower()
        content = str(op.get("content") or "").strip()
        try:
            mid = int(op.get("id") or 0)
        except (TypeError, ValueError):
            mid = 0
        if kind == "add" and content and content not in known_contents:
            row = repo.add(role_key, str(op.get("type") or ""), content, source="auto")
            if row:
                known_contents.add(content)
                applied.append(f"add#{row['id']}")
        elif kind == "update" and mid in known_ids and content:
            row = repo.update(mid, {"content": content})
            if row:
                known_contents.add(content)
                applied.append(f"update#{mid}")
        elif kind == "delete" and mid in known_ids:
            if repo.delete(mid):
                applied.append(f"delete#{mid}")
    return applied


def schedule_extraction(role_key: str, user_name: str,
                        user_text: str, assistant_text: str) -> Optional[asyncio.Task]:
    """fire-and-forget 包装：后台跑抽取，任何异常都吞在任务里。"""
    try:
        return asyncio.create_task(
            extract_and_reconcile(role_key, user_name, user_text, assistant_text)
        )
    except Exception:
        logger.exception("同事记忆抽取调度失败 role=%s", role_key)
        return None
