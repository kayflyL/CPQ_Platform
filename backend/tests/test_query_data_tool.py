# -*- coding: utf-8 -*-
"""query_data 原语（步骤2）单测：工具注册/门控/边界拒止/白名单放行/审计上下文。

宪法断言：权限全在 data_boundary（物理层），工具层只做接线；
角色 tool_ids 未勾选 query_data 时工具不进对话循环。
"""
import pytest

from app.services.skill_chat import tool_query_data, requirement_prompt


def _ctx(boundary, role="assistant"):
    from app.services import skill_chat
    return skill_chat._TOOL_CTX.set({
        "boundary": boundary, "role_key": role, "price_ok": True,
        "ext": {}, "save": lambda: None, "user_text": "",
    })


ALLOW = {"mode": "allow_read", "schemas": [], "tables_allow": ["opportunities.opportunities"],
         "masked_fields": []}


# ── 工具层：边界接线 ─────────────────────────────────────────────────────────

def test_query_data_deny_all_boundary():
    token = _ctx({"mode": "deny_all", "schemas": [], "tables_allow": [], "masked_fields": ["price"]})
    try:
        out = tool_query_data({"sql": "SELECT 1"})
        assert out["ok"] is False and "拒绝模式" in out["error"]
    finally:
        from app.services import skill_chat
        skill_chat._TOOL_CTX.reset(token)


def test_query_data_no_context_fails_closed():
    from app.services import skill_chat
    token = skill_chat._TOOL_CTX.set({})  # 引擎路径：无边界上下文
    try:
        out = tool_query_data({"sql": "SELECT 1"})
        assert out["ok"] is False
    finally:
        skill_chat._TOOL_CTX.reset(token)


def test_query_data_missing_sql():
    token = _ctx(ALLOW)
    try:
        out = tool_query_data({})
        assert out["ok"] is False and "sql" in out["error"]
    finally:
        from app.services import skill_chat
        skill_chat._TOOL_CTX.reset(token)


def test_query_data_whitelisted_table_executes(monkeypatch):
    from app.services import data_boundary
    calls = []

    def fake_execute_read(sql, boundary, *, limit=50, **kw):
        calls.append((sql, limit))
        return {"ok": True, "error": "", "columns": ["n"], "rows": [[1]],
                "row_count": 1, "truncated": False}

    monkeypatch.setattr(data_boundary, "execute_read", fake_execute_read)
    token = _ctx(ALLOW)
    try:
        out = tool_query_data({"sql": "SELECT count(*) AS n FROM opportunities.opportunities",
                               "limit": "30"})
        assert out["ok"] is True and out["rows"] == [[1]]
        assert calls == [("SELECT count(*) AS n FROM opportunities.opportunities", 30)]
    finally:
        from app.services import skill_chat
        skill_chat._TOOL_CTX.reset(token)


def test_query_data_bad_limit_falls_back():
    from app.services import data_boundary
    import app.services.skill_chat as sc
    seen = {}

    def fake_execute_read(sql, boundary, *, limit=50, **kw):
        seen["limit"] = limit
        return {"ok": True, "columns": [], "rows": [], "row_count": 0}

    orig = data_boundary.execute_read
    data_boundary.execute_read = fake_execute_read
    # skill_chat 内 import 的是模块属性，patch 模块函数即可
    token = _ctx(ALLOW)
    try:
        tool_query_data({"sql": "SELECT 1", "limit": "abc"})
        assert seen["limit"] == 50
    finally:
        sc._TOOL_CTX.reset(token)
        data_boundary.execute_read = orig


# ── 工具注册与退役 ───────────────────────────────────────────────────────────

def test_query_data_registered_default_off():
    from app.services.agent_tool_specs import _TOOL_SPECS, build_tool_registry
    assert "query_data" in _TOOL_SPECS
    assert _TOOL_SPECS["query_data"]["default_enabled"] is False
    # 默认全集不含 query_data（显式启用才进循环）
    reg = build_tool_registry({})
    assert "query_data" not in reg.names()
    reg2 = build_tool_registry({"enabled_tools": ["query_data"]})
    assert "query_data" in reg2.names()


def test_retired_tools_gone():
    from app.services.agent_tool_specs import _TOOL_SPECS
    for name in ("query_cpq_data", "list_server_types", "list_server_models", "get_server_model"):
        assert name not in _TOOL_SPECS, name


def test_capability_specs_no_retired_defaults():
    from app.services.capability_spec import SPECS, validate_specs
    for spec in SPECS.values():
        for tid in spec.default_tools:
            assert tid not in ("query_cpq_data", "list_server_types",
                               "list_server_models", "get_server_model")
    assert validate_specs() == []


# ── 提示词门控 ───────────────────────────────────────────────────────────────

def test_requirement_prompt_data_rule_gated():
    with_line = requirement_prompt({}, price_ok=True, query_data_ok=True)
    without_line = requirement_prompt({}, price_ok=True, query_data_ok=False)
    assert "query_data" in with_line and "information_schema" in with_line
    assert "query_data" not in without_line
