# -*- coding: utf-8 -*-
"""Fixed capability workflow executor.

Conversation layer decides *whether* to invoke a capability; this module
decides *how* the capability graph is executed. It runs the graph in a
deterministic order and reuses reasoning_executor._dispatch for every node,
so existing node handlers are not reimplemented.

Only one graph-level behavior is special-cased:
- `agent_fill` 智能对话填表 Agent：信息不足时中断等待用户回答，否则沿主链继续。
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from app.services import llm_client
from app.services.reasoning_executor import _dispatch, _eval_condition

logger = logging.getLogger(__name__)


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




def _intent_context(ctx: dict) -> str:
    """把当前状态拼成意图判定的上下文（只含真实状态，不写死业务词）。"""
    parts: list[str] = []
    target = str(ctx.get("current_target") or "").strip() or "需求分析"
    parts.append("当前所在环节：" + target)
    last_ask = str(ctx.get("last_ask_question") or "").strip()
    if last_ask:
        parts.append("AI 上一条问的是：" + last_ask)
    req = str(ctx.get("requirement_text") or "").strip()
    if req:
        parts.append("客户已表达需求：" + req[:200])
    baselines = ctx.get("baselines") or []
    if isinstance(baselines, list) and baselines:
        names = [str((b or {}).get("name") or "") for b in baselines[:8] if isinstance(b, dict)]
        if names:
            parts.append("当前候选机型：" + "、".join(n for n in names if n))
    return "\n".join(parts)


async def _route_resume_intent(ctx: dict, broadcast: Callable[..., Any], node_id: str) -> bool:
    """多轮回复时，先用 LLM 判“这句到底在干嘛”；
    对于确定节点会答错的意图（看目录/听不懂/闲聊/普通提问）直接给自然回复并停在原地，
    其余意图放行回确定性节点（取消/自配/重选/确认/补需求仍由节点处理）。"""
    answer = str(ctx.get("last_user_answer") or "").strip()
    if not answer:
        return False
    try:
        from app.services.workflow_intent import resolve_intent
        intent_data = await resolve_intent(answer, _intent_context(ctx))
    except Exception:
        return False
    intent = str(intent_data.get("intent") or "").strip().lower()
    if intent not in ("list_catalog", "explain", "noise", "ask"):
        return False

    if intent == "list_catalog":
        try:
            from app.services.workflow_intent import catalog_digest
            lines = await catalog_digest()
        except Exception:
            lines = "（暂时读不到目录，请稍后再试）"
        reply = "当前在售服务器目录如下，你可以补充具体需求（场景/类型/系列/形态/预算）：\n" + str(lines)
    else:
        reply = ""
        try:
            from app.services.workflow_intent import reply_with_context
            _ctx_lines = _intent_context(ctx)
            try:
                from app.services.workflow_intent import catalog_digest
                _ctx_lines += "\n\n【在售目录】\n" + (await catalog_digest())
            except Exception:
                pass
            reply = await reply_with_context(answer, _ctx_lines)
        except Exception:
            reply = ""
        if not reply:
            reply = "收到。你可以继续补充需求，或告诉我去详情页自己配置。"

    ctx["awaiting_input"] = True
    ctx["current_target"] = node_id
    ctx["last_ask_question"] = reply
    if broadcast:
        try:
            await broadcast({"type": "need_confirm", "step": node_id, "question": reply,
                             "options": [], "why": "根据用户提问直接回应"})
        except Exception:
            pass
    return True


async def run_fixed_workflow(
    thread_id: str,
    requirement_text: str,
    flow: dict,
    broadcast: Callable[..., Any],
    initial_ctx: Optional[dict] = None,
    ctx_ref: Optional[dict] = None,
) -> dict[str, Any]:
    """Run one capability graph without LLM deciding the next node."""
    node_configs = flow.get("node_configs") or {}
    nodes, adj, indeg, order = _graph_maps(flow)

    ctx: dict[str, Any] = {
        "requirement_text": requirement_text,
        "opportunity_id": thread_id,
        "flow_configs": node_configs,
        "llm_enabled": llm_client.is_llm_enabled(),
    }
    if initial_ctx:
        ctx.update(initial_ctx)
    if ctx_ref is not None:
        ctx_ref["ctx"] = ctx

    steps = [
        {"key": node_id, "label": (node.get("label") or node_id)}
        for node_id, node in sorted(nodes.items(), key=lambda item: order.get(item[0], 9999))
        if (node.get("runtime") or node.get("type")) not in ("condition", "extract")
    ]
    await broadcast({"type": "pipeline_start", "steps": steps})

    resume_from = str(ctx.get("current_target") or "").strip()
    if resume_from and resume_from in nodes and await _route_resume_intent(ctx, broadcast, resume_from):
        return ctx
    queue: list[str] = sorted([nid for nid, degree in indeg.items() if degree == 0])
    if resume_from and resume_from in nodes:
        # 多轮能力会话：用户回答后从暂停节点继续，避免重跑 input/agent_fill 后把
        # “选型号/换配件/取消”等用户回答误当成原始需求补问。
        queue = [resume_from]
    if not queue and nodes:
        queue = [min(nodes.keys(), key=lambda n: order.get(n, 9999))]
    visited: set[str] = set()

    def enqueue(targets: list[str]) -> None:
        for target in targets:
            if target in nodes and target not in visited and target not in queue:
                queue.append(target)

    while queue:
        node_id = queue.pop(0)
        if node_id in visited:
            continue
        visited.add(node_id)
        node = nodes[node_id]
        node_type = node.get("runtime") or node.get("type") or node_id
        config = node_configs.get(node_id) or {}

        if node_type == "extract":
            continue
        if node_type == "condition":
            branch = _eval_condition(config.get("expr", ""), ctx)
            handle = "true" if branch else "false"
            edges = [edge for edge in adj.get(node_id) or [] if (edge.get("source_handle") or "true") == handle]
            if not edges:
                edges = adj.get(node_id) or []
            enqueue([str(edge.get("target") or "") for edge in edges])
            continue

        label = node.get("label") or node_id
        input_preview, _, _, _ = _trace_preview(node_type, ctx)
        await broadcast({"type": "step_start", "step": node_id, "label": label, "input": input_preview})
        try:
            payload = await _dispatch(node_type, ctx, config, broadcast)
        except Exception as exc:
            logger.exception("capability node failed node=%s type=%s", node_id, node_type)
            payload = {"error": str(exc)}
        _, output_preview, artifact, summary = _trace_preview(node_type, ctx, payload)
        await broadcast({"type": "step_done", "step": node_id, "payload": payload,
                         "input": input_preview, "output": output_preview, "artifact": artifact, "summary": summary})

        if payload.get("error") or ctx.get("agent_fill_error"):
            ctx["fatal_error"] = str(payload.get("error") or ctx.get("agent_fill_error"))
            return ctx
        if ctx.get("awaiting_input"):
            return ctx
        if ctx.get("flow_exit") in ("self_config", "cancelled"):
            return ctx
        enqueue([str(edge.get("target") or "") for edge in adj.get(node_id) or []])

    return ctx
