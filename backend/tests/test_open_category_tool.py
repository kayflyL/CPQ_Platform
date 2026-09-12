# -*- coding: utf-8 -*-
"""open_category（类目目录页）回归：只读导航 + 真话口径（2026-09-10）。

Mistral agentic search 的 navigate 类比：查之前先看「这个类目有哪些字段、值域长什么样」，
把盲试换成看着字段查。硬约束：只读——零去库写入、**不登记接地索引**，example_names 不是候选。
"""
import os
import sys

from app.services import part_selector, skill_tool_context, skill_tools_open

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CATS = {
    "GPU": [
        {"id": 1, "model": "A100 80G", "price": 90000.0, "currency": "RMB",
         "applicable": {"series": ["KR2280"]},
         "specs": {"Capacity": "80 GB", "Architecture": "Ampere"}},
        {"id": 2, "model": "L40S 48G", "price": 50000.0, "currency": "RMB",
         "applicable": {"series": ["KR2380"]},
         "specs": {"Capacity": "48 GB", "Architecture": "Ada Lovelace"}},
    ],
    "NIC": [
        {"id": 3, "model": "X710 4port", "price": 3000.0, "currency": "RMB",
         "applicable": {"series": ["Other"]},
         "specs": {"Link Speed": "10G", "Ports": "4"}},
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
                        lambda: {"显卡": "GPU", "网卡": "NIC"})
    skill_tool_context.TOOL_CTX.set({
        "task_active": True, "engine": {}, "kp_rows_ctx": [],
        "price_ok": True, "kp_series": series, "save": lambda: None})


def test_category_schema_alias_and_readonly(monkeypatch):
    """中文别名 → 库内类目；回字段画像；且零写入（example_names 不是候选）。"""
    _wire(monkeypatch)
    r = skill_tools_open.tool_open_category({"category": "显卡"})
    assert r["ok"] is True and r["mode"] == "category"
    assert r["db_category"] == "GPU" and r["category"] == "显卡"
    assert r["parts_in_library"] == 2 and "显卡" in r["aliases"]
    fields = {f["key"]: f for f in r["spec_fields"]}
    assert fields["Capacity"]["kind"] == "numeric"
    assert fields["Capacity"]["parts"] == 2 and fields["Capacity"]["distinct"] == 2
    assert fields["Capacity"]["values"] == ["80 GB", "48 GB"]
    assert fields["Architecture"]["kind"] == "text"
    assert r["price_range"] == {"min": 50000.0, "max": 90000.0, "currency": "RMB"}
    assert r["example_names"]
    assert set(skill_tool_context.TOOL_CTX.get()) == {
        "task_active", "engine", "kp_rows_ctx", "price_ok", "kp_series", "save"}


def test_unknown_and_empty_category_list_real_ones(monkeypatch):
    """类目猜错 / 不传：把库内真实类目与别名摆出来，不让模型继续猜词。"""
    _wire(monkeypatch)
    r = skill_tools_open.tool_open_category({"category": "不存在"})
    assert r["ok"] is False and r["error"] == "unknown_category"
    assert {c["category"] for c in r["categories"]} == {"GPU", "NIC"}
    r2 = skill_tools_open.tool_open_category({})
    assert r2["ok"] is False and r2["error"] == "invalid_args" and r2["categories"]


def test_series_scope_disclosed_not_silently_filtered(monkeypatch):
    """类目件数与「适配当前平台的件数」分开报；全类目不适配时必须点明，措辞不许含糊。"""
    _wire(monkeypatch, series="KR2280")
    r = skill_tools_open.tool_open_category({"category": "GPU"})
    assert r["parts_in_library"] == 2 and r["parts_in_series"] == 1
    assert r["series"] == "KR2280"
    r2 = skill_tools_open.tool_open_category({"category": "网卡"})
    assert r2["parts_in_library"] == 1 and r2["parts_in_series"] == 0
    assert "适配当前平台" in r2["note"] and "的件数：0" in r2["note"]
    assert "库内共 1 件" in r2["note"]


def test_price_hidden_when_price_not_ok(monkeypatch):
    _wire(monkeypatch)
    skill_tool_context.TOOL_CTX.get()["price_ok"] = False
    r = skill_tools_open.tool_open_category({"category": "GPU"})
    assert r["ok"] is True and "price_range" not in r


def test_rejects_outside_task(monkeypatch):
    _wire(monkeypatch)
    skill_tool_context.TOOL_CTX.set({"task_active": False})
    r = skill_tools_open.tool_open_category({"category": "GPU"})
    assert r["ok"] is False and r["error"] == "task_not_active"


def test_spec_profile_sorts_by_coverage_and_flags_numeric():
    prof, all_keys = skill_tools_open._spec_profile([
        {"specs": {"A": "1", "B": "x"}},
        {"specs": {"A": "2"}},
    ])
    assert all_keys == ["A", "B"]
    assert [p["key"] for p in prof] == ["A", "B"]
    assert prof[0]["kind"] == "numeric" and prof[1]["kind"] == "text"
    assert prof[0]["parts"] == 2 and prof[0]["distinct"] == 2
