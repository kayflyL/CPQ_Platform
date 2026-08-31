# -*- coding: utf-8 -*-
"""需求分析 Skill 的硬编排引擎（skill plan runtime）。

两器官架构（2026-08-28 宪法）：
- 引擎没有对话能力。它接收结构化登记表，产出**产物**（BOM 方案）或**缺口数据**
  （{slot, options, reason_code} 列表）；"怎么向用户要"属于 AI 角色，不属于这里。
- 阶段顺序由代码固定：normalize → model → kp_gate → kp → compose → output；
- 本模块不 import agent_react；唯一的 LLM 调用点封装在 skill_phases（试运行抽取/受约束选型）；
- 对前端广播 pipeline_start / node_trace(真实产物+真实耗时) / pipeline_paused。
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from app.services.skill_node_runtime import compose_plans, finalize_output

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Awaitable[None]]

PHASE_TABLE = [
    {"key": "input", "label": "需求接收"},
    {"key": "agent_fill", "label": "需求理解填表"},
    {"key": "model_reason", "label": "机型选型"},
    {"key": "kp_reason", "label": "配件选型"},
    {"key": "compose", "label": "BOM 组装"},
    {"key": "output", "label": "产出交接"},
]

# 对客户有意义的里程碑阶段（input/agent_fill 在对话里自然发生，不出现在流程预告里）
USER_FACING_PHASES = {"model_reason", "kp_reason", "compose", "output"}


def skill_steps_view(flow_configs: dict, user_facing_only: bool = False) -> list[dict]:
    """步骤清单单源：角色提议话术与 pipeline_start 共用，画布改 label/description 两处同步变。"""
    steps = []
    for ph in PHASE_TABLE:
        if user_facing_only and ph["key"] not in USER_FACING_PHASES:
            continue
        cfg = flow_configs.get(ph["key"]) if isinstance(flow_configs.get(ph["key"]), dict) else {}
        item = {"step": ph["key"], "label": str((cfg or {}).get("label") or ph["label"])}
        desc = str((cfg or {}).get("description") or "").strip()
        if desc:
            item["description"] = desc
        steps.append(item)
    return steps


def _graph_maps(flow: dict) -> tuple[dict[str, dict], dict[str, list[dict]], dict[str, int], dict[str, int]]:
    """画布 graph JSON → (nodes, adj, indeg, order)；extract 节点不进执行序。"""
    graph = flow.get("graph") or {}
    nodes: dict[str, dict] = {}
    order: dict[str, int] = {}
    for index, node in enumerate(graph.get("nodes") or []):
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        runtime = node.get("runtime") or node.get("type")
        if not nid or runtime == "extract":
            continue
        nodes[str(nid)] = node
        order[str(nid)] = index
    adj: dict[str, list[dict]] = {nid: [] for nid in nodes}
    indeg: dict[str, int] = {nid: 0 for nid in nodes}
    for edge in graph.get("edges") or []:
        if not isinstance(edge, dict):
            continue
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source in nodes and target in nodes:
            adj[source].append(edge)
            indeg[target] = indeg.get(target, 0) + 1
    return nodes, adj, indeg, order


async def _emit(broadcast: BroadcastFn, payload: dict) -> None:
    if broadcast is None:
        return
    try:
        await broadcast(payload)
    except Exception:
        logger.exception("skill engine broadcast failed type=%s", payload.get("type"))


def _node_cfg(ctx: dict, key: str) -> dict:
    cfg = (ctx.get("flow_configs") or {}).get(key)
    return dict(cfg) if isinstance(cfg, dict) else {}


def _trace(key: str, label: str, status: str, **extra) -> dict:
    payload = {"type": "node_trace", "step": key, "label": label, "status": status,
               "input": extra.get("input"), "output": extra.get("output"),
               "summary": extra.get("summary") or "", "artifact": extra.get("artifact")}
    if extra.get("duration_ms") is not None:
        payload["duration_ms"] = extra["duration_ms"]
    return payload


def engine_result_of(ctx: dict) -> dict:
    """引擎终态协议：done（含产物）或 gaps（结构化缺口数据，无话术）。"""
    gaps = list(ctx.get("engine_gaps") or [])
    if gaps:
        return {"status": "gaps", "gaps": gaps, "assumptions": list(ctx.get("assumptions") or [])}
    return {"status": "done",
            "artifact": (ctx.get("business_entity") or {}).get("entity"),
            "payload": ctx.get("output_payload") or {},
            "assumptions": list(ctx.get("assumptions") or [])}


async def run_skill_plan_core(ctx: dict, flow_configs: dict, broadcast: BroadcastFn, title: str = "") -> dict:
    """引擎唯一入口。ctx 契约：requirement_text/ext（对话路径由角色预填并置 slots_provided=True）/
    history/force_complete/llm_model/business_mode/output_kind/flow_configs。
    返回 ctx：engine_result=done|gaps；awaiting_input=True 表示有缺口待角色补齐。
    title：任务名（前端任务胶囊展示），缺省「配置任务」。
    """
    from app.services.portal_flow_adapter import requirement_slots_from_ext
    from app.services.skill_phases import (
        kp_args_from_ext,
        kp_gate_gap,
        phase_kp_reason,
        phase_model_reason,
        phase_normalize_slots,
    )

    ctx["flow_configs"] = flow_configs
    steps_meta = skill_steps_view(flow_configs)
    labels = {s["step"]: s["label"] for s in steps_meta}
    await _emit(broadcast, {"type": "pipeline_start", "title": str(title or "配置任务"), "steps": steps_meta})

    timings = ctx.setdefault("timings", {})
    t0 = time.perf_counter()

    def _fail(step: str, message: str) -> dict:
        ctx["fatal_error"] = message[:200]
        _emit_sync(broadcast, _trace(step, labels.get(step, step), "failed", summary=str(message)[:120]))
        _emit_sync(broadcast, {"type": "error", "message": ctx["fatal_error"]})
        return ctx

    def _pause_with_gap(gap: dict) -> dict:
        ctx["engine_gaps"] = [gap]
        ctx["awaiting_input"] = True
        timings["elapsed_ms"] = round((time.perf_counter() - t0) * 1000)
        _emit_sync(broadcast, {"type": "pipeline_paused", "gaps": [gap]})
        return ctx

    def _emit_sync(broadcast_, payload):
        # 同步包装：失败/暂停路径里也要发事件（异常仅记日志）。
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_emit(broadcast_, payload))
        except RuntimeError:
            pass

    # ── input ──
    text = str(ctx.get("requirement_text") or "").strip()
    await _emit(broadcast, _trace("input", labels["input"], "running"))
    if not text:
        return _fail("input", "缺少需求文本")
    await _emit(broadcast, _trace("input", labels["input"], "done", input=text, output=text,
                                  summary="已接收需求原文", duration_ms=0))

    # ── normalize（槽位规范化；试运行路径在此做 LLM 抽取）──
    key = "agent_fill"
    await _emit(broadcast, _trace(key, labels[key], "running"))
    try:
        started = time.perf_counter()
        await phase_normalize_slots(ctx, _node_cfg(ctx, key), broadcast)
        slots = requirement_slots_from_ext(dict(ctx.get("ext") or {}))
        await _emit(broadcast, _trace(
            key, labels[key], "done",
            output={"missing_critical": list(ctx.get("blockers") or [])},
            summary="线索登记表已更新",
            artifact={"kind": "requirement_slots", "title": "线索登记表", "data": {**slots, "requirement_text": text}},
            duration_ms=round((time.perf_counter() - started) * 1000)))
    except Exception as exc:
        logger.exception("normalize 阶段失败")
        return _fail(key, f"需求理解阶段失败：{exc}")

    # ── model（机型选型）──
    key = "model_reason"
    await _emit(broadcast, _trace(key, labels[key], "running"))
    try:
        started = time.perf_counter()
        gap = await phase_model_reason(ctx, _node_cfg(ctx, key), broadcast)
        chosen = str(((ctx.get("_locked_baseline") or {}).get("name")) or "")
        pool = [compact_candidate(b) for b in (ctx.get("baselines_pool") or [])][:10]
        from app.repository.bom_case_repo import _l6_rows_from_base_config
        base_id = ((ctx.get("_locked_baseline") or {}).get("id"))
        l6_rows = _l6_rows_from_base_config(base_id) if base_id else []
        await _emit(broadcast, _trace(
            key, labels[key], "done",
            output={"chosen": chosen, "reason": ctx.get("lock_reason") or ""},
            summary=(f"锁定机型 {chosen}" if chosen else "未锁定机型"),
            artifact={"kind": "l6_chassis", "title": "机箱表",
                      "data": {"rows": l6_rows, "chosen": chosen, "reason": ctx.get("lock_reason") or "",
                               "candidates": pool}},
            duration_ms=round((time.perf_counter() - started) * 1000)))
    except Exception as exc:
        logger.exception("model 阶段失败")
        return _fail(key, f"机型选型阶段失败：{exc}")
    if gap is not None:
        return _pause_with_gap(gap)

    # ── kp gate（配件意向缺口，业务选项数据）──
    key = "kp_reason"
    if not bool(ctx.get("force_complete")):
        gate_gap = kp_gate_gap(ctx)
        if gate_gap is not None:
            return _pause_with_gap(gate_gap)
    else:
        if not (ctx.get("kp_parts") or (ctx.get("ext") or {}).get("kp_mode")) and \
                not kp_args_from_ext(dict(ctx.get("ext") or {})):
            ctx.setdefault("assumptions", []).append({
                "code": "kp_skipped", "slot": "kp_mode",
                "reason": "需求未指定配件：仅按整机底座出方案，可在配置页添加配件"})

    # ── kp（确定性落地）──
    started = time.perf_counter()
    await _emit(broadcast, _trace(key, labels[key], "running"))
    await phase_kp_reason(ctx, _node_cfg(ctx, key), broadcast)
    summary_map = dict(ctx.get("kp_summary") or {})
    unmatched_rows = [{"category": p.get("category"), "reason": p.get("unmatched_reason")}
                      for p in (ctx.get("kp_parts") or []) if p.get("unmatched")]
    await _emit(broadcast, _trace(
        key, labels[key], "done", output=dict(summary_map),
        summary=f"落地配件 {summary_map.get('kp_count', 0)} 项"
                + (f"（未命中 {summary_map.get('unmatched_count')}）" if summary_map.get("unmatched_count") else ""),
        artifact={"kind": "kp_table", "title": "KP表",
                  "data": {"rows": [
                      {"category": p.get("category"), "name": p.get("name") or p.get("pn") or "",
                       "description": p.get("matched_spec") or "", "qty": p.get("qty") or 1,
                       "unit_price": p.get("unit_price") or 0, "unmatched": bool(p.get("unmatched")),
                       "unmatched_reason": p.get("unmatched_reason") or "",
                       "spec_mismatch": bool(p.get("spec_mismatch"))}
                      for p in (ctx.get("kp_parts") or [])
                  ], "summary": summary_map, "unmatched": unmatched_rows}},
        duration_ms=round((time.perf_counter() - started) * 1000)))

    # ── compose ──
    key = "compose"
    await _emit(broadcast, _trace(key, labels[key], "running"))
    started = time.perf_counter()
    await compose_plans(ctx, _node_cfg(ctx, key), broadcast)
    plans = ctx.get("plans") or []
    await _emit(broadcast, _trace(
        key, labels[key], "done", output={"plans_count": len(plans)},
        summary=f"组装 {len(plans)} 个整机配置" if plans else "无可组装的整机基准",
        artifact={"kind": "compose", "title": "BOM 组装结果",
                  "data": [{"model": (p.get("model") or ""), "total_cost": ((p.get("summary") or {}).get("total_cost"))} for p in plans]},
        duration_ms=round((time.perf_counter() - started) * 1000)))

    # ── output ──
    key = "output"
    await _emit(broadcast, _trace(key, labels[key], "running"))
    started = time.perf_counter()
    out_payload = await finalize_output(ctx, _node_cfg(ctx, key), broadcast)
    bom_entity = (ctx.get("business_entity") or {}).get("entity")
    await _emit(broadcast, _trace(
        key, labels[key], "done", output=out_payload if isinstance(out_payload, dict) else {},
        summary="已生成交接产物" if bom_entity is not None else "会话模式产出预览",
        artifact=None, duration_ms=round((time.perf_counter() - started) * 1000)))
    timings["plan_total_ms"] = round((time.perf_counter() - t0) * 1000)
    ctx["awaiting_input"] = False
    return ctx


def compact_candidate(candidate: dict) -> dict:
    return {
        "id": str(candidate.get("server_model_id") or candidate.get("id") or ""),
        "name": str(candidate.get("name") or ""),
        "type": str(candidate.get("server_type_name") or ""),
        "series": str(candidate.get("series") or ""),
        "form": str(candidate.get("form") or ""),
        "price": candidate.get("total_price"),
    }


# scene_gap/kp_mode_gap 从 skill_phases 引用（re-export 供旧调用兼容）
from app.services.skill_phases import kp_mode_gap, scene_gap  # noqa: E402,F401
