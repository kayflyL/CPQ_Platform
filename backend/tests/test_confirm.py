# -*- coding: utf-8 -*-
"""P2：LLM 确认面板（confirm 节点）+ LLM 反问（llm_ask / ask_user 追问注入）。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_confirm.py -q
"""
import asyncio
from unittest.mock import patch

from app.services.reasoning_executor import (
    _ask_catalog_question, _confirm_llm_items, _dispatch, _llm_questions,
)
from app.services.requirement_slots import apply_confirm_decisions

CONFLICT_ITEM = {"id": "cf_series", "slot": "series", "label": "所属系列",
                 "rule": "Orion", "llm": "Polaris", "level": "conflict", "default": "accept"}
LOW_CONF_ITEM = {"id": "cf_form", "slot": "form", "label": "机箱形态",
                 "rule": None, "llm": "2U", "level": "low_confidence",
                 "confidence": 0.4, "default": "accept"}


# ============================================================
# apply_confirm_decisions —— 默认采纳 / 可改忽略 / 冲突回规则值
# ============================================================

def test_apply_confirm_decisions_accept_llm_ignore_clears():
    ext = {"series": "Orion", "form": None}
    applied = apply_confirm_decisions(ext, [CONFLICT_ITEM, LOW_CONF_ITEM],
                                      {"cf_series": "accept", "cf_form": "ignore"})
    assert ext["series"] == "Polaris"   # accept → 采纳 LLM 值
    assert ext["form"] is None          # ignore（无规则值）→ 清空
    assert len(applied) == 2
    dec = {a["id"]: a["decision"] for a in applied}
    assert dec == {"cf_series": "accept", "cf_form": "ignore"}


def test_apply_confirm_decisions_default_accept():
    ext = {"series": None}
    applied = apply_confirm_decisions(ext, [LOW_CONF_ITEM], {})
    assert ext["form"] == "2U"          # 默认采纳
    assert applied[0]["decision"] == "accept"


def test_apply_confirm_decisions_conflict_ignore_keeps_rule():
    ext = {"series": "Orion"}
    apply_confirm_decisions(ext, [CONFLICT_ITEM], {"cf_series": "ignore"})
    assert ext["series"] == "Orion"     # ignore → 保留规则值


# ============================================================
# confirm 节点（_confirm_llm_items）
# ============================================================

async def _run_confirm(ctx, config=None):
    return await _confirm_llm_items(ctx, None, config or {})


def test_confirm_skips_when_no_items():
    r = asyncio.run(_run_confirm({"slot_validation": {"confirm_items": []}}))
    assert r["skip"] is True


def test_confirm_pending_when_no_decisions_and_not_force():
    ctx = {"slot_validation": {"confirm_items": [CONFLICT_ITEM]},
           "force_complete": False, "opportunity_id": "test-run"}
    r = asyncio.run(_run_confirm(ctx))
    assert r["awaiting"] is True
    assert ctx["confirm_pending"] is True
    assert ctx["awaiting_input"] is True
    assert ctx["confirm_items"] == [CONFLICT_ITEM]


def test_confirm_force_complete_auto_accept_all():
    ctx = {"slot_validation": {"confirm_items": [CONFLICT_ITEM, LOW_CONF_ITEM]},
           "force_complete": True, "opportunity_id": "test-run", "ext": {"series": "Orion"}}
    with patch("app.services.requirement_intel_service._write_llm_feedback_sample") as m:
        r = asyncio.run(_run_confirm(ctx))
    assert r["count"] == 2
    assert ctx["ext"]["series"] == "Polaris"   # 默认全采纳
    assert ctx["ext"]["form"] == "2U"
    m.assert_called_once()


def test_confirm_applies_user_decisions():
    ctx = {"slot_validation": {"confirm_items": [CONFLICT_ITEM, LOW_CONF_ITEM]},
           "force_complete": False, "opportunity_id": "test-run", "ext": {"series": "Orion", "form": "2U"},
           "confirm_decisions": {"cf_series": "ignore", "cf_form": "ignore"},
           "confirm_answered": True}
    with patch("app.services.requirement_intel_service._write_llm_feedback_sample"):
        r = asyncio.run(_run_confirm(ctx))
    assert ctx["ext"]["series"] == "Orion"   # ignore → 回规则值
    assert ctx["ext"]["form"] is None        # ignore → 清空 LLM 补充
    assert r["count"] == 2
    assert ctx["confirm_consumed"] is True


def test_dispatch_confirm_branch():
    async def broadcast(_p):
        return None
    ctx = {"requirement_text": "AMD 服务器", "opportunity_id": "test-run",
           "force_complete": False, "ext": {"series": "Orion"},
           "confirm_decisions": {"cf_series": "ignore"}, "confirm_answered": True,
           "slot_validation": {"confirm_items": [CONFLICT_ITEM]}}
    with patch("app.services.requirement_intel_service._write_llm_feedback_sample"):
        payload = asyncio.run(_dispatch("confirm", ctx, {}, broadcast))
    assert ctx["ext"]["series"] == "Orion"
    assert payload["count"] == 1


# ============================================================
# _llm_questions + ask_user/llm_ask 追问注入
# ============================================================

def test_llm_questions_only_when_ok():
    assert _llm_questions({"llm_report": {"reason": "disabled", "questions": ["x"]}}) == []
    assert _llm_questions({"llm_report": {"reason": "llm_error", "questions": ["x"]}}) == []
    assert _llm_questions({"llm_report": {"reason": "ok", "questions": ["a", "b"]}}) == ["a", "b"]
    assert _llm_questions({}) == []


def test_ask_catalog_question_injects_llm_questions():
    async def broadcast(_p):
        return None
    with patch("app.services.catalog_guide.build_question_with_catalog",
               return_value=("请选择服务器类型", ["AI / 加速计算服务器"], {"mode": "ask"}, "fmt")), \
         patch("app.services.catalog_guide.load_ask_config", return_value={}), \
         patch("app.services.requirement_intel_service._persist_catalog_offer", return_value=None):
        ctx = {"catalog_stage": "type", "catalog_state": {}, "flow_configs": {},
               "opportunity_id": "test-run", "clarify_round": 1, "clarity_capped": False}
        payload = asyncio.run(_ask_catalog_question(
            ctx, broadcast, extra_questions=["请确认CPU型号；内存容量"]))
    assert "请一并确认" in payload["question"]
    assert "请确认CPU型号；内存容量" in payload["question"]
