# -*- coding: utf-8 -*-
"""基准配置「机箱能力约束」消费链路单测（2026-09-01）：
PSU 档位收敛到机型物理支持范围（_clamp_psu_wattage）。功耗推断已移除，
引擎只按 AI/人工传入值收敛到 baseline.psu_wattages。

跑法（backend 目录）：
  python -X utf8 -m pytest tests/test_base_config_capability.py -q
"""
from app.services.plan_builder import _clamp_psu_wattage


def test_clamp_psu_wattage_within_allowed():
    assert _clamp_psu_wattage("1300", [1300, 1600, 2000]) == "1300"   # 档内不变
    assert _clamp_psu_wattage("1600", [1300, 1600, 2000]) == "1600"


def test_clamp_psu_wattage_takes_next_higher():
    assert _clamp_psu_wattage("1800", [1300, 1600, 2000]) == "2000"   # 取 ≥ 给定值的最小档


def test_clamp_psu_wattage_over_limit_takes_max():
    assert _clamp_psu_wattage("2700", [1300, 1600, 2000]) == "2000"   # 超机型上限 → 最大档（宁高勿低）


def test_clamp_psu_wattage_unset_no_change():
    assert _clamp_psu_wattage("2700", None) == "2700"                # 机型未配档位 → 沿用全局
    assert _clamp_psu_wattage("2700", []) == "2700"
    assert _clamp_psu_wattage("2700", ["abc"]) == "2700"             # 脏档位列表安全失败
