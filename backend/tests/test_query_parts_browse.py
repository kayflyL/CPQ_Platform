# -*- coding: utf-8 -*-
"""query_parts 双模式单测（2026-10-11 流程锁换权限锁）：

流程外=日常浏览模式（只读检索、series 置空、limit 收窄、rows 拒绝、price 随 price_ok）；
流程内=原选配模式行为不变（rows 批量、行清单状态回传、limit 上限 20）。
hybrid_search 打桩，不碰库。
"""
from app.services.skill_tool_context import TOOL_CTX
from app.services.skill_tools_kp import tool_query_parts


def _patch_hybrid(monkeypatch, capture):
    def fake(category, *, text="", spec_filters=None, series="", limit=8,
             offset=0, price_ok=True, mode="query", _repo=None):
        capture.update(category=category, text=text, series=series, limit=limit,
                       offset=offset, price_ok=price_ok, mode=mode)
        return {"ok": True, "rows": [
            {"part_id": "p1", "name": "480G SSD", "price": 329.0,
             "specs": {"Capacity": "480G", "Media": "SSD"}, "match": ["lex"]}],
            "total": 1, "next_offset": None, "truncated": False,
            "spec_keys": ["Capacity", "Media"], "source": "kp_library/part_query"}
    monkeypatch.setattr("app.services.part_search.hybrid_search", fake)


def test_browse_mode_without_task(monkeypatch):
    cap = {}
    _patch_hybrid(monkeypatch, cap)
    TOOL_CTX.set({"role_key": "assistant", "price_ok": False})
    r = tool_query_parts({"category": "SSD", "keywords": "480G"})
    assert r["ok"] is True and r["mode"] == "browse"
    assert cap["series"] == "" and cap["price_ok"] is False
    assert cap["limit"] == 6 and cap["mode"] == "query"
    row = r["results"][0]
    assert "price" not in row, "无价权限：price 字段整个不出现"
    assert row["specs"] == {"Capacity": "480G", "Media": "SSD"}
    assert "rows" not in r, "浏览模式不带回流程行清单状态"


def test_browse_limit_capped_at_10(monkeypatch):
    cap = {}
    _patch_hybrid(monkeypatch, cap)
    TOOL_CTX.set({"price_ok": True})
    r = tool_query_parts({"category": "SSD", "limit": 50})
    assert cap["limit"] == 10
    assert r["results"][0]["price"] == 329.0, "price_ok 为真时候选带价"


def test_browse_rejects_rows_mode(monkeypatch):
    _patch_hybrid(monkeypatch, {})
    TOOL_CTX.set({"price_ok": False})
    r = tool_query_parts({"rows": "all"})
    assert r["ok"] is False and r["error"] == "rows_only_in_task"


def test_browse_requires_category():
    TOOL_CTX.set({"price_ok": False})
    r = tool_query_parts({"keywords": "480G"})
    assert r["ok"] is False and r["error"] == "invalid_args"


def test_task_mode_keeps_flow_semantics(monkeypatch):
    cap = {}
    _patch_hybrid(monkeypatch, cap)
    TOOL_CTX.set({"task_active": True, "price_ok": True, "engine": {}})
    r = tool_query_parts({"category": "SSD", "limit": 50})
    assert r["ok"] is True and r["mode"] == "task"
    assert cap["limit"] == 20, "流程内 limit 上限仍为 20"
    assert r["rows"] == [], "行清单状态照旧回传（空任务=空行）"
