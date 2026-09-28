# -*- coding: utf-8 -*-
"""query_data 原语单测：工具注册/价格脱敏接线/白名单放行/审计上下文。

宪法断言（2026-09-13 工具即权限）：权限全在 data_boundary（物理层），工具层只做接线；
边界由工具自建（表白名单=工具自有配置，价格列按同事 price_access 脱敏）；
角色 tool_ids 未勾选 query_data 时工具不进对话循环。
"""
import pytest

from app.services.skill_tools_fill import requirement_prompt
from app.services.skill_tools_misc import tool_query_data
from app.services import skill_tool_context


def _ctx(price_ok=True, role="assistant"):
    return skill_tool_context.TOOL_CTX.set({
        "role_key": role, "price_ok": price_ok,
        "ext": {}, "save": lambda: None, "user_text": "",
    })


ALLOW = {"mode": "allow_read", "schemas": [], "tables_allow": ["opportunities.opportunities"],
         "masked_fields": []}


# ── 工具层：边界接线 ─────────────────────────────────────────────────────────

def test_query_data_boundary_masks_price_without_access(monkeypatch):
    """price_ok=False → 边界带 price 脱敏域（工具自建边界，不看同事 data_boundary）。"""
    from app.services import data_boundary
    seen = {}

    def fake_execute_read(sql, boundary, *, limit=50, **kw):
        seen["boundary"] = boundary
        return {"ok": True, "error": "", "columns": [], "rows": [], "row_count": 0}

    monkeypatch.setattr(data_boundary, "execute_read", fake_execute_read)
    token = _ctx(price_ok=False)
    try:
        tool_query_data({"sql": "SELECT 1"})
        assert seen["boundary"]["masked_fields"] == ["price"]
        assert seen["boundary"]["mode"] == "allow_read"
    finally:
        skill_tool_context.TOOL_CTX.reset(token)


def test_query_data_no_context_fails_closed_on_price(monkeypatch):
    """引擎路径空上下文：表照常走工具白名单，价格按最严口径脱敏。"""
    from app.services import data_boundary
    seen = {}

    def fake_execute_read(sql, boundary, *, limit=50, **kw):
        seen["boundary"] = boundary
        return {"ok": True, "error": "", "columns": [], "rows": [], "row_count": 0}

    monkeypatch.setattr(data_boundary, "execute_read", fake_execute_read)
    token = skill_tool_context.TOOL_CTX.set({})  # 引擎路径：无同事上下文
    try:
        out = tool_query_data({"sql": "SELECT 1"})
        assert out["ok"] is True
        assert seen["boundary"]["masked_fields"] == ["price"]  # 价格 fail closed
    finally:
        skill_tool_context.TOOL_CTX.reset(token)


def test_query_data_missing_sql():
    token = _ctx()
    try:
        out = tool_query_data({})
        assert out["ok"] is False and "sql" in out["error"]
    finally:
        skill_tool_context.TOOL_CTX.reset(token)


def test_query_data_whitelisted_table_executes(monkeypatch):
    from app.services import data_boundary
    calls = []

    def fake_execute_read(sql, boundary, *, limit=50, **kw):
        calls.append((sql, limit))
        return {"ok": True, "error": "", "columns": ["n"], "rows": [[1]],
                "row_count": 1, "truncated": False}

    monkeypatch.setattr(data_boundary, "execute_read", fake_execute_read)
    token = _ctx()
    try:
        out = tool_query_data({"sql": "SELECT count(*) AS n FROM opportunities.opportunities",
                               "limit": "30"})
        assert out["ok"] is True and out["rows"] == [[1]]
        assert calls == [("SELECT count(*) AS n FROM opportunities.opportunities", 30)]
    finally:
        skill_tool_context.TOOL_CTX.reset(token)


def test_query_data_bad_limit_falls_back():
    from app.services import data_boundary
    seen = {}

    def fake_execute_read(sql, boundary, *, limit=50, **kw):
        seen["limit"] = limit
        return {"ok": True, "columns": [], "rows": [], "row_count": 0}

    orig = data_boundary.execute_read
    data_boundary.execute_read = fake_execute_read
    # skill_chat 内 import 的是模块属性，patch 模块函数即可
    token = _ctx()
    try:
        tool_query_data({"sql": "SELECT 1", "limit": "abc"})
        assert seen["limit"] == 50
    finally:
        skill_tool_context.TOOL_CTX.reset(token)
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


# ── 数据查询规则下沉到工具描述（不再由 requirement_prompt 门控注入）─────────────

def test_data_rule_lives_in_query_data_tool_description():
    """data_rule 已进入 query_data 工具 schema；requirement_prompt 不再注入数据查询规则。"""
    from app.services import agent_tool_specs as ats
    desc = ats._TOOL_SPECS["query_data"]["description"]
    assert "information_schema" in desc and "只读 SELECT" in desc
    p = requirement_prompt({}, price_ok=True)
    assert "query_data" not in p and "information_schema" not in p
