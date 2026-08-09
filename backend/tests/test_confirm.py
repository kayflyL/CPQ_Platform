# -*- coding: utf-8 -*-
"""LLM 追问注入：_llm_questions（取主理解缺失项追问）+ ask_user/llm_ask 追问注入。

（confirm 节点 + apply_confirm_decisions 已随双路线重构删除，本文件仅保留追问相关用例。）

跑法（backend 目录）：python -X utf8 -m pytest tests/test_confirm.py -q
"""
import asyncio
from unittest.mock import patch

from app.services.reasoning_executor import (
    _ask_catalog_question, _llm_questions,
)


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
