# -*- coding: utf-8 -*-
"""步进管线：节点自动 begin、完成产物打包、步骤轨迹广播。

2026-09-10 自 skill_chat.py 拆出（纯搬运，零行为变更）。
2026-09-12 node_mission 退役：指令唯一出处=左栏 manual_rules，节点层不再有第二套。
"""
from __future__ import annotations

import logging
from app.services.skill_node_artifacts import node_payload as _node_payload
from app.services.skill_node_state import FrozenDocView, fill_node, unwrap_doc
from app.services.skill_tool_context import TOOL_CTX
from typing import Optional


logger = logging.getLogger(__name__)


async def _engine_begin_step(args: dict) -> dict:
    ctx = TOOL_CTX.get()
    engine = ctx.get("engine") or {}
    key = str((args or {}).get("step") or "").strip()
    if key not in (engine.get("flow_configs") or {}):
        return {"ok": False, "error": "unknown_step", "hint": f"步骤 {key} 不在本任务说明书中"}
    from app.services.skill_plan_runtime import prepare_step
    res = await prepare_step(engine, key, ctx.get("event_sink"))
    if res.get("ok"):
        engine["current_step"] = key
        # 上游冻结文档（线索登记表）对非属主节点只读：给的是 FrozenDocView，
        # 任何写入当场报错——「下游永不回填上游」落在类型上，不是靠约定。
        raw = unwrap_doc(engine.get("ext"))
        if key != fill_node() and isinstance(raw, dict):
            engine["_ext_raw"] = raw
            engine["ext"] = FrozenDocView(raw, key)
        else:
            engine.pop("_ext_raw", None)
            engine["ext"] = raw
        ctx["ext"] = engine["ext"]
        # 该步干活所需上下文由节点插件桥接进 TOOL_CTX（工具从那里读）；编排壳不认识节点名。
        from app.services.skill_node_plugins import plugin_for
        plugin_for(key).bridge_ctx(engine, ctx)
    return res



def manual_rules_block(manual_rules: str) -> str:
    """任务规则注入块：左栏「使用说明」（graph.manual_rules）是唯一出处，
    各处大脑回合共用同一份注入格式，代码不另写第二套。空串返回空串。"""
    txt = str(manual_rules or "").strip()
    return "任务规则（配置者编写，全程遵守）：\n" + txt if txt else ""


def _node_done_payload(engine: dict, key: str, label: str, summary: str,
                       vres: Optional[dict] = None) -> dict:
    """节点完成广播载荷：除 summary 外，带上该节点的真实产物（output/artifact）。

    产物由插头侧按 target.artifacts[].kind 分发（skill_node_artifacts 注册表）——
    本处不再按节点 key 分支：换目标表 = 改抽屉/注册 builder，主循环零改动。
    """
    return _node_payload(engine, key, label, summary, vres)


async def _emit_step_trace(ctx: dict, key: str, status: str, summary: str,
                            vres: Optional[dict] = None) -> None:
    sink = ctx.get("event_sink")
    if not sink:
        return
    engine = ctx.get("engine") or {}
    labels = {str(k): str((v or {}).get("label") or k)
              for k, v in ((engine.get("flow_configs") or {}).items()
                           if isinstance(engine.get("flow_configs"), dict) else [])}
    node_label = (engine.get("node_labels") or {}).get(key) or labels.get(key) or key
    try:
        if status == "done":
            payload = _node_done_payload(engine, key, node_label, summary, vres)
        else:
            payload = {"type": "node_trace", "step": key, "label": node_label, "status": status,
                       "input": None, "output": None, "summary": summary, "artifact": None}
        payload["thread_id"] = ctx.get("thread_id") or ""
        await sink(payload)
    except Exception:
        logger.exception("step trace emit failed")


async def _emit_brain_status(sink, text: str) -> None:
    """大脑回合过程状态（重试中/预算到点）：只走事件流给前端看板，kind=tool 不进旁白落库。"""
    if not sink:
        return
    try:
        await sink({"type": "step_progress", "step": "react",
                    "sub": {"kind": "tool", "text": text}})
    except Exception:
        pass
