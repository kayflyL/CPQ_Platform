# -*- coding: utf-8 -*-
"""盘件规格属性替代：_cap_to_gb / _drive_spec_substitute / _pick_drive_groups。

背景（2026-08-03）：需求容量在 KP 库没有同名件时（如 1.6T），之前直接 unmatched；
现在按 Capacity/Type 规格属性数值选替代件（同容量等级 → 够用最小 → 最接近），
BOM 标注「替代」，仍无才 unmatched。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_drive_spec_substitute.py -q
"""
import pytest

from app.api.candidate_search import (
    _cap_to_gb,
    _drive_spec_substitute,
    _gb_label,
    _part_capacity_gb,
    _part_type_matches,
    _pick_drive_groups,
)

_MIN_PRICE = lambda parts: min(parts, key=lambda p: p.get("price") or 0)


class FakeRepo:
    """最小 fake：get_by_category（名字搜）+ get_by_category_with_specs（带规格）。"""

    def __init__(self, parts):
        self.parts = parts

    def get_by_category(self, category, search=""):
        out = []
        for pt in self.parts:
            if pt.get("category") != category:
                continue
            if search and search.lower() not in pt["model"].lower():
                continue
            out.append({"model": pt["model"], "price": pt.get("price", 0.0),
                        "currency": pt.get("currency", "RMB")})
        return out

    def get_by_category_with_specs(self, category):
        return [{"model": pt["model"], "price": pt.get("price", 0.0),
                 "currency": pt.get("currency", "RMB"),
                 "specs": dict(pt.get("specs") or {})}
                for pt in self.parts if pt.get("category") == category]


def _part(model, price=100.0, specs=None, category="HDD/SSD"):
    return {"model": model, "price": price, "category": category, "specs": specs or {}}


# ============================================================
# _cap_to_gb / _gb_label —— 容量数值换算（单位感知）
# ============================================================

def test_cap_to_gb_units():
    assert _cap_to_gb("960G") == 960
    assert _cap_to_gb("960 GB") == 960
    assert _cap_to_gb("1.92T") == 1966
    assert _cap_to_gb("1.92 TB") == 1966
    assert _cap_to_gb("7.68T") == 7864
    assert _cap_to_gb("480") == 480
    assert _cap_to_gb("") is None
    assert _cap_to_gb(None) is None
    assert _cap_to_gb("SATA SSD") is None


def test_gb_label():
    assert _gb_label(960) == "960G"
    assert _gb_label(1966) == "1.92T"
    assert _gb_label(1024) == "1T"


# ============================================================
# _part_capacity_gb / _part_type_matches —— 件属性提取
# ============================================================

def test_part_capacity_prefers_spec_then_name():
    p = _part("3.84T NVME SSD Gen4", specs={"Type": "NVMe"})   # 无 Capacity 规格
    assert _part_capacity_gb(p) == 3932                          # 从名字解析
    p2 = _part("企业盘", specs={"Capacity": "1.92 TB", "Type": "SATA"})
    assert _part_capacity_gb(p2) == 1966


def test_part_type_matches_spec_authoritative():
    assert _part_type_matches(_part("1.92T NVME SSD", specs={"Type": "NVMe"}), "NVMe")
    assert not _part_type_matches(_part("1.92T NVME SSD", specs={"Type": "NVMe"}), "SATA")
    # 无 Type 规格 → 回落名字
    assert _part_type_matches(_part("1.92T SATA SSD 读取密集型"), "SATA")
    assert not _part_type_matches(_part("1.92T SATA SSD 读取密集型"), "NVMe")
    assert _part_type_matches(_part("1.92T SATA SSD"), None)     # 无接口要求 → 全过


# ============================================================
# _drive_spec_substitute —— 数值容量替代链
# ============================================================

def test_substitute_same_capacity_class():
    repo = FakeRepo([_part("1T SATA SSD", specs={"Capacity": "1 TB", "Type": "SATA"}),
                     _part("2T SATA HDD", specs={"Capacity": "2 TB", "Type": "SATA"})])
    subs = _drive_spec_substitute(repo, "HDD/SSD", "960G", "SATA")
    assert len(subs) == 1 and "1T" in subs[0]["model"]          # 960G ≈ 1T 同等级


def test_substitute_smallest_over_demand():
    # 1.6T 需求，库无 1.6T → 取容量≥需求的最小件（1.92T，而非 2T/3.84T）
    repo = FakeRepo([_part("3.84T SATA SSD", specs={"Capacity": "3.84 TB", "Type": "SATA"}),
                     _part("2T SATA SSD", specs={"Capacity": "2 TB", "Type": "SATA"}),
                     _part("1.92T SATA SSD", specs={"Capacity": "1.92 TB", "Type": "SATA"})])
    subs = _drive_spec_substitute(repo, "HDD/SSD", "1.6T", "SATA")
    assert subs and "1.92T" in subs[0]["model"]


def test_substitute_largest_under_within_80pct():
    # 960G 需求只有 480G/800G → 取最接近的 800G（≥80% 需求）
    repo = FakeRepo([_part("480G SATA SSD", specs={"Capacity": "480 GB", "Type": "SATA"}),
                     _part("800G SATA SSD", specs={"Capacity": "800 GB", "Type": "SATA"})])
    subs = _drive_spec_substitute(repo, "HDD/SSD", "960G", "SATA")
    assert subs and "800G" in subs[0]["model"]


def test_substitute_respects_interface():
    repo = FakeRepo([_part("1.92T SATA SSD", specs={"Capacity": "1.92 TB", "Type": "SATA"}),
                     _part("1.92T NVME SSD", specs={"Capacity": "1.92 TB", "Type": "NVMe"})])
    subs = _drive_spec_substitute(repo, "HDD/SSD", "1.6T", "NVMe")
    assert subs and "NVME" in subs[0]["model"].upper()


def test_substitute_no_capacity_data_returns_empty():
    repo = FakeRepo([_part("SATA 企业盘", price=50.0)])          # 无规格无容量字
    assert _drive_spec_substitute(repo, "HDD/SSD", "960G", "SATA") == []


def test_substitute_unparseable_term_returns_empty():
    repo = FakeRepo([_part("1.92T SATA SSD", specs={"Capacity": "1.92 TB", "Type": "SATA"})])
    assert _drive_spec_substitute(repo, "HDD/SSD", "企业级", None) == []


# ============================================================
# _pick_drive_groups —— 匹配链端到端（名字 → 替代 → unmatched）
# ============================================================

def test_pick_exact_name_and_kind_hit_no_substitute():
    repo = FakeRepo([_part("960G SATA SSD", price=80.0, specs={"Capacity": "960 GB", "Type": "SATA"}),
                     _part("960G NVME SSD", price=70.0, specs={"Capacity": "960 GB", "Type": "NVMe"})])
    out = []
    n = _pick_drive_groups([{"term": "960G", "qty": 2, "kind": "SATA"}],
                           "HDD/SSD", repo, _MIN_PRICE, out)
    assert n == 1
    assert out[0]["pn"] == "960G SATA SSD"
    assert "替代" not in out[0]["matched_spec"]


def test_pick_kind_mismatch_falls_to_substitute():
    # 名字含 960G 但接口不符（需求 SATA，只有 960G NVMe）→ 不硬选错接口，走替代
    repo = FakeRepo([_part("960G NVME SSD", price=70.0, specs={"Capacity": "960 GB", "Type": "NVMe"}),
                     _part("1.92T SATA SSD", price=90.0, specs={"Capacity": "1.92 TB", "Type": "SATA"})])
    out = []
    n = _pick_drive_groups([{"term": "960G", "qty": 1, "kind": "SATA"}],
                           "HDD/SSD", repo, _MIN_PRICE, out)
    assert n == 1
    assert out[0]["pn"] == "1.92T SATA SSD"
    assert "替代" in out[0]["matched_spec"]


def test_pick_substitute_marks_transparent():
    repo = FakeRepo([_part("1.92T SATA SSD", price=90.0, specs={"Capacity": "1.92 TB", "Type": "SATA"}),
                     _part("2T SATA HDD", price=80.0, specs={"Capacity": "2 TB", "Type": "SATA"})])
    out = []
    _pick_drive_groups([{"term": "1.6T", "qty": 1, "kind": "SATA"}],
                       "HDD/SSD", repo, _MIN_PRICE, out)
    assert "容量 1.6T" in out[0]["matched_spec"]
    assert "替代 1.92T" in out[0]["matched_spec"]


def test_pick_no_hit_stays_unmatched():
    repo = FakeRepo([_part("3.84T SATA SSD", price=90.0, specs={"Capacity": "3.84 TB", "Type": "SATA"})])
    out = []
    _pick_drive_groups([{"term": "800G", "qty": 1, "kind": "NVMe"}],
                       "HDD/SSD", repo, _MIN_PRICE, out)
    assert out[0]["unmatched"] is True
    assert "未命中" in out[0]["unmatched_reason"]


def test_pick_spec_substitute_disabled_stays_strict():
    repo = FakeRepo([_part("1.92T SATA SSD", price=90.0, specs={"Capacity": "1.92 TB", "Type": "SATA"})])
    out = []
    _pick_drive_groups([{"term": "1.6T", "qty": 1, "kind": "SATA"}],
                       "HDD/SSD", repo, _MIN_PRICE, out, spec_substitute=False)
    assert out[0]["unmatched"] is True


# ============================================================
# 真实库验证：1.6T 需求（库无）→ 替代 1.92T
# ============================================================

def test_real_db_1_6t_substitutes_1_92t():
    from app.repository.kp_repo import KPRepository
    repo = KPRepository()
    try:
        subs = _drive_spec_substitute(repo, "HDD/SSD", "1.6T", None)
    finally:
        repo.close()
    assert subs, "HDD/SSD 库应能按容量数值找到 1.6T 的替代件"
    assert "1.92T" in subs[0]["model"]


def test_real_db_pick_drive_groups_1_6t():
    from app.repository.kp_repo import KPRepository
    repo = KPRepository()
    out = []
    try:
        n = _pick_drive_groups([{"term": "1.6T", "qty": 1, "kind": None}],
                               "HDD/SSD", repo, _MIN_PRICE, out)
    finally:
        repo.close()
    assert n == 1
    assert out[0].get("unmatched") is not True
    assert "替代" in out[0]["matched_spec"]
    assert "1.92T" in out[0]["pn"] or "1.92T" in out[0]["name"]