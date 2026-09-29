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


_CN_NUM = "一二三四五六七八九十"


def split_answer_sections(answer: str, sections: list[dict]) -> dict:
    """AI 整段 answer 按目标层章节契约头「一、{title}」确定性拆段 → {section_key: 文本}。

    契约头格式由 skill_target_contract.format_document_contract 规定；容忍 AI 偶发
    markdown # 前缀与标题行尾接「：要求」。首行「数据范围：…」落在第一个契约头之前，
    天然不进任何槽（PDF 封面口径由配置单源计算，不吃 AI 复述）。没匹配到契约头的
    章节=槽空，模板对应 text 块自动隐藏，不报错不挡交付。
    """
    import re as _re

    out: dict = {}
    if not answer or not isinstance(sections, list):
        return out
    marks: list[tuple[int, int, str]] = []
    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            continue
        title = str(sec.get("title") or "").strip()
        key = str(sec.get("key") or "").strip()
        if not title or not key:
            continue
        numeral = _CN_NUM[min(i, 9)]
        pat = _re.compile(rf"^[ \t>#*]*{numeral}[、.．:：]\s*{_re.escape(title)}", _re.M)
        m = pat.search(answer)
        if not m:
            continue
        # 内容起点=标题正后方（AI 常把正文首句写在标题行「：」之后，不能丢）；
        # 段首再剥掉残留的分隔符（：/。/空串）
        marks.append((m.start(), m.end(), key))
    marks.sort(key=lambda t: t[0])
    for j, (_start, cstart, key) in enumerate(marks):
        cend = marks[j + 1][0] if j + 1 < len(marks) else len(answer)
        text = str(answer[cstart:cend] or "").strip()
        text = _re.sub(r"^[\s:：.。;；]+", "", text).strip()
        if text:
            out[key] = text
    return out


async def _render_file_artifacts(ctx: dict, answer: str, payload_fields: dict | None = None) -> list:
    """文件产物渲染：内容（报告名/章节/数据范围）来自目标层文档卡，呈现（render：
    是否出文件/格式/模板）来自输出节点 config——均由 skill_turn_engine 组装进
    ctx["document_target"]。文件产物是增强不是闸门，失败只记日志跳过，绝不挡交付。

    两条内容路线：answer 文本（章节拆段进文本槽，legacy reportlab 兜底）与
    结构化 payload（无文档卡的流如需求分析：ext 字段表 + plans 明细表，
    默认排版按值形状自动组 blocks）。
    """
    files: list = []
    doc = ctx.get("document_target") if isinstance(ctx.get("document_target"), dict) else {}
    render = doc.get("render") if isinstance(doc.get("render"), dict) else {}
    fields = payload_fields or {}
    has_text = bool(str(answer or "").strip())
    has_struct = any(bool(v) and isinstance(v, (dict, list)) for v in fields.values())
    if not doc or not (has_text or has_struct) or render.get("enabled") is not True:
        return files
    if str(render.get("format") or "pdf").strip().lower() != "pdf":
        return files
    title = str(doc.get("name") or "").strip() or "数据报告"
    template_key = str(render.get("template_key") or "").strip()
    rendered: bytes | None = None
    if template_key:
        rendered = await _render_by_template(template_key, title, answer, fields, doc)
    if rendered is None and has_text:
        try:
            from app.services.report_pdf import render_markdown_report_pdf, report_meta_now

            rendered = await asyncio.to_thread(
                render_markdown_report_pdf, title, answer, meta=report_meta_now())
        except Exception:
            logger.exception("PDF 文件产物渲染失败（不挡交付）")
            return files
    if rendered is None and has_struct:
        rendered = await _render_structured_default(title, fields)
        if rendered is None:
            return files
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
            "template_key": template_key or "default_layout",
            "rendered_by": "output_node",
        })
    except Exception:
        logger.exception("PDF 文件产物落盘失败（不挡交付）")
    return files


async def _render_by_template(template_key: str, title: str, answer: str,
                              payload_fields: dict, doc: dict | None = None) -> bytes | None:
    """产出物模板渲染；任何失败返回 None 让调用方走 legacy reportlab。

    三桥（内容侧配置→渲染管线，全部来自目标层文档卡 doc）：
    - 章节→槽位：answer 按「一、{title}」拆段进 render_payload，模板 text 块
      source=payload key={章节key} 各取各段；
    - 数据范围→封面：period_label 由 _report_window 确定性计算（不吃 AI 复述）；
    - 数据范围→图表：range_days → asset_params，按资产 schema clamp，不认 days 的
      资产（kpi/profit）自动忽略。
    """
    try:
        from app.repository.artifact_template_repo import ArtifactTemplateRepo
        from app.services.artifact_render import render_report_pdf
        from app.services.skill_target_contract import _report_window, range_days

        repo = ArtifactTemplateRepo()
        try:
            tpl = repo.get_by_key(template_key)
        finally:
            repo.close()
        if not tpl:
            logger.warning("产出物模板不存在 key=%s，回退 legacy 渲染", template_key)
            return None
        doc = doc or {}
        window, label = _report_window(doc)
        meta = {
            "title": title or tpl.get("name") or tpl.get("key"),
            "generated_by": "AI 办公室 · 工作流输出节点",
        }
        if window:
            meta["period_label"] = f"统计区间：{window}（{label}）"
        slots = split_answer_sections(answer, doc.get("sections") or [])
        days = range_days(doc)
        render_payload = {
            **payload_fields, **slots, "answer": answer,
            "meta": {**(payload_fields.get("meta") or {}), **meta},
        }
        asset_params = {"days": days} if days else None
        return await render_report_pdf(tpl.get("blocks") or [], render_payload,
                                       template_name=tpl.get("name") or "",
                                       asset_params=asset_params)
    except Exception:
        logger.exception("产出物模板渲染失败 key=%s（回退 legacy）", template_key)
        return None


_STRUCT_BLOCK_TITLES = {"ext": "需求单字段", "plans": "BOM 配置行"}


async def _render_structured_default(title: str, payload_fields: dict) -> bytes | None:
    """结构化输出（无 answer 文本）的默认排版：按 payload 值形状自动组 blocks——
    dict → 字段表区块，list[dict] → 明细表区块，交给产出物渲染管线出 PDF。"""
    try:
        from app.services.artifact_render import render_report_pdf

        blocks: list = [{"type": "title"}]
        for key, val in payload_fields.items():
            label = _STRUCT_BLOCK_TITLES.get(str(key), str(key))
            if isinstance(val, dict) and val:
                blocks.append({"type": "fields", "key": str(key), "title": label})
            elif isinstance(val, list) and val and all(isinstance(r, dict) for r in val):
                blocks.append({"type": "table", "source": "payload", "key": str(key), "title": label})
        if len(blocks) == 1:
            return None
        meta = {"title": title, "generated_by": "AI 办公室 · 工作流输出节点"}
        return await render_report_pdf(blocks, {**payload_fields, "meta": meta}, template_name=title)
    except Exception:
        logger.exception("结构化默认排版渲染失败（不挡交付）")
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
        # 文件产物：内容配置唯一权威=目标层文档卡（ctx["document_target"]），输出节点零配置
        payload["files"] = await _render_file_artifacts(ctx, answer, payload_fields=payload)
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
