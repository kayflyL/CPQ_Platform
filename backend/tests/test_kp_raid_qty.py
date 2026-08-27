# -*- coding: utf-8 -*-
"""KP 配件选型回归：结构化信号经 select_parts 落地真实料号。"""
from app.services.part_selector import select_parts


def _raids(out):
    return [r for r in out if "raid" in (r.get("category") or "").lower() or "阵列" in (r.get("category") or "")]


def test_raid_qty_not_doubled():
    """单个显式 RAID 型号只出一条真实料号。"""
    out = select_parts(
        categories=["Raid card"],
        raid_groups=[{"model": "LSI 9361-8i", "qty": 1}],
    )
    raids = _raids(out)
    assert len(raids) == 1, f"RAID 应只出一条，实际 {len(raids)}: {raids}"
    assert raids[0]["qty"] == 1
    assert raids[0].get("unmatched") is not True
    assert "9361-8i" in (raids[0].get("pn") or "")


def test_raid_space_model_matches_hyphen_part():
    """LLM 输出空格型号时归一化到库内连字符料号。"""
    out = select_parts(
        categories=["Raid card"],
        raid_groups=[
            {"model": "LSI 9560 16i", "qty": 1},
            {"model": "LSI 9364 8i", "qty": 1},
        ],
    )
    raids = _raids(out)
    assert len(raids) == 2, f"RAID 应出两行，实际 {raids}"
    pns = {r.get("pn") or "" for r in raids}
    assert any("LSI 9560-16i" in pn for pn in pns)
    assert any("LSI 9364-8i" in pn for pn in pns)
    assert all(r.get("unmatched") is not True for r in raids)


def test_memory_per_stick_lands_real_pn():
    """显式 32G×8 内存信号应落地 8 条真实料号。"""
    out = select_parts(
        categories=["Memory"],
        mem_signal={"type": "DDR5", "speed": 4800, "per_stick_gb": 32, "qty": 8},
    )
    mems = [r for r in out if "mem" in (r.get("category") or "").lower()]
    assert mems, out
    assert mems[0]["qty"] == 8
    assert mems[0].get("unmatched") is not True
    assert "32G" in (mems[0].get("pn") or "")
