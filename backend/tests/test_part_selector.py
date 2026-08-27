# -*- coding: utf-8 -*-
"""part_selector.select_parts 结构化信号选件单测（stub 仓库/规则库，确定性）。"""
from app.services import part_selector as ps
from app.services import requirement_rule_catalog as rc


class _FakeRepo:
    _mu = {
        "CPU": [
            {"model": "AMD EPYC 9124", "price": 800.0, "currency": "RMB", "specs": {}},
            {"model": "Intel Xeon 8380", "price": 1200.0, "currency": "RMB", "specs": {}},
            {"model": "KH40000 32C", "price": 900.0, "currency": "RMB", "specs": {}},
        ],
        "Memory": [
            {"model": "16G DDR4 3200", "price": 1200.0, "currency": "RMB",
             "specs": {"Type": "DDR4", "Speed": "3200", "Capacity": "16G"}},
            {"model": "32G DDR5", "price": 2600.0, "currency": "RMB",
             "specs": {"Type": "DDR5", "Speed": "4800", "Capacity": "32G"}},
        ],
        "HDD/SSD": [
            {"model": "960G SATA", "price": 4000.0, "currency": "RMB",
             "specs": {"Capacity": "960 GB", "Type": "SATA", "Media": "SSD"}},
            {"model": "8T SATA", "price": 6000.0, "currency": "RMB",
             "specs": {"Capacity": "8 TB", "Type": "SATA", "Media": "HDD"}},
        ],
        "GPU": [
            {"model": "NVIDIA A100 80G", "price": 90000.0, "currency": "RMB",
             "specs": {"Capacity": "80G"}},
            {"model": "NVIDIA A800 80G", "price": 85000.0, "currency": "RMB",
             "specs": {"Capacity": "80G"}},
        ],
    }

    def __init__(self):
        self.closed = False

    def get_categories(self):
        return [{"category": k, "count": len(v)} for k, v in self._mu.items()]

    def get_by_category(self, category, search=""):
        rows = self._mu.get(category, [])
        if search:
            rows = [r for r in rows if search.lower() in r["model"].lower()]
        return rows

    def get_by_category_with_specs(self, category):
        return self._mu.get(category, [])

    def close(self):
        self.closed = True


def _stub_ctlg(monkeypatch):
    monkeypatch.setattr(ps, "KPRepository", _FakeRepo)
    monkeypatch.setattr(rc, "category_aliases", lambda *a, **k: {
        "CPU": ["CPU", "处理器"],
        "Memory": ["Memory", "内存"],
        "HDD/SSD": ["HDD", "SSD", "硬盘", "存储"],
        "GPU": ["GPU", "显卡"],
    })
    monkeypatch.setattr(rc, "part_selection_policy", lambda category_key=None, *a, **k: {
        "gpu": {"allow_capacity_fallback_when_model_missing": False,
                "check_capacity_after_model_match": True,
                "capacity_tolerance_ratio": 0.05},
        "drive": {"capacity_tolerance_ratio": 0.05},
    }.get(str(category_key).lower(), {}) if category_key else {})


def test_cpu_signal_lands_real_pn(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(categories=["CPU"], cpu_signal={"model": "Intel", "qty": 2})
    assert len(parts) == 1
    assert parts[0]["pn"] == "Intel Xeon 8380"
    assert parts[0]["qty"] == 2
    assert parts[0]["unmatched"] is False


def test_cpu_token_normalization_matches_short_model(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(categories=["CPU"], cpu_signal={"model": "AMD 9124", "qty": 1})
    assert len(parts) == 1
    assert parts[0]["pn"] == "AMD EPYC 9124"
    assert parts[0]["unmatched"] is False


def test_cpu_alias_rule_resolves_semantic_term(monkeypatch):
    _stub_ctlg(monkeypatch)
    monkeypatch.setattr(rc, "part_aliases", lambda *a, **k: {"兆芯": ["KH40000", "KH50000"]})
    parts = ps.select_parts(categories=["CPU"], cpu_signal={"model": "兆芯", "qty": 1})
    assert len(parts) == 1
    assert parts[0]["unmatched"] is False
    assert "KH40000" in parts[0]["pn"]


def test_memory_per_stick_lands_real_pn(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(
        categories=["Memory"],
        mem_signal={"type": "DDR5", "speed": 4800, "per_stick_gb": 32, "qty": 8},
    )
    assert parts[0]["pn"] == "32G DDR5"
    assert parts[0]["qty"] == 8
    assert parts[0]["unmatched"] is False


def test_cn_alias_matches(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(
        categories=["内存"],
        mem_signal={"type": "DDR5", "speed": 4800, "per_stick_gb": 32, "qty": 4},
    )
    assert parts[0]["category"] == "Memory"
    assert parts[0]["pn"] == "32G DDR5"
    assert parts[0]["unmatched"] is False


def test_drive_group_unmatched_is_whitebox(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(
        categories=["HDD/SSD"],
        drive_groups=[{"term": "12345G", "qty": 1, "kind": "NVMe"}],
    )
    assert parts and parts[0]["unmatched"] is True
    assert "12345G" in parts[0]["unmatched_reason"]


def test_list_kp_categories_returns_db_mapping(monkeypatch):
    monkeypatch.setattr(ps, "KPRepository", _FakeRepo)
    monkeypatch.setattr(rc, "category_aliases", lambda *a, **k: {
        "Memory": ["Memory", "内存"],
    })
    cats = ps.list_kp_categories()
    memory = next(c for c in cats if c["key"] == "Memory")
    assert memory["db_category"] == "Memory"


def test_model_match_tolerates_redundant_suffix():
    assert ps._model_match("LSI 9560 16i 8G缓存", "LSI 9560-16i")
    assert ps._model_match("RTX PRO 4500 Server 32G", "RTX 4500")
    assert ps._model_match("9560-16i", "LSI 9560-16i")


def test_memory_exact_speed_no_silent_drift(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(
        categories=["Memory"],
        mem_signal={"type": "DDR5", "speed": 5600, "per_stick_gb": 32, "qty": 8},
    )
    assert parts and parts[0]["unmatched"] is True
    assert "5600" in parts[0]["unmatched_reason"]


def test_gpu_model_token_lands_real_pn(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(
        categories=["GPU"],
        gpu_groups=[{"tokens": ["A800"], "qty": 8, "cap": "80G"}],
    )
    assert parts and parts[0]["pn"] == "NVIDIA A800 80G"
    assert parts[0]["unmatched"] is False
    assert parts[0]["spec_mismatch"] is False


def test_gpu_missing_model_does_not_fallback_by_capacity(monkeypatch):
    _stub_ctlg(monkeypatch)
    parts = ps.select_parts(
        categories=["GPU"],
        gpu_groups=[{"tokens": ["H100"], "qty": 8, "cap": "80G"}],
    )
    assert parts and parts[0]["unmatched"] is True
    assert "H100" in parts[0]["unmatched_reason"]
    assert parts[0]["pn"] == ""


def test_ground_raid_level_not_arbitrary_pick(monkeypatch):
    class _RaidRepo:
        def get_by_category_with_specs(self, category):
            return [{"model": "LSI 9560-16i", "price": 3000.0, "currency": "RMB", "specs": {}}]
    parts = ps._ground_raid(
        _RaidRepo(), "Raid card", [{"model": "RAID 0,1,10", "qty": 1}],
        lambda r: r[0] if r else None,
    )
    assert parts and parts[0]["unmatched"] is True
    assert "RAID 0/1/10" in parts[0]["unmatched_reason"]
