# -*- coding: utf-8 -*-
"""Unified AI-colleague turn runtime.

Every office-colleague chat entry point reaches this service instead of
hardcoded keyword branches. A colleague with tools runs a text-ReAct loop;
a colleague without tools streams a normal conversation. Tool results that
represent draft/write actions are parked in the office governance queue and
must be confirmed before continuing.
"""
from __future__ import annotations

import asyncio
import logging
import json
import time
from typing import Any, Callable, Optional

from app.repository.assistant_repo import AssistantRepository
from app.repository.skill_catalog_repo import SkillCatalogRepository
from app.repository.system_config_repo import SystemConfigRepository
from app.services import llm_client
from app.services.agent_react import run_react_loop
from app.services.agent_tool_specs import tool_requires_approval, tool_required_data_sources
from app.services.ai_colleague_service import colleague_tool_ids, effective_data_sources, get_ai_colleague_config
from app.services.assistant_hub import assistant_hub
from app.services.llm_client import LLMError
from app.services.office_events import publish_office_event
from app.services.office_governance import office_governance
from app.services.office_mission import record_mission
from app.services.office_access import allowed_chat_role_keys
from app.services.skill_contracts import (
    SKILL_SESSION_ACTIVE,
    SKILL_SESSION_IDLE,
    SKILL_SESSION_PROPOSING,
)
from app.services.skill_registry import resolve_skill_manifest

logger = logging.getLogger(__name__)

_DEFAULT_CHAT_SYSTEM_PROMPT = (
    "你是 CPQ 平台的 AI 同事，辅助用户完成商机、配置、成本与报价相关工作。"
    "你是对话中的协作者，先理解用户意图，再决定是否需要调用系统工具；"
    "信息不足时应像真人一样反问最关键的问题，不要一看到关键词就机械进入业务流程。"
    "要求：用中文回复；对料号、价格、库存、具体型号等易变信息不要编造，"
    "不确定时明确说明并请用户确认。"
)


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
    refs = colleague.get("skills")
    if not isinstance(refs, list):
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
        str(skill.get("type") or "").strip() == "workflow"
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
            prompt = str(cfg.get("chat_system_prompt") or "").strip() or _DEFAULT_CHAT_SYSTEM_PROMPT
    else:
        prompt = str(cfg.get("chat_system_prompt") or "").strip() or _DEFAULT_CHAT_SYSTEM_PROMPT
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
        if str(skill.get("type") or "").strip() != "workflow"
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


def _handoff_hint(colleague: Optional[dict]) -> str:
    """私聊转接建议提示（2026-08-30 定调：系统转接只发生在团队群；私聊由角色口头提议）。

    名册=DB 业务数据（colleague_roster_digest，与转接判官共用单源）；
    规则=提示词契约层——自己能办的自己办，缺 skill/工具/数据时建议一位合适同事，由客户决定。
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
    return (
        "【同事转接建议】在册同事（转接建议参考）：\n" + "\n".join(lines) + "\n"
        "你的 skill、工具、数据能覆盖的请求一律自己完成，不要推给同事。"
        "只有请求确实超出你的能力范围（没有对应的 skill、工具或数据）时，才说明哪部分你办不了，"
        "并按名册职责建议一位更合适的同事，由客户决定（团队群里 @ 点名，或从通讯录直接找 TA）；"
        "一次最多建议一位，禁止把客户推来推去。"
    )


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


async def _persist_and_broadcast(
    thread_id: str,
    colleague: Optional[dict],
    final_text: str,
    *,
    final_office_event: Optional[dict] = None,
) -> None:
    role_key = (colleague or {}).get("role_key") or "assistant"
    repo = AssistantRepository()
    try:
        asst = repo.add_message(
            thread_id=thread_id,
            role="assistant",
            content=final_text,
            colleague_role_key=(colleague or {}).get("role_key"),
        )
    except Exception:
        logger.exception("colleague reply persistence failed")
        asst = None
    finally:
        repo.close()
    await assistant_hub.broadcast(thread_id, {"type": "done", "message": asst})

    if final_office_event:
        try:
            await publish_office_event(
                final_office_event.get("role_key") or role_key,
                final_office_event.get("status") or "done",
                final_office_event.get("activity") or "回复完成",
                message=final_office_event.get("message") or final_text[:160],
                zone=final_office_event.get("zone"),
                intent=final_office_event.get("intent"),
                thread_id=thread_id,
                priority="user",
                source="assistant_chat",
            )
        except Exception:
            logger.exception("final office event publish failed")


def _add_assistant_message(
    thread_id: str,
    colleague: Optional[dict],
    content: str,
    *,
    kind: str = "text",
    data: Optional[str] = None,
) -> Optional[dict]:
    """把结构化 AI 回复落进 assistant 会话，供所有聊天入口重放。"""
    repo = AssistantRepository()
    try:
        return repo.add_message(
            thread_id=thread_id,
            role="assistant",
            content=content,
            kind=kind,
            data=data,
            colleague_role_key=(colleague or {}).get("role_key"),
        )
    except Exception:
        logger.exception("colleague structured message persistence failed")
        return None
    finally:
        repo.close()


async def _trace(trace_sink: Optional[Callable[..., None]], **kwargs: Any) -> None:
    if not trace_sink:
        return
    try:
        trace_sink(**kwargs)
    except Exception:
        logger.exception("colleague turn trace failed")


def _ensure_ai_office_opportunity(
    thread_id: str,
    user: Optional[dict],
    requirement_text: str,
) -> str:
    """为 AI Office 会话创建一条隐藏的内部商机，用于承载真实四步表单数据。"""
    import uuid

    from app.repository.opportunity_repo import OpportunityRepository

    user_name = str((user or {}).get("name") or (user or {}).get("user_id") or "用户").strip() or "用户"
    snippet = (requirement_text or "").strip().replace("\n", " ")[:24] or "AI 办公室会话"
    opportunity_id = f"ai-{uuid.uuid4().hex[:24]}"

    opp_repo = OpportunityRepository()
    try:
        opp_repo.create_or_update_opportunity(
            opportunity_id,
            {
                "customer_name": f"{user_name} · {snippet}",
                "sales_person": user_name,
                "owner_user_id": str((user or {}).get("user_id") or "") or None,
                "fae": "",
                "quotation_person": "",
                "industry": "",
                "order_type": "",
            },
        )
        # 内部商机暂不进入「我的商机列表」；转真实商机时再改为 active。
        opp_repo.update_meta(opportunity_id, {"status": "ai_office"})
    finally:
        opp_repo.close()

    repo = AssistantRepository()
    try:
        repo.update_thread_opportunity_id(thread_id, opportunity_id)
    finally:
        repo.close()
    return opportunity_id


async def _broadcast_chat_progress(
    thread_id: str,
    colleague: Optional[dict],
    step: str,
    status: str,
    text: str,
    *,
    kind: str = "text",
    data: Optional[str] = None,
) -> None:
    if not text:
        return
    message = _add_assistant_message(thread_id, colleague, text, kind=kind, data=data)
    await assistant_hub.broadcast(thread_id, {
        "type": "chat_progress",
        "step": step,
        "status": status,
        "message": message,
    })


async def _run_plain_turn(
    thread_id: str,
    user_text: str,
    context_summary: Optional[str],
    history: list,
    colleague: Optional[dict],
    memory_block: str,
    final_office_event: Optional[dict],
    trace_sink: Optional[Callable[..., None]],
    user: Optional[dict] = None,
) -> None:
    role_key = (colleague or {}).get("role_key") or "assistant"
    messages = _base_messages(colleague, user_text, context_summary, history, memory_block)
    prompt_chars = sum(len(str(m.get("content") or "")) for m in messages)
    started = time.perf_counter()
    final_text: Optional[str] = None
    trace_status = "ok"
    trace_error = None
    try:
        profile = build_chat_config(colleague).get("response_profile") or {}
        temperature = profile.get("temperature")
        max_tokens = profile.get("max_tokens")
        # 普通对话也走流式思考：reasoning → thinking，正文 → chunk（ChatGPT 式白盒）
        await assistant_hub.broadcast(thread_id, {"type": "chat_status", "text": "思考中…"})
        full: list = []
        async for item in llm_client.stream_agent_chat(
            messages,
            model=(colleague or {}).get("model_override") or None,
            temperature=temperature if isinstance(temperature, (int, float)) else None,
            max_tokens=max_tokens if isinstance(max_tokens, int) and max_tokens > 0 else None,
        ):
            item_type = item.get("type")
            delta = item.get("delta") or ""
            if item_type == "reasoning":
                if delta:
                    await assistant_hub.broadcast(thread_id, {"type": "thinking", "text": delta})
            elif item_type == "content":
                full.append(delta)
                await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": delta})
        final_text = "".join(full) or "(空回复)"
    except LLMError as e:
        trace_status = "llm_error"
        trace_error = str(e)
        final_text = (
            f"⚠️ 模型调用失败：{e}\n\n"
            "请到「AI 设置 → 模型与连接」检查端点 / Key / 模型名，"
            "可用「测试连接」按钮定位具体原因。"
        )
        await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": final_text})
        await publish_office_event(role_key, "error", "模型调用失败", message=final_text[:160], thread_id=thread_id)

    _schedule_memory_extraction(colleague, _user_name(user), user_text, final_text or "")
    await publish_office_event(role_key, "done", "回复完成", message=final_text[:160], thread_id=thread_id)
    await _trace(
        trace_sink,
        tool_name="colleague_llm",
        status=trace_status,
        duration_ms=int((time.perf_counter() - started) * 1000),
        thread_id=thread_id,
        response_chars=len(final_text or ""),
        error=trace_error,
        model=(colleague or {}).get("model_override"),
        prompt_chars=prompt_chars,
        node_type="colleague_llm",
        role_key=role_key,
    )
    await _persist_and_broadcast(thread_id, colleague, final_text or "(空回复)", final_office_event=final_office_event)


def _first_workflow_skill(colleague: Optional[dict]) -> Optional[dict]:
    """取当前角色第一个 workflow skill 的本地绑定信息；没有返回 None。"""
    for skill in _resolved_skills(colleague):
        if str(skill.get("type") or "").strip() == "workflow":
            return skill
    return None


def _skill_phase_hint(skill_manifest: Optional[dict], phase: Optional[str]) -> str:
    """把 skill 能力描述转成同一大脑回合内的一段阶段指令。

    这里只提供“当前是否该提交”的业务约束，不再单独发起意图判断或确认判断 LLM。
    分态（2026-09-02，进任务前不碰节点内容）：IDLE 只给能力级描述；PROPOSING 才给
    流程步骤预告（单源 skill_steps_view，与 pipeline_start 同一份画布配置）；
    ACTIVE（任务进行中/试运行直启）给任务态指令（文本存 DB active_hint，提示词面板可改）。
    """
    if not isinstance(skill_manifest, dict) or phase not in (
            SKILL_SESSION_IDLE, SKILL_SESSION_PROPOSING, SKILL_SESSION_ACTIVE):
        return ""
    name = str(skill_manifest.get("name") or skill_manifest.get("skill_key") or "").strip()
    desc = str(skill_manifest.get("description") or skill_manifest.get("prompt") or "").strip()
    if phase == SKILL_SESSION_IDLE:
        return (
            "\n\n当前可用流程："
            + (name or "未命名流程")
            + ("。流程能力描述：" + desc if desc else "")
            + "。如果用户当前需求与这个流程匹配，请先根据用户真实说过的话总结需求，"
            + "然后询问用户是否确认按这个理解开始流程。用户确认前不要调用 submit_registration。"
        )
    if phase == SKILL_SESSION_ACTIVE:
        try:
            from app.services.skill_prompts import load_skill_prompts
            active_hint = str(load_skill_prompts().get("active_hint") or "").strip()
        except Exception:
            logger.exception("任务态指令读取失败")
            active_hint = ""
        return ("\n\n" + active_hint) if active_hint else ""
    steps_preview = ""
    try:
        from app.services.skill_plan_runtime import skill_steps_view
        from app.services.skill_prompts import load_skill_prompts
        steps = skill_steps_view(dict(skill_manifest.get("node_configs") or {}), user_facing_only=True)
        if steps:
            step_lines = "\n".join(
                f"- {s.get('label')}" + (f"：{s.get('description')}" if s.get("description") else "")
                for s in steps)
            preview_tpl = str(load_skill_prompts().get("plan_rule") or "")
            steps_preview = preview_tpl.replace("<<STEPS>>", step_lines)
    except Exception:
        logger.exception("流程预告组装失败")
    return (
        "\n\n上一轮你已经请用户确认是否开始流程。请判断用户最新回复："
        "确认开始就调用 submit_registration；用户仍在补充或纠正需求，则继续澄清，不要提交。"
        + (("\n" + steps_preview) if steps_preview else "")
    )


async def _run_tool_turn(
    thread_id: str,
    user_text: str,
    context_summary: Optional[str],
    history: list,
    colleague: Optional[dict],
    memory_block: str,
    allowed_tool_ids: list,
    final_office_event: Optional[dict],
    trace_sink: Optional[Callable[..., None]],
    user: Optional[dict] = None,
    opportunity_id: Optional[str] = None,
    option_slot: Optional[str] = None,
) -> None:
    role_key = (colleague or {}).get("role_key") or "assistant"
    history = _short_term_history(colleague, history)
    chat_cfg = build_chat_config(colleague)
    system_prompt = "\n\n".join([chat_cfg["chat_system_prompt"], _style_hint(chat_cfg)])
    skill_prompt = _skill_prompt(colleague)
    if skill_prompt:
        system_prompt += "\n\n" + skill_prompt
    handoff = _handoff_hint(colleague)
    if handoff:
        system_prompt += "\n\n" + handoff
    if memory_block:
        system_prompt += "\n\n" + memory_block

    async def event_sink(payload: dict) -> None:
        sub = (payload or {}).get("sub") or {}
        tool = sub.get("tool")
        if (sub.get("kind") or "") == "thinking":
            _think_text = sub.get("text") or ""
            if _think_text:
                await assistant_hub.broadcast(thread_id, {"type": "thinking", "text": _think_text})
        skill = _skill_for_tool(colleague, str(tool or ""))
        office_action = skill.get("office_action") if isinstance(skill.get("office_action"), dict) else {}
        await publish_office_event(
            role_key,
            str(office_action.get("status") or "working"),
            str(office_action.get("activity") or sub.get("text") or "正在调用工具"),
            tool=tool,
            thread_id=thread_id,
            intent=str(office_action.get("intent") or ""),
            zone=str(office_action.get("zone") or ""),
        )

    async def governance_guard(name: str, args: dict, result: Any) -> Any:
        if not tool_requires_approval(name):
            return result
        skill = _skill_for_tool(colleague, name)
        office_action = skill.get("office_action") if isinstance(skill.get("office_action"), dict) else {}
        payload = {
            "role_key": role_key,
            "status": str(office_action.get("status") or "waiting_input"),
            "activity": str(office_action.get("activity") or f"等待审批：{name}"),
            "message": str(office_action.get("message") or "AI 已生成草稿，等待用户确认后再继续。"),
            "tool": name,
            "thread_id": thread_id,
            "approval_required": True,
            "priority": "user",
            "source": "colleague_turn",
            "draft": result,
            "args": args,
        }
        try:
            item = await office_governance.enqueue(payload)
            item_id = item.get("id")
        except Exception:
            logger.exception("governance enqueue failed for %s", name)
            item_id = None
        approval_text = f"AI 已生成 {name} 草稿并提交审批。审批通过后才会写入业务数据。"
        approval_msg = _add_assistant_message(
            thread_id,
            colleague,
            approval_text,
            kind="approval_required",
            data=json.dumps({
                "governance_id": item_id,
                "tool": name,
                "draft": result,
            }, ensure_ascii=False, default=str),
        )
        await assistant_hub.broadcast(thread_id, {
            "type": "approval_required",
            "governance_id": item_id,
            "tool": name,
            "message": approval_msg,
        })
        return {
            "status": "pending_approval",
            "governance_id": item_id,
            "message": "系统已生成草稿并进入审批队列，未经用户确认不会写入业务数据。",
            "draft": result,
        }

    async def downstream_guard(handoff: dict) -> Optional[dict]:
        """输出交接若指向无权限的下游 AI 角色，转成审批项，不直接调用该角色。"""
        actions = handoff.get("actions") if isinstance(handoff.get("actions"), list) else []
        allowed = allowed_chat_role_keys(user) if isinstance(user, dict) else None
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_name = str(action.get("action") or action.get("type") or "").strip()
            if action_name not in {"submit_approval", "handoff", "queue_downstream", "downstream"}:
                continue
            target_role = str(action.get("target_role") or action.get("role_key") or "").strip()
            if not target_role:
                continue
            if allowed is None or target_role in allowed:
                continue
            payload = {
                "role_key": role_key,
                "status": "waiting_approval",
                "activity": f"申请转交 {target_role}",
                "message": f"当前账号无权直接使用 {target_role}，AI 已生成草稿并提交审批。",
                "tool": "downstream_handoff",
                "thread_id": thread_id,
                "opportunity_id": opportunity_id or "",
                "approval_required": True,
                "priority": "user",
                "source": "colleague_turn",
                "draft": handoff,
                "args": {"target_role": target_role},
            }
            try:
                item = await office_governance.enqueue(payload)
                return {
                    "status": "pending_approval",
                    "governance_id": item.get("id"),
                    "target_role": target_role,
                }
            except Exception:
                logger.exception("downstream governance enqueue failed for %s", target_role)
                return {"status": "pending_approval", "governance_id": None, "target_role": target_role}
        return None

    started = time.perf_counter()
    if not allowed_tool_ids:
        await publish_office_event(role_key, "thinking", "切换普通对话", thread_id=thread_id)
        await _run_plain_turn(
            thread_id, user_text, context_summary, history, colleague, memory_block,
            final_office_event=final_office_event, trace_sink=trace_sink, user=user,
        )
        return

    profile = build_chat_config(colleague).get("response_profile") or {}
    profile_temperature = profile.get("temperature")
    profile_max_tokens = profile.get("max_tokens")
    result = await run_react_loop(
        user_text,
        {"enabled_tools": allowed_tool_ids},
        extra_context=context_summary or "",
        system_prompt=system_prompt,
        allowed_tool_ids=allowed_tool_ids,
        allowed_data_sources=_effective_data_sources(colleague, allowed_tool_ids),
        model=(colleague or {}).get("model_override") or None,
        event_sink=event_sink,
        history=history,
        tool_guard=governance_guard,
        llm_temperature=profile_temperature if isinstance(profile_temperature, (int, float)) else None,
        llm_max_tokens=profile_max_tokens if isinstance(profile_max_tokens, int) and profile_max_tokens > 0 else None,
    )
    if result.get("ok") and str(result.get("answer") or "").strip():
        final_text = str(result["answer"]).strip()
        trace_status = "ok"
        trace_error = None
    else:
        await publish_office_event(role_key, "thinking", "工具流程未收敛，切换普通对话", thread_id=thread_id)
        await _run_plain_turn(
            thread_id, user_text, context_summary, history, colleague, memory_block,
            final_office_event=final_office_event, trace_sink=trace_sink, user=user,
        )
        return

    await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": final_text})
    _schedule_memory_extraction(colleague, _user_name(user), user_text, final_text)
    await publish_office_event(role_key, "done", "回复完成", message=final_text[:160], thread_id=thread_id)
    await _trace(
        trace_sink,
        tool_name="colleague_agent",
        status=trace_status,
        duration_ms=int((time.perf_counter() - started) * 1000),
        thread_id=thread_id,
        response_chars=len(final_text),
        error=trace_error,
        model=(colleague or {}).get("model_override"),
        prompt_chars=len(system_prompt) + len(user_text),
        node_type="colleague_agent",
        role_key=role_key,
    )
    await _persist_and_broadcast(thread_id, colleague, final_text, final_office_event=final_office_event)


# ── Skill 对话路径（两器官架构）：角色=对话脑（skill_chat），引擎=纯执行 ──────────

def _skill_chat_memory_active(thread_id: str, role_key: str) -> bool:
    from app.services.skill_chat import _load_mem
    return bool(_load_mem(thread_id, role_key))


async def _run_skill_chat(thread_id, user_text, context_summary, history, colleague, memory_block,
                          final_office_event=None, trace_sink=None, user=None,
                          opportunity_id=None, option_slot=None, card_selections=None,
                          force_submit: bool = False,
                          skill_manifest: Optional[dict] = None,
                          session_phase: Optional[str] = None,
                          enable_clarity: Optional[bool] = None) -> None:
    """绑定工作流 Skill 的 AI 角色：普通聊天阶段不读 Skill 节点内容；
    force_submit=True 表示已确认/试运行/续跑，直接进入固定六步引擎，不再由模型决定是否提交。"""
    from app.services.skill_chat import load_skill_session, save_skill_session, handle_skill_chat_turn

    role_key = (colleague or {}).get("role_key") or "assistant"
    started = time.perf_counter()
    chat_cfg = build_chat_config(colleague)
    persona = "\n\n".join([chat_cfg["chat_system_prompt"], _style_hint(chat_cfg)])
    handoff = _handoff_hint(colleague)
    if handoff:
        persona += "\n\n" + handoff
    if memory_block:
        persona += "\n\n" + memory_block

    async def raw_broadcast(payload: dict) -> None:
        payload.setdefault("thread_id", thread_id)
        payload.setdefault("opportunity_id", opportunity_id or "")
        await assistant_hub.broadcast(thread_id, payload)

    # 缺口回合的旁白先于卡问题落库（历史回看顺序 = 旁白 → 缺口问题，与实时流一致）
    gap_narration_persisted = {"text": ""}

    async def emit_input_card(question: str, data: dict) -> None:
        pre = str((data or {}).pop("narration") or "").strip()
        if pre:
            await _persist_and_broadcast(thread_id, colleague, pre)
            gap_narration_persisted["text"] = pre
        option_data = json.dumps(data, ensure_ascii=False, default=str)
        await _broadcast_chat_progress(thread_id, colleague, "need_input", "question", question,
                                       kind="input_options", data=option_data)

    async def event_sink(payload: dict) -> None:
        sub = (payload or {}).get("sub") or {}
        kind = (sub.get("kind") or "")
        if kind == "thinking" and sub.get("text"):
            await assistant_hub.broadcast(thread_id, {"type": "thinking", "text": sub.get("text")})
        elif kind == "chunk" and isinstance(sub.get("delta"), str):
            # v2 流式对话：正文增量直推（前端 streamingText 逐字增长），落库文本与之严格一致
            await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": sub.get("delta")})
        elif kind == "tool" and sub.get("text"):
            await assistant_hub.broadcast(thread_id, {"type": "chat_status", "text": str(sub.get("text"))})
        if (payload or {}).get("type") in ("node_trace", "pipeline_start", "pipeline_paused", "pipeline_done", "error"):
            await raw_broadcast(payload)

    if not opportunity_id:
        opportunity_id = _ensure_ai_office_opportunity(thread_id, user, user_text)

    await publish_office_event(role_key, "working", "接收新任务", message=user_text or "", thread_id=thread_id)

    phase_hint = _skill_phase_hint(skill_manifest, session_phase)
    allow_submit = bool(force_submit or session_phase in (SKILL_SESSION_PROPOSING, SKILL_SESSION_ACTIVE))

    try:
        # 整轮硬超时护栏：中转半死连接（只挂不断）会绕过 LLM 客户端超时，把回合拖到无限。
        # 放弃式（同 skill_chat 900s 防线）：黑洞连接上「取消完成」也可能被 httpx 清理拖死，
        # wait_for 等任务响应取消=本协程跟着挂死（整回合静默挂死实锤根因之一）。到点
        # cancel 不等回收，立刻落错误终态。920s>内层 900s：内层到点会出「重新继续分析」
        # 缺口卡并正常返回（保留现场可续跑），外层只兜内层防线也失效的极端情况。
        _turn_task = asyncio.ensure_future(handle_skill_chat_turn(
            thread_id=thread_id, user_text=user_text, colleague=colleague,
            chat_system_prompt=persona, history=history, user=user,
            opportunity_id=opportunity_id, option_slot=option_slot,
            event_sink=event_sink, emit_input_card=emit_input_card,
            card_selections=card_selections, force_submit=force_submit,
            skill_phase_hint=phase_hint, allow_submit=allow_submit,
            enable_clarity=enable_clarity,
        ))
        _turn_done, _turn_pending = await asyncio.wait({_turn_task}, timeout=920.0)
        if _turn_pending:
            _turn_task.cancel()
            logger.error("skill chat turn 超时(920s，放弃式) thread=%s", thread_id)
            outcome = {"kind": "error", "reply": "这一轮处理超时了（模型服务暂时无响应），请重发一次或稍后再试。"}
        else:
            outcome = _turn_task.result()
    except Exception as exc:
        logger.exception("skill chat turn failed thread=%s", thread_id)
        outcome = {"kind": "error", "reply": f"回复处理失败：{exc}"}

    kind = outcome.get("kind")
    reply = str(outcome.get("reply") or "").strip()
    logger.info("skill chat outcome kind=%s reply_len=%s thread=%s", kind, len(reply), thread_id)

    if session_phase == SKILL_SESSION_IDLE and kind == "chat":
        session = load_skill_session(thread_id, role_key)
        session["phase"] = SKILL_SESSION_PROPOSING
        if isinstance(skill_manifest, dict):
            session["skill_key"] = str(skill_manifest.get("skill_key") or "requirement_analysis")
        save_skill_session(thread_id, role_key, session)
    elif kind in ("done", "gaps"):
        session = load_skill_session(thread_id, role_key)
        session["phase"] = SKILL_SESSION_ACTIVE
        if isinstance(skill_manifest, dict):
            session["skill_key"] = str(skill_manifest.get("skill_key") or session.get("skill_key") or "requirement_analysis")
        save_skill_session(thread_id, role_key, session)

    async def _final_report(engine_ctx: dict) -> str:
        """引擎完成后的收尾汇报：唯一大脑把确定性结果串成完整对话（只引用事实，禁止编造）。
        失败返回空串，调用方回退到固定短句。"""
        try:
            requirement = dict(engine_ctx.get("requirement") or {})
            model = dict(engine_ctx.get("model_selection") or {})
            kp = dict(engine_ctx.get("kp_summary") or {})
            plans = engine_ctx.get("plans") or []
            facts = {
                "已登记配置": {k: v for k, v in requirement.items()
                                   if k != "kp_rows" and v not in (None, "", [], {})},
                "部件清单": [{"类别": r.get("part_category"), "描述": r.get("description"), "数量": r.get("qty")}
                                for r in (requirement.get("kp_rows") or []) if isinstance(r, dict)],
                "锁定机型": {"机型": model.get("name"), "系列": model.get("series"),
                               "形态": model.get("form"), "理由": engine_ctx.get("lock_reason") or ""},
                "配件落地": {"件数": kp.get("kp_count"), "未命中": kp.get("unmatched_count"),
                                 "分类": kp.get("by_category") or {}},
                "生成方案": [{"名称": p.get("name"),
                                  "总成本": (p.get("summary") or {}).get("total_cost")} for p in plans],
            }
            from app.services.skill_prompts import load_skill_prompts
            hint = str(load_skill_prompts().get("final_report_hint") or "").strip()
            system = build_chat_config(colleague)["chat_system_prompt"] + "\n\n" + (
                hint or "向客户汇报需求分析的完整结果：只引用给定事实，禁止编造；两三句话，面向客户口吻。")
            _fr_msgs = [
                {"role": "system", "content": system},
                {"role": "user", "content": "引擎结果事实：\n" + json.dumps(facts, ensure_ascii=False)
                 + '\n\n请向客户汇报。只输出 JSON：{"reply": "..."}'},
            ]
            _fr_t0 = time.perf_counter()
            data = await llm_client.chat_json(_fr_msgs, timeout=30, max_attempts=1,
                # 收尾=事实串讲（接地任务）：低推理档够了，员工 profile 显式配置可覆盖
                reasoning_effort=(build_chat_config(colleague).get("response_profile") or {}).get("reasoning_effort") or "low")
            from app.services.llm_trace import record_llm_trace
            record_llm_trace(node_type="skill_final", opportunity_id=thread_id, role_key=role_key,
                             duration_ms=int((time.perf_counter() - _fr_t0) * 1000),
                             prompt_chars=sum(len(str(m.get("content") or "")) for m in _fr_msgs),
                             response_chars=len(str((data or {}).get("reply") or "")), status="ok")
            return str((data or {}).get("reply") or "").strip()
        except Exception:
            logger.exception("收尾汇报生成失败")
            return ""

    if kind == "done":
        engine_ctx = outcome.get("engine_ctx") or {}
        # 登记回合旁白留痕（不消失）；大脑提问卡路径已随卡前置落库同一份旁白，去重防双写
        fill_nar = str(outcome.get("narration") or "").strip()
        if fill_nar and fill_nar != gap_narration_persisted["text"]:
            await _persist_and_broadcast(thread_id, colleague, fill_nar)
        # v2：提交前的 narration 已流式播出，这里落库定稿（done 事件清前端 streamingText），
        # 历史会话里 narration 与方案产物上下文完整；随后再广播方案产物
        if reply:
            await _persist_and_broadcast(thread_id, colleague, reply)
        payload = engine_ctx.get("output_payload") or {}
        plans = engine_ctx.get("plans") or []
        bom_entity = (engine_ctx.get("business_entity") or {}).get("entity")
        bom_view = payload.get("bom_scheme") if isinstance(payload.get("bom_scheme"), dict) else {}
        config_count = len(bom_view.get("configs") or []) or len(plans) or 1
        # 收尾汇报是非流式 chat_json（数秒级零事件）：先推一条状态，别让前端干转点
        await assistant_hub.broadcast(thread_id, {"type": "chat_status", "text": "正在汇总分析结果…"})
        report = await _final_report(engine_ctx)
        result_msg = (report + "\n\n✅ 已生成 BOM 方案草稿（" + str(config_count) + " 个配置页签），点击下方卡片查看。") if report \
            else "✅ 需求分析完成，已生成 BOM 方案草稿（" + str(config_count) + " 个配置页签）。"
        result_data = {"bom_scheme": bom_entity or payload.get("bom_scheme"), "entity_type": "bom_scheme",
                       "opportunity_id": opportunity_id or "", "target": "bom_scheme"}
        result_asst = _add_assistant_message(thread_id, colleague, result_msg, kind="business_artifact",
                                             data=json.dumps(result_data, ensure_ascii=False, default=str))
        # message 必须是完整落库对象（与 done 事件同口径）：裸字符串到前端会落进
        # 消息组件的直播兜底分支渲染成永久三点泡，方案卡永不出现（2026-09-06 定案：
        # 消息已落库、事件已到达、唯 message 字段不是对象——第四遍三个点真因）
        await raw_broadcast({"type": "business_entity_ready", "entity_type": "bom_scheme",
                             "entity": bom_entity, "opportunity_id": opportunity_id or "", "message": result_asst})
        await raw_broadcast({"type": "analysis_finished"})
        try:
            record_mission(
                f"requirement_analysis：{user_text[:80]}" if user_text else "requirement_analysis",
                created_by=(user or {}).get("name") or (user or {}).get("user_id") or "user",
                owner_role_key=role_key, opportunity_id=opportunity_id or "",
                flow_node="bom_scheme", skill_key="requirement_analysis",
                artifacts=[{"type": "bom_scheme_draft", "title": "方案 / BOM 草稿",
                            "content": f"已生成 {config_count} 个配置页签，点击查看或转成本核算。",
                            "data": result_data}],
                status="done",
            )
        except Exception:
            logger.exception("record AI office mission artifact failed")
        _schedule_memory_extraction(colleague, _user_name(user), user_text, result_msg)
        await publish_office_event(role_key, "done", "需求分析完成", message=result_msg[:160], thread_id=thread_id)
        await _trace(trace_sink, tool_name="skill_chat", status="ok",
                     duration_ms=int((time.perf_counter() - started) * 1000), thread_id=thread_id,
                     node_type="skill_chat", role_key=role_key)
        return

    if kind == "error":
        msg = str(outcome.get("reply") or "需求分析执行失败")
        await raw_broadcast({"type": "error", "message": msg})
        _add_assistant_message(thread_id, colleague, msg, kind="error")
        await publish_office_event(role_key, "error", "需求分析失败", thread_id=thread_id)
        return

    # chat / gaps：正常对话回复；缺口时问题文本已随选项卡发出，不再重复存普通消息
    if not reply and kind != "gaps":
        reply = "我在的，继续说说你的需求～"
    if kind == "gaps":
        # 登记回合旁白留痕（不随缺口卡弹出而消失）；发卡路径已随卡前置落库，不重复
        fill_nar = str(outcome.get("narration") or "").strip()
        if fill_nar and fill_nar != gap_narration_persisted["text"]:
            await _persist_and_broadcast(thread_id, colleague, fill_nar)
        # 问题文本已随选项卡广播（handle_skill_chat_turn 内 emit_input_card）；
        # 卡没发出去（异常/通道缺失）时必须落普通消息，绝不让用户面对静默
        if not outcome.get("card_emitted") and reply:
            await _persist_and_broadcast(thread_id, colleague, reply)
        # 此处发裸 done 只为清掉前端还挂着的流式 narration 气泡，不重复落消息
        await assistant_hub.broadcast(thread_id, {"type": "done"})
        await publish_office_event(role_key, "waiting", "等待客户补充", thread_id=thread_id)
        await _trace(trace_sink, tool_name="skill_chat", status="ok",
                     duration_ms=int((time.perf_counter() - started) * 1000), thread_id=thread_id,
                     node_type="skill_chat", role_key=role_key)
        return
    _schedule_memory_extraction(colleague, _user_name(user), user_text, reply)
    await publish_office_event(role_key, "done", "回复完成", message=reply[:160], thread_id=thread_id)
    await _trace(trace_sink, tool_name="skill_chat", status="ok",
                 duration_ms=int((time.perf_counter() - started) * 1000), thread_id=thread_id,
                 node_type="skill_chat", role_key=role_key)
    # v2 真流式：正文在生成期间已经过 chunk 通道逐字推出，这里只落库定稿（done），
    # 不再做生成完后的打字机回放（假流式已删除）。
    await _persist_and_broadcast(thread_id, colleague, reply, final_office_event=final_office_event)


# 每线程互斥锁：重发消息不再叠加并行流水线（互踩 pending state 的根因）。
_THREAD_TURN_LOCKS: dict[str, asyncio.Lock] = {}
# Claude Code 语义：任务执行中用户仍可发消息引导——排队等当前回合结束串行续跑，
# 不再拒绝。参数原样保存，drain 时按到达顺序重放进同一入口。
_THREAD_TURN_QUEUE: dict[str, list[dict]] = {}


async def _drain_thread_queue(thread_id: str) -> None:
    """当前回合结束后串行处理排队消息；锁被占/队列空即退出（多个 drain 并存安全收敛）。"""
    while True:
        lock = _THREAD_TURN_LOCKS.get(thread_id)
        if lock is None or lock.locked():
            return
        queue = _THREAD_TURN_QUEUE.get(thread_id)
        if not queue:
            _THREAD_TURN_QUEUE.pop(thread_id, None)
            return
        item = queue.pop(0)
        if not queue:
            _THREAD_TURN_QUEUE.pop(thread_id, None)
        await run_colleague_turn(**item)


def _clear_thread_queue(thread_id: str) -> None:
    _THREAD_TURN_QUEUE.pop(thread_id, None)


async def run_colleague_turn(
    thread_id: str,
    user_text: str,
    context_summary: Optional[str],
    history: list,
    colleague: Optional[dict],
    final_office_event: Optional[dict] = None,
    trace_sink: Optional[Callable[..., None]] = None,
    user: Optional[dict] = None,
    opportunity_id: Optional[str] = None,
    option_slot: Optional[str] = None,
    card_selections: Optional[list] = None,
    entry_point: Optional[str] = None,
    enable_clarity: Optional[bool] = None,
) -> None:
    """Route one colleague message through the unified runtime."""
    role_key = (colleague or {}).get("role_key") or "assistant"
    lock = _THREAD_TURN_LOCKS.setdefault(thread_id, asyncio.Lock())
    if lock.locked():
        # 同线程已有回合在跑：排队（串行防互踩），当前回合结束后自动续跑，
        # 用户中途补充的话会作为下一轮输入进角色登记表——引导而非打断。
        _THREAD_TURN_QUEUE.setdefault(thread_id, []).append({
            "thread_id": thread_id, "user_text": user_text, "context_summary": context_summary,
            "history": history, "colleague": colleague, "final_office_event": final_office_event,
            "trace_sink": trace_sink, "user": user, "opportunity_id": opportunity_id,
            "option_slot": option_slot, "card_selections": card_selections, "entry_point": entry_point,
            "enable_clarity": enable_clarity,
        })
        msg = "已收到，这条会排在当前任务完成后处理。"
        await assistant_hub.broadcast(thread_id, {"type": "chat_status", "text": msg})
        return
    try:
        async with lock:
            await publish_office_event(role_key, "thinking", "正在思考回复", thread_id=thread_id)
            memory_block = await _memory_block(colleague, user_text)
            allowed_tool_ids = _effective_tool_ids(colleague)
            from app.services.skill_chat import load_skill_session, save_skill_session
            session = load_skill_session(thread_id, role_key)
            is_preview = (entry_point or "").strip() == "skill_studio_preview"

            if is_preview or session.get("phase") == SKILL_SESSION_ACTIVE:
                skill_key = str(session.get("skill_key") or "requirement_analysis")
                manifest = resolve_skill_manifest(skill_key) or resolve_skill_manifest("requirement_analysis")
                await _run_skill_chat(
                    thread_id, user_text, context_summary, history, colleague, memory_block,
                    final_office_event=final_office_event, trace_sink=trace_sink,
                    user=user, opportunity_id=opportunity_id, option_slot=option_slot,
                    card_selections=card_selections, force_submit=True,
                    skill_manifest=manifest, session_phase=SKILL_SESSION_ACTIVE,
                    enable_clarity=enable_clarity,
                )
            elif session.get("phase") == SKILL_SESSION_PROPOSING:
                skill_key = str(session.get("skill_key") or "requirement_analysis")
                manifest = resolve_skill_manifest(skill_key) or resolve_skill_manifest("requirement_analysis")
                await _run_skill_chat(
                    thread_id, user_text, context_summary, history, colleague, memory_block,
                    final_office_event=final_office_event, trace_sink=trace_sink,
                    user=user, opportunity_id=opportunity_id, option_slot=option_slot,
                    card_selections=card_selections, force_submit=False,
                    skill_manifest=manifest, session_phase=SKILL_SESSION_PROPOSING,
                    enable_clarity=enable_clarity,
                )
            elif _skill_chat_memory_active(thread_id, role_key):
                # 旧流程记忆（无 skill_session 字段）视为已启动，继续跑固定六步。
                save_skill_session(thread_id, role_key, {
                    "phase": SKILL_SESSION_ACTIVE,
                    "skill_key": "requirement_analysis",
                    "entry_point": entry_point or "",
                })
                manifest = resolve_skill_manifest("requirement_analysis")
                await _run_skill_chat(
                    thread_id, user_text, context_summary, history, colleague, memory_block,
                    final_office_event=final_office_event, trace_sink=trace_sink,
                    user=user, opportunity_id=opportunity_id, option_slot=option_slot,
                    card_selections=card_selections, force_submit=True,
                    skill_manifest=manifest, session_phase=SKILL_SESSION_ACTIVE,
                    enable_clarity=enable_clarity,
                )
            elif _has_workflow_skills(colleague):
                skill = _first_workflow_skill(colleague) or {}
                skill_key = str(skill.get("workflow_key") or skill.get("key") or "requirement_analysis")
                manifest = resolve_skill_manifest(skill_key) or resolve_skill_manifest("requirement_analysis")
                await _run_skill_chat(
                    thread_id, user_text, context_summary, history, colleague, memory_block,
                    final_office_event=final_office_event, trace_sink=trace_sink,
                    user=user, opportunity_id=opportunity_id, option_slot=option_slot,
                    card_selections=card_selections, force_submit=False,
                    skill_manifest=manifest, session_phase=SKILL_SESSION_IDLE,
                    enable_clarity=enable_clarity,
                )
            else:
                await _run_plain_turn(
                    thread_id, user_text, context_summary, history, colleague, memory_block,
                    final_office_event=final_office_event, trace_sink=trace_sink, user=user,
                )
    except asyncio.CancelledError:
        # stop 端点取消任务：广播终态即可（登记表记忆保留，用户可继续）。
        # 用户按停=不要了：排队中的引导消息一并清掉（历史里仍可看到原话）。
        logger.warning("colleague turn 被取消 thread=%s", thread_id)
        _clear_thread_queue(thread_id)
        try:
            await assistant_hub.broadcast(thread_id, {"type": "analysis_cancelled", "message": "已取消当前任务。"})
        except Exception:
            pass
        raise
    except Exception as e:
        logger.exception("colleague turn runtime failed")
        msg = f"回复处理失败：{e}"
        # 必达终态：错误必须落库，不能只广播（无 WS 客户端时广播蒸发=用户看到"卡住"）。
        try:
            _add_assistant_message(thread_id, colleague, msg, kind="error")
        except Exception:
            logger.exception("落库终态错误消息失败")
        await assistant_hub.broadcast(thread_id, {"type": "error", "message": msg})
    finally:
        # 回合收尾：有排队消息则串行续跑（Claude Code 式执行中引导）。
        if _THREAD_TURN_QUEUE.get(thread_id):
            asyncio.create_task(_drain_thread_queue(thread_id))
