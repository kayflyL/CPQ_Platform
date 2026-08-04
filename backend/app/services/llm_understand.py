# -*- coding: utf-8 -*-
"""LLM 主理解节点 llm_understand —— 需求原文 + 目录上下文 → 统一 RequirementSlots 契约。

背景（2026-08 需求分析 LLM 重构，P1）：
  - 旧「extract/scene/review 三处散装 LLM 增强」默认关闭、规则赢、只补缺 → 典型需求
    规则已抽全 → LLM 永不改变结果（用户实测"接了和没接一样"）。
  - 新方案：LLM 收拢为单一主理解节点，输出统一 RequirementSlots 契约（槽位 + 置信度 +
    证据 + 预算 + 意图摘要 + 缺失项 + 追问），配合目录白名单做语义校验，只许从白名单选、
    选不出写 null、禁编料号；失败带具体错误喂回重试 1 次；再失败静默降级规则。

本模块职责：
  1) build_messages —— 需求原文 + 规则抽取摘要 + 目录白名单 + schema 说明（可追加校验反馈）；
  2) run_llm_understand —— chat_json → 语义校验 → 失败带错误重试 → apply_llm_merge 进 ext。
"""
import json
import logging
from typing import Optional

from app.services import llm_client
from app.services.requirement_slots import (
    build_catalog_context, _catalog_summary, LLM_UNDERSTAND_SCHEMA, SLOT_KEYS,
    validate_slots, apply_llm_merge, compute_coverage,
)

logger = logging.getLogger(__name__)

LLM_UNDERSTAND_SYSTEM_PROMPT = (
    "你是 CPQ 服务器需求的结构化理解器。输入：需求原文 + 规则引擎已抽取摘要 + 在售目录白名单。\n"
    "任务：把需求理解成统一的 JSON 槽位契约。只输出 JSON 对象，不要任何多余文字。\n"
    "硬性约束：\n"
    "1) 只从目录白名单里选：server_type 只在白名单类型里选、series 只在白名单系列里选、"
    "form 只在 1U/2U/4U/5U/6U/8U 里选；选不出就写 value=null，绝不编造。\n"
    "2) 型号（cpu.model / gpu[].model / nic[].model / raid.model）必须是需求原文里出现过的、"
    "或命中型号家族词表的型号；没把握一律 null，禁止编造料号。\n"
    "3) 能力声明 ≠ 实际配置：「支持/最多/最大 N 个 X」是机箱能力，不是要配 N 个 X；"
    "例如「支持8个GPU」不产 8 张 GPU（除非给出具体型号）。\n"
    "4) 数量写实际要配的数量（条/颗/块/张），不是插槽数；单条内存容量不知道就 null。\n"
    "5) 预算 budget 用数字（元），原文写「30万」→ 300000；没写就 null。\n"
    "6) 每个槽位带 confidence（0~1，把握程度）、source（text=需求明说 / catalog=目录匹配 / "
    "infer=语义推断）、evidence（一句话依据，来自需求原文）。\n"
    "7) missing 列出需求里确实缺失、会影响选型的关键槽位；questions 生成一次性追问"
    "（把所有缺失项放一起问，不要逐个问）。\n"
    "8) 规则已抽到且你同意的项也要带出（确认即价值），但不要编新项。"
)


def _ext_digest(ext: dict) -> dict:
    """规则抽取摘要（给 LLM 看规则已经抽到什么）。"""
    ext = ext or {}
    return {
        "categories": ext.get("categories") or [],
        "keywords": ext.get("keywords") or [],
        "server_type": ext.get("server_type_name"),
        "series": ext.get("series"),
        "form": ext.get("form"),
        "budget": ext.get("budget"),
        "cpu_signal": ext.get("cpu_signal"),
        "mem_signal": ext.get("mem_signal"),
        "psu_signal": ext.get("psu_signal"),
        "drive_groups": ext.get("drive_groups") or [],
        "gpu_groups": ext.get("gpu_groups") or [],
        "mem_groups": ext.get("mem_groups") or [],
    }


def _catalog_text(catalog: dict) -> str:
    """目录白名单 → 提示词里的可读文本（全量类型/系列/形态 + 每类型代表机型名）。"""
    lines = []
    lines.append("在售服务器类型：" + ("、".join(catalog.get("server_types") or []) or "（无）"))
    lines.append("在售系列：" + ("、".join(catalog.get("series") or []) or "（无）"))
    lines.append("机箱形态：" + ("、".join(catalog.get("forms") or []) or "（无）"))
    mbt = catalog.get("models_by_type") or {}
    if mbt:
        lines.append("各类型在售机型（机型名仅供参考，选 server_type 即可）：")
        for tn, ms in mbt.items():
            lines.append(f"  - {tn}：{'、'.join(ms[:8])}" + ("…" if len(ms) > 8 else ""))
    fw = catalog.get("family_words") or {}
    if fw:
        parts = []
        for cat, kws in fw.items():
            if kws:
                parts.append(f"{cat}：{'/'.join(kws[:20])}")
        lines.append("型号家族词表（型号必须命中这里或出现在需求原文）：" + "；".join(parts))
    return "\n".join(lines)


def build_messages(requirement_text: str, ext: dict, catalog: dict,
                   feedback: Optional[list] = None) -> list:
    """构造 chat_json 的 messages：系统 prompt + 需求原文 + 规则摘要 + 目录白名单 + 校验反馈。"""
    user = (
        f"需求原文：\n{(requirement_text or '').strip()}\n\n"
        f"规则引擎已抽取（可能不完整/有误）：\n{json.dumps(_ext_digest(ext), ensure_ascii=False, default=str)}\n\n"
        f"在售目录白名单（只允许从这里选）：\n{_catalog_text(catalog)}\n\n"
    )
    if feedback:
        user += (
            "上一次输出的以下字段未通过校验，请修正（改不了就置 null，不要编造）：\n"
            + "\n".join(f"- {f}" for f in feedback)
            + "\n\n"
        )
    user += (
        "请输出统一 JSON 槽位契约，字段：server_type/series/form（对象：value/confidence/"
        "source/evidence）、cpu{model,qty}、memory{per_stick_gb,qty,type}、storage["
        "{capacity,capacity_gb,interface,qty}]、gpu[{model,qty}]、nic[{model,speed_g,ports,"
        "qty,with_optical_module}]、psu{wattage,qty}、raid{model,qty}、budget{value}、"
        "intent_summary、missing、questions。所有槽位对象都要带 confidence/source/evidence。"
    )
    return [
        {"role": "system", "content": LLM_UNDERSTAND_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


def _strip_slots(data: dict) -> dict:
    """从完整契约里取槽位部分（不含 intent_summary/missing/questions 元信息）。"""
    return {k: data.get(k) for k in SLOT_KEYS if data.get(k) is not None}


def _record_trace(status: str, merged: bool, opportunity_id: str, pipeline_id: str,
                  prompt_chars: int = 0, response_chars: int = 0, error: Optional[str] = None) -> None:
    """llm_understand 调用 trace（P3：指标数据源）。试运行不污染。"""
    if not (opportunity_id or "") or (opportunity_id or "").startswith("test"):
        return  # 无商机（单测/未挂载）或试运行：不写 trace，避免污染指标
    try:
        from app.services.llm_trace import record_llm_trace
        record_llm_trace(
            node_type="llm_understand", opportunity_id=opportunity_id, pipeline_id=pipeline_id,
            status=status, called=True, merged=merged,
            prompt_chars=prompt_chars, response_chars=response_chars,
            issue_count=0, retried=False, error=error,
        )
    except Exception as e:
        logger.warning("写 llm_trace 失败: %s", e)


async def run_llm_understand(requirement_text: str, ext: dict, config: dict,
                             opportunity_id: str = "", pipeline_id: str = "") -> dict:
    """llm_understand 节点主入口：LLM 主理解 → 语义校验 → 重试 1 次 → 合并进 ext。

    返回结果字典（called/reason/slots/changes/merged/retried/errors/warnings/
    coverage/intent_summary/missing/questions/catalog）。任何失败静默降级（ext 原样）。
    """
    base: dict = {
        "called": False,
        "reason": None,
        "error": None,
        "slots": {},
        "changes": [],
        "merged": False,
        "retried": False,
        "errors": [],
        "warnings": [],
        "coverage": None,
        "intent_summary": None,
        "missing": [],
        "questions": [],
        "catalog": None,
    }
    config = config or {}
    if not config.get("enable_llm"):
        base["reason"] = "disabled"
        base["coverage"] = compute_coverage(ext or {}, None)
        return base
    try:
        if not llm_client.is_llm_enabled():
            base["reason"] = "global_ai_disabled"
            base["coverage"] = compute_coverage(ext or {}, None)
            return base
    except Exception:
        pass

    catalog = build_catalog_context()
    base["catalog"] = _catalog_summary(catalog)
    messages = build_messages(requirement_text or "", ext or {}, catalog)
    try:
        data = await llm_client.chat_json(messages, schema=LLM_UNDERSTAND_SCHEMA)
    except llm_client.LLMError as e:
        base.update(called=True, reason="llm_error", error=str(e)[:300])
        _record_trace("llm_error", False, opportunity_id, pipeline_id, error=str(e)[:300])
        return base

    errors, warnings = validate_slots(data, catalog, requirement_text or "")
    try:
        max_retry = int(config.get("max_retry") or 1)
    except (TypeError, ValueError):
        max_retry = 1  # 脏配置（非数字）按默认 1 处理，不抛
    if errors and max_retry > 0:
        try:
            retry_msgs = build_messages(requirement_text or "", ext or {}, catalog, feedback=errors)
            data2 = await llm_client.chat_json(retry_msgs, schema=LLM_UNDERSTAND_SCHEMA)
            base["retried"] = True
            errors2, warnings2 = validate_slots(data2, catalog, requirement_text or "")
            if not errors2:
                data, errors, warnings = data2, errors2, warnings2
            else:
                # 重试后仍有硬错误：保留重试结果，但记录最终错误（合并层仍做白名单/数量闸门）
                base["errors"] = errors2
        except llm_client.LLMError as e2:
            base["errors"] = errors
            base["error"] = str(e2)[:300]
    if errors and not base.get("errors"):
        base["errors"] = errors
    base["warnings"] = warnings

    changes = apply_llm_merge(ext or {}, data, requirement_text or "", catalog)
    base.update(
        called=True,
        reason="ok",
        slots=_strip_slots(data),
        changes=changes,
        merged=bool(changes),
        coverage=compute_coverage(data, catalog),
        intent_summary=str(data.get("intent_summary") or "").strip() or None,
        missing=[str(x) for x in (data.get("missing") or []) if str(x).strip()],
        questions=[str(x) for x in (data.get("questions") or []) if str(x).strip()],
    )
    _record_trace("ok", bool(changes), opportunity_id, pipeline_id,
                  prompt_chars=sum(len(m.get("content") or "") for m in messages),
                  response_chars=len(json.dumps(data, ensure_ascii=False, default=str)),
                  error=None)
    return base
