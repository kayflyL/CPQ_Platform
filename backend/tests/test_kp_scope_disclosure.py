# -*- coding: utf-8 -*-
"""取件工具的作用域真话回归（Step 7 护栏）。

机型锁定后候选池只剩「适配该机型平台」的料（_SeriesScopedRepo 在取数边界过滤）。
这会带来一个危险的误读：**「库里有、但不适配当前平台」被说成「库里没有」**，
AI 于是拿着错误前提去问客户（实测：兆芯 KH50000 只适配 Polaris，机型平台被推断成
Orion 后，每一轮都在问「要不要换成 AMD」）。

本文件锁住：作用域内零命中 ≠ 库里没有——必须把被平台挡住的料与它们适配的平台如实报出。
"""
from app.services import skill_tools_kp
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.data_tools import part_query, part_recall, _scope_blocked

ZX = {"id": 128, "model": "KH50000 96C", "price": 12000.0, "currency": "RMB",
      "specs": {"Cores": "96", "Type": "KH50000"},
      "applicable": {"series": ["Polaris"]}}


class _StubRepo:
    """假配件库：只有一件兆芯 CPU，且只适配 Polaris。"""

    def __init__(self, rows):
        self._rows = list(rows)

    def get_categories(self):
        return [{"category": "CPU", "count": len(self._rows)}]

    def get_by_category_with_specs(self, category):
        return list(self._rows)

    def close(self):
        pass


def test_scope_blocked_is_silent_when_no_scope():
    assert _scope_blocked(lambda: {"rows": [ZX]}, "") == {}


def test_scope_blocked_is_silent_when_library_really_has_nothing():
    assert _scope_blocked(lambda: {"rows": []}, "Orion") == {}


def test_part_query_says_nothing_instead_of_library_has_none():
    """平台不匹配时：别报「库里没有」，要报「库里有，但只适配 Polaris」。"""
    res = part_query("CPU", keywords="50000", series="Orion", _repo=_StubRepo([ZX]))
    assert res["ok"] is True
    assert res["rows"] == [], "不适配当前平台的料不该进候选池"
    assert res["out_of_scope"][0]["name"] == "KH50000 96C"
    assert res["out_of_scope"][0]["applicable_series"] == ["Polaris"]
    assert "Polaris" in res["scope_note"]
    assert "不是「库里没有」" in res["scope_note"]


def test_part_query_returns_part_when_platform_matches():
    res = part_query("CPU", keywords="50000", series="Polaris", _repo=_StubRepo([ZX]))
    assert [r["name"] for r in res["rows"]] == ["KH50000 96C"]
    assert "out_of_scope" not in res


def test_part_query_without_scope_returns_part():
    res = part_query("CPU", keywords="50000", _repo=_StubRepo([ZX]))
    assert [r["name"] for r in res["rows"]] == ["KH50000 96C"]
    assert "out_of_scope" not in res


def test_part_recall_also_discloses_out_of_scope():
    """按行召回同样不许静默丢数据，并要带出该料适配的平台。"""
    res = part_recall("CPU", desc="2颗兆芯50000 96C", series="Orion", _repo=_StubRepo([ZX]))
    assert res["rows"] == []
    assert res["out_of_scope"][0]["applicable_series"] == ["Polaris"]
    assert res["scope_note"]


def test_zero_reason_reports_scope_block_instead_of_missing():
    """行批量召回里，零命中的 reason 必须说真话（否则大脑照着假前提追问）。"""
    from app.services.skill_tools_kp import _zero_reason
    q = part_recall("CPU", desc="2颗兆芯50000 96C", series="Orion", _repo=_StubRepo([ZX]))
    reason = _zero_reason("CPU", q)
    assert "Polaris" in reason
    assert "库内无精确匹配" not in reason
