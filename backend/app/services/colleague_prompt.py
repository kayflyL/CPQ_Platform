# -*- coding: utf-8 -*-
"""AI 同事回合的「配置 / 提示词组装」层。

从 colleague_turn_service.py 拆出（2026-09-11，零行为改动）：回答「这个同事有什么能力、
能用哪些工具、系统提示词怎么拼、短期记忆取多少」。回合编排壳（colleague_turn_service）
与回合执行器（colleague_turn_runners）都从这里取事实，不各自重算。

注意：提示词**文本**不在这里——只做组装；文本唯一出处=员工自身 system_prompt
+ 编辑器左栏任务规则（见 docs 宪法条款 C1；节点抽屉 2026-09-12 起只留机制配置）。
"""
from __future__ import annotations

import asyncio
from typing import Optional

from app.repository.skill_catalog_repo import SkillCatalogRepository
from app.repository.system_config_repo import SystemConfigRepository
from app.services.agent_tool_specs import tool_required_data_sources
from app.services.ai_colleague_service import colleague_tool_ids, effective_data_sources
from app.services.skill_types import is_capability_skill, is_workflow_skill


def _skill_library() -> dict:
    repo = SkillCatalogRepository()
    try:
        items = repo.list()
    except Exception:
        items = []
    finally:
        repo.close()
    return {
        str(item.get("key") or "").strip(): item
        for item in items
        if isinstance(item, dict) and str(item.get("key") or "").strip()
    }


def _resolved_skills(colleague: Optional[dict]) -> list:
    if not isinstance(colleague, dict):
        return []
    refs: list = []
    for name in ("skills", "workflows"):
        raw = colleague.get(name)
        if isinstance(raw, list):
            refs.extend(raw)
    if not refs:
        return []
    library = _skill_library()
    resolved: list = []
    for ref in refs:
        if isinstance(ref, str):
            key = ref.strip()
            overrides: dict = {}
        elif isinstance(ref, dict):
            key = str(ref.get("key") or "").strip()
            overrides = ref
        else:
            continue
        if not key or overrides.get("enabled") is False:
            continue
        skill = library.get(key) or {"key": key, "name": key}
        merged = dict(skill)
        merged.update({k: v for k, v in overrides.items() if k != "key" and v is not None})
        resolved.append(merged)
    return resolved


def _has_workflow_skills(colleague: Optional[dict]) -> bool:
    return any(
        is_workflow_skill(skill)
        and bool(str(skill.get("workflow_key") or skill.get("key") or "").strip())
        for skill in _resolved_skills(colleague)
    )


def _effective_tool_ids(colleague: Optional[dict]) -> list:
    allowed = colleague_tool_ids(colleague)
    skill_tools: list = []
    for skill in _resolved_skills(colleague):
        tools = skill.get("tool_ids") or []
        if isinstance(tools, list):
            skill_tools.extend([str(t) for t in tools if str(t)])
    if allowed is None:
        return list(dict.fromkeys(skill_tools))
    return list(dict.fromkeys([str(t) for t in allowed if str(t)] + skill_tools))


def _effective_data_sources(colleague: Optional[dict], tool_ids: Optional[list] = None) -> list:
    """数据域 = 角色自身数据权限 + 当前可用工具所需数据权限（绑定 Skill 自动授权）。"""
    sources = set(effective_data_sources(colleague))
    sources.update(tool_required_data_sources(tool_ids))
    return sorted(sources)


def build_chat_config(colleague: Optional[dict] = None) -> dict:
    """Same config contract as assistant chat, used by this unified runtime."""
    try:
        repo = SystemConfigRepository()
        try:
            cfg = repo.get_value("ai_assistant_config", {}) or {}
        finally:
            repo.close()
    except Exception:
        cfg = {}
    if colleague:
        prompt = str(colleague.get("system_prompt") or "").strip()
        profile = colleague.get("response_profile") if isinstance(colleague.get("response_profile"), dict) else {}
        style = profile.get("style") or colleague.get("response_style") or cfg.get("response_style") or "detailed"
        if not prompt:
            prompt = str(cfg.get("chat_system_prompt") or "").strip()
    else:
        prompt = str(cfg.get("chat_system_prompt") or "").strip()
        profile = cfg.get("response_profile") if isinstance(cfg.get("response_profile"), dict) else {}
        style = profile.get("style") or cfg.get("response_style") or "detailed"
    return {"chat_system_prompt": prompt, "response_style": style, "response_profile": profile}


def _style_hint(chat_cfg: dict) -> str:
    profile = chat_cfg.get("response_profile") if isinstance(chat_cfg.get("response_profile"), dict) else {}
    style_prompt = str(profile.get("style_prompt") or "").strip()
    if style_prompt:
        return style_prompt
    if chat_cfg.get("response_style") == "brief":
        return "回复风格：简洁，尽量要点化，避免冗长。"
    return "回复风格：详细，尽量完整、结构化。"


def _skill_prompt(colleague: Optional[dict]) -> str:
    skills = [
        skill for skill in _resolved_skills(colleague)
        if is_capability_skill(skill)
    ]
    if not skills:
        return ""
    lines = []
    for skill in skills:
        name = str(skill.get("name") or skill.get("key") or "").strip()
        prompt = str(skill.get("prompt") or skill.get("description") or "").strip()
        if not prompt and not name:
            continue
        key = str(skill.get("key") or "").strip()
        text = f"[技能] {name or key}" + (f"（skill_key={key}）" if key else "")
        if prompt:
            text += f"：{prompt}"
        lines.append(text)
    return "同事已启用技能：\n" + "\n".join(lines)


def _workflow_hint(colleague: Optional[dict]) -> str:
    """给普通对话的角色一份「可用工作流」索引，供其自然建议，而非自动发起。"""
    skills = [
        skill for skill in _resolved_skills(colleague)
        if is_workflow_skill(skill)
        and bool(str(skill.get("workflow_key") or skill.get("key") or "").strip())
    ]
    if not skills:
        return ""
    lines = []
    for skill in skills:
        name = str(skill.get("name") or skill.get("key") or "").strip()
        desc = str(skill.get("description") or skill.get("prompt") or "").strip()
        key = str(skill.get("workflow_key") or skill.get("key") or "").strip()
        line = f"- {name or key}"
        if desc:
            line += f"：{desc}"
        lines.append(line)
    return ("本角色可发起的工作流（用户通过输入框旁「+」显式选择发起）：\n"
            + "\n".join(lines))


def _handoff_hint(colleague: Optional[dict]) -> str:
    """私聊转接建议提示（2026-08-30 定调：系统转接只发生在团队群；私聊由角色口头提议）。

    名册=DB 业务数据（colleague_roster_digest，与转接判官共用单源）；转接不在这里下规则——
    该怎么转由各员工自身的提示词（Manage Teams · 员工）承担。
    """
    from app.services.ai_colleague_service import colleague_roster_digest
    self_key = str((colleague or {}).get("role_key") or "").strip()
    lines = []
    for c in colleague_roster_digest():
        if str(c.get("role_key") or "") == self_key:
            continue
        duty = str(c.get("职责") or "").strip()
        skills = "、".join(str(s) for s in (c.get("skills") or []) if str(s))
        desc = "；".join(x for x in (duty, skills) if x)
        lines.append(f"- {c.get('name') or c.get('role_key')}" + (f"：{desc}" if desc else ""))
    if not lines:
        return ""
    return "【同事转接】在册同事（转接参考）：\n" + "\n".join(lines)


def _memory_policy(colleague: Optional[dict]) -> dict:
    if isinstance(colleague, dict):
        policy = colleague.get("memory_policy")
        if isinstance(policy, dict):
            return {k: v for k, v in policy.items() if k != "long_term_store"}
    return {
        "enabled": True,
        "short_term_max_turns": 12,
        "query_recent": 6,
        "save_after_turn": True,
        "auto_memory": True,
    }


def _short_term_history(colleague: Optional[dict], history: list) -> list:
    if not isinstance(history, list):
        return []
    try:
        max_turns = int(_memory_policy(colleague).get("short_term_max_turns") or 0)
    except (TypeError, ValueError):
        max_turns = 0
    if max_turns > 0:
        return history[-max_turns:]
    return history


def _skill_for_tool(colleague: Optional[dict], tool_name: str) -> dict:
    if not tool_name:
        return {}
    for skill in _resolved_skills(colleague):
        tools = skill.get("tool_ids") or []
        if isinstance(tools, list) and tool_name in [str(t) for t in tools]:
            return skill
    return {}


async def _memory_block(colleague: Optional[dict], user_text: str) -> str:
    policy = _memory_policy(colleague)
    if policy.get("enabled") is False:
        return ""
    try:
        limit = max(1, min(int(policy.get("query_recent") or 6), 20))
    except (TypeError, ValueError):
        limit = 6
    role_key = (colleague or {}).get("role_key") or "assistant"
    from app.services import colleague_memory_service
    return await asyncio.to_thread(colleague_memory_service.memory_block, role_key, limit)


def _user_name(user: Optional[dict]) -> str:
    return str((user or {}).get("name") or (user or {}).get("user_id") or "用户").strip() or "用户"


def _schedule_memory_extraction(colleague: Optional[dict], user_name: str,
                                user_text: str, final_text: str) -> None:
    """回复完成后后台抽取结构化记忆（fire-and-forget，失败静默不影响主流程）。"""
    policy = _memory_policy(colleague)
    if policy.get("enabled") is False or policy.get("save_after_turn") is False:
        return
    if policy.get("auto_memory") is False:
        return
    role_key = (colleague or {}).get("role_key") or "assistant"
    from app.services import colleague_memory_service
    colleague_memory_service.schedule_extraction(role_key, user_name, user_text, final_text)


def _base_messages(
    colleague: Optional[dict],
    user_text: str,
    context_summary: Optional[str],
    history: list,
    memory_block: str,
) -> list:
    chat_cfg = build_chat_config(colleague)
    history = _short_term_history(colleague, history)
    parts = [chat_cfg["chat_system_prompt"], _style_hint(chat_cfg)]
    skill_prompt = _skill_prompt(colleague)
    if skill_prompt:
        parts.append(skill_prompt)
    workflow_hint = _workflow_hint(colleague)
    if workflow_hint:
        parts.append(workflow_hint)
    handoff = _handoff_hint(colleague)
    if handoff:
        parts.append(handoff)
    if memory_block:
        parts.append(memory_block)
    messages: list = [{"role": "system", "content": "\n\n".join(parts)}]
    if context_summary:
        messages.append({"role": "user", "content": f"[当前上下文]\n{context_summary}"})
        messages.append({"role": "assistant", "content": "收到，我会基于这个上下文作答。"})
    for m in history:
        role = (m or {}).get("role")
        content = (m or {}).get("content")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_text})
    return messages
