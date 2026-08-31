# -*- coding: utf-8 -*-
"""Skill 计划执行器（试运行/画布预览入口）。

只负责把试运行参数装配成核心内核的 ctx 契约，然后交给硬编排阶段机：
backend/app/services/skill_plan_runtime.run_skill_plan_core。
真实 AI 角色对话路径（colleague_turn_service）走同一内核，保证两入口行为一致。
"""
from __future__ import annotations

import time
from typing import Any, Callable, Optional

from app.services.skill_plan_runtime import run_skill_plan_core

BroadcastFn = Callable[[dict], Any]


async def run_skill_plan(
    thread_id: str,
    requirement_text: str,
    flow: dict,
    broadcast: BroadcastFn,
    initial_ctx: Optional[dict] = None,
    ctx_ref: Optional[dict] = None,
) -> dict:
    """试运行入口：与 AI 角色对话共用同一硬编排内核。"""
    flow_configs = dict(flow.get("node_configs") or {})
    ctx: dict = {
        "requirement_text": str(requirement_text or "").strip(),
        "normalized_text": str(requirement_text or "").strip(),
        "opportunity_id": thread_id,
        "flow_configs": flow_configs,
        "llm_enabled": True,
        "business_mode": "conversation",
        "ext": {},
        "requirement": {},
        "history": [],
        "timings": {"_t0": time.perf_counter()},
    }
    if isinstance(initial_ctx, dict):
        for k, v in initial_ctx.items():
            if v is not None:
                ctx[k] = v
    if ctx_ref is not None:
        ctx_ref["ctx"] = ctx

    return await run_skill_plan_core(ctx, flow_configs, broadcast)
