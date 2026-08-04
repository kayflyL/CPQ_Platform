# -*- coding: utf-8 -*-
"""LLM 方案校对节点 llm_audit（P3）：few-shot 检索 / 一次调用校对多方案 / 降级 / review 合并。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_llm_audit.py -q
"""
import asyncio
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from app.services import llm_client
from app.services.llm_audit import (
    build_audit_messages, find_reference_cases, run_llm_audit,
)
from app.services.reasoning_executor import _dispatch

CASES = [
    {"case_key": "BC-1", "name": "AI 训练 4U", "series": "Orion", "form": "4U",
     "scenario_tags": ["ai", "训练"], "requirement": "跑大模型训练，8卡H100",
     "l6_rows": [{"catalogue": "C1", "description": "背板", "qty": 1}], "kp_lines": [{"part_id": 1, "qty": 2}]},
    {"case_key": "BC-2", "name": "通用 2U", "series": "Orion", "form": "2U",
     "scenario_tags": ["通用"], "requirement": "数据库服务器", "l6_rows": [], "kp_lines": []},
]

PLAN = {
    "name": "Orion 2U AI", "series": "Orion", "form": "2U", "bays": 12,
    "cfg": {"bom_excel_rows": [
        {"part_category": "CPU", "description": "EPYC 9254", "qty": 2},
        {"part_category": "Memory", "description": "32G DDR5", "qty": 8},
        {"part_category": "GPU", "description": "H100", "qty": 8},
    ]},
}


def _patch_env(chat_return=None, chat_side=None, refs=None, enabled=True):
    m = AsyncMock(return_value=chat_return)
    if chat_side is not None:
        m.side_effect = chat_side
    patches = [
        patch("app.services.llm_client.chat_json", m),
        patch("app.services.llm_client.is_llm_enabled", return_value=enabled),
        patch("app.services.llm_audit.find_reference_cases",
              return_value=CASES if refs is None else refs),
        patch("app.services.llm_audit._record_trace"),
    ]
    return patches, m


def _use(patches):
    es = ExitStack()
    for p in patches:
        es.enter_context(p)
    return es


# ============================================================
# find_reference_cases —— 同平台 few-shot
# ============================================================

def test_find_reference_cases_same_series_ranked_by_keywords():
    with patch("app.repository.bom_case_repo.BomCaseRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.list_cases.return_value = list(CASES)
        refs = find_reference_cases(PLAN, "跑大模型训练，8卡 H100", limit=1)
    repo.list_cases.assert_called_once()
    assert repo.list_cases.call_args.kwargs["series"] == "Orion"
    assert refs and refs[0]["case_key"] == "BC-1"   # 需求关键词命中多 → 排前


def test_find_reference_cases_fallback_when_no_series():
    with patch("app.repository.bom_case_repo.BomCaseRepository") as repo_cls:
        repo = repo_cls.return_value
        repo.list_cases.side_effect = lambda **kw: list(CASES) if kw.get("enabled") else []
        refs = find_reference_cases({"name": "x", "series": ""}, "服务器", limit=2)
    assert len(refs) == 2


def test_find_reference_cases_db_failure_returns_empty():
    with patch("app.repository.bom_case_repo.BomCaseRepository",
               side_effect=RuntimeError("db down")):
        refs = find_reference_cases(PLAN, "服务器")
    assert refs == []


# ============================================================
# build_audit_messages
# ============================================================

def test_build_audit_messages_contains_requirement_refs_plans():
    msgs = build_audit_messages("客户要 AI 训练服务器", [PLAN], CASES)
    user = msgs[1]["content"]
    assert "客户需求原文" in user and "AI 训练服务器" in user
    assert "同平台参考案例" in user and "BC-1" in user
    assert "[0]" in user and "Orion 2U AI" in user
    assert "price" not in user.lower() and "cost" not in user.lower()   # 不暴露价格
    assert "禁止逐行 diff" in msgs[0]["content"] or "逐行 diff" in msgs[0]["content"]


# ============================================================
# run_llm_audit —— 开关 / 成功 / 降级 / trace
# ============================================================

def _run(text, plans, config):
    return asyncio.run(run_llm_audit(text, plans, config, opportunity_id="opp1"))


def test_disabled_skips_llm():
    patches, m = _patch_env(chat_return={})
    with _use(patches):
        res = _run("服务器", [PLAN], {"enable_llm": False})
    assert res["reason"] == "disabled"
    m.assert_not_called()


def test_success_audits_all_plans_once():
    data = {"plans": [
        {"index": 0, "passed": False, "issues": ["GPU 可能不足，训练场景建议 8 卡"]},
    ]}
    patches, m = _patch_env(chat_return=data)
    with _use(patches):
        res = _run("AI 训练 8卡", [PLAN], {"enable_llm": True})
    assert res["called"] is True and res["reason"] == "ok"
    assert res["plans_checked"] == 1
    assert res["issue_plans"] == 1
    assert res["audits"][0]["issues"] == ["GPU 可能不足，训练场景建议 8 卡"]
    assert res["references"] == ["BC-1", "BC-2"]
    m.assert_called_once()          # 一次调用校对全部方案
    assert res["duration_ms"] >= 0


def test_llm_error_degrades_silently():
    patches, m = _patch_env(chat_side=llm_client.LLMError("boom"))
    with _use(patches):
        res = _run("服务器", [PLAN], {"enable_llm": True})
    assert res["called"] is True
    assert res["reason"] == "llm_error"
    assert res["audits"] == []
    assert "boom" in (res["error"] or "")


def test_global_ai_disabled():
    patches, m = _patch_env(chat_return={}, enabled=False)
    with _use(patches):
        res = _run("服务器", [PLAN], {"enable_llm": True})
    assert res["reason"] == "global_ai_disabled"
    m.assert_not_called()


# ============================================================
# executor：llm_audit 分支 + review 合并
# ============================================================

def test_dispatch_llm_audit_branch():
    async def broadcast(_p):
        return None
    ctx = {"requirement_text": "AI 训练", "plans": [PLAN], "opportunity_id": "test-run",
           "pipeline_id": "pl_1"}
    with patch("app.services.llm_audit.run_llm_audit") as m:
        async def fake(text, plans, config, **kw):
            return {"called": True, "reason": "ok", "audits": [{"index": 0, "passed": False,
                    "issues": ["GPU 可能不足"]}], "plans_checked": 1, "issue_plans": 1,
                    "duration_ms": 10, "references": ["BC-1"]}
        m.side_effect = fake
        payload = asyncio.run(_dispatch("llm_audit", ctx, {"enable_llm": True}, broadcast))
    assert ctx["llm_audits"][0]["issues"] == ["GPU 可能不足"]
    assert payload["issue_plans"] == 1


def test_review_merges_llm_audit_issues():
    async def broadcast(_p):
        return None
    plan = {"name": "Orion 2U", "series": "Orion", "cfg": {"bom_excel_rows": [
        {"part_category": "CPU", "description": "EPYC 9254", "qty": 2},
        {"part_category": "Memory", "description": "32G", "qty": 8}]}}
    ctx = {"plans": [plan], "ext": {}, "requirement_text": "AI 训练服务器",
           "llm_audits": [{"index": 0, "passed": False, "issues": ["GPU 可能不足"]}]}
    with patch("app.services.requirement_checker.audit_plan",
               return_value={"status": "ok", "issues": [], "issue_count": 0}):
        payload = asyncio.run(_dispatch("review", ctx, {}, broadcast))
    assert plan["audit"]["status"] == "review"      # 规则通过但 LLM 存疑 → review
    assert "GPU 可能不足" in plan["audit"]["issues"]
    assert payload["blocked"] == 0
