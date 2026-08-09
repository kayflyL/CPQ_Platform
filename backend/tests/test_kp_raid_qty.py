# -*- coding: utf-8 -*-
"""KP RAID 数量回归：显式 RAID 型号不因 stage-1 关键词命中 + raid_groups 双路径而双计 qty。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.api.candidate_search import pick_kp_parts


def test_raid_qty_not_doubled():
    """需求 'RAID: 2GB缓存,接口数8个' + 显式模型 9361-8i → 只出一条 LSI 9361-8i ×1。"""
    out = pick_kp_parts(
        ["CPU", "Memory", "HDD/SSD", "GPU", "Network(NIC) requirement", "Raid Card"],
        ["9354", "9361-8i"],
        requirement_text="8卡服务器 RAID:Raid_2GB缓存,支持接口数8个",
        qty_map={"CPU": 2},
        mem_signal={"type": "DDR5", "speed": 4800, "total_gb": 256},
        mem_groups=[{"term": "32G", "qty": 8}],
        gpu_groups=[{"tokens": ["R9700"], "qty": 8, "cap": 32}],
        drive_groups=[{"term": "480G", "qty": 2, "kind": "SATA"}, {"term": "1024G", "qty": 2, "kind": None}],
        raid_groups=[{"model": "LSI 9361-8i", "qty": 1}],
        platform_series="Orion",
    )
    raids = [r for r in out if "raid" in (r.get("category") or "").lower()]
    assert len(raids) == 1, f"RAID 应只出一条，实际 {len(raids)}: {raids}"
    assert raids[0]["qty"] == 1, f"RAID qty 应为 1，实际 {raids[0]['qty']}"
    assert "9361" in (raids[0]["name"] or "")


def test_memory_total_resolves_sticks():
    """256GB 总量 + 8 通道 → 8×32G（LLM 提议与 merge 联动后，pick 出的内存条数正确）。"""
    out = pick_kp_parts(
        ["CPU", "Memory"],
        ["9354"],
        requirement_text="256GB DDR5-4800",
        qty_map={"CPU": 2},
        mem_signal={"type": "DDR5", "speed": 4800, "total_gb": 256},
        mem_groups=[{"term": "32G", "qty": 8}],
        platform_series="Orion",
    )
    mems = [r for r in out if "mem" in (r.get("category") or "").lower()]
    assert mems and mems[0]["qty"] == 8
