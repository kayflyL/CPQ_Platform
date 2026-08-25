# -*- coding: utf-8 -*-
"""Unified AI-colleague turn runtime.

Every office-colleague chat entry point reaches this service instead of
hardcoded keyword branches. A colleague with tools runs a text-ReAct loop;
a colleague without tools streams a normal conversation. Tool results that
represent draft/write actions are parked in the office governance queue and
must be confirmed before continuing.
"""
from __future__ import annotations

import logging
import json
import time
from typing import Any, Callable, Optional

from app.repository.assistant_repo import AssistantRepository
from app.repository.system_config_repo import SystemConfigRepository
from app.repository.skill_catalog_repo import SkillCatalogRepository
from app.services import llm_client
from app.services.agent_react import run_react_loop
from app.services.agent_tools import tool_requires_approval, tool_required_data_sources
from app.services.ai_colleague_service import colleague_tool_ids, effective_data_sources, get_ai_colleague_config
from app.services.assistant_hub import assistant_hub
from app.services.llm_client import LLMError
from app.services.office_events import publish_office_event
from app.services.office_governance import office_governance
from app.services.office_memory import office_memory
from app.services.office_mission import record_mission
from app.services.office_access import allowed_chat_role_keys
from app.services.skill_router import conversation_text, route_skill_llm

logger = logging.getLogger(__name__)

_DEFAULT_CHAT_SYSTEM_PROMPT = (
    "你是 CPQ 平台的 AI 同事，辅助用户完成商机、配置、成本与报价相关工作。"
    "你是对话中的协作者，先理解用户意图，再决定是否需要调用系统工具；"
    "信息不足时应像真人一样反问最关键的问题，不要一看到关键词就机械进入业务流程。"
    "要求：用中文回复；对料号、价格、库存、具体型号等易变信息不要编造，"
    "不确定时明确说明并请用户确认。"
)


def _load_pending_workflow(thread_id: str) -> Optional[dict]:
    """读取暂停在反问环节的 workflow 会话；无有效状态时返回 None。"""
    try:
        repo = AssistantRepository()
        try:
            raw = repo.get_reasoning_state(thread_id)
        finally:
            repo.close()
    except Exception:
        logger.exception("load pending workflow failed thread=%s", thread_id)
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    session = data.get("skill_workflow")
    if (
        isinstance(session, dict)
        and session.get("status") == "awaiting_input"
        and str(session.get("skill_key") or "").strip()
    ):
        return session
    return None


def _save_pending_workflow(thread_id: str, session: Optional[dict]) -> None:
    """写入（或清除）暂停中的 workflow 会话状态，统一走 reasoning_state 列。"""
    try:
        repo = AssistantRepository()
        try:
            repo.update_reasoning_state(thread_id, {"skill_workflow": session})
        finally:
            repo.close()
    except Exception:
        logger.exception("save pending workflow failed thread=%s", thread_id)


def _clear_pending_workflow(thread_id: str) -> None:
    _save_pending_workflow(thread_id, None)


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


def _memory_policy(colleague: Optional[dict]) -> dict:
    if isinstance(colleague, dict):
        policy = colleague.get("memory_policy")
        if isinstance(policy, dict):
            return policy
        legacy = colleague.get("memory")
        if isinstance(legacy, dict):
            return {
                "enabled": True,
                "short_term_max_turns": None,
                "long_term_store": legacy.get("long_term_store") or "office_memory",
                "query_recent": 6,
                "save_after_turn": True,
                "auto_memory": True,
            }
    return {
        "enabled": True,
        "short_term_max_turns": 12,
        "long_term_store": "office_memory",
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
    return await office_memory.memory_prompt(role_key, query=user_text, limit=limit)


async def _remember_reply(colleague: Optional[dict], final_text: str) -> None:
    policy = _memory_policy(colleague)
    if policy.get("enabled") is False or policy.get("save_after_turn") is False:
        return
    if policy.get("auto_memory") is False:
        return
    role_key = (colleague or {}).get("role_key") or "assistant"
    await office_memory.remember(
        role_key,
        f"我回复：{str(final_text or '')[:400]}",
        kind="episodic",
        importance=0.35,
    )


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


async def mark_self_config_flow(thread_id: str, colleague: Optional[dict]) -> Optional[dict]:
    """候选卡“去配置这台服务器”点击后，把当前待机型 workflow 置为 self_config 并跳过下游 BOM。

    只处理挂在 model_reason 候选确认上的 pending；无 pending 时返回 None（调用方转 409）。
    """
    pending = _load_pending_workflow(thread_id)
    if not pending:
        return None
    _clear_pending_workflow(thread_id)
    self_text = "已切换为自行配置。可在服务器详情页完成配置；如需继续组装 BOM，再回来告知。"
    _add_assistant_message(thread_id, colleague, self_text)
    role_key = str((colleague or {}).get("role_key") or "assistant")
    await assistant_hub.broadcast(thread_id, {
        "type": "analysis_finished",
        "message": self_text,
        "exit": "self_config",
        "thread_id": thread_id,
        "opportunity_id": str(pending.get("opportunity_id") or ""),
    })
    await publish_office_event(role_key, "done", "用户选择自行配置机型", thread_id=thread_id)
    return pending


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
) -> None:
    if not text:
        return
    message = _add_assistant_message(thread_id, colleague, text)
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

    await _remember_reply(colleague, final_text or "")
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
) -> None:
    role_key = (colleague or {}).get("role_key") or "assistant"
    history = _short_term_history(colleague, history)
    chat_cfg = build_chat_config(colleague)
    system_prompt = "\n\n".join([chat_cfg["chat_system_prompt"], _style_hint(chat_cfg)])
    skill_prompt = _skill_prompt(colleague)
    if skill_prompt:
        system_prompt += "\n\n" + skill_prompt
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

    workflow_result_sent = {"value": False}
    workflow_started = False

    async def workflow_runner(args: dict) -> dict:
        nonlocal opportunity_id
        nonlocal workflow_started
        if workflow_started:
            return {
                "status": "already_processed",
                "message": "当前 Skill 工作流本轮已执行，请基于已有结果继续回复用户，不要重复运行。",
            }
        workflow_started = True
        _clear_pending_workflow(thread_id)
        text = str((args or {}).get("requirement_text") or "").strip()
        if not text:
            return {"error": "缺少 requirement_text"}
        skill_key = str((args or {}).get("skill_key") or "").strip()
        if not skill_key:
            for resolved in _resolved_skills(colleague):
                workflow_key = str(resolved.get("workflow_key") or "").strip()
                if resolved.get("type") == "workflow" and workflow_key:
                    skill_key = workflow_key
                    break
        if not skill_key:
            return {"error": "当前同事未绑定可执行的工作流型 Skill"}

        skill_output_kind = ""
        for resolved in _resolved_skills(colleague):
            key = str(resolved.get("workflow_key") or resolved.get("key") or "").strip()
            if key == skill_key:
                skill_output_kind = str(resolved.get("output_kind") or "").strip()
                break
        if skill_key == "requirement_analysis":
            skill_output_kind = "bom_scheme_draft"
        if not skill_output_kind:
            skill_output_kind = {
                "requirement_analysis": "bom_scheme_draft",
                "trend_analysis": "data_answer",
            }.get(skill_key, "generic")

        budget = (args or {}).get("budget")
        last_ask_question = str((args or {}).get("last_ask_question") or "").strip()
        last_user_answer = str((args or {}).get("supplement_text") or "").strip() if last_ask_question else ""
        operator_name = str((user or {}).get("name") or (user or {}).get("user_id") or "")
        full_text = text
        # AI Office 会话没有商机上下文时，创建一条隐藏内部商机，让真实四步表单可以落库。
        if not opportunity_id and skill_output_kind == "bom_scheme_draft":
            opportunity_id = _ensure_ai_office_opportunity(thread_id, user, text)
        if opportunity_id:
            from app.services.portal_flow_adapter import build_requirement_text
            supplement_text = str((args or {}).get("supplement_text") or "").strip()
            full_text = build_requirement_text(opportunity_id, text, supplement_text)
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        from app.services.capability_executor import run_fixed_workflow

        repo = ReasoningFlowRepository()
        try:
            flow = repo.ensure_skill_flow(skill_key, name=skill_key)
        finally:
            repo.close()
        if not flow:
            return {"error": f"Skill '{skill_key}' 没有可执行的工作流"}

        flow_node_configs = flow.get("node_configs") or {}
        ctx_holder: dict = {}

        async def raw_broadcast(payload: dict) -> None:
            payload.setdefault("thread_id", thread_id)
            payload.setdefault("opportunity_id", opportunity_id or "")
            await assistant_hub.broadcast(thread_id, payload)

        async def chat_broadcast(payload: dict) -> None:
            event_type = payload.get("type")
            ctx = ctx_holder.get("ctx") or {}

            if event_type == "pipeline_start":
                return
            if event_type in ("step_start", "step_done"):
                node_id = str(payload.get("step") or "")
                label = str(payload.get("label") or node_id)
                done = event_type == "step_done"
                if not done:
                    await assistant_hub.broadcast(thread_id, {
                        "type": "chat_status",
                        "step": node_id,
                        "text": "思考中…",
                    })
                # 对话不渲染节点卡（前端已删 NodeTraceList），但画布节点依赖 node_trace
                # 回填「产出/下游交接」与线索登记表（requirement_slots）等 artifact。
                await assistant_hub.broadcast(thread_id, {
                    "type": "node_trace",
                    "step": node_id,
                    "label": label,
                    "status": "running" if not done else "done",
                    "input": payload.get("input"),
                    "output": payload.get("output") if done else None,
                    "summary": payload.get("summary") if done else None,
                    "artifact": payload.get("artifact") if done else None,
                })
                return
            if event_type == "step_progress":
                sub = payload.get("sub") or {}
                if (sub.get("kind") or "") == "thinking":
                    await assistant_hub.broadcast(thread_id, {
                        "type": "thinking",
                        "step": payload.get("step") or "agent_fill",
                        "text": sub.get("text") or "",
                    })
                return
            if event_type == "need_input":
                question = str(payload.get("question") or "").strip()
                options = payload.get("options") or []
                why = str(payload.get("why") or "").strip()
                lines = [question] if question else []
                if options:
                    lines.append("可选：" + "、".join(str(item) for item in options))
                if why:
                    lines.append(why)
                await _broadcast_chat_progress(
                    thread_id, colleague, "need_input", "question", "\n".join(lines),
                )
                return
            if event_type == "need_confirm":
                question = str(payload.get("question") or "").strip()
                await _broadcast_chat_progress(
                    thread_id, colleague, "need_confirm", "question", question,
                )
                _candidates = payload.get("candidates") or []
                if isinstance(_candidates, list) and _candidates:
                    try:
                        _cards = [c for c in _candidates if c]
                        if _cards:
                            _card_data = {
                                "entity_type": "model_candidates",
                                "entity": {"candidates": _cards, "question": question},
                                "opportunity_id": opportunity_id or "",
                                "target": "model_reason",
                            }
                            _card_lede = str(question or "").strip()
                            if not _card_lede:
                                _names = "、".join(str((c or {}).get("name") or "") for c in _cards if c)
                                _card_lede = (("候选机型：" + _names) if _names else "候选机型")

                            _card_msg = _add_assistant_message(
                                thread_id, colleague,
                                _card_lede,
                                kind="business_artifact",
                                data=json.dumps(_card_data, ensure_ascii=False, default=str),
                            )
                            if _card_msg:
                                await assistant_hub.broadcast(thread_id, {
                                    "type": "business_entity_ready",
                                    "entity_type": "model_candidates",
                                    "entity": _card_data,
                                    "opportunity_id": opportunity_id or "",
                                    "message": _card_msg,
                                })
                    except Exception:
                        logger.exception("broadcast model_candidates card failed")
                return
            if event_type in ("handoff_ready",):
                return
            await raw_broadcast(payload)

        force_complete = bool((args or {}).get("force_complete"))
        max_ask_rounds = (args or {}).get("max_ask_rounds")
        try:
            max_ask_rounds = int(max_ask_rounds) if max_ask_rounds is not None else 0
        except (TypeError, ValueError):
            max_ask_rounds = 0
        restored_slot = (args or {}).get("slot_state") or {}
        restored_ext = dict(restored_slot.get("ext") or {})
        restored_target = str((args or {}).get("current_target") or restored_slot.get("current_target") or "").strip()
        ctx = await run_fixed_workflow(
            thread_id,
            full_text,
            flow,
            chat_broadcast,
            initial_ctx={
                "budget": budget,
                "force_complete": force_complete,
                "max_ask_rounds": max_ask_rounds,
                "output_kind": skill_output_kind,
                "opportunity_id": opportunity_id or thread_id,
                "operator_name": operator_name,
                "last_ask_question": last_ask_question,
                "last_user_answer": last_user_answer,
                "ext": dict(restored_ext),
                "requirement": dict(restored_slot.get("requirement") or {}),
                "requirement_text_snapshot": restored_slot.get("requirement_text_snapshot") or "",
                "baselines": list(restored_slot.get("baselines") or []),
                "kp_parts": list(restored_slot.get("kp_parts") or []),
                "kp_by_model": dict(restored_slot.get("kp_by_model") or {}),
                "model_selection": restored_slot.get("model_selection"),
                "model_phase": restored_slot.get("model_phase") or "",
                "_locked_baseline": restored_slot.get("_locked_baseline") or {},
                "missing_fields": list(restored_slot.get("missing_fields") or []),
                "feasibility": restored_slot.get("feasibility"),
                "turn_count": int(restored_slot.get("turn_count") or 0),
                "current_target": restored_target,
                "business_mode": "opportunity_flow" if opportunity_id else "conversation",
                "history": history,
            },
            ctx_ref=ctx_holder,
        )
        if ctx.get("fatal_error"):
            error = str(ctx.get("fatal_error") or "需求分析执行失败")
            await raw_broadcast({"type": "error", "message": error})
            workflow_result_sent["value"] = True
            return f"需求分析执行失败：{error}"
        handoff = ctx.get("handoff") if isinstance(ctx.get("handoff"), dict) else {}
        payload = handoff.get("payload") if isinstance(handoff.get("payload"), dict) else {}
        output_kind = str(handoff.get("output_kind") or ctx.get("output_kind") or skill_output_kind).strip() or "generic"
        plans = payload.get("plans") or ctx.get("plans") or []
        ext = payload.get("ext") or ctx.get("ext") or {}
        if ctx.get("awaiting_input"):
            try:
                from app.services.portal_flow_adapter import persist_requirement_from_ctx
                persist_requirement_from_ctx(ctx, operator_name)
            except Exception:
                logger.exception("AI Office 反问暂停前写需求草稿失败 thread=%s", thread_id)
            slot_state = dict(ctx.get("slot_state") or {})
            slot_state.update({
                "ext": dict(ctx.get("ext") or {}),
                "requirement": dict(ctx.get("requirement") or {}),
                "requirement_text_snapshot": ctx.get("requirement_text_snapshot") or "",
                "baselines": list(ctx.get("baselines") or []),
                "kp_parts": list(ctx.get("kp_parts") or []),
                "kp_by_model": dict(ctx.get("kp_by_model") or {}),
                "model_selection": ctx.get("model_selection"),
                "model_phase": ctx.get("model_phase") or "",
                "_locked_baseline": dict(ctx.get("_locked_baseline") or {}),
                "missing_fields": list(ctx.get("missing_fields") or []),
                "feasibility": ctx.get("feasibility"),
                "turn_count": int(ctx.get("turn_count") or 0) + 1,
            })
            _save_pending_workflow(thread_id, {
                "status": "awaiting_input",
                "skill_key": skill_key,
                "opportunity_id": opportunity_id or "",
                "requirement_text": full_text,
                "force_complete": force_complete,
                "max_ask_rounds": max_ask_rounds,
                "last_ask_question": ctx.get("last_ask_question") or "",
                "slot_state": slot_state,
                "current_target": ctx.get("current_target") or "",
            })
            await raw_broadcast({"type": "pipeline_paused"})
            workflow_result_sent["value"] = True
            return "系统已向用户发起澄清提问，请等待用户补充信息后再继续。"
        if ctx.get("flow_exit") == "cancelled":
            _clear_pending_workflow(thread_id)
            cancel_text = "本次方案配置已取消。可重新描述需求，或继续其他步骤。"
            _add_assistant_message(thread_id, colleague, cancel_text)
            await raw_broadcast({"type": "analysis_cancelled", "message": cancel_text})
            await publish_office_event(role_key, "done", "已取消方案配置", thread_id=thread_id)
            workflow_result_sent["value"] = True
            return "已取消本次方案配置。"
        if ctx.get("flow_exit") == "self_config":
            _clear_pending_workflow(thread_id)
            self_text = "已切换为自行配置。可在服务器详情页完成配置；如需继续组装 BOM，再回来告知。"
            _add_assistant_message(thread_id, colleague, self_text)
            await raw_broadcast({"type": "analysis_finished", "message": self_text, "exit": "self_config"})
            await publish_office_event(role_key, "done", "用户选择自行配置机型", thread_id=thread_id)
            workflow_result_sent["value"] = True
            return "用户选择自行配置机型，下游 BOM 节点已跳过。"
        downstream = await downstream_guard(handoff)
        if downstream:
            target_role = str(downstream.get("target_role") or "更高权限的 AI 角色")
            approval_text = f"草稿已生成。下一步需要 {target_role} 处理，系统已提交审批。审批通过后我会继续。"
            approval_msg = _add_assistant_message(
                thread_id,
                colleague,
                approval_text,
                kind="approval_required",
                data=json.dumps({
                    "governance_id": downstream.get("governance_id"),
                    "target_role": downstream.get("target_role"),
                    "handoff": handoff,
                }, ensure_ascii=False, default=str),
            )
            await raw_broadcast({
                "type": "approval_required",
                "governance_id": downstream.get("governance_id"),
                "target_role": downstream.get("target_role"),
                "handoff": handoff,
                "message": approval_msg,
            })
            workflow_result_sent["value"] = True
            return "已生成草稿，但下一步需要更高权限的 AI 角色，系统已提交审批。"
        if output_kind == "bom_scheme_draft" and payload.get("bom_scheme"):
            bom_scheme = payload.get("bom_scheme") or {}
            config_count = len((bom_scheme.get("configs") or []))
            _fz = ctx.get("feasibility") or {}
            _fz_lines = [f"⚠️ {w}" for w in (_fz.get("warnings") or [])] + [f"提示：{h}" for h in (_fz.get("hints") or [])]
            _fz_suffix = ("\n" + "\n".join(_fz_lines)) if _fz_lines else ""
            result_data = {
                "bom_scheme": bom_scheme,
                "entity_type": "bom_scheme",
                "opportunity_id": opportunity_id or "",
                "target": handoff.get("target") or "bom_scheme",
            }
            result_msg = _add_assistant_message(
                thread_id,
                colleague,
                f"✅ 需求分析完成，已生成 BOM 方案草稿（{config_count} 个配置页签）。{_fz_suffix}",
                kind="business_artifact",
                data=json.dumps(result_data, ensure_ascii=False, default=str),
            )
            await assistant_hub.broadcast(thread_id, {
                "type": "business_entity_ready",
                "entity_type": "bom_scheme",
                "entity": bom_scheme,
                "opportunity_id": opportunity_id or "",
                "message": result_msg,
            })
            await assistant_hub.broadcast(thread_id, {"type": "analysis_finished"})
            try:
                record_mission(
                    f"{skill_key}：{text[:80]}" if text else skill_key,
                    created_by=(user or {}).get("name") or (user or {}).get("user_id") or "user",
                    owner_role_key=role_key,
                    opportunity_id=opportunity_id or "",
                    flow_node=handoff.get("target") or "bom_scheme",
                    skill_key=skill_key,
                    artifacts=[{
                        "type": "bom_scheme_draft",
                        "title": "方案 / BOM 草稿",
                        "content": f"已生成 {config_count} 个配置页签，点击查看或转成本核算。",
                        "data": result_data,
                    }],
                    status="done",
                )
            except Exception:
                logger.exception("record AI office mission artifact failed")
            workflow_result_sent["value"] = True
            return "需求分析已完成，BOM 方案草稿已写入商机流程。请告知用户可查看方案草稿，确认后转成本核算。"

        agent_result = ctx.get("agent_result") if isinstance(ctx.get("agent_result"), dict) else {}
        answer = str(payload.get("answer") or agent_result.get("answer") or "").strip()
        if answer:
            try:
                record_mission(
                    f"{skill_key}：{text[:80]}" if text else skill_key,
                    created_by=(user or {}).get("name") or (user or {}).get("user_id") or "user",
                    owner_role_key=role_key,
                    opportunity_id=opportunity_id or "",
                    flow_node=handoff.get("target") or "conversation_reply",
                    skill_key=skill_key,
                    artifacts=[{
                        "type": "data_answer",
                        "title": "数据结论",
                        "content": answer[:500],
                    }],
                    status="done",
                )
            except Exception:
                logger.exception("record AI office mission data_answer failed")
            return {"skill_key": skill_key, "answer": answer}
        return {
            "skill_key": skill_key,
            "awaiting_input": bool(ctx.get("awaiting_input")),
            "result": payload.get("result") if isinstance(payload.get("result"), dict) else (ctx.get("assembled") if isinstance(ctx.get("assembled"), dict) else {}),
        }

    pending = _load_pending_workflow(thread_id)
    if pending:
        pending_opportunity_id = str(pending.get("opportunity_id") or "").strip()
        if pending_opportunity_id:
            opportunity_id = pending_opportunity_id
        await workflow_runner({
            "requirement_text": str(pending.get("requirement_text") or user_text).strip() or user_text,
            "skill_key": pending.get("skill_key"),
            "supplement_text": user_text,
            "force_complete": bool(pending.get("force_complete")),
            "max_ask_rounds": pending.get("max_ask_rounds"),
            "last_ask_question": pending.get("last_ask_question") or "",
            "slot_state": pending.get("slot_state") or {},
            "current_target": pending.get("current_target") or "",
        })
        if workflow_result_sent.get("value"):
            await publish_office_event(role_key, "done", "Skill 工作流已处理", thread_id=thread_id)
        else:
            await publish_office_event(role_key, "error", "需求分析续跑未完成", thread_id=thread_id)
            await assistant_hub.broadcast(thread_id, {"type": "error", "message": "需求分析续跑未完成，请稍后重试。"})
        return

    routed = await route_skill_llm(
        _resolved_skills(colleague),
        user_text,
        conversation_text(history),
        model=(colleague or {}).get("model_override") or None,
    )
    if routed:
        routed_skill = routed.get("skill") if isinstance(routed.get("skill"), dict) else {}
        routed_rule = routed.get("rule") if isinstance(routed.get("rule"), dict) else {}
        routed_key = str(routed_skill.get("workflow_key") or routed_skill.get("key") or "").strip()
        if routed_key:
            action = routed_rule.get("action") if isinstance(routed_rule.get("action"), dict) else {}
            conversation_input = conversation_text(history)
            requirement_source = str(action.get("requirement_source") or "current_or_conversation").strip()
            if requirement_source == "conversation":
                requirement_text = conversation_input or user_text
            elif requirement_source in {"current_or_conversation", "conversation_or_current"}:
                requirement_text = user_text or conversation_input
            else:
                requirement_text = user_text or conversation_input
            supplement_text = "" if requirement_text == conversation_input else conversation_input
            await workflow_runner({
                "requirement_text": requirement_text,
                "skill_key": routed_key,
                "supplement_text": supplement_text,
                "force_complete": bool(action.get("force_complete")),
                "max_ask_rounds": action.get("max_ask_rounds"),
            })
            if workflow_result_sent.get("value"):
                try:
                    repo = SkillCatalogRepository()
                    try:
                        repo.increment_hit(str(routed_skill.get("key") or routed_key).strip())
                    finally:
                        repo.close()
                except Exception:
                    logger.exception("record skill trigger hit failed for %s", routed_key)
                await publish_office_event(role_key, "done", "Skill 工作流已处理", thread_id=thread_id)
                return

    started = time.perf_counter()
    if not allowed_tool_ids:
        await publish_office_event(role_key, "thinking", "切换普通对话", thread_id=thread_id)
        await _run_plain_turn(
            thread_id, user_text, context_summary, history, colleague, memory_block,
            final_office_event=final_office_event, trace_sink=trace_sink,
        )
        return

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
    )
    if workflow_result_sent.get("value"):
        await publish_office_event(role_key, "done", "Skill 工作流已处理", thread_id=thread_id)
        return
    if result.get("ok") and str(result.get("answer") or "").strip():
        final_text = str(result["answer"]).strip()
        trace_status = "ok"
        trace_error = None
    else:
        await publish_office_event(role_key, "thinking", "工具流程未收敛，切换普通对话", thread_id=thread_id)
        await _run_plain_turn(
            thread_id, user_text, context_summary, history, colleague, memory_block,
            final_office_event=final_office_event, trace_sink=trace_sink,
        )
        return

    await assistant_hub.broadcast(thread_id, {"type": "chunk", "delta": final_text})
    await _remember_reply(colleague, final_text)
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
) -> None:
    """Route one colleague message through the unified runtime."""
    role_key = (colleague or {}).get("role_key") or "assistant"
    try:
        await publish_office_event(role_key, "thinking", "正在思考回复", thread_id=thread_id)
        memory_block = await _memory_block(colleague, user_text)
        allowed_tool_ids = _effective_tool_ids(colleague)
        # 无论如何，只要已存在追问中的 workflow（pending），必须回到 _run_tool_turn 续跑，
        # 不能因为本轮 colleague 绑定/解析不同而落入 _run_plain_turn 自由对话（否则 AI 会“自由总结”绕过图）。
        if allowed_tool_ids or _has_workflow_skills(colleague) or _load_pending_workflow(thread_id):
            await _run_tool_turn(
                thread_id,
                user_text,
                context_summary,
                history,
                colleague,
                memory_block,
                allowed_tool_ids,
                final_office_event=final_office_event,
                trace_sink=trace_sink,
                user=user,
                opportunity_id=opportunity_id,
            )
        else:
            await _run_plain_turn(
                thread_id,
                user_text,
                context_summary,
                history,
                colleague,
                memory_block,
                final_office_event=final_office_event,
                trace_sink=trace_sink,
            )
    except Exception as e:
        logger.exception("colleague turn runtime failed")
        await assistant_hub.broadcast(thread_id, {"type": "error", "message": f"回复处理失败：{e}"})
