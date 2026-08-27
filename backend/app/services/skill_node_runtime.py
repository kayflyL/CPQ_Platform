# -*- coding: utf-8 -*-
"""需求分析 skill 的确定性节点运行时（skill node runtime）。

铁律：本模块是「节点只读层」，只做契约校验、产物组装、事件广播与落库；
绝不 import agent_react / llm_client，不发起任何 LLM 调用。唯一决策循环在
AI 角色主循环里完成，这里只承接决策结果并做确定性校验/落库。
"""
import logging
from typing import Any, Awaitable, Callable

from app.api.candidate_search import build_plan
from app.services.slot_contract import canonical_get

logger = logging.getLogger(__name__)


BroadcastFn = Callable[[dict], Awaitable[None]]


def _agent_fill_options(ctx: dict, config: dict, missing: list) -> dict:
    """为 agent_fill 缺槽反问生成候选选项：目录字段取在售目录真实值，数量给常用档位。"""
    slot_options: dict = {}
    try:
        from app.services.slot_contract import slot_spec, slot_label
        from app.services.capabilities import _catalog_whitelist
        whitelist = _catalog_whitelist(config, ctx.get("ext") or {}, str(ctx.get("requirement_text") or ""))
    except Exception:
        slot_label = lambda k: str(k)
        whitelist = {}
    spec = {}
    try:
        from app.services.slot_contract import slot_spec as _spec
        spec = {item.get("key"): item for item in _spec()}
    except Exception:
        spec = {}
    bucket = {
        "server_type": "types",
        "platform_type": "series",
        "chassis_form": "forms",
        "server_model": "models",
    }
    for key in missing:
        source = str((spec.get(key) or {}).get("candidate_source") or "")
        if source == "catalog" and key in bucket:
            values = whitelist.get(bucket[key]) or []
            slot_options[key] = [{"label": str(v), "value": str(v), "slot": key, "group": slot_label(key)} for v in values if str(v).strip()]
        elif key == "purchase_qty":
            slot_options[key] = [{"label": str(n), "value": str(n), "slot": key, "group": slot_label(key)} for n in (1, 2, 3, 5, 10)]
    return slot_options


async def agent_fill_validate(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """agent_fill 的确定性契约校验：只读已抽好的需求槽位，做缺失反问 + 落表。

    不再起独立 LLM（理解/措辞已由外层 AI 角色 extract_requirement_slots 完成），
    保证不重复思考、不再套壳。
    """
    try:
        from app.services.slot_contract import _missing_critical, slot_label, slot_spec
        from app.services.slot_state import is_confirmed
        from app.services.capabilities import _has_recommend_signal
    except Exception:
        _missing_critical = lambda ext: []
        slot_label = lambda k: str(k)
        slot_spec = lambda: []
        is_confirmed = lambda ext, k: True
        _has_recommend_signal = lambda ext: True

    ext = dict(ctx.get("ext") or {})
    req_text = str(ctx.get("requirement_text") or "").strip()
    req_keys = {s.get("key") for s in slot_spec() if s.get("src_type") != "kp" and s.get("key") != "server_model"}
    prev_missing = list(ctx.get("missing_fields") or [])
    missing = [m for m in _missing_critical(ext) if m in req_keys and not is_confirmed(ext, m)]

    ctx["missing_fields"] = missing
    # 反问收敛：用户答了但缺口完全一致 → 停止机械重复，按 partial 交下游。
    _no_progress = bool(ctx.get("last_user_answer")) and bool(prev_missing) and sorted(missing) == sorted(prev_missing)
    ctx["converged"] = bool(_no_progress)
    need_ask = bool(missing) and not ctx.get("force_complete") and not ctx.get("delegated") and not _no_progress and not _has_recommend_signal(ext)

    # 缺关键槽：触发反问，把外层 AI 角色已生成的自然反问 question 透传；无则用字段名组成中性提示。
    if need_ask:
        question = str(ctx.get("agent_fill_ask") or "").strip()
        if not question:
            question = "还有几个关键信息待确认：" + "、".join([slot_label(m) for m in missing])
        slot_options = _agent_fill_options(ctx, config, missing)
        options = [o for items in slot_options.values() for o in items]
        import uuid
        rid = f"agent_{uuid.uuid4().hex[:12]}"
        ctx["awaiting_input"] = True
        ctx["current_target"] = "agent_fill"
        ctx["last_reply_id"] = rid
        ctx["last_ask_question"] = question
        _fz = ctx.get("feasibility") or {}
        _fz_lines = [("⚠️ " + w) for w in (_fz.get("warnings") or [])] + [("提示：" + h) for h in (_fz.get("hints") or [])]
        if _fz_lines:
            question = "\n".join(_fz_lines) + "\n" + question
        if broadcast:
            try:
                await broadcast({"type": "need_input", "reply_id": rid, "question": question,
                                 "options": options, "slot_options": slot_options, "why": "", "missing_fields": missing,
                                 "source": "agent_fill"})
            except Exception:
                pass
        return {"ok": True, "question": question, "options": options, "slot_options": slot_options, "source": "agent_fill",
                "sufficient": False, "missing_critical": missing}

    # 校验 + 落表：无关键缺口（或已委托/已收敛），固化需求快照并推进下游。
    ctx["awaiting_input"] = False
    _has_model = bool(canonical_get(ext, "server_model"))
    if ctx.get("delegated"):
        ctx["clarity"] = "delegated"
    elif ctx.get("converged"):
        ctx["clarity"] = "partial"
    elif _has_model:
        ctx["clarity"] = "explicit"
    elif missing:
        ctx["clarity"] = "partial"
    else:
        ctx["clarity"] = "explicit" if _has_model else "partial"

    # 固化需求快照（下游只读，不回填）。
    try:
        from app.services.capabilities import _freeze_requirement
        _freeze_requirement(ctx, ext, req_text)
    except Exception:
        pass

    if ctx.get("business_mode") == "opportunity_flow" and ctx.get("opportunity_id"):
        try:
            from app.services.portal_flow_adapter import persist_requirement_from_ctx
            persist_requirement_from_ctx(ctx, str(ctx.get("operator_name") or ""))
        except Exception:
            logger.exception("持久化真实需求草稿失败 opportunity=%s", ctx.get("opportunity_id"))

    return {"ok": True, "source": "agent_fill", "sufficient": bool(not missing),
            "missing_critical": missing, "done": not need_ask}


async def compose_plans(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """compose 的确定性组装：按真实 BOM 模板把已锁机型 + 配件组装成 plans。"""
    from app.services.capabilities import _compose_config, _get_nested
    cfg = _compose_config(config)
    baselines = ctx.get("baselines") or []
    kp_by_model = ctx.get("kp_by_model") or {}
    if not baselines:
        ctx["plans"] = []
        return {"plans_count": 0, "warning": "无匹配的整机基准配置，请调整需求后重试"}
    # 每个机型取自己的 KP（match_kp per-机型配的），fallback 到全局 kp_parts；来源策略由节点配置决定。
    plans = []
    _ext = ctx.get("ext") or {}
    # 电源：需求文本显式瓦数/数量 > build_plan 按负载推断；是否启用和读取路径均由节点配置决定。
    _sig_w = _get_nested(ctx, cfg.get("psu_wattage_source"), None) if cfg.get("psu_override_enabled", True) else None
    _sig_q = _get_nested(ctx, cfg.get("psu_qty_source"), None) if cfg.get("psu_override_enabled", True) else None
    for bl in baselines:
        mid = bl.get("server_model_id") or bl.get("id")
        bl_kp = (ctx.get("kp_parts") or []) if cfg.get("kp_source") == "global" else (kp_by_model.get(mid) or ctx.get("kp_parts") or [])
        # 需求文本功率/数量优先覆盖 build_plan 推断，并让覆盖值在 L6 模板求值前生效（模板行直接显示正确瓦数）。
        _p = build_plan(bl, bl_kp, psu_wattage=_sig_w, psu_qty=_sig_q)
        plans.append(_p)
    ctx["plans"] = plans
    return {"plans_count": len(plans)}


def _ctx_value(ctx: dict, path: str) -> Any:
    """按点分路径读取 ctx 值；路径不存在返回 None。"""
    cur: Any = ctx
    for part in str(path or "").split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _default_output_target(output_kind: str) -> str:
    if output_kind == "requirement_draft":
        return "requirement"
    if output_kind == "bom_scheme_draft":
        return "bom_scheme"
    if output_kind == "data_answer":
        return "conversation_reply"
    return "artifact"


def _apply_payload_map(payload_map: dict, ctx: dict) -> dict:
    payload: dict = {}
    for dest, source in (payload_map or {}).items():
        if not dest:
            continue
        if isinstance(source, str) and source.startswith("ctx."):
            payload[str(dest)] = _ctx_value(ctx, source[4:])
        elif isinstance(source, dict) and isinstance(source.get("source"), str):
            payload[str(dest)] = _ctx_value(ctx, source["source"].removeprefix("ctx."))
        else:
            payload[str(dest)] = source
    return payload


async def finalize_output(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """output 的确定性交接契约：把上游 ctx 结果映射成下游业务实体/对话文本并返回回执。"""
    output_kind = str(config.get("output_kind") or ctx.get("output_kind") or "generic").strip() or "generic"
    target = str(config.get("target") or _default_output_target(output_kind)).strip() or _default_output_target(output_kind)
    payload = _apply_payload_map(config.get("payload_map") or {}, ctx)

    entity = None
    entity_type = ""

    if output_kind == "requirement_draft":
        entity_type = "requirement"
        try:
            from app.services.portal_flow_adapter import persist_requirement_from_ctx
            entity = persist_requirement_from_ctx(ctx, str(ctx.get("operator_name") or ""))
        except Exception:
            logger.exception("输出节点持久化需求草稿失败 opportunity=%s", ctx.get("opportunity_id"))
        if entity:
            payload["requirement"] = entity
    elif output_kind == "bom_scheme_draft":
        entity_type = "bom_scheme"
        try:
            from app.services.portal_flow_adapter import persist_requirement_and_bom_from_ctx, build_preview_bom_scheme
            entity = persist_requirement_and_bom_from_ctx(ctx, str(ctx.get("operator_name") or ""), config)
            if not entity:
                # 会话/无商机模式不落库，但兜底输出可读 BOM 预览（含 configs），保证画布与聊天可点开。
                entity = build_preview_bom_scheme(ctx, config)
        except Exception:
            logger.exception("输出节点持久化需求单/BOM 方案草稿失败 opportunity=%s", ctx.get("opportunity_id"))
        if entity:
            payload["bom_scheme"] = entity
    elif output_kind == "data_answer":
        agent_result = ctx.get("agent_result") if isinstance(ctx.get("agent_result"), dict) else {}
        answer = str(agent_result.get("answer") or "").strip() or str(_ctx_value(ctx, "assembled.answer") or "").strip()
        payload.setdefault("answer", answer)
        payload.setdefault("data", ctx.get("assembled") if isinstance(ctx.get("assembled"), dict) else {})
    else:
        payload.setdefault("result", ctx.get("assembled") if isinstance(ctx.get("assembled"), dict) else {})
        payload.setdefault("template", config.get("template") or "")
        payload.setdefault("output_schema", config.get("output_schema") or {})

    actions = config.get("actions") or []
    handoff = {
        "output_kind": output_kind,
        "target": target,
        "payload": payload,
        "actions": list(actions),
    }
    ctx["output_kind"] = output_kind
    ctx["output_target"] = target
    ctx["output_payload"] = payload
    ctx["output_actions"] = handoff["actions"]
    ctx["handoff"] = handoff

    if entity_type and entity:
        # 只把真实业务实体挂到 ctx，由各通道终端统一补发 business_entity_ready 消息；
        # 避免在 executor 内提前广播一条无 message 的事件，造成前端重复收流。
        ctx["business_entity"] = {
            "entity_type": entity_type,
            "entity": entity,
            "opportunity_id": ctx.get("opportunity_id") or "",
            "target": target,
            "payload": payload,
            "actions": handoff["actions"],
        }
    else:
        await broadcast({
            "type": "handoff_ready",
            "output_kind": output_kind,
            "target": target,
            "payload": payload,
            "actions": handoff["actions"],
        })

    return {
        "output_kind": output_kind,
        "target": target,
        "payload": payload,
        "actions": handoff["actions"],
    }
