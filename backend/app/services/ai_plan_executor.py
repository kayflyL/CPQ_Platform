# -*- coding: utf-8 -*-
"""AI 角色计划执行器（需求分析 skill 专用，先由 executor='ai_plan' 开关接入）。

目标：把「节点自己动脑」改成「AI 角色按计划执行」。

- graph 只用于声明步骤、提供 node_configs（目标/工具/契约）。
- agent_fill 复用外层 AI 抽槽；model_reason / kp_reason 由 AI 调工具做决定，
  但料号/价格/机型只能来自工具返回，最后走确定性校验。
- compose / output 不调 LLM，只做组装、校验、落库与事件广播。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Optional

from app.services.capability_executor import _graph_maps, _trace_preview
from app.services.reasoning_executor import _handle_agent_fill, _handle_compose, _handle_generic_output

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Any]


def _answer_obj(answer: Any) -> dict:
    if isinstance(answer, dict):
        return answer
    text = str(answer or "").strip()
    if not text:
        return {}
    try:
        obj = json.loads(text)
    except Exception:
        try:
            from app.services.llm_client import _parse_json_content
            obj = _parse_json_content(text)
        except Exception:
            return {}
    return obj if isinstance(obj, dict) else {}


def _selected_name(obj: dict) -> str:
    for key in ("selected", "selected_name", "model", "model_name", "name"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("config_id", "model_id", "selected_id"):
        value = obj.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _dedupe_parts(parts: list) -> list:
    seen: set = set()
    out: list = []
    for part in (parts or []):
        if not isinstance(part, dict):
            continue
        key = (str(part.get("category") or ""), str(part.get("pn") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


async def _agent_fill_step(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    from app.services.capabilities import extract_requirement_slots
    _cfg = dict(config or {})
    _cfg.setdefault("llm_enabled", ctx.get("llm_enabled", True))
    res = await extract_requirement_slots(ctx, _cfg, broadcast)
    if res.get("ok") or res.get("missing_critical"):
        ctx["agent_fill_missing"] = res.get("missing_critical") or []
        ctx["agent_fill_done"] = bool(res.get("done", True))
        ctx["agent_fill_ask"] = str(res.get("ask") or "").strip()
        if res.get("delegated"):
            ctx["delegated"] = True
    return await _handle_agent_fill(ctx, _cfg, broadcast)


async def _model_reason_step(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """AI 调 select_models 决策候选；事实源用 AI 实际工具参数回放取完整机型。"""
    from app.services.agent_react import run_react_loop
    from app.services import prompt_store
    from app.services.capabilities import run_select_baseline_rule
    from app.api.candidate_search import select_models

    ext = dict(ctx.get("ext") or {})
    slots = {
        "server_type": ext.get("server_type_name") or ext.get("server_type"),
        "series": ext.get("series") or ext.get("platform_type"),
        "form": ext.get("form") or ext.get("chassis_form"),
        "purchase_qty": ext.get("purchase_qty") or ext.get("n"),
        "categories": ext.get("categories"),
        "gpu_groups": ext.get("gpu_groups"),
    }
    extra = ("当前线索登记表：" + json.dumps(slots, ensure_ascii=False) +
             "\n必须调用 select_models 查事实；只能从返回的候选中选一台，禁止编造型号。"
             "\n如果需求里有 GPU 卡数，应优先按 AI/加速计算场景选机型，不要把 GPU 需求归到通用计算。")
    sys_prompt = str((config or {}).get("system_prompt") or "").strip() or str(
        prompt_store.get_prompt_defaults("model_reason_ai").get("system_prompt")
        or prompt_store.get_prompt_defaults("model_reason").get("system_prompt") or "")
    if not sys_prompt:
        sys_prompt = "你是服务器选型决策器。只能从 select_models 返回的候选中选一台，禁止编造型号。"
    result = await run_react_loop(
        requirement_text=str(ctx.get("requirement_text") or "（无需求原文）"),
        config={**config, "enabled_tools": ["select_models", "get_server_model"]},
        system_prompt=sys_prompt,
        history=[],
        extra_context=extra,
        max_iterations=min(int((config or {}).get("max_iterations") or 3), 3),
        event_sink=broadcast,
        prefer_text_react=True,
        final_only=False,
    )
    baselines: list = []
    for tc in (result.get("tool_calls_log") or []):
        if tc.get("name") != "select_models":
            continue
        args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
        try:
            baselines = select_models(
                args.get("usage"),
                args.get("server_type_name"),
                args.get("series"),
                args.get("form"),
                limit=None,
                fallback_order=args.get("fallback_order") or ["exact", "same_series", "same_form", "all"],
            )
        except Exception as exc:
            logger.warning("回放 select_models 参数失败: %s", exc)
        if baselines:
            break
    if not baselines:
        run_select_baseline_rule(ctx, config)
        baselines = list(ctx.get("baselines") or [])
    if not baselines:
        ctx["awaiting_input"] = False
        ctx["model_reason"] = {"source": "ai_plan", "reason": "目录未命中机型"}
        return {"count": 0, "matches": [], "source": "ai_plan", "reason": "目录未命中机型"}

    chosen_name = _selected_name(_answer_obj(result.get("answer")))
    locked = None
    if chosen_name:
        low = chosen_name.lower()
        for b in baselines:
            name = str(b.get("name") or "").strip()
            mid = str(b.get("id") or b.get("server_model_id") or "").strip()
            if name and low == name.lower():
                locked = b
                break
            if mid and low == mid:
                locked = b
                break
        if locked is None:
            for b in baselines:
                name = str(b.get("name") or "").strip()
                if name and low in name.lower():
                    locked = b
                    break
    if locked is None:
        locked = baselines[0]

    ctx["baselines"] = [locked]
    ctx["model_selection"] = {"id": locked.get("id"), "name": locked.get("name") or ""}
    ctx["model_reason"] = {"source": "ai_plan", "baseline": locked,
                           "reason": "AI 已按需求选择机型 " + str(locked.get("name") or "")}
    ctx["awaiting_input"] = False
    return {"count": 1, "matches": [{
        "config_id": locked.get("id"), "name": locked.get("name") or "",
        "series": locked.get("series") or "", "form": locked.get("form") or "",
        "match_stage": locked.get("match_stage"), "fallback_note": locked.get("fallback_note") or "",
    }], "source": "ai_plan", "reason": "已按需求锁定机型，继续配件选配"}


async def _kp_reason_step(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """AI 调 select_parts 编排配件；parts_proposal 只从工具结果回收，LLM 不写料号。"""
    from app.services.agent_react import run_react_loop
    from app.services import prompt_store

    ext = dict(ctx.get("ext") or {})
    baseline = (ctx.get("baselines") or [None])[0]
    slots = {
        "server_type_name": ext.get("server_type_name"),
        "categories": ext.get("categories"),
        "cpu_signal": ext.get("cpu_signal"),
        "mem_signal": ext.get("mem_signal"),
        "drive_groups": ext.get("drive_groups"),
        "gpu_groups": ext.get("gpu_groups"),
        "raid_groups": ext.get("raid_groups"),
        "psu_signal": ext.get("psu_signal"),
        "purchase_qty": ext.get("purchase_qty"),
    }
    extra = ("当前线索登记表：" + json.dumps(slots, ensure_ascii=False) +
             "\n已锁机型：" + (baseline.get("name") if isinstance(baseline, dict) else "（未锁定）") +
             "\n用 select_parts 查事实；把需求里的数量/规格翻译成 categories/qty_map/search_map，"
             "不要编造料号；工具未匹配的项要保留 unmatched。")
    sys_prompt = str((config or {}).get("system_prompt") or "").strip() or str(
        prompt_store.get_prompt_defaults("kp_reason_ai").get("system_prompt")
        or prompt_store.get_prompt_defaults("kp_reason").get("system_prompt") or "")
    if not sys_prompt:
        sys_prompt = "你是配件选型编排器。只能从 select_parts 返回的候选中组提案，禁止编造料号。"
    result = await run_react_loop(
        requirement_text=str(ctx.get("requirement_text") or "（无需求原文）"),
        config={**config, "enabled_tools": ["select_parts"]},
        system_prompt=sys_prompt,
        history=[],
        extra_context=extra,
        max_iterations=min(int((config or {}).get("max_iterations") or 3), 3),
        event_sink=broadcast,
        prefer_text_react=True,
        final_only=False,
    )
    parts: list = []
    for tc in (result.get("tool_calls_log") or []):
        if tc.get("name") != "select_parts":
            continue
        res = tc.get("result") if isinstance(tc.get("result"), dict) else {}
        parts.extend(res.get("parts") or [])
    parts = _dedupe_parts(parts)
    if not parts:
        from app.services.capabilities import run_match_kp_rule
        rule_res = run_match_kp_rule(ctx, config)
        ctx["kp_reason"] = {**rule_res, "source": "ai_plan-empty"}
        ctx["awaiting_input"] = False
        return {**rule_res, "source": "ai_plan-empty", "reason": "配件工具未返回候选"}

    mid = None
    if isinstance(baseline, dict):
        mid = baseline.get("server_model_id") or baseline.get("id")
    ctx["kp_parts"] = parts
    if mid is not None:
        ctx["kp_by_model"] = {str(mid): parts}
    by_category: dict[str, int] = {}
    for part in parts:
        cat = str(part.get("category") or "其他")
        by_category[cat] = by_category.get(cat, 0) + 1
    unmatched_count = sum(1 for part in parts if part.get("unmatched"))
    ctx["kp_reason"] = {"source": "ai_plan", "by_category": by_category,
                        "unmatched_count": unmatched_count, "reason": "AI 已编排配件选型"}
    ctx["awaiting_input"] = False
    return {"kp_count": len(parts), "by_category": by_category,
            "unmatched_count": unmatched_count, "source": "ai_plan",
            "reason": "配件方案已由 AI 编排"}


async def run_ai_skill_plan(
    thread_id: str,
    requirement_text: str,
    flow: dict,
    broadcast: BroadcastFn,
    initial_ctx: Optional[dict] = None,
    ctx_ref: Optional[dict] = None,
) -> dict:
    """按 flow.graph 的声明步骤执行，AI 角色做决策，节点只做进度/契约/校验。"""
    node_configs = flow.get("node_configs") or {}
    nodes, adj, indeg, order = _graph_maps(flow)
    ctx: dict = {
        "requirement_text": requirement_text,
        "opportunity_id": thread_id,
        "flow_configs": node_configs,
        "llm_enabled": True,
    }
    if initial_ctx:
        ctx.update(initial_ctx)
    if ctx_ref is not None:
        ctx_ref["ctx"] = ctx
    timings = ctx.setdefault("timings", {})

    steps = [
        {"key": nid, "label": (node.get("label") or nid)}
        for nid, node in sorted(nodes.items(), key=lambda item: order.get(item[0], 9999))
        if (node.get("runtime") or node.get("type")) not in ("condition", "extract")
    ]
    await broadcast({"type": "pipeline_start", "steps": steps})

    queue: list[str] = [nid for nid in sorted(nodes, key=lambda n: order.get(n, 9999))]
    visited: set = set()
    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)
        node = nodes[node_id]
        node_type = node.get("runtime") or node.get("type") or node_id
        config = node_configs.get(node_id) or {}
        label = node.get("label") or node_id

        if node_type in ("condition", "extract"):
            continue
        input_preview, _, _, _ = _trace_preview(node_type, ctx)
        await broadcast({"type": "step_start", "step": node_id, "label": label, "input": input_preview})
        _t0 = time.perf_counter()
        try:
            if node_type == "agent_fill":
                payload = await _agent_fill_step(ctx, config, broadcast)
            elif node_type == "model_reason":
                payload = await _model_reason_step(ctx, config, broadcast)
            elif node_type == "kp_reason":
                payload = await _kp_reason_step(ctx, config, broadcast)
            elif node_type == "compose":
                payload = await _handle_compose(ctx, config, broadcast)
            elif node_type == "output":
                payload = await _handle_generic_output(ctx, config, broadcast)
            else:
                payload = {"skipped": node_type}
        except Exception as exc:
            logger.exception("ai_plan node failed node=%s type=%s", node_id, node_type)
            ctx["fatal_error"] = str(exc)
            return ctx
        duration_ms = round((time.perf_counter() - _t0) * 1000, 1)
        _, output_preview, artifact, summary = _trace_preview(node_type, ctx, payload)
        await broadcast({"type": "step_done", "step": node_id, "payload": payload,
                         "duration_ms": duration_ms, "input": input_preview,
                         "output": output_preview, "artifact": artifact, "summary": summary})
        if ctx.get("awaiting_input") or ctx.get("flow_exit") == "cancelled":
            return ctx
    timings["plan_total_ms"] = round((time.perf_counter() - timings.get("_t0", time.perf_counter())) * 1000, 1)
    return ctx
