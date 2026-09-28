# -*- coding: utf-8 -*-
"""Unified AI-colleague turn runtime —— 薄壳。

Every office-colleague chat entry point reaches this service instead of
hardcoded keyword branches. A colleague with tools runs a text-ReAct loop;
a colleague without tools streams a normal conversation. Tool results that
represent draft/write actions are parked in the office governance queue and
must be confirmed before continuing.

2026-09-11 拆分（零行为改动）：实现搬进 colleague_prompt / colleague_turn_io /
colleague_turn_runners，本文件只留「线程串行队列 + 回合总入口 run_colleague_turn」，
并重导出原名字以保持既有导入路径不变（布局守卫见 tests/test_colleague_turn_layout.py）。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from app.services.assistant_hub import assistant_hub
from app.services.colleague_prompt import (
    _effective_tool_ids,
    _group_channel_note,
    _memory_block,
    _resolved_skills,
    _skill_library,
    build_chat_config,
    _base_messages,
    _handoff_hint,
    _has_workflow_skills,
    _memory_policy,
    _short_term_history,
    _skill_for_tool,
    _skill_prompt,
    _style_hint,
    _user_name,
    _workflow_hint,
)
from app.services.colleague_turn_io import (
    _add_assistant_message,
    _ensure_ai_office_opportunity,
    _persist_and_broadcast,
    _trace,
)
from app.services.colleague_turn_runners import (
    _broadcast_chat_progress,
    _first_workflow_skill,
    _run_plain_turn,
    _run_skill_chat,
    _skill_write_mode,
    _run_tool_turn,
    _skill_chat_memory_active,
    _skill_phase_hint,
)
from app.services.office_events import publish_office_event
from app.services.skill_contracts import SKILL_SESSION_ACTIVE
from app.services.skill_memory import flow_delivered, reset_flow_memory
from app.services.skill_registry import resolve_skill_manifest
from app.services.skill_types import is_workflow_skill

logger = logging.getLogger(__name__)


_THREAD_TURN_LOCKS: dict[str, asyncio.Lock] = {}
# Claude Code 语义：任务执行中用户仍可发消息引导——排队等当前回合结束串行续跑，
# 不再拒绝。参数原样保存，drain 时按到达顺序重放进同一入口。
_THREAD_TURN_QUEUE: dict[str, list[dict]] = {}
# 回合在跑的确定事实（供 REST 轮询端点读取，done 丢失时看门狗据此判定终态）：
# 排队中的消息不算在跑，drain 续跑会重新进入 run_colleague_turn 再标记。
_THREAD_TURN_ACTIVE: set[str] = set()


def turn_active(thread_id: str) -> bool:
    """该线程当前是否真有回合在执行（排队等待不算）。"""
    return thread_id in _THREAD_TURN_ACTIVE


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
        await assistant_hub.broadcast(
            thread_id, {"type": "queue_state", "depth": len(_THREAD_TURN_QUEUE.get(thread_id) or [])})
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
    workflow_key: Optional[str] = None,
    channel_kind: Optional[str] = None,
) -> None:
    """Route one colleague message through the unified runtime."""
    role_key = (colleague or {}).get("role_key") or "assistant"
    # 团队群（未绑定同事的总助线程）注入渠道事实块：群成员构成（人类+在册同事数）。
    channel_note = _group_channel_note(user) if channel_kind == "group" else ""
    lock = _THREAD_TURN_LOCKS.setdefault(thread_id, asyncio.Lock())
    if lock.locked():
        # 同线程已有回合在跑：排队串行续跑，不拒绝（Claude Code 语义）。
        _THREAD_TURN_QUEUE.setdefault(thread_id, []).append({
            "thread_id": thread_id, "user_text": user_text, "context_summary": context_summary,
            "history": history, "colleague": colleague, "final_office_event": final_office_event,
            "trace_sink": trace_sink, "user": user, "opportunity_id": opportunity_id,
            "option_slot": option_slot, "card_selections": card_selections, "entry_point": entry_point,
            "workflow_key": workflow_key, "channel_kind": channel_kind,
        })
        msg = "已收到，这条会排在当前任务完成后处理。"
        await assistant_hub.broadcast(thread_id, {"type": "chat_status", "text": msg})
        # 排队可见化（P0-③）：被扣住的消息不能看起来和空闲一样——队列深度实时可数
        await assistant_hub.broadcast(
            thread_id, {"type": "queue_state", "depth": len(_THREAD_TURN_QUEUE[thread_id])})
        return
    try:
        _THREAD_TURN_ACTIVE.add(thread_id)
        async with lock:
            await publish_office_event(role_key, "thinking", "正在思考回复", thread_id=thread_id)
            memory_block = await _memory_block(colleague, user_text, user)
            allowed_tool_ids = _effective_tool_ids(colleague)
            from app.services.skill_memory import load_skill_session, save_skill_session
            session = load_skill_session(thread_id, role_key)
            is_preview = (entry_point or "").strip() == "skill_studio_preview"
            # B1：写模式由入口显式决定（试运行不落库 / 带商机落草稿 / 都没有不落库）；续跑沿用线程记的入口。
            write_mode = _skill_write_mode(
                entry_point or session.get("entry_point"), opportunity_id)

            # 交付守卫（2026-09-13）：方案已交付（phase=DONE 或 compose 已落 steps_done）→ 归普通聊天，不再重放流程。
            _flow_delivered = (not is_preview and flow_delivered(thread_id, role_key))
            if is_preview or (session.get("phase") == SKILL_SESSION_ACTIVE and not _flow_delivered):
                # 预览首条消息按画布当前 skill 起会话；跨流切换的干净重开在 skill_chat._prepare 统一判定。
                skill_key = str(workflow_key or session.get("skill_key") or "requirement_analysis")
                manifest = resolve_skill_manifest(skill_key) or resolve_skill_manifest("requirement_analysis")
                await _run_skill_chat(
                    thread_id, user_text, context_summary, history, colleague, memory_block,
                    final_office_event=final_office_event, trace_sink=trace_sink,
                    user=user, opportunity_id=opportunity_id, option_slot=option_slot,
                    card_selections=card_selections, force_submit=True,
                    skill_manifest=manifest, session_phase=SKILL_SESSION_ACTIVE,
                    write_mode=write_mode,
                )
            elif _skill_chat_memory_active(thread_id, role_key) and not _flow_delivered:
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
                    write_mode=write_mode,
                )
            elif (entry_point or "").strip() == "workflow_launcher":
                # 显式发起：用户点「+」选择某工作流 → 直接进入 ACTIVE，不再走 IDLE→PROPOSING。
                # 首个节点负责按需反问/收集，不在此处预置任何流程内容（防幻觉）。
                requested = str(workflow_key or "").strip()
                bound = _first_workflow_skill(colleague) or {}
                skill_key = requested or str(bound.get("workflow_key") or bound.get("key") or "requirement_analysis")
                bound_keys = {
                    str(s.get("workflow_key") or s.get("key") or "").strip()
                    for s in _resolved_skills(colleague)
                    if is_workflow_skill(s)
                }
                if requested and requested not in bound_keys:
                    skill_key = str(bound.get("workflow_key") or bound.get("key") or "requirement_analysis")
                # 显式发起 = 干净重开（2026-09-13）：清掉上一轮流程记忆（ext/进度/中断点），
                # 否则旧现场（如已锁定机型）会被带进新一轮。非 ACTIVE 才能走到这里，清了才安全。
                reset_flow_memory(thread_id, role_key, {
                    "phase": SKILL_SESSION_ACTIVE,
                    "skill_key": skill_key,
                    "entry_point": entry_point or "",
                })
                manifest = resolve_skill_manifest(skill_key) or resolve_skill_manifest("requirement_analysis")
                await _run_skill_chat(
                    thread_id, user_text, context_summary, history, colleague, memory_block,
                    final_office_event=final_office_event, trace_sink=trace_sink,
                    user=user, opportunity_id=opportunity_id, option_slot=option_slot,
                    card_selections=card_selections, force_submit=True,
                    skill_manifest=manifest, session_phase=SKILL_SESSION_ACTIVE,
                    write_mode=write_mode,
                )
            else:
                # 有工具的角色走 ReAct 工具循环（模块文档契约；2026-09-26 修复：
                # 编排重构后此分支只剩纯文本，工具角色裸聊——提示词承诺 query_data
                # 而运行时没挂工具，模型只能把查询演出来并编造结果）。
                if allowed_tool_ids:
                    await _run_tool_turn(
                        thread_id, user_text, context_summary, history, colleague, memory_block,
                        allowed_tool_ids,
                        final_office_event=final_office_event, trace_sink=trace_sink,
                        user=user, opportunity_id=opportunity_id, option_slot=option_slot,
                        channel_note=channel_note,
                    )
                else:
                    await _run_plain_turn(
                        thread_id, user_text, context_summary, history, colleague, memory_block,
                        final_office_event=final_office_event, trace_sink=trace_sink, user=user,
                        channel_note=channel_note,
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
        _THREAD_TURN_ACTIVE.discard(thread_id)
        # 回合收尾：有排队消息则串行续跑（Claude Code 式执行中引导）。
        if _THREAD_TURN_QUEUE.get(thread_id):
            asyncio.create_task(_drain_thread_queue(thread_id))
