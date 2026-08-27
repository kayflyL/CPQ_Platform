# -*- coding: utf-8 -*-
"""基准配置「机箱能力约束」消费链路单测（2026-08-08）：
PSU 档位收敛到机型支持范围（_clamp_psu_wattage / _infer_psu_wattage）、
CPU TDP 数据驱动（配件库 specs.tdp 优先于型号表兜底）。

跑法（backend 目录）：
  python -X utf8 -m pytest tests/test_base_config_capability.py -q
"""
from app.api.candidate_search import (
    _clamp_psu_wattage, _infer_psu_wattage, _estimate_system_load,
)


# ── PSU 档位收敛（基准配置 psu_wattages，如 ES22V3-P=[1300,1600,2000]）──
def test_clamp_psu_wattage_within_allowed():
    assert _clamp_psu_wattage("1300", [1300, 1600, 2000]) == "1300"   # 档内不变
    assert _clamp_psu_wattage("1600", [1300, 1600, 2000]) == "1600"


def test_clamp_psu_wattage_takes_next_higher():
    assert _clamp_psu_wattage("1800", [1300, 1600, 2000]) == "2000"   # 取 ≥ 推断值的最小档


def test_clamp_psu_wattage_over_limit_takes_max():
    assert _clamp_psu_wattage("2700", [1300, 1600, 2000]) == "2000"   # 超机型上限 → 最大档（宁高勿低）


def test_clamp_psu_wattage_unset_no_change():
    assert _clamp_psu_wattage("2700", None) == "2700"                # 机型未配档位 → 沿用全局
    assert _clamp_psu_wattage("2700", []) == "2700"
    assert _clamp_psu_wattage("2700", ["abc"]) == "2700"             # 脏档位列表安全失败


def test_infer_psu_wattage_clamped_by_model():
    # 8×高功耗 GPU 全局 tier=2700，但 ES22V3-P 只支持到 2000 → 收敛
    assert _infer_psu_wattage(8, high_tdp=True, allowed_wattages=[1300, 1600, 2000]) == "2000"
    # 未配机型档位 → 全局行为不变
    assert _infer_psu_wattage(8, high_tdp=True) == "2700"


def test_infer_psu_wattage_gpu1_high_tdp_default():
    # 1 张高功耗 GPU 不匹配任何 tier → no_gpu_wattage=1600（档内不变）
    assert _infer_psu_wattage(1, high_tdp=True, allowed_wattages=[1300, 1600, 2000]) == "1600"


# ── CPU TDP 数据驱动（配件库 specs.tdp 优先，9005 等新 SKU 不再低估）──
def test_estimate_system_load_uses_part_tdp_spec():
    rows = [
        {"category": "CPU", "name": "AMD EPYC 9755", "qty": 2, "specs": {"tdp": 500}},  # Turin 500W
        {"category": "CPU", "name": "AMD EPYC 9654", "qty": 1, "specs": None},          # 型号表兜底 360W
    ]
    assert _estimate_system_load(rows) == 260 + 1000 + 360


def test_estimate_system_load_fallback_map_when_no_spec():
    rows = [{"category": "CPU", "name": "AMD EPYC 9124", "qty": 1}]  # 无 specs → 型号表 200W
    assert _estimate_system_load(rows) == 260 + 200
