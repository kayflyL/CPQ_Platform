"""Skill 触发路由：只由 LLM 根据 Skill 的 name/description 判断是否调用。"""
from __future__ import annotations

import logging
from typing import Optional

from app.services import llm_client

logger = logging.getLogger(__name__)


def _workflow_skills(skills: list) -> list:
    return [
        skill for skill in (skills or [])
        if isinstance(skill, dict)
        and str(skill.get("type") or "").strip() == "workflow"
        and bool(str(skill.get("workflow_key") or skill.get("key") or "").strip())
    ]


_ROUTER_SYSTEM_PROMPT = (
    "你是技能路由决策器。根据用户当前输入和对话上下文，判断是否需要调用候选技能。"
    "你只做选择，不要执行业务，不要编造候选之外的 key。"
    "只有用户已经明确表达“要配置服务器并产出 BOM/方案”时，才触发需求分析类技能；"
    "普通聊天、只问目录、比价、技术科普、闲聊都返回空字符串，交给普通对话继续处理。"
    "如果需要调用，返回最合适的一个技能 key；否则 skill_key 返回空字符串。"
)


async def route_skill_llm(
    skills: list,
    current_text: str,
    conversation_text: str,
    model: Optional[str] = None,
) -> Optional[dict]:
    """LLM 选择 Skill；LLM 不可用或调用失败时不触发任何 Skill。"""
    candidates = _workflow_skills(skills)
    if not candidates:
        return None

    candidate_lines = []
    for skill in candidates:
        key = str(skill.get("workflow_key") or skill.get("key") or "").strip()
        name = str(skill.get("name") or key).strip()
        description = str(skill.get("description") or "").strip() or "暂无说明"
        candidate_lines.append(f"- key: {key}\n  name: {name}\n  description: {description}")

    messages = [
        {"role": "system", "content": _ROUTER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "候选技能：\n"
                + "\n".join(candidate_lines)
                + "\n\n当前消息：\n"
                + (current_text or "").strip()
                + "\n\n对话上下文：\n"
                + (conversation_text or "").strip()
                + '\n\n只输出 JSON：{"skill_key":"", "reason":""}'
            ),
        },
    ]

    try:
        data = await llm_client.chat_json(
            messages,
            model=model,
            temperature=0,
            timeout=20.0,
            max_attempts=1,
        )
    except Exception as exc:
        logger.debug("skill router LLM failed: %s", exc)
        return None

    if isinstance(data, dict) and "skill_key" in data:
        selected = str(data.get("skill_key") or "").strip()
        if not selected:
            return None
        for skill in candidates:
            key = str(skill.get("workflow_key") or skill.get("key") or "").strip()
            if key == selected:
                return {"skill": skill, "rule": None, "priority": None, "source": "llm"}

    return None


def conversation_text(history: list, limit: int = 8) -> str:
    """把最近消息压缩成路由可匹配的会话文本。"""
    parts: list[str] = []
    items = history[-limit:] if isinstance(history, list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("role") or "").lower() in ("assistant", "system"):
            continue
        content = item.get("content") or item.get("text") or ""
        if str(content).strip():
            parts.append(str(content).strip())
    return "\n".join(parts)
