# -*- coding: utf-8 -*-
"""Skill 计划执行器（仅试运行/画布预览等无 AI 角色上下文时使用）。

这里只有一个主循环：把固定节点计划注入 system prompt，让模型在同一个会话里按
节点声明调用工具；节点进度/产物保存由 skill_plan_runtime 的确定性守卫完成。
正常业务对话不应调用本模块，AI 角色应直接在自己的 _run_tool_turn 主循环中执行。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from app.services.agent_react import run_react_loop
from app.services.skill_plan_runtime import (
    apply_skill_decision,
    build_skill_plan_prompt,
    finalize_skill_artifacts,
    make_skill_tool_guard,
    skill_allowed_tools,
)

BroadcastFn = Callable[[dict], Any]


async def run_skill_plan(
    thread_id: str,
    requirement_text: str,
    flow: dict,
    broadcast: BroadcastFn,
    initial_ctx: Optional[dict] = None,
    ctx_ref: Optional[dict] = None,
) -> dict:
    """试运行入口：单次 Agent 会话按画布计划执行，不再按节点各起 LLM。"""
    node_configs = flow.get("node_configs") or {}
    ctx: dict = {
        "requirement_text": requirement_text,
        "normalized_text": requirement_text,
        "opportunity_id": thread_id,
        "flow_configs": node_configs,
        "llm_enabled": True,
        "timings": {"_t0": time.perf_counter()},
    }
    if initial_ctx:
        ctx.update(initial_ctx)
    if ctx_ref is not None:
        ctx_ref["ctx"] = ctx
    ctx_holder: dict = {"ctx": ctx}

    plan_prompt = build_skill_plan_prompt(flow)
    skill_tools = skill_allowed_tools(flow)
    guard = make_skill_tool_guard(flow, ctx_holder, broadcast, thread_id)

    async def _run(prompt: str, tools: list[str], max_iterations: int = 8) -> dict:
        return await run_react_loop(
            requirement_text or "（无需求原文）",
            {"enabled_tools": tools},
            system_prompt=prompt,
            allowed_tool_ids=tools,
            history=ctx.get("history") or [],
            event_sink=broadcast,
            tool_guard=guard,
            max_iterations=max_iterations,
            llm_reasoning_effort="low",
        )

    result = await _run(plan_prompt, skill_tools, int(initial_ctx.get("max_iterations") or 8) if initial_ctx else 8)
    answer = str((result or {}).get("answer") or "") if isinstance(result, dict) else str(result or "")
    if isinstance(result, dict) and result.get("ok") is False:
        ctx["fatal_error"] = str(result.get("error") or "需求分析主循环未收敛")[:200]
    else:
        apply_skill_decision(ctx, answer)
        if not ctx.get("awaiting_input") and ctx.get("baselines") and not ctx.get("kp_parts"):
            phase_tools = [t for t in skill_tools if t in ("list_kp_categories", "select_parts", "resolve_part_alias", "compose_memory")]
            phase_prompt = plan_prompt + "\n\n当前已锁定机型，必须继续执行配件选型阶段：调用 select_parts，把原文中的每一类配件、每个盘组/GPU 组都逐行覆盖，禁止只配部分盘。完成后按最终回复约束输出 JSON。"
            result = await _run(phase_prompt, phase_tools, 8)
            answer = str((result or {}).get("answer") or "") if isinstance(result, dict) else str(result or "")
            if isinstance(result, dict) and result.get("ok") is False:
                ctx["fatal_error"] = str(result.get("error") or "配件选型阶段未收敛")[:200]
            else:
                apply_skill_decision(ctx, answer)
        if not ctx.get("awaiting_input") and not ctx.get("fatal_error"):
            await finalize_skill_artifacts(ctx, flow, broadcast)
    ctx["timings"]["plan_total_ms"] = round((time.perf_counter() - ctx["timings"].get("_t0", time.perf_counter())) * 1000, 1)
    return ctx
