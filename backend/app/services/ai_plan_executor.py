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

from app.services.capability_executor import _clear_workflow_stop, _graph_maps, _trace_preview, _workflow_stop_event
from app.services.skill_node_runtime import agent_fill_validate, compose_plans, finalize_output

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


_KP_SIGNAL_KEYS = (
    "categories", "cpu_signal", "mem_signal", "drive_groups",
    "gpu_groups", "raid_groups", "psu_signal", "multi_spec_filters",
)


def _merge_ai_wins_base_fallback(base: dict, override: Optional[dict]) -> dict:
    """合并 select_parts 参数：AI 给出的非空字段优先，登记表只兜底 AI 未给的字段。

    原因：客户需求原文是覆盖范围真值源，结构化登记表只是缓存。AI 从原文补全或修正
    信号后，不能再被登记表的旧值压回（例如 agent_fill 漏抽 drive_groups 时，AI 补出
    的盘组必须生效）。递归合并 dict，标量/列表由 AI 值覆盖；AI 空值不覆盖，避免误删。
    """
    out: dict = dict(base or {})
    for key, value in (override or {}).items():
        if value in (None, "", []):
            continue
        if key not in out or out.get(key) in (None, "", []):
            out[key] = value
        elif isinstance(out.get(key), dict) and isinstance(value, dict):
            out[key] = _merge_ai_wins_base_fallback(out[key], value)
        else:
            out[key] = value
    return out


def _writeback_signals(ctx: dict, signals: dict) -> None:
    """把归并后的 select_parts 信号写回 ctx.ext 与 ctx.requirement。

    登记表只读快照的旧约定已经废弃：原文是真相源，结构化 slots 只是可修正缓存。
    这里只回写 select_parts 会消费的信号字段，避免污染机型/语义等其他字段。
    """
    import copy as _copy
    ext = dict(ctx.get("ext") or {})
    for key in _KP_SIGNAL_KEYS:
        if key in signals:
            ext[key] = _copy.deepcopy(signals[key])
    ctx["ext"] = ext
    req = dict(ctx.get("requirement") or {})
    for key in _KP_SIGNAL_KEYS:
        if key in signals:
            req[key] = _copy.deepcopy(signals[key])
    ctx["requirement"] = req


async def _input_step(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """input 的确定性入口：把用户文本规范化进共享 skill 上下文，无 LLM。"""
    raw = str(ctx.get("requirement_text") or "").strip()
    ctx["input"] = raw
    ctx["skill_input"] = raw
    ctx["normalized_text"] = raw
    return {"input": raw}


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
    return await agent_fill_validate(ctx, _cfg, broadcast)


async def _run_decision_loop(
    ctx: dict,
    config: dict,
    enabled_tools: list,
    system_prompt: str,
    extra_context: str,
    max_iterations: int,
    broadcast: BroadcastFn,
) -> dict:
    """唯一决策循环入口：AI 角色在本步骤内调用工具做选择/补全，返回 tool_calls_log 与 answer。

    事实（机型/料号/价格/兼容）不得来自本循环的最终文本输出，只来自后续确定性工具回收。
    """
    from app.services.agent_react import run_react_loop
    return await run_react_loop(
        requirement_text=str(ctx.get("requirement_text") or "（无需求原文）"),
        config={**config, "enabled_tools": list(enabled_tools)},
        system_prompt=system_prompt,
        history=[],
        extra_context=extra_context,
        max_iterations=max_iterations,
        event_sink=broadcast,
        prefer_text_react=False,
        final_only=False,
    )


async def _model_reason_step(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """AI 调 select_models 决策候选；事实源用 AI 实际工具参数回放取完整机型。"""
    from app.services.capabilities import run_select_baseline_rule
    from app.services.agent_tools import build_tool_registry

    ext = dict(ctx.get("ext") or {})
    slots = {
        "server_type": ext.get("server_type_name") or ext.get("server_type"),
        "series": ext.get("series") or ext.get("platform_type"),
        "form": ext.get("form") or ext.get("chassis_form"),
        "purchase_qty": ext.get("purchase_qty") or ext.get("n"),
        "categories": ext.get("categories"),
        "gpu_groups": ext.get("gpu_groups"),
    }
    type_name = ext.get("server_type_name") or ext.get("server_type") or ""
    series = ext.get("series") or ext.get("platform_type") or ""
    form = ext.get("form") or ext.get("chassis_form") or ""
    fallback_args = {
        "usage": "",
        "server_type_name": type_name or None,
        "series": series or None,
        "form": form or None,
    }
    sys_prompt = str((config or {}).get("system_prompt") or "").strip() or "你是服务器选型决策器。只能从候选机型里选一台，禁止编造型号。"
    extra = ("当前线索登记表草稿（仅参考）：" + json.dumps(slots, ensure_ascii=False) +
             "\n任务：先调用 select_models 获取候选机型；只能从工具返回的候选中选一台；"
             '最终只输出 JSON {"selected_name":"<候选 name>"}。禁止编造型号。')
    result = await _run_decision_loop(ctx, config, ["select_models"], sys_prompt, extra, 3, broadcast)

    select_args = None
    for call in reversed(result.get("tool_calls_log") or []):
        if call.get("name") == "select_models" and isinstance(call.get("args"), dict):
            select_args = dict(call.get("args"))
            break
    if select_args is None:
        select_args = fallback_args

    registry = build_tool_registry(
        {**config, "enabled_tools": ["select_models"]},
        allowed_tool_ids=["select_models"],
    )
    materialized = await registry.execute("select_models", {**select_args, "include_raw": True})
    baselines = materialized.get("raw") if isinstance(materialized, dict) else None
    if not isinstance(baselines, list):
        baselines = []
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

    # 机型字段以锁定候选的目录事实为准，禁止下游继续使用 LLM 抽槽时的自由值。
    _ext = dict(ctx.get("ext") or {})
    if locked.get("server_type_name"):
        _ext["server_type_name"] = locked["server_type_name"]
        _ext["server_type"] = locked["server_type_name"]
    if locked.get("series"):
        _ext["series"] = locked["series"]
    if locked.get("form"):
        _ext["form"] = locked["form"]
    ctx["ext"] = _ext
    _req = dict(ctx.get("requirement") or {})
    _req["server_type_name"] = _ext.get("server_type_name") or ""
    _req["series"] = _ext.get("series") or ""
    _req["form"] = _ext.get("form") or ""
    ctx["requirement"] = _req

    ctx["baselines"] = [locked]
    ctx["model_selection"] = {
        "id": locked.get("id"),
        "name": locked.get("name") or "",
        "server_type_name": locked.get("server_type_name") or "",
        "series": locked.get("series") or "",
        "form": locked.get("form") or "",
    }
    ctx["model_reason"] = {"source": "ai_plan", "baseline": locked,
                           "reason": "AI 已按需求选择机型 " + str(locked.get("name") or "")}
    ctx["awaiting_input"] = False
    return {"count": 1, "matches": [{
        "config_id": locked.get("id"), "name": locked.get("name") or "",
        "server_type_name": locked.get("server_type_name") or "",
        "series": locked.get("series") or "", "form": locked.get("form") or "",
        "match_stage": locked.get("match_stage"), "fallback_note": locked.get("fallback_note") or "",
    }], "source": "ai_plan", "reason": "已按需求锁定机型，继续配件选配"}


async def _kp_reason_step(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """AI 单次补全配件信号，工具确定性落地；parts_proposal 只来自工具返回，LLM 不写料号。"""
    from app.services.agent_tools import build_tool_registry

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
        "multi_spec_filters": ext.get("multi_spec_filters"),
        "purchase_qty": ext.get("purchase_qty"),
    }
    req_text = str(ctx.get("requirement_text") or ctx.get("normalized_text") or "").strip()
    extra = ("客户需求原文（覆盖范围唯一真值源）：\n" + (req_text or "（无原文）") +
             "\n\n线索登记表缓存（仅已归一化的值，缺失或与原文冲突时以原文为准）：" +
             json.dumps(slots, ensure_ascii=False) +
             "\n已锁机型：" + (baseline.get("name") if isinstance(baseline, dict) else "（未锁定）") +
             "\n任务：先把原文逐项对照登记表，凡是原文提到、登记表却漏掉的配件类别"
             "（CPU/内存/盘/GPU/阵列卡/网卡/电源等），都要从原文补进对应的 select_parts 信号；"
             "登记表与原文冲突时以原文修正。"
             "语义术语/别名（如「兆芯」）先调 resolve_part_alias；内存只给总容量先调 compose_memory；"
             "类目不确定先调 list_kp_categories；然后调用 select_parts，参数必须覆盖原文全部配件类别。"
             "内存缺 speed_mt 时去原文找，找不回留空不要填 6400；盘缺 interface/qty 时从原文补；"
             "GPU 缺型号时补 tokens；RAID 只给级别时补 raid_levels，不要写 model。"
             "料号/价格由工具返回，禁止编造料号。")
    sys_prompt = str((config or {}).get("system_prompt") or "").strip() or "你是配件选型编排器。只补全规格，不编造料号。"
    result = await _run_decision_loop(ctx, config, ["list_kp_categories", "select_parts", "resolve_part_alias", "compose_memory"], sys_prompt, extra, 4, broadcast)
    registry = build_tool_registry(
        {**config, "enabled_tools": ["list_kp_categories", "select_parts", "resolve_part_alias", "compose_memory"]},
        allowed_tool_ids=["list_kp_categories", "select_parts", "resolve_part_alias", "compose_memory"],
    )
    base_args = {k: v for k, v in slots.items()
                 if k != "purchase_qty" and v not in (None, "", [])}
    ai_args = {}
    for call in reversed(result.get("tool_calls_log") or []):
        if call.get("name") == "select_parts" and isinstance(call.get("args"), dict):
            ai_args = dict(call.get("args"))
            break
    merged_args = _merge_ai_wins_base_fallback(base_args, ai_args)
    tool_result = await registry.execute("select_parts", merged_args)
    _writeback_signals(ctx, merged_args)
    parts = []
    if isinstance(tool_result, list):
        parts = tool_result
    elif isinstance(tool_result, dict):
        raw_parts = tool_result.get("parts")
        if isinstance(raw_parts, list):
            parts = raw_parts
        elif isinstance(tool_result, dict) and tool_result.get("error"):
            parts = []
    parts = _dedupe_parts(parts)
    if not parts:
        ctx["kp_parts"] = []
        ctx["kp_by_model"] = {}
        ctx["kp_reason"] = {"source": "ai_plan", "by_category": {},
                            "unmatched_count": 0, "spec_mismatch_count": 0,
                            "reason": "无配件信号，工具未返回候选"}
        ctx["awaiting_input"] = False
        return {"kp_count": 0, "by_category": {}, "unmatched_count": 0,
                "spec_mismatch_count": 0,
                "source": "ai_plan", "reason": "无配件信号，工具未返回候选"}

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
    spec_mismatch_count = sum(1 for part in parts if part.get("spec_mismatch"))
    ctx["kp_reason"] = {"source": "ai_plan", "by_category": by_category,
                        "unmatched_count": unmatched_count,
                        "spec_mismatch_count": spec_mismatch_count,
                        "reason": "AI 已编排配件选型"}
    ctx["awaiting_input"] = False
    return {"kp_count": len(parts), "by_category": by_category,
            "unmatched_count": unmatched_count, "source": "ai_plan",
            "spec_mismatch_count": spec_mismatch_count,
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
    timings["_t0"] = time.perf_counter()

    stop_event = _workflow_stop_event(thread_id)
    stop_event.clear()

    steps = [
        {"key": nid, "label": (node.get("label") or nid)}
        for nid, node in sorted(nodes.items(), key=lambda item: order.get(item[0], 9999))
        if (node.get("runtime") or node.get("type")) not in ("condition", "extract")
    ]
    await broadcast({"type": "pipeline_start", "steps": steps})

    if stop_event.is_set():
        ctx["stop_requested"] = True
        ctx["awaiting_input"] = True
        ctx["current_target"] = next(iter(nodes), "input")
        ctx["last_ask_question"] = "任务已暂停，等待你的下一步指令。"
        return ctx

    queue: list[str] = [nid for nid in sorted(nodes, key=lambda n: order.get(n, 9999))]
    visited: set = set()
    while queue:
        if stop_event.is_set():
            ctx["stop_requested"] = True
            ctx["awaiting_input"] = True
            ctx["current_target"] = queue[0]
            ctx["last_ask_question"] = "任务已暂停，等待你的下一步指令。"
            return ctx
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
            if node_type == "input":
                payload = await _input_step(ctx, config, broadcast)
            elif node_type == "agent_fill":
                payload = await _agent_fill_step(ctx, config, broadcast)
            elif node_type == "model_reason":
                payload = await _model_reason_step(ctx, config, broadcast)
            elif node_type == "kp_reason":
                payload = await _kp_reason_step(ctx, config, broadcast)
            elif node_type == "compose":
                payload = await compose_plans(ctx, config, broadcast)
            elif node_type == "output":
                payload = await finalize_output(ctx, config, broadcast)
            else:
                ctx.setdefault("exec_trace", []).append({"type": node_type, "status": "skipped_unknown"})
                logger.warning("未知节点类型，跳过执行: %s", node_type)
                payload = {"skipped": "unknown_node", "node": node_type}
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
    _clear_workflow_stop(thread_id)
    timings["plan_total_ms"] = round((time.perf_counter() - timings.get("_t0", time.perf_counter())) * 1000, 1)
    return ctx
