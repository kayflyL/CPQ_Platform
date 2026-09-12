# -*- coding: utf-8 -*-
"""已锁行描述冻结（P2.0 行键稳定化）回归测试。

2026-09-07 P0 复拍实测病灶：大脑在后续回合重发 kp_rows 时把已确认行的描述
「规范化」（兆芯50000 → KH50000 96C）→ 行键变 → 已确认 pick 作废 → 客户被
重复问同一行、已提交行被覆盖吞掉。_merge_kp_rows_locked 冻结带 pick 的旧行。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.capabilities import _apply_extracted_slots


def test_locked_rows_survive_rephrase():
    ext = {
        "kp_rows": [
            {"part_category": "CPU", "description": "2颗兆芯50000 处理器（2.2GHz/96C）", "qty": 2},
            {"part_category": "Memory", "description": "768GB DDR5", "qty": 1},
            {"part_category": "HDD/SSD", "description": "2块480G SSD", "qty": 2},
        ],
    }
    # 已锁定行 = kp_reason 节点私有状态（节点隔离，不在共享 ext 上）
    picks = {
        "CPU|2颗兆芯50000 处理器（2.2GHz/96C）": {"name": "KH50000 96C", "price": 3500.0, "qty": 2},
        "Memory|768GB DDR5": {"name": "32G 4800 DDR5 RDIMM", "price": 8800.0, "qty": 24},
    }
    # 大脑后续回合重发全表：CPU/Memory 描述被规范化，新增 GPU 行
    slots = {"kp_rows": [
        {"part_category": "CPU", "description": "2颗KH50000 96C（2.2GHz/96C）", "qty": 2},
        {"part_category": "Memory", "description": "768GB DDR5（32G 4800 DDR5 RDIMM ×24）", "qty": 1},
        {"part_category": "HDD/SSD", "description": "2块480G SSD", "qty": 2},
        {"part_category": "GPU", "description": "无", "qty": 1},
    ]}
    _apply_extracted_slots(ext, slots, picks=picks)
    rows = ext["kp_rows"]
    descs = [r["description"] for r in rows]
    # 已锁行描述冻结（行键稳定 → pick 不作废）
    assert "2颗兆芯50000 处理器（2.2GHz/96C）" in descs
    assert "768GB DDR5" in descs
    # 确认后变体不重复入表
    assert "2颗KH50000 96C（2.2GHz/96C）" not in descs
    assert "768GB DDR5（32G 4800 DDR5 RDIMM ×24）" not in descs
    # 未锁新行正常采纳、未锁旧行保留（不丢行）
    assert any(r["part_category"] == "GPU" for r in rows)
    assert "2块480G SSD" in descs
    assert len(rows) == 4


def test_unlocked_rows_still_replace_normally():
    ext = {"kp_rows": [{"part_category": "HDD/SSD", "description": "硬盘", "qty": 1}]}
    slots = {"kp_rows": [{"part_category": "HDD/SSD", "description": "4块6T HDD", "qty": 4}]}
    _apply_extracted_slots(ext, slots)
    descs = [r["description"] for r in ext["kp_rows"]]
    assert descs == ["4块6T HDD"]


def test_no_picks_behaves_as_before():
    ext = {"kp_rows": [{"part_category": "CPU", "description": "旧", "qty": 1}]}
    slots = {"kp_rows": [{"part_category": "CPU", "description": "新", "qty": 2}]}
    _apply_extracted_slots(ext, slots)
    assert ext["kp_rows"][0]["description"] == "新"


def test_partial_fill_does_not_wipe_registered_categories():
    """同回合分批/重试只发部分行时，不得覆盖吞掉先前已登记的其它类目部件。"""
    ext = {"kp_rows": [
        {"part_category": "CPU", "description": "2颗兆芯50000 处理器（2.2GHz/96C）", "qty": 2},
        {"part_category": "Memory", "description": "768GB DDR5", "qty": 1},
        {"part_category": "HDD/SSD", "description": "2块480G SSD", "qty": 2},
    ]}
    # 大脑后续只补发 Raid card（未带 replace）：已登记 CPU/Memory/HDD/SSD 应保留
    slots = {"kp_rows": [{"part_category": "Raid card", "description": "1GB缓存 RAID卡", "qty": 1}]}
    _apply_extracted_slots(ext, slots)
    cats = {r["part_category"] for r in ext["kp_rows"]}
    assert {"CPU", "Memory", "HDD/SSD", "Raid card"} <= cats


def test_replace_still_authoritative():
    """replace=true（客户改口确认整表）仍整批替换未锁行。"""
    ext = {"kp_rows": [
        {"part_category": "CPU", "description": "旧 CPU", "qty": 1},
        {"part_category": "Memory", "description": "旧内存", "qty": 1},
    ]}
    slots = {"kp_rows": [{"part_category": "Raid card", "description": "新的 RAID 卡", "qty": 1}]}
    _apply_extracted_slots(ext, slots, allow_overwrite=True)
    assert len(ext["kp_rows"]) == 1
    assert ext["kp_rows"][0]["part_category"] == "Raid card"


def test_placeholder_row_yields_when_customer_names_same_category():
    """客户后补型号：占位行与点名行是同一条需求 → 同类目只留一行（不再新旧并存）。

    实测病象（2026-09-12）：别的类目已锁（有 pick）时，未锁的占位行只按「完全相同的
    (类目,描述)」去重，于是「CPU|通用计算服务器处理器（客户未指定型号）」与后一轮的
    「CPU|兆芯 9654」同类目并存 → 同一行被多问一轮。归属：该行在登记表里只有一条，
    新表同类目即覆盖旧行（与无 picks 的增量合并口径一致）。
    """
    ext = {"kp_rows": [
        {"part_category": "CPU", "description": "通用计算服务器处理器（客户未指定型号）", "qty": 2},
        {"part_category": "Memory", "description": "768GB DDR5", "qty": 1},
    ]}
    picks = {"Memory|768GB DDR5": {"name": "32G 4800 DDR5 RDIMM", "price": 8800.0, "qty": 24}}
    slots = {"kp_rows": [{"part_category": "CPU", "description": "2颗兆芯 9654 处理器", "qty": 2}]}
    _apply_extracted_slots(ext, slots, picks=picks)
    rows = ext["kp_rows"]
    cpu = [r for r in rows if r["part_category"] == "CPU"]
    assert len(cpu) == 1, [r["description"] for r in cpu]
    assert cpu[0]["description"] == "2颗兆芯 9654 处理器"
    assert any(r["part_category"] == "Memory" for r in rows), "新表没提到的已登记类目不许丢"


def test_registration_owned_categories_match_slot_spec():
    """「登记表申报的类目」唯一事实来源 = 登记表部件槽（slot_spec 里 src_type=kp）。"""
    from app.services.slot_contract import registration_owned_categories, slot_spec
    owned = registration_owned_categories()
    assert owned == frozenset(
        str(s.get("category") or "").strip() for s in slot_spec()
        if str(s.get("src_type") or "") == "kp" and str(s.get("category") or "").strip())
    assert "CPU" in owned and "HDD/SSD" in owned
    assert not ({"Bridge", "HBA", "NVSwitch"} & owned), "登记表没有的大类才允许 cfg: 声明行"
