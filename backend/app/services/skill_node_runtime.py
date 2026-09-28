# -*- coding: utf-8 -*-
"""需求分析 skill 的确定性节点运行时（skill node runtime）。

铁律：本模块是「节点只读层」，只做契约校验、产物组装、事件广播与落库；
绝不 import agent_react / llm_client，不发起任何 LLM 调用。唯一决策循环在
AI 角色主循环里完成，这里只承接决策结果并做确定性校验/落库。
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable

from app.services.plan_builder import build_plan

logger = logging.getLogger(__name__)


BroadcastFn = Callable[[dict], Awaitable[None]]


def build_plans(ctx: dict, config: dict) -> list:
    """compose 的确定性组装（同步版）：按真实 BOM 模板把已锁机型 + 配件组装成 plans。

    唯一组装口径：compose 步（异步 compose_plans）与「中途把进度写回方案配置草稿」
    （portal_flow_adapter.save_scheme_progress_from_ctx）共用本函数，不各写一套。
    """
    from app.services.capabilities import _compose_config, _get_nested
    cfg = _compose_config(config)
    baselines = ctx.get("baselines") or []
    kp_by_model = ctx.get("kp_by_model") or {}
    if not baselines:
        return []
    # 每个机型取自己的 KP（match_kp per-机型配的），fallback 到全局 kp_parts；来源策略由节点配置决定。
    plans = []
    _ext = ctx.get("ext") or {}
    # 电源：瓦数/数量一律取 AI 语义层（ext.psu.*）显式值，引擎不做功耗推断；
    # 是否启用和读取路径均由节点配置决定（psu_override_enabled / psu_*_source）。
    _sig_w = _get_nested(ctx, cfg.get("psu_wattage_source"), None) if cfg.get("psu_override_enabled", True) else None
    _sig_q = _get_nested(ctx, cfg.get("psu_qty_source"), None) if cfg.get("psu_override_enabled", True) else None
    for bl in baselines:
        mid = bl.get("server_model_id") or bl.get("id")
        bl_kp = (ctx.get("kp_parts") or []) if cfg.get("kp_source") == "global" else (kp_by_model.get(mid) or ctx.get("kp_parts") or [])
        _p = build_plan(bl, bl_kp, psu_wattage=_sig_w, psu_qty=_sig_q)
        plans.append(_p)
    return plans


async def compose_plans(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """compose 步的组装：无匹配基准时如实回缺（不落穿），否则按 build_plans 组装。"""
    plan_cfg = config if isinstance(config, dict) else {}
    if not (ctx.get("baselines") or []):
        ctx["plans"] = []
        return {"plans_count": 0, "warning": "无匹配的整机基准配置，请调整需求后重试"}
    plans = build_plans(ctx, plan_cfg)
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


async def _render_file_artifacts(config: dict, answer: str, payload_fields: dict | None = None) -> list:
    """输出节点 artifacts 插槽：把已定稿的文本结论渲染成文件产物（当前支持 PDF 报告）。

    两条渲染路线：
    - template_key：产出物模板（rules.artifact_template blocks + 图表资产）→ HTML →
      Playwright PDF；失败回退 legacy reportlab（模板渲染是增强不是闸门）。
    - legacy：reportlab 直渲 markdown（无模板时的既有链路，保留为兜底）。

    文件产物是增强不是闸门，单个产物失败只记日志跳过，绝不挡交付。answer 为空直接跳过
    （模板链路里 answer 是 text 块的内容源，空则模板只剩图表，无意义）。
    """
    files: list = []
    if not str(answer or "").strip():
        return files
    for art in (config.get("artifacts") or []):
        if not isinstance(art, dict):
            continue
        if str(art.get("kind") or "").strip() != "document":
            continue
        if str(art.get("format") or "pdf").strip() != "pdf":
            continue
        title = str(art.get("title") or "").strip() or "数据报告"
        template_key = str(art.get("template_key") or "").strip()
        rendered: bytes | None = None
        if template_key:
            rendered = await _render_by_template(template_key, title, answer, payload_fields or {})
        if rendered is None:
            try:
                from app.services.report_pdf import render_markdown_report_pdf, report_meta_now

                rendered = await asyncio.to_thread(
                    render_markdown_report_pdf, title, answer, meta=report_meta_now())
            except Exception:
                logger.exception("PDF 文件产物渲染失败（不挡交付）")
                continue
        try:
            from app.services.report_pdf import save_office_report
            from app.services.storage_adapter import build_object_id

            object_id = build_object_id(f"{title}.pdf")
            url = save_office_report(object_id, rendered)
            files.append({
                "url": url,
                "filename": f"{object_id}.pdf",
                "size": len(rendered),
                "mime": "application/pdf",
                "title": title,
            })
        except Exception:
            logger.exception("PDF 文件产物落盘失败（不挡交付）")
    return files


async def _render_by_template(template_key: str, title: str, answer: str, payload_fields: dict) -> bytes | None:
    """产出物模板渲染；任何失败返回 None 让调用方走 legacy reportlab。"""
    try:
        from app.repository.artifact_template_repo import ArtifactTemplateRepo
        from app.services.artifact_render import render_report_pdf

        repo = ArtifactTemplateRepo()
        try:
            tpl = repo.get_by_key(template_key)
        finally:
            repo.close()
        if not tpl:
            logger.warning("产出物模板不存在 key=%s，回退 legacy 渲染", template_key)
            return None
        meta = {
            "title": title or tpl.get("name") or tpl.get("key"),
            "generated_by": "AI 办公室 · 工作流输出节点",
        }
        render_payload = {**payload_fields, "answer": answer, "meta": {**(payload_fields.get("meta") or {}), **meta}}
        return await render_report_pdf(tpl.get("blocks") or [], render_payload, template_name=tpl.get("name") or "")
    except Exception:
        logger.exception("产出物模板渲染失败 key=%s（回退 legacy）", template_key)
        return None


async def finalize_output(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """output 的确定性交接契约：把上游 ctx 结果映射成下游业务实体/对话文本并返回回执。"""
    output_kind = str(config.get("output_kind") or ctx.get("output_kind") or "generic").strip() or "generic"
    # 交付去向由 output_kind 决定（唯一权威）。历史上这里读的是 config["target"] 字符串，
    # 与节点配置里的目标层插头（target.artifacts）同名不同义，已收口：target 只表示插头。
    target = _default_output_target(output_kind)
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
        # 文件产物（输出节点 artifacts 插槽）：确定性渲染 markdown→PDF，失败不挡交付
        payload["files"] = await _render_file_artifacts(config, answer, payload_fields=payload)
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
