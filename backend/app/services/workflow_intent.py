# -*- coding: utf-8 -*-
"""Multi-turn workflow intent resolver.

When a paused capability node re-runs on a follow-up reply, ask the configured LLM to
classify what that reply actually *means* before the deterministic node re-executes.

Only flow-control classification lives here. Persona wording comes from the role-level
chat system prompt (single persona source); catalog facts come from the data layer.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.services import llm_client

logger = logging.getLogger(__name__)

_INTENTS = {
    "list_catalog", "explain", "refine", "auto_recommend",
    "cancel", "confirm_choice", "reselect", "grasp", "noise", "ask",
}

_INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": sorted(_INTENTS)},
    },
    "required": ["intent"],
}

_REPLY_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
}

_CLASSIFIER_PATH = Path(__file__).with_name("workflow_intent_classifier.txt")


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


async def resolve_intent(message: Optional[str], context: Optional[str] = None) -> dict:
    """Label the latest user utterance intent. Facts stay in tools / rule library."""
    text = str(message or "").strip()
    if not text:
        return {"intent": "grasp"}
    if not llm_client.is_llm_enabled():
        return {"intent": "grasp"}
    cls = _load_text(_CLASSIFIER_PATH) or "Classify the user message into one of the allowed intents."
    system = cls.replace("{context}", str(context or "")[:2000])
    try:
        data = await llm_client.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": text}],
            schema=_INTENT_SCHEMA,
            temperature=0.0,
            timeout=60.0,
            max_attempts=1,
        )
    except Exception as exc:
        logger.debug("workflow intent LLM 判定失败，按 grasp 处理: %s", exc)
        return {"intent": "grasp"}
    intent = str((data or {}).get("intent") or "").strip().lower()
    if intent not in _INTENTS:
        intent = "grasp"
    return {"intent": intent}


async def reply_with_context(message: str, context: str, persona: str = "") -> str:
    """Generate a grounded, persona-driven natural reply. persona must be the role-level
    chat system prompt (single persona source); no file fallback in this module."""
    persona = str(persona or "").strip()
    if not llm_client.is_llm_enabled() or not persona:
        return ""
    system = persona + "\n\n【当前对话上下文】\n" + str(context or "")[:3000]
    try:
        data = await llm_client.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": str(message or "")}],
            schema=_REPLY_SCHEMA,
            temperature=0.7,
            timeout=60.0,
            max_attempts=1,
        )
    except Exception as exc:
        logger.debug("workflow intent reply LLM 失败: %s", exc)
        return ""
    return str((data or {}).get("reply") or "").strip()
