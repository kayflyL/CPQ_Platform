# -*- coding: utf-8 -*-
"""_kp_signals 品类/协议检测单测：词表来自规则库，这里锁定默认行为防回归。
跑法（backend 目录）：python -X utf8 -m pytest tests/test_kp_signals.py -q
"""
from app.api import candidate_search as cs


def _sig(monkeypatch, parts):
    monkeypatch.setattr(cs, "_load_psu_inference", lambda: {})
    return cs._kp_signals(parts)


def test_gpu_card_counts(monkeypatch):
    qty, kinds, high, tdp = _sig(monkeypatch, [{"category": "GPU Card", "name": "RTX 5090", "qty": 8, "specs": {"tdp": 350}}])
    assert qty == 8 and kinds == set() and high is False and tdp == 350.0


def test_hdd_defaults_sata(monkeypatch):
    qty, kinds, high, tdp = _sig(monkeypatch, [{"category": "HDD", "name": "SATA 8TB", "qty": 4}])
    assert qty == 0 and kinds == {"SATA"}


def test_nvme_and_sas_kinds(monkeypatch):
    qty, kinds, high, tdp = _sig(monkeypatch, [
        {"category": "SSD", "name": "NVMe 3.84T", "qty": 2},
        {"category": "SAS", "name": "SAS 12T", "qty": 6},
    ])
    assert qty == 0 and kinds == {"NVMe", "SAS"}


def test_gpu_cat_zh_and_drive(monkeypatch):
    qty, kinds, high, tdp = _sig(monkeypatch, [
        {"category": "显卡", "name": "AMD R9700", "qty": 2},
        {"category": "硬盘", "name": "SATA 4T", "qty": 4},
    ])
    assert qty == 2 and kinds == {"SATA"}


def test_non_drive_ignored(monkeypatch):
    qty, kinds, high, tdp = _sig(monkeypatch, [{"category": "内存", "name": "32G DDR5", "qty": 8}])
    assert qty == 0 and kinds == set() and high is False


def test_empty_no_signal(monkeypatch):
    qty, kinds, high, tdp = _sig(monkeypatch, [])
    assert qty == 0 and kinds == set()
