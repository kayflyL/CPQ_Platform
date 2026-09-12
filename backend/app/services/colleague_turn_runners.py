# -*- coding: utf-8 -*-
"""AI 同事回合的三种执行器。

从 colleague_turn_service.py 拆出（2026-09-11，零行为改动）：
- _run_plain_turn：无工具的普通对话（流式思考 + 正文）
- _run_tool_turn：有工具的角色走 ReAct 循环（含审批中断）
- _run_skill_chat：绑定 workflow skill 的角色走对话脑（skill_chat）

依赖方向：colleague_prompt ← colleague_turn_io ← 本模块 ← colleague_turn_service（薄壳）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Optional

from app.services import llm_client
from app.services.agent_react import run_react_loop
from app.services.agent_tool_specs import tool_requires_approval
from app.services.assistant_hub import assistant_hub
from app.services.colleague_prompt import (
    _base_messages,
    _effective_data_sources,
    _handoff_hint,
    _resolved_skills,
    _schedule_memory_extraction,
    _short_term_history,
    _skill_for_tool,
    _skill_prompt,
    _style_hint,
    _user_name,
    build_chat_config,
)
from app.services.colleague_turn_io import (
    _add_assistant_message,
    _ensure_ai_office_opportunity,
    _persist_and_broadcast,
    _trace,
)
from app.services.llm_client import LLMError
from app.services.office_access import allowed_chat_role_keys
from app.services.office_events import publish_office_event
from app.services.office_governance import office_governance
from app.services.office_mission import record_mission
from app.services.skill_contracts import SKILL_SESSION_ACTIVE
from app.services.skill_types import is_workflow_skill

logger = logging.getLogger(__name__)


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
        if is_workflow_skill(skill):
            return skill
    return None


def _skill_phase_hint(skill_manifest: Optional[dict], phase: Optional[str]) -> str:
    """把 skill 能力描述转成同一大脑回合内的一段阶段指令。

    2026-09-09（工作流显式发起后）：只剩 ACTIVE（任务进行中/试运行直启）给任务态指令；
    引擎内联、不落库；IDLE/PROPOSING 提交/确认轮与 submit_registration 已整体移除。
    """
    if not isinstance(skill_manifest, dict) or phase != SKILL_SESSION_ACTIVE:
        return ""
    return (
        "\n\n这是技能试运行/任务续跑：用户输入就是需求上下文，直接推进流程；"
        "是否反问由流程策略（缺口卡）决定，无需等待确认。"
    )


# 落库写模式（B1，2026-09-12）：入口显式决定，不再依赖全仓从不写入的 business_mode。
PREVIEW_ENTRY_POINTS = {"skill_studio_preview"}


def _skill_write_mode(entry_point: Optional[str], opportunity_id: Optional[str]) -> str:
    """试运行入口 → preview（不落库）；带商机 → draft（每步原地写回草稿）；都没有 → none。"""
    if str(entry_point or "").strip() in PREVIEW_ENTRY_POINTS:
        return "preview"
    return "draft" if str(opportunity_id or "").strip() else "none"


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
            "message": str(office_action.get("message") or ""),
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
        # 审批中断与技能暂停用同一份载荷（P5-B3）：形状=工厂，只有事实与原因码，不再手搓第二套。
        from app.services.skill_plan_runtime import pause_payload
        pause = pause_payload(kind="approval",
                              pending=[{"governance_id": item_id, "tool": name}],
                              steps_done=[])
        await assistant_hub.broadcast(thread_id, {
            "type": "approval_required",
            "governance_id": item_id,
            "tool": name,
            "message": approval_msg,
            "pause": pause,
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
    from app.services.skill_memory import _load_mem
    return bool(_load_mem(thread_id, role_key))


async def _run_skill_chat(thread_id, user_text, context_summary, history, colleague, memory_block,
                          final_office_event=None, trace_sink=None, user=None,
                          opportunity_id=None, option_slot=None, card_selections=None,
                          force_submit: bool = False,
                          skill_manifest: Optional[dict] = None,
                          session_phase: Optional[str] = None,
                          write_mode: str = "",
) -> None:
    """绑定工作流 Skill 的 AI 角色：普通聊天阶段不读 Skill 节点内容；
    force_submit=True 表示已确认/试运行/续跑，直接进入固定六步引擎，不再由模型决定是否提交。"""
    from app.services.skill_chat import handle_skill_chat_turn
    from app.services.skill_memory import load_skill_session, save_skill_session

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
        if (payload or {}).get("type") in ("node_trace", "pipeline_start", "pipeline_paused", "pipeline_waiting", "pipeline_done", "error"):
            await raw_broadcast(payload)

    if not opportunity_id:
        opportunity_id = _ensure_ai_office_opportunity(thread_id, user, user_text)

    await publish_office_event(role_key, "working", "接收新任务", message=user_text or "", thread_id=thread_id)

    phase_hint = _skill_phase_hint(skill_manifest, session_phase)

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
            skill_phase_hint=phase_hint, write_mode=write_mode,
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

    if kind in ("done", "gaps"):
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
            hint = ""
            try:
                from app.repository.reasoning_flow_repo import ReasoningFlowRepository
                _repo = ReasoningFlowRepository()
                try:
                    _flow = _repo.ensure_skill_flow("requirement_analysis", name="需求分析")
                finally:
                    _repo.close()
                hint = str(((_flow or {}).get("node_configs") or {}).get("output", {})
                           .get("description") or "").strip()
            except Exception:
                logger.exception("收尾汇报纪律回读失败（左栏 output 节点使命）")
            system = build_chat_config(colleague)["chat_system_prompt"]
            if hint:
                system = system + "\n\n" + hint
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
        await raw_broadcast({"type": "turn_finished"})
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
        await raw_broadcast({"type": "turn_finished"})
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
        # 回合规范终态信号（协议统一）：每种结局（gaps/done/error/chat）最后一个事件都是
        # turn_finished，消费方据此收工，不再靠静默超时猜。前端 default 分支忽略它。
        # 不复用 pipeline_done：前端该分支会把 paused 改写成 done，误标任务状态。
        await assistant_hub.broadcast(thread_id, {"type": "turn_finished"})
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
    await assistant_hub.broadcast(thread_id, {"type": "turn_finished"})
