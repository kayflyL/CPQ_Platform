# -*- coding: utf-8 -*-
"""part_selector.select_parts 干净版选件单测（stub 仓库/规则库，确定性）。
跑法（backend 目录）：python -X utf8 -m pytest tests/test_part_selector.py -q
"""
from app.services import part_selector as ps
from app.services import requirement_rule_catalog as rc


class _FakeRepo:
    _mu = {"CPU": [("AMD EPYC 9124", 800.0), ("Intel Xeon 8380", 1200.0)],
           "Memory": [("16G DDR4 3200", 1200.0), ("32G DDR5", 2600.0)],
           "HDD/SSD": [("960G SATA", 4000.0), ("8T SATA", 6000.0)]}

    def __init__(self):
        self.closed = False

    def get_categories(self):
        return [{"category": k} for k in self._mu]

    def get_latest_prices(self, search="", category="", sort_by="", sort_order="",
                          include_record_count=False):
        rows = self._mu.get(category, [])
        if search:
            rows = [r for r in rows if search.lower() in r[0].lower()]
        return [{"model": n, "price": p, "currency": "RMB", "note": ""} for n, p in rows]

    def close(self):
        self.closed = True


def _stub_ctlg(monkeypatch):
    monkeypatch.setattr(ps, "KPRepository", _FakeRepo)
    monkeypatch.setattr(rc, "category_aliases", lambda *a, **k: {
        "CPU": ["CPU"], "Memory": ["Memory"], "HDD/SSD": ["HDD/SSD"]})


def test_explicit_categories_and_qty(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(categories=["CPU", "Memory"], qty_map={"CPU": 2, "Memory": 8})
    assert [p["category"] for p in parts] == ["CPU", "Memory"]
    assert parts[0]["pn"] == "AMD EPYC 9124"  # min_price
    assert parts[0]["qty"] == 2 and parts[1]["qty"] == 8
    assert parts[0]["unmatched"] is False


def test_search_narrows(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(categories=["CPU"], search="Intel")
    assert len(parts) == 1 and parts[0]["pn"] == "Intel Xeon 8380"


def test_infer_from_type(monkeypatch):
    monkeypatch.setattr(ps, "KPRepository", _FakeRepo)
    monkeypatch.setattr(rc, "type_packages", lambda *a, **k: [
        {"type_keyword": "AI", "categories": ["CPU", "GPU"], "mandatory_gpu": True}])
    monkeypatch.setattr(rc, "conditional_kp_categories", lambda *a, **k: {
        "GPU": {"package_flag": "mandatory_gpu"}})
    monkeypatch.setattr(rc, "category_aliases", lambda *a, **k: {
        "CPU": ["CPU"], "GPU": ["GPU"]})
    parts = ps.select_parts(server_type_name="AI 推理服务器")
    assert "CPU" in [p["category"] for p in parts]
