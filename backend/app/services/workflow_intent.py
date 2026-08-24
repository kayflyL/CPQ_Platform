# -*- coding: utf-8 -*-
"""Multi-turn workflow intent resolver.

When a paused capability node re-runs on a follow-up reply, ask the configured LLM to
classify what that reply actually *means* before the deterministic node re-executes.

Persona / boundary / classifier wording lives in .txt data files next to this module so the
Python layer holds only orchestration logic (no user-facing sentences).
"""
from __future__ import annotations

import logging
from pathlib import Path
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

_REPLY_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
}

_PERSONA_PATH = Path(__file__).with_name("workflow_persona.txt")
_CLASSIFIER_PATH = Path(__file__).with_name("workflow_intent_classifier.txt")


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def resolve_intent_keywords(message: str) -> Optional[str]:
    """Conservative fallback when the LLM is unavailable: only the clearest keywords."""
    text = str(message or "").strip().lower()
    if not text:
        return None
    phrases: dict = {}
    try:
        from app.services import requirement_rule_catalog as _rc
        phrases = _rc.model_action_phrases()
    except Exception:
        phrases = {}
    for action in ("cancel", "self_config", "reselect", "auto_recommend",
                   "list_catalog", "explain"):
        # 词表一律来自规则库（model_action_phrases / intent_keywords 语义同源），py 不背业务中文词。
        if action == "auto_recommend":
            keys = phrases.get("auto_pick") or []
        else:
            keys = phrases.get(action) or []
        if any(k in text for k in keys):
            return action
    return None


async def resolve_intent(message: Optional[str], context: Optional[str] = None) -> dict:
    """Label the latest user utterance intent. Facts stay in tools / rule library."""
    text = str(message or "").strip()
    if not text:
        return {"intent": "grasp", "reply": ""}
    if not llm_client.is_llm_enabled():
        fb = resolve_intent_keywords(text)
        return {"intent": fb or "grasp", "reply": ""}
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
        logger.debug("workflow intent LLM 判定失败，回退关键词: %s", exc)
        fb = resolve_intent_keywords(text)
        return {"intent": fb or "grasp", "reply": ""}
    intent = str((data or {}).get("intent") or "").strip().lower()
    if intent not in _INTENTS:
        intent = "grasp"
    return {"intent": intent, "reply": str((data or {}).get("reply") or "").strip()}


async def catalog_digest() -> str:
    """Read the real in-sale catalog into a compact factual dump (no canned prose)."""
    lines: list[str] = []
    try:
        from app.services.catalog_guide import load_catalog
        types, models_by_type = load_catalog()
    except Exception:
        return ""
    for t in types or []:
        tname = str(t.get("name") or "").strip()
        if not tname:
            continue
        models = models_by_type.get(tname) or []
        lines.append(tname + ":")
        for m in models[:30]:
            bc = m.get("base_config") or {}
            series = str(bc.get("series") or m.get("series") or "").strip()
            form = str(bc.get("form") or m.get("form") or "").strip()
            extra = "/".join(x for x in (series, form) if x)
            nm = str(m.get("name") or m.get("id") or "").strip()
            lines.append("  - " + nm + (("(" + extra + ")") if extra else ""))
    return "\n".join(lines)


async def reply_with_context(message: str, context: str) -> str:
    """Generate a grounded, persona-driven natural reply. No canned fallback in code."""
    if not llm_client.is_llm_enabled():
        return ""
    persona = _load_text(_PERSONA_PATH)
    if not persona:
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
