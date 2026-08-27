# -*- coding: utf-8 -*-
"""需求分析 Skill 的确定性计划运行时（skill plan runtime）。

本模块是主 AI 角色的“计划约束层”，不是另一个 LLM Agent：
- 把画布节点图转成系统提示词里的固定计划；
- 把节点配置的 enabled_tools 转成主 Agent 可用工具清单；
- 在主 Agent 的工具调用边界保存产物、广播进度、回放真实数据；
- 完成后确定性地组装 BOM 并落库。

铁律：本模块不得 import llm_client / agent_react，不发起任何 LLM 调用。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, Optional

from app.services.capability_executor import _graph_maps
from app.services.skill_node_runtime import compose_plans, finalize_output

logger = logging.getLogger(__name__)

BroadcastFn = Callable[[dict], Any]


def _ordered_nodes(flow: dict) -> list[dict]:
    nodes, _adj, _indeg, order = _graph_maps(flow)
    return [
        node for node in sorted(nodes.values(), key=lambda n: order.get(n.get("id"), 9999))
        if (node.get("runtime") or node.get("type")) not in ("condition", "extract")
    ]


def _node_key(node: dict) -> str:
    return str(node.get("id") or node.get("runtime") or node.get("type") or "")


def _node_label(node: dict, key: str) -> str:
    return str(node.get("label") or key or "节点")


def _node_config(flow: dict, key: str) -> dict:
    return dict((flow.get("node_configs") or {}).get(key) or {})


def build_skill_plan_prompt(flow: dict) -> str:
    """把画布节点图转成给主 AI 角色的固定计划说明，不产生独立节点提示词。"""
    lines = ["你现在按以下固定计划完成需求分析，节点图只是这个计划的可视化，不要另起一套流程。"]
    for idx, node in enumerate(_ordered_nodes(flow), 1):
        key = _node_key(node)
        cfg = _node_config(flow, key)
        goal = str(cfg.get("goal") or cfg.get("description") or "").strip()
        tools = [str(t) for t in (cfg.get("enabled_tools") or []) if str(t)]
        artifact = str(cfg.get("output_artifact") or "").strip()
        tool_text = "、".join(tools) if tools else "无工具"
        line = f"{idx}. {_node_label(node, key)}：{goal or '执行该阶段'}"
        if tool_text != "无工具":
            line += f"；可调用工具：{tool_text}"
        if artifact:
            line += f"；产出：{artifact}"
        lines.append(line)
    output_cfg = _node_config(flow, "output")
    final_contract = str(output_cfg.get("final_contract") or "").strip()
    if final_contract:
        lines.append("\n最终回复约束：\n" + final_contract)
    return "\n".join(lines)


def skill_allowed_tools(flow: dict) -> list[str]:
    """汇总节点配置声明的工具；顺序按节点顺序去重。"""
    seen: list[str] = []
    for node in _ordered_nodes(flow):
        cfg = _node_config(flow, _node_key(node))
        for tool in (cfg.get("enabled_tools") or []):
            tool = str(tool).strip()
            if tool and tool not in seen:
                seen.append(tool)
    return seen


def tool_phase_map(flow: dict) -> dict[str, str]:
    """工具 -> 节点阶段映射，完全来自节点配置，不硬编码工具名。"""
    mapping: dict[str, str] = {}
    for node in _ordered_nodes(flow):
        key = _node_key(node)
        cfg = _node_config(flow, key)
        for tool in (cfg.get("enabled_tools") or []):
            tool = str(tool).strip()
            if tool and tool not in mapping:
                mapping[tool] = key
    return mapping


def _extract_last_json(text: str) -> dict:
    """从模型最终文本中提取最后一个 JSON 对象；失败返回空 dict。"""
    if not text:
        return {}
    start = max(int(text.rfind("{")), int(text.rfind("[")))
    if start < 0:
        return {}
    # 从最后一个起始符开始向后找匹配终点，避免嵌套对象/数组漏掉。
    stack: list[str] = []
    openers = {"{": "}", "[": "]"}
    closers = {")": "(", "}": "{", "]": "["}
    close_for = {"{": "}", "[": "]"}
    for i in range(start, len(text)):
        ch = text[i]
        if ch in openers:
            stack.append(ch)
        elif ch in closers:
            if not stack:
                continue
            if close_for.get(stack[-1]) == ch:
                stack.pop()
                if not stack:
                    snippet = text[start:i + 1]
                    try:
                        obj = json.loads(snippet)
                    except Exception:
                        obj = {}
                    return obj if isinstance(obj, dict) else {}
            else:
                # 括号不匹配，退回空结果。
                return {}
    return {}


def _match_baseline_name(answer: str, baselines: list[dict]) -> Optional[dict]:
    text = str(answer or "").lower()
    for baseline in baselines:
        name = str(baseline.get("name") or "").strip()
        mid = str(baseline.get("id") or baseline.get("server_model_id") or "").strip()
        if name and name.lower() in text:
            return baseline
        if mid and mid.lower() in text:
            return baseline
    return None


def parse_skill_decision(answer: str, baselines: list[dict]) -> dict:
    """从主 AI 回复中解析完成/待澄清与机型选择，只做确定性回读。"""
    decision = _extract_last_json(answer or "")
    selected_name = str(decision.get("selected_model_name") or decision.get("model_name") or "").strip()
    question = str(decision.get("question") or decision.get("need_input") or "").strip()
    done = bool(decision.get("done", not question))
    locked = None
    if selected_name:
        low = selected_name.lower()
        for baseline in baselines:
            name = str(baseline.get("name") or "").strip()
            mid = str(baseline.get("id") or baseline.get("server_model_id") or "").strip()
            if (name and name.lower() == low) or (mid and mid.lower() == low):
                locked = baseline
                break
        if locked is None:
            for baseline in baselines:
                name = str(baseline.get("name") or "").strip()
                if name and name.lower() in low:
                    locked = baseline
                    break
    if locked is None:
        locked = _match_baseline_name(answer or "", baselines)
    if locked is None and baselines:
        locked = baselines[0]
    return {
        "done": done,
        "question": question,
        "locked": locked,
        "raw": decision,
    }


def apply_skill_decision(ctx: dict, answer: str) -> dict:
    """把主 AI 最终回复写入 ctx，并锁定机型。"""
    baselines = list(ctx.get("baselines") or [])
    decision = parse_skill_decision(answer, baselines)
    ctx["skill_final"] = decision
    if decision["locked"]:
        ctx["baselines"] = [decision["locked"]]
        ctx["model_selection"] = {
            "id": decision["locked"].get("id"),
            "name": decision["locked"].get("name") or "",
            "server_type_name": decision["locked"].get("server_type_name") or "",
            "series": decision["locked"].get("series") or "",
            "form": decision["locked"].get("form") or "",
        }
        ext = dict(ctx.get("ext") or {})
        for field in ("server_type_name", "server_type", "series", "form"):
            value = decision["locked"].get(field)
            if value:
                ext[field] = value
        ctx["ext"] = ext
        req = dict(ctx.get("requirement") or {})
        for field in ("server_type_name", "series", "form"):
            value = decision["locked"].get(field)
            if value:
                req[field] = value
        ctx["requirement"] = req
    question = str(decision["question"] or "").strip()
    if question and not decision["done"]:
        ctx["awaiting_input"] = True
        ctx["current_target"] = "agent_fill"
        ctx["last_ask_question"] = question
    return decision


def make_skill_tool_guard(
    flow: dict,
    ctx_holder: dict,
    broadcast: BroadcastFn,
    thread_id: str,
) -> Callable[[str, dict, Any], Any]:
    """构造工具调用后置守卫：只广播节点进度、保存真实产物，不发起 LLM。"""
    phase_map = tool_phase_map(flow)
    seen: set = set()

    async def _broadcast_step(phase: str, node: dict, payload: dict) -> None:
        if broadcast is None:
            return
        label = _node_label(node, phase)
        try:
            await broadcast({
                "type": "step_done",
                "step": phase,
                "label": label,
                "payload": payload,
                "duration_ms": 0,
                "input": {},
                "output": {},
                "artifact": payload.get("artifact") or {},
                "summary": payload.get("summary") or "",
            })
        except Exception:
            logger.exception("skill plan broadcast failed phase=%s", phase)

    async def guard(name: str, args: dict, result: Any) -> Any:
        ctx = ctx_holder.get("ctx") or {}
        phase = phase_map.get(name)
        if not phase:
            return result
        node = next((n for n in _ordered_nodes(flow) if _node_key(n) == phase), {})
        payload: dict = {}
        try:
            if name == "select_models":
                from app.api.candidate_search import select_models
                baselines = select_models(
                    usage=(args or {}).get("usage") or "",
                    server_type_name=(args or {}).get("server_type_name"),
                    series=(args or {}).get("series"),
                    form=(args or {}).get("form"),
                    limit=(args or {}).get("limit") or None,
                    fallback_order=(args or {}).get("fallback_order") or ["exact", "same_series", "same_form", "all"],
                )
                ctx["baselines"] = list(baselines or [])
                payload = {"count": len(ctx["baselines"]), "matches": [
                    {"name": b.get("name") or "", "server_type_name": b.get("server_type_name") or "",
                     "series": b.get("series") or "", "form": b.get("form") or ""}
                    for b in ctx["baselines"]
                ]}
                seen.add(phase)
            elif name == "select_parts":
                from app.services.part_selector import select_parts
                parts = select_parts(
                    categories=(args or {}).get("categories"),
                    server_type_name=(args or {}).get("server_type_name"),
                    cpu_signal=(args or {}).get("cpu_signal"),
                    mem_signal=(args or {}).get("mem_signal"),
                    drive_groups=(args or {}).get("drive_groups"),
                    gpu_groups=(args or {}).get("gpu_groups"),
                    raid_groups=(args or {}).get("raid_groups"),
                    psu_signal=(args or {}).get("psu_signal"),
                    multi_spec_filters=(args or {}).get("multi_spec_filters"),
                )
                ctx["kp_parts"] = list(parts or [])
                baseline = (ctx.get("baselines") or [{}])[0] if ctx.get("baselines") else {}
                mid = baseline.get("server_model_id") or baseline.get("id")
                if mid is not None:
                    ctx["kp_by_model"] = {str(mid): list(parts or [])}
                by_category: dict[str, int] = {}
                for part in (parts or []):
                    cat = str(part.get("category") or "其他")
                    by_category[cat] = by_category.get(cat, 0) + 1
                payload = {
                    "kp_count": len(parts or []),
                    "by_category": by_category,
                    "unmatched_count": sum(1 for p in (parts or []) if p.get("unmatched")),
                    "spec_mismatch_count": sum(1 for p in (parts or []) if p.get("spec_mismatch")),
                }
                seen.add(phase)
            elif name in ("list_server_types", "list_server_models", "get_server_model", "list_kp_categories"):
                payload = {"called": True}
                seen.add(phase)
            elif name in ("resolve_part_alias", "compose_memory"):
                payload = {"called": True}
                seen.add(phase)
        except Exception as exc:
            logger.exception("skill tool guard failed tool=%s phase=%s", name, phase)
            payload = {"error": str(exc)}
        ctx_holder["ctx"] = ctx
        await _broadcast_step(phase, node, payload)
        return result

    return guard


async def finalize_skill_artifacts(ctx: dict, flow: dict, broadcast: BroadcastFn) -> dict:
    """确定性执行 compose/output：只组装真实 BOM 并落库，不调用 LLM。"""
    compose_cfg = _node_config(flow, "compose")
    output_cfg = _node_config(flow, "output")
    await compose_plans(ctx, compose_cfg, broadcast)
    payload = await finalize_output(ctx, output_cfg, broadcast)
    return payload
