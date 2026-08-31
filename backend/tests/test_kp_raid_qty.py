# -*- coding: utf-8 -*-
"""KP 配件候选检索回归：引擎只检索候选池，语义选型交还 AI 角色。

select_parts 不再做型号/规格匹配，只把结构化信号转成「交由 AI 选型」的缺口行；
候选池由 retrieve_part_candidates 返回（真实库内料号），并断言目录确实存在目标件。
"""
from app.services.part_selector import retrieve_part_candidates, select_parts


def _raids(out):
    return [r for r in out if "raid" in (r.get("category") or "").lower() or "阵列" in (r.get("category") or "")]


def _catalogue_models(*categories):
    pools = retrieve_part_candidates(categories=list(categories))
    models = set()
    for rows in pools.values():
        for c in rows:
            models.add(str(c.get("model") or ""))
    return models


def test_raid_qty_not_doubled():
    """单个显式 RAID 型号只出一条「交由 AI 选型」缺口行；目录含 LSI 9361-8i 候选。"""
    out = select_parts(categories=["Raid card"], raid_groups=[{"model": "LSI 9361-8i", "qty": 1}])
    raids = _raids(out)
    assert len(raids) == 1, f"RAID 应只出一条，实际 {len(raids)}: {raids}"
    assert raids[0]["qty"] == 1
    assert raids[0].get("unmatched") is True
    models = _catalogue_models("Raid card")
    assert any("LSI 9361-8i" in m for m in models), f"目录缺 LSI 9361-8i: {sorted(models)[:5]}"


def test_raid_space_model_matches_hyphen_part():
    """候选池含连字符料号；select_parts 为每个组各产一行缺口，不再静态归一化。"""
    out = select_parts(categories=["Raid card"], raid_groups=[
        {"model": "LSI 9560 16i", "qty": 1},
        {"model": "LSI 9364 8i", "qty": 1},
    ])
    raids = _raids(out)
    assert len(raids) == 2, f"RAID 应出两行缺口，实际 {raids}"
    assert all(r.get("unmatched") for r in raids)
    models = _catalogue_models("Raid card")
    assert any("LSI 9560-16i" in m for m in models)
    assert any("LSI 9364-8i" in m for m in models)


def test_memory_per_stick_lands_real_pn():
    """显式 32G×8 内存信号转成缺口行；目录含 32G DDR5 候选。"""
    out = select_parts(categories=["Memory"],
                       mem_signal={"type": "DDR5", "speed": 4800, "per_stick_gb": 32, "qty": 8})
    mems = [r for r in out if "mem" in (r.get("category") or "").lower()]
    assert mems, out
    assert mems[0]["qty"] == 8
    assert mems[0].get("unmatched") is True
    models = _catalogue_models("Memory")
    assert any("32G" in m and "DDR5" in m.upper() for m in models), f"目录缺 32G DDR5: {sorted(models)[:5]}"
