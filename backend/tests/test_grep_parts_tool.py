# -*- coding: utf-8 -*-
"""grep_parts（定向搜索）回归：字面/正则扫全库 + 只读口径（2026-09-10）。

Mistral agentic search 的 grep 类比：拿一个词看它出现在哪，再顺着去查找候选。
硬约束：只读——零写入、**不登记接地索引**，matches 不是候选（锁定仍须 query_parts）。
"""
import os
import sys

from app.services import part_selector, skill_tool_context, skill_tools_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CATS = {
    "GPU": [
        {"id": 1, "model": "A100 80G", "applicable": {"series": ["KR2280"]},
         "specs": {"Capacity": "80 GB", "Interface": "PCIe 5.0 x16"}},
        {"id": 2, "model": "L40S 48G", "applicable": {"series": ["KR2380"]},
         "specs": {"Capacity": "48 GB", "Interface": "PCIe Gen4"}},
    ],
    "Raid card": [
        {"id": 3, "model": "9361-16i", "applicable": {},
         "specs": {"Cache": "2G", "Interface": "PCIe 3.0"}},
    ],
}


class _FakeRepo:
    def __init__(self, *_a, **_k):
        pass

    def get_categories(self):
        return [{"category": c, "id": i, "count": len(v)}
                for i, (c, v) in enumerate(_CATS.items())]

    def get_by_category_with_specs(self, category):
        return [dict(r) for r in _CATS.get(category, [])]

    def close(self):
        pass


def _wire(monkeypatch, series=""):
    monkeypatch.setattr(part_selector, "KPRepository", _FakeRepo)
    monkeypatch.setattr(part_selector, "_category_aliases",
                        lambda: {"显卡": "GPU", "阵列卡": "Raid card"})
    skill_tool_context.TOOL_CTX.set({
        "task_active": True, "engine": {}, "kp_rows_ctx": [],
        "price_ok": True, "kp_series": series, "save": lambda: None})


def test_literal_terms_hit_name_and_specs(monkeypatch):
    _wire(monkeypatch)
    r = skill_tools_open.tool_grep_parts({"pattern": "9361"})
    assert r["ok"] is True and r["mode"] == "grep"
    assert r["total"] == 1 and r["parts_scanned"] == 3
    assert r["matches"][0]["category"] == "Raid card"
    assert r["matches"][0]["hits"][0]["field"] == "name"
    assert r["matched_categories"] == {"Raid card": 1}
    # 多词 = 任一命中（OR）
    r2 = skill_tools_open.tool_grep_parts({"pattern": "80G 48G", "fields": "name"})
    assert r2["total"] == 2 and [m["name"] for m in r2["matches"]] == ["A100 80G", "L40S 48G"]


def test_field_scope_and_spec_key_restriction(monkeypatch):
    _wire(monkeypatch)
    r = skill_tools_open.tool_grep_parts({"pattern": "PCIe", "fields": "specs"})
    assert r["total"] == 3
    assert all(h["field"] == "Interface" for m in r["matches"] for h in m["hits"])
    # 只搜名称：specs 里的 PCIe 不该命中
    assert skill_tools_open.tool_grep_parts({"pattern": "PCIe", "fields": "name"})["total"] == 0
    r2 = skill_tools_open.tool_grep_parts({"pattern": "2", "fields": "specs", "spec_key": "Cache"})
    assert r2["total"] == 1 and r2["matches"][0]["part_id"] == "3"


def test_regex_mode_and_invalid_pattern(monkeypatch):
    _wire(monkeypatch)
    r = skill_tools_open.tool_grep_parts({"pattern": "[0-9]+G", "fields": "name", "regex": True})
    assert r["total"] == 2
    bad = skill_tools_open.tool_grep_parts({"pattern": "(", "regex": True})
    assert bad["ok"] is False and bad["error"] == "invalid_args"
    empty = skill_tools_open.tool_grep_parts({})
    assert empty["ok"] is False and empty["error"] == "invalid_args"


def test_paging_reports_true_total(monkeypatch):
    _wire(monkeypatch)
    p1 = skill_tools_open.tool_grep_parts({"pattern": "G", "fields": "name", "limit": 1})
    assert p1["total"] == 2 and len(p1["matches"]) == 1
    assert p1["truncated"] is True and p1["next_offset"] == 1
    p2 = skill_tools_open.tool_grep_parts({"pattern": "G", "fields": "name", "limit": 1, "offset": 1})
    assert len(p2["matches"]) == 1 and p2["truncated"] is False and p2["next_offset"] is None
    assert p1["matches"][0]["part_id"] != p2["matches"][0]["part_id"]


def test_category_scope_alias_and_unknown(monkeypatch):
    _wire(monkeypatch)
    r = skill_tools_open.tool_grep_parts({"pattern": "PCIe", "category": "阵列卡"})
    assert r["total"] == 1 and r["categories_scanned"] == 1
    bad = skill_tools_open.tool_grep_parts({"pattern": "x", "category": "不存在"})
    assert bad["ok"] is False and bad["error"] == "unknown_category"
    assert bad["categories"]


def test_readonly_and_suggest_next_closes_loop(monkeypatch):
    """只读（零写入），但必须给下一步：拿命中的词去 query_parts 取候选。"""
    _wire(monkeypatch)
    r = skill_tools_open.tool_grep_parts({"pattern": "9361"})
    assert set(skill_tool_context.TOOL_CTX.get()) == {
        "task_active", "engine", "kp_rows_ctx", "price_ok", "kp_series", "save"}
    assert r["suggest_next"] == {"tool": "query_parts",
                                 "parameters": {"category": "Raid card", "keywords": "9361"}}
    # 零命中：只说清「字面匹配、不做语义等价」；怎么补救由左栏规则说
    z = skill_tools_open.tool_grep_parts({"pattern": "大显存"})
    assert z["total"] == 0 and "语义等价" in z["message"]
    assert "open_category" not in z["message"]


def test_series_scope_is_marked_not_hidden(monkeypatch):
    _wire(monkeypatch, series="KR2280")
    r = skill_tools_open.tool_grep_parts({"pattern": "G", "fields": "name", "limit": 5})
    flags = {m["name"]: m["in_scope"] for m in r["matches"]}
    assert flags == {"A100 80G": True, "L40S 48G": False}


def test_rejects_outside_task(monkeypatch):
    _wire(monkeypatch)
    skill_tool_context.TOOL_CTX.set({"task_active": False})
    r = skill_tools_open.tool_grep_parts({"pattern": "x"})
    assert r["ok"] is False and r["error"] == "task_not_active"
