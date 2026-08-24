# -*- coding: utf-8 -*-
"""build_variant_signals 规则驱动单测：词表来自规则库，此处锁定默认行为防回归。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_variant_signals.py -q
"""
from app.api.candidate_search import build_variant_signals


def _sig(text, **ext):
    return build_variant_signals(ext, text)


def test_direct_signal_from_zh():
    s = _sig("4U 8卡 GPU 直通 服务器", categories=["GPU"])
    assert s["direct"] is True
    assert s["switch"] is False


def test_switch_signal_from_zh():
    s = _sig("用交换机", categories=[])
    assert s["switch"] is True


def test_storage_kinds_from_text():
    s = _sig("前置8*SATA 外加 SAS 盘 和 NVMe", categories=[])
    assert s["storage_kinds"] == {"SATA", "SAS", "NVMe"}


def test_storage_nvme_from_cat_aliases():
    s = _sig("存储服务器", categories=["NVMe"])
    assert "NVMe" in s["storage_kinds"]


def test_raid_via_category_and_word():
    s1 = _sig("RAID 0，1，10", categories=["Raid card"])
    assert s1["has_raid"] is True
    s2 = _sig("阵列卡", categories=[])
    assert s2["has_raid"] is True


def test_gpu_qty_fallback_groups():
    s = _sig("显卡 AMD R9700*8", categories=["GPU"], qty_map={}, gpu_groups=[{"qty": 8}])
    assert s["gpu_qty"] == 8


def test_has_config_quantities():
    s = _sig("CPU 8核*2 内存*4", categories=["CPU"])
    assert s["has_config_quantities"] is True


def test_has_cpu_signal():
    s = _sig("8核 32G", categories=["CPU"])
    assert s["has_cpu"] is True
