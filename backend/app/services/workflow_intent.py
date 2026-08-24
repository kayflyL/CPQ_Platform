# -*- coding: utf-8 -*-
"""Multi-turn workflow intent resolver.

When a paused capability node re-runs on a follow-up reply, ask the configured LLM
to classify what that reply actually *means* before the deterministic node re-executes.
Facts (catalog / candidates / rules / price / compat) always come from tools or the rule
library; this module only labels intent and optionally narrates a natural-language reply.

Only a few intents are intercepted here because the existing node handlers already do the
right thing for the others:
- list_catalog -> present the real in-sale catalog (data-driven)
- explain      -> explain the previous ask/state in plain words
- noise        -> off-topic / politeness, acknowledge briefly
Everything else falls through to the deterministic node, whose own handlers already cover
cancel / self_config / reselect / auto_recommend / confirm_choice / refine / grasp.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.services import llm_client

logger = logging.getLogger(__name__)

_INTENTS = {
    "list_catalog", "explain", "refine", "auto_recommend", "self_config",
    "cancel", "confirm_choice", "reselect", "grasp", "noise", "ask",
}

_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": sorted(_INTENTS)},
        "reply": {"type": "string"},
    },
    "required": ["intent"],
}


def resolve_intent_keywords(message: str) -> Optional[str]:
    """LLM 不可用时的保守兜底：只识别最明确的关键词，其余交给原节点。"""
    text = str(message or "").strip().lower()
    if not text:
        return None
    phrases: dict = {}
    try:
        from app.services import requirement_rule_catalog as _rc
        phrases = _rc.model_action_phrases()
    except Exception:
        phrases = {}
    for action, keys in (("cancel", phrases.get("cancel") or []),
                         ("self_config", phrases.get("self_config") or []),
                         ("reselect", phrases.get("reselect") or []),
                         ("auto_recommend", phrases.get("auto_pick") or [])):
        if any(k in text for k in keys):
            return action
    for k in ("有哪些", "有什么", "都有什么", "什么机型", "哪些服务器", "有哪些服务器", "你们卖什么"):
        if k in text:
            return "list_catalog"
    for k in ("什么意思", "啥意思", "解释", "不懂", "没懂", "为什么"):
        if k in text:
            return "explain"
    return None


async def resolve_intent(message: Optional[str], context: Optional[str] = None) -> dict:
    """Label the latest user utterance intent. Facts stay in tools/rule library."""
    text = str(message or "").strip()
    if not text:
        return {"intent": "grasp", "reply": ""}
    if not llm_client.is_llm_enabled():
        fb = resolve_intent_keywords(text)
        return {"intent": fb or "grasp", "reply": ""}
    system = (
        "你是 CPQ 服务器需求分析对话的意图理解器。\n"
        "背景（来自工具/规则库，仅供理解，不要编造）：\n" + str(context or "")[:2000] + "\n\n"
        "判断用户这句话在做什么，只返回以下一种 intent：\n"
        "- list_catalog: 用户想浏览/了解当前有哪些服务器/机型/类型/系列。例：有哪些服务器/都有什么机型/你们卖什么。\n"
        "- explain: 用户没听懂上一条 AI 的话，追问“什么意思/为什么/解释一下/啥意思”。\n"
        "- refine: 用户在**给出或改口需求**（场景、类型、系列、形态、预算、用途、规格）。例：我要一台通用计算服务器，2U。\n"
        "- ask: 用户在**提问**，想了解候选/目录/价格/配置/区别/流程/原因，而不是在给需求。例：这个多少钱/这台什么配置/这两种有什么区别/怎么选/为什么推荐这个/有XX吗。\n"
        "- auto_recommend: 用户把决定权交给系统。例：你推荐/都行/随便/帮我配/最合适的。\n"
        "- self_config: 用户要自己配置。例：我自己配/我来自配/我去详情页。\n"
        "- cancel: 用户要取消本次配置。例：取消/不配了/算了。\n"
        "- confirm_choice: 用户在候选里确认一个。例：选第1个/就这个/选XX型号。\n"
        "- reselect: 用户要重新选机型。例：重选/换一个/重新选。\n"
        "- grasp: 用户在正常回答一个封闭问题/给出简短确认，应继续走流程。例：通用计算（回答上一句的类型询问）。\n"
        "- noise: 与需求无关的闲聊、客套、表情、无意义内容。\n"
        "关键区分：**给需求/回答封闭问题 → refine/grasp；想了解信息/提问 → ask/explain/list_catalog；决定权（推荐/自配/取消）→ auto_recommend/self_config/cancel。**\n"
        "规则：只有 explain/noise/ask 需要用 reply 给一句自然中文回应（ask 的 reply 说明你理解的问题、或提示需要选型后确认数据）；其余 reply 留空。"
        "只输出 JSON，不要输出 Markdown。"
    )
    try:
        data = await llm_client.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": text}],
            schema=_INTENT_SCHEMA,
            temperature=0.0,
            timeout=60.0,
            max_attempts=1,
        )
    except Exception as exc:
        logger.debug("workflow intent LLM 判定失败，回退关键词: %s", exc)
        fb = resolve_intent_keywords(text)
        return {"intent": fb or "grasp", "reply": ""}
    intent = str((data or {}).get("intent") or "").strip().lower()
    if intent not in _INTENTS:
        intent = "grasp"
    return {"intent": intent, "reply": str((data or {}).get("reply") or "").strip()}


async def catalog_digest() -> str:
    """Read the real in-sale catalog and build a user-facing list (no hardcoded names)."""
    lines: list[str] = []
    try:
        from app.services.catalog_guide import load_catalog
        types, models_by_type = load_catalog()
    except Exception:
        return "（当前无法读取服务器目录，请稍后再试。）"
    if not types:
        return "（当前在售服务器目录为空，暂无候选机型。）"
    for t in types:
        tname = str(t.get("name") or "").strip() or "未命名类型"
        models = models_by_type.get(tname) or []
        lines.append(f"{tname}：")
        for m in models[:20]:
            bc = m.get("base_config") or {}
            series = str(bc.get("series") or m.get("series") or "").strip()
            form = str(bc.get("form") or m.get("form") or "").strip()
            extra = "/".join(x for x in (series, form) if x)
            nm = str(m.get("name") or m.get("id") or "").strip()
            lines.append("  - " + nm + (("（" + extra + "）") if extra else ""))
    return "\n".join(lines)


_REPLY_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
}


async def reply_with_context(message: str, context: str) -> str:
    """对“普通提问/解释/闲聊”给一句自然中文回复，答案只能基于给定真实上下文。"""
    if not llm_client.is_llm_enabled():
        return ""
    system = (
        "你是 CPQ 服务器需求分析对话助手。请用一到三句自然中文回应用户。\n"
        "答案只能基于下面的真实上下文；没有明确数据（如价格/兼容/库存）就说“选型后我会帮你确认”，"
        "不要编造型号、参数、价格。\n\n上下文：\n" + str(context or "")[:3000]
    )
    try:
        data = await llm_client.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": str(message or "")}],
            schema=_REPLY_SCHEMA,
            temperature=0.3,
            timeout=60.0,
            max_attempts=1,
        )
    except Exception as exc:
        logger.debug("workflow intent reply LLM 失败: %s", exc)
        return ""
    return str((data or {}).get("reply") or "").strip()
