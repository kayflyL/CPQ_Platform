# -*- coding: utf-8 -*-
"""共享能力执行辅助：图映射、节点 trace 预览、协作式停止信号。

需求分析 skill 的正式执行入口在 ai_plan_executor.run_ai_skill_plan；
本模块不再包含固定图执行器，只提供无决策的只读辅助函数。
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_WORKFLOW_STOP_EVENTS: dict[str, asyncio.Event] = {}


def request_workflow_stop(thread_id: str) -> None:
    """请求暂停当前工作流：协作式停止，节点边界处落 pending 再退出。"""
    _WORKFLOW_STOP_EVENTS.setdefault(thread_id, asyncio.Event()).set()


def _workflow_stop_event(thread_id: str) -> asyncio.Event:
    return _WORKFLOW_STOP_EVENTS.setdefault(thread_id, asyncio.Event())


def _clear_workflow_stop(thread_id: str) -> None:
    _WORKFLOW_STOP_EVENTS.pop(thread_id, None)


def _graph_maps(flow: dict) -> tuple[dict[str, dict], dict[str, list[dict]], dict[str, int], dict[str, int]]:
    graph = flow.get("graph") or {}
    raw_nodes = graph.get("nodes") or []
    raw_edges = graph.get("edges") or []

    nodes: dict[str, dict] = {}
    order: dict[str, int] = {}
    for index, node in enumerate(raw_nodes):
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
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source in nodes and target in nodes:
            adj[source].append(edge)
            indeg[target] = indeg.get(target, 0) + 1
    return nodes, adj, indeg, order





def _brief_list(value, limit: int = 5) -> list:
    if not isinstance(value, list):
        return []
    return value[:limit]


def _trace_preview(node_type: str, ctx: dict, payload: Optional[dict] = None):
    ext = ctx.get("ext") if isinstance(ctx.get("ext"), dict) else {}
    # 线索登记表只以「需求分析节点冻结的需求快照」为准；未冻结（如早期节点）兜底用 ext。
    lead_slots = ctx.get("requirement") if isinstance(ctx.get("requirement"), dict) else {}
    _req_snap = lead_slots or ext
    input_preview: dict[str, Any] = {}
    output_preview: dict[str, Any] = {}
    artifact: Optional[dict] = None
    summary = ""

    if node_type == "input":
        input_preview = {"requirement_text": str(ctx.get("requirement_text") or "")[:200]}
        output_preview = {
            "requirement_text": str(ctx.get("requirement_text") or "")[:200],
            "normalized_text": str(ctx.get("normalized_text") or "")[:200],
            "opportunity_id": ctx.get("opportunity_id"),
        }
        summary = "已注入需求原文与商机上下文"
    elif node_type == "agent_fill":
        input_preview = {"requirement_text": str(ctx.get("requirement_text") or "")[:200]}
        output_preview = {
            "slots": _req_snap,
            "purchase_qty": _req_snap.get("purchase_qty"),
            "missing_critical": (payload or {}).get("missing_critical") or ctx.get("missing_fields") or [],
            "issues": (payload or {}).get("issues") or [],
            "question": (payload or {}).get("question") or "",
        }
        artifact = {"kind": "requirement_slots", "title": "线索登记表", "data": _req_snap}
        summary = "智能对话填表 Agent：边答边填线索登记表"
    elif node_type == "model_reason":
        input_preview = {"slots": ext, "catalog": str(ctx.get("catalog") or "")[:120]}
        output_preview = {
            "matches": _brief_list((payload or {}).get("matches"), 5),
            "reason": str((payload or {}).get("reason") or "")[:200],
            "trace": _brief_list((payload or {}).get("trace"), 5),
            "count": (payload or {}).get("count"),
        }
        artifact = {"kind": "model_choice", "title": "机型决策", "data": output_preview}
        summary = "已从在售目录中选出机型"
    elif node_type == "kp_reason":
        input_preview = {"slots": ext, "baselines": _brief_list(ctx.get("baselines"), 5)}
        kp_by_model = ctx.get("kp_by_model") if isinstance(ctx.get("kp_by_model"), dict) else {}
        output_preview = {
            "kp_by_model": {k: len(v) if isinstance(v, list) else v for k, v in list(kp_by_model.items())[:8]},
            "kp_parts": _brief_list(ctx.get("kp_parts"), 8),
            "by_category": (payload or {}).get("by_category") or {},
            "proposal": ctx.get("kp_reason"),
        }
        artifact = {"kind": "parts_proposal", "title": "配件决策", "data": output_preview}
        summary = "已规划内存 / RAID / 网卡 / 电源等配件"
    elif node_type == "compose":
        kp_map = ctx.get("kp_by_model") if isinstance(ctx.get("kp_by_model"), dict) else {}
        plans = ctx.get("plans") or []
        input_preview = {"baselines": _brief_list(ctx.get("baselines"), 5), "kp_by_model_keys": list(kp_map.keys())[:8]}
        output_preview = {"plans_count": len(plans), "plan_names": [str(x.get("name") or x.get("model") or "") for x in _brief_list(plans, 5)]}
        artifact = {"kind": "plans", "title": "方案组装", "data": output_preview}
        summary = f"已组装 {len(plans)} 个候选方案"
    elif node_type == "output":
        input_preview = {"plans_count": len(ctx.get("plans") or []), "slots": ext, "opportunity_id": ctx.get("opportunity_id")}
        output_kind = str((payload or {}).get("output_kind") or ctx.get("output_kind") or "generic")
        output_preview = {
            "output_kind": output_kind,
            "target": (payload or {}).get("target") or ctx.get("output_target"),
            "plans_count": len(ctx.get("plans") or []),
        }
        if output_kind in ("bom_scheme_draft", "plans"):
            _node_payload = (payload or {}).get("payload") if isinstance((payload or {}).get("payload"), dict) else {}
            bom_draft = _node_payload.get("bom_scheme") or _node_payload.get("requirement") or {}
            if not isinstance(bom_draft, dict) or not bom_draft:
                _bus = ctx.get("business_entity")
                bom_draft = (_bus.get("entity") or {}) if isinstance(_bus, dict) else {}
            artifact = {"kind": "bom_scheme", "title": "BOM 方案", "data": bom_draft or {"plans_count": len(ctx.get("plans") or [])}}
            summary = "已生成 BOM 方案草稿"
        elif output_kind == "requirement_draft":
            artifact = {"kind": "requirement_slots", "title": "线索登记表", "data": _req_snap}
            summary = "已生成需求单草稿"
        else:
            artifact = {"kind": "handoff", "title": "交接回执", "data": {"target": output_preview.get("target")}}
            summary = "已生成交接回执"
    else:
        input_preview = {"requirement_text": str(ctx.get("requirement_text") or "")[:200]}
        output_preview = {"result": payload or {}}
        summary = "节点已执行完成"

    return input_preview, output_preview, artifact, summary
