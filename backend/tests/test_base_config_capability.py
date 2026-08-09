# -*- coding: utf-8 -*-
"""基准配置「机箱能力约束」消费链路单测（2026-08-08）：
PSU 档位收敛到机型支持范围（_clamp_psu_wattage / _infer_psu_wattage）、
CPU TDP 数据驱动（配件库 specs.tdp 优先于型号表兜底）、
内存容量反推按机型通道数/条数上限选（_pick_memory_part target/max）。

跑法（backend 目录）：
  python -X utf8 -m pytest tests/test_base_config_capability.py -q
"""
from app.api.candidate_search import (
    _clamp_psu_wattage, _infer_psu_wattage, _estimate_system_load, _pick_memory_part,
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


def _mem_parts(*caps):
    return [{"model": f"{c}G DDR5 RDIMM", "price": 10 * c, "currency": "RMB", "matched_spec": f"{c}G"}
            for c in caps]


def _pick(parts):
    return min(parts, key=lambda p: p["price"])


# ── 内存容量反推：目标条数/上限按机型通道数驱动（EPYC 12ch/路 → 双路 24）──
def test_pick_memory_old_behavior_target_8():
    parts = _mem_parts(64, 32, 16)
    row = _pick_memory_part(parts, {"total_gb": 768}, _pick)
    assert row["qty"] == 12 and row["matched_spec"].endswith("64G")   # 旧默认：目标 8 → 64G×12


def test_pick_memory_target_24_by_channels():
    parts = _mem_parts(64, 32, 16)
    row = _pick_memory_part(parts, {"total_gb": 768}, _pick, target_sticks=24, max_sticks=24)
    assert row["qty"] == 24 and row["matched_spec"].endswith("32G")   # 双路 24 通道 → 32G×24


def test_pick_memory_max_sticks_respected():
    # total=800：32G×25 超 24 上限 → 该容量跳过，退回 64G×13（≤24）
    parts = _mem_parts(64, 32)
    row = _pick_memory_part(parts, {"total_gb": 800}, _pick, target_sticks=24, max_sticks=24)
    assert row["qty"] == 13 and row["matched_spec"].endswith("64G")
