# -*- coding: utf-8 -*-
"""bom_compare 对照引擎单测：规格级对照（品类数量/件级属性/需求信号/L6 结构）。

关键用例：
- 内存速率 5600 vs 4800 必须报 part 差异（category+qty 层会漏——2026-08-04 训练案例验证）
- 需求国产 CPU 系统推 AMD 必须报 requirement 重大差异（KH50000 判据）
- U.2 盘接口归一（U.2 即 NVMe，不产生假差异）
- L6 缺 riser 报 major
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[0]))  # backend/tests

from app.services.bom_compare import compare_boms


def _kp(cat, name, qty, desc=""):
    return {"category": "Key Parts", "part_category": cat, "catalogue": name, "description": desc, "qty": qty}


def _l6(name, desc, qty):
    return {"category": "L6", "catalogue": name, "description": desc, "qty": qty}


def _ok_rows():
    return [
        _l6("Chassis", "2U12", 1),
        _l6("Tri-Mode Backplane", "12*3.5 SATA/SAS/NVMe", 1),
        _l6("CPU Heatsink", "2U heatsink", 2),
        _l6("系统风扇(2U)", "", 6),
        _l6("Slide Rail, 1U", "", 1),
        _l6("Power Supply", "1300W", 2),
        _kp("CPU", "AMD 9654", 2),
        _kp("Memory", "32GB DDR5 5600MHz RDIMM", 16),
        _kp("HDD/SSD", "960G SATA SSD", 2),
        _kp("HDD/SSD", "7.68T NVMe U.2 SSD", 2),
        _kp("Raid card", "LSI 9560-8i", 1),
        _kp("Network(NIC) requirement", "25G 2port CX5+光模块", 2),
    ]


def _case_rows():
    """与技术员 BOM 同构（BI-2026-0709 ES22V3-P）。"""
    return [
        _l6("Front backplane", "12*3.5 SATA/SAS/NVMe", 1),
        _l6("IO1", "1*X16+1*X8 FHFL", 1),
        _l6("IO2", "1*X16+1*X8 FHFL", 1),
        _l6("Heatsink", "2U heatsink", 2),
        _l6("FAN", "6056", 6),
        _l6("Power Supply Requirement", "1300W", 2),
        _l6("Power cord", "C13-C14", 2),
        _l6("Rail kit", "Rail", 1),
        _l6("Cable", "9560 8 sas cable, 2NVMe cable", 1),
        _kp("CPU", "AMD 9654", 2),
        _kp("Memory", "32G 4800 DDR5 RDIMM", 16),
        _kp("HDD/SSD", "960G SATA SSD", 2),
        _kp("HDD/SSD", "7.68T NVMe", 2),
        _kp("Raid card", "LSI 9560-8I 4G cache", 1),
        _kp("Network(NIC) requirement", "Dual port 25G network card + optical module", 2),
    ]


_REQ_ES22V3 = """机箱：2U机架式
CPU：AMD 9654 * 2
内存：DDR5  32 * 16
硬盘：SATA SSD 960G * 2
硬盘：U.2 NVME 7.68T * 2
RAID卡：9560-8I * 1
网卡：CX5 25G 双口 含光模块 * 2
电源：根据功耗选择"""


def _speed_diffs(report):
    return [d for cat in report["part_level"] for d in cat["diffs"] if d.get("field") == "speed"]


def _l6_item(report, name):
    return [d for d in report["l6_level"] if d["item"] == name]


def test_memory_speed_diff_detected():
    """核心：category+qty 全 ok，但内存速率 5600 vs 4800 必须报 part 差异。"""
    sys_rows = _ok_rows()
    sys_rows = [r for r in sys_rows if not (r.get("part_category") == "Memory")]
    sys_rows.append(_kp("Memory", "32GB DDR5 5600MHz RDIMM", 16))
    report = compare_boms(sys_rows, _case_rows(), requirement=_REQ_ES22V3,
                          system_chassis_signals={"psu_wattage": "1300", "psu_qty": 2})
    # 品类数量全 ok
    assert all(c["status"] == "ok" for c in report["category_level"])
    # 速率差异被抓住
    sd = _speed_diffs(report)
    assert len(sd) == 1 and "5600" in sd[0]["system"] and "4800" in sd[0]["case"]
    assert report["summary"]["part_diff"] >= 1


def test_ok_rows_no_real_diff():
    """系统侧改成 4800（和技术员一致）→ 只剩 riser 缺失 + format，无 part 真差异。"""
    sys_rows = _ok_rows()
    sys_rows = [r for r in sys_rows if not (r.get("part_category") == "Memory")]
    sys_rows.append(_kp("Memory", "32GB DDR5 4800MHz RDIMM", 16))
    report = compare_boms(sys_rows, _case_rows(), requirement=_REQ_ES22V3,
                          system_chassis_signals={"psu_wattage": "1300", "psu_qty": 2})
    assert report["summary"]["part_diff"] == 0
    assert _l6_item(report, "IO/Riser")  # riser 缺失仍在


def test_cpu_platform_violation_major():
    """需求国产（KH50000）系统推 AMD → requirement 重大差异。"""
    sys_rows = [_kp("CPU", "AMD EPYC 9554", 2)]
    report = compare_boms(sys_rows, [_kp("CPU", "兆芯 KH-50000-72", 2)],
                          requirement="CPU：兆芯 KH50000 * 2")
    rq = report["requirement_checks"]
    assert any(c["signal"] == "cpu_platform" and c["status"] == "violated" for c in rq)
    assert report["summary"]["major"] >= 1


def test_cpu_platform_match_no_violation():
    """需求国产系统也国产 → 无 violation。"""
    sys_rows = [_kp("CPU", "兆芯 KH-50000-72", 2)]
    report = compare_boms(sys_rows, [_kp("CPU", "兆芯 KH-50000-72", 2)],
                          requirement="CPU：兆芯 KH50000 * 2")
    assert not any(c["signal"] == "cpu_platform" and c["status"] == "violated" for c in report["requirement_checks"])


def test_drive_u2_normalized_no_false_diff():
    """U.2 是形态不是接口：系统 '7.68T NVMe U.2 SSD' vs 技术员 '7.68T NVMe' 不报接口差异。"""
    sys_rows = [_kp("HDD/SSD", "7.68T NVMe U.2 SSD", 2)]
    case_rows = [_kp("HDD/SSD", "7.68T NVMe", 2)]
    report = compare_boms(sys_rows, case_rows, requirement="硬盘：U.2 NVME 7.68T * 2")
    iface_diffs = [d for cat in report["part_level"] for d in cat["diffs"] if d.get("field") == "iface"]
    assert iface_diffs == []


def test_l6_riser_missing_major():
    """系统 L6 无 riser、技术员 2 块 → l6 差异 major。"""
    report = compare_boms(_ok_rows(), _case_rows(), requirement=_REQ_ES22V3,
                          system_chassis_signals={"psu_wattage": "1300", "psu_qty": 2})
    riser = _l6_item(report, "IO/Riser")
    assert riser and riser[0]["system_qty"] == 0 and riser[0]["case_qty"] == 2
    assert report["summary"]["major"] >= 1


def test_psu_from_signals_no_false_diff():
    """系统电源来自 chassis_signals（不在 L6 行）→ 不误报电源缺失。"""
    report = compare_boms(_ok_rows(), _case_rows(), requirement=_REQ_ES22V3,
                          system_chassis_signals={"psu_wattage": "1300", "psu_qty": 2})
    assert not _l6_item(report, "电源")


def test_unmatched_data_gap():
    """需求品类库里无料 → 诚实标 data_gap。"""
    report = compare_boms([], [_kp("CPU", "AMD 9654", 2)],
                          requirement="CPU：AMD 9654 * 2",
                          system_unmatched=[{"category": "GPU", "reason": "需求 GPU 型号库中无料"}])
    assert any(c["signal"] == "unmatched" and c["status"] == "data_gap" for c in report["requirement_checks"])


def test_psu_inference_memory_capacity_aware():
    """I15/I61 R24：电源纯性能推算，内存按容量计功耗——64G×24 高配推断 1600W（原 10W/条 低估到 1300W）。"""
    from app.api.candidate_search import _estimate_system_load, _suggest_psu_wattage
    # LLW：2×9554(360W) + 24×64G(15W) + 2×SATA + 1×RAID + 3×NIC
    kp = [
        {"category": "CPU", "name": "AMD 9554", "qty": 2},
        {"category": "Memory", "name": "64G 5600 DDR5 RDIMM", "qty": 24},
        {"category": "HDD/SSD", "name": "960G SATA SSD", "qty": 2},
        {"category": "Raid card", "name": "LSI 9560-8i", "qty": 1},
        {"category": "Network(NIC) requirement", "name": "10G 2port", "qty": 3},
    ]
    load = _estimate_system_load(kp)
    assert _suggest_psu_wattage(load) == "1600"
    # BI：2×9654(360W) + 16×32G(10W) → 1300W
    kp2 = [
        {"category": "CPU", "name": "AMD 9654", "qty": 2},
        {"category": "Memory", "name": "32G 4800 DDR5 RDIMM", "qty": 16},
        {"category": "HDD/SSD", "name": "960G SATA SSD", "qty": 2},
        {"category": "HDD/SSD", "name": "7.68T NVMe U.2", "qty": 2},
        {"category": "Raid card", "name": "LSI 9560-8i", "qty": 1},
        {"category": "Network(NIC) requirement", "name": "25G 2port", "qty": 2},
    ]
    assert _suggest_psu_wattage(_estimate_system_load(kp2)) == "1300"


def test_drive_iface_ignores_raid_line():
    """R23：RAID 行 '12Gb SAS RAID 卡' 的 SAS 不当盘接口（误报修复）。"""
    sys_rows = [_kp("HDD/SSD", "960G SATA SSD", 2)]
    case_rows = [_kp("HDD/SSD", "960G SATA SSD", 2)]
    req = "系统固态硬盘：960GB SSD *2\nRAID 阵列卡：LSI 9560-8i 12Gb SAS RAID 卡, 8 个 SAS 口、4GB 缓存、PCIe4.0 *1"
    report = compare_boms(sys_rows, case_rows, requirement=req)
    assert not any(c["signal"] == "drive_iface" and c["status"] == "violated" for c in report["requirement_checks"])


def test_riser_content_diff_detected():
    """R27：行数相同但槽位规格不同要抓（YC 样本：技术员 IO2=2*X8 vs 系统 1*X16+1*X8）。"""
    sys_rows = [_l6("IO1", "1*X16+1*X8 FHFL", 1), _l6("IO2", "1*X16+1*X8 FHFL", 1)]
    case_rows = [_l6("IO1", "1*X16+1*X8 FHFL", 1), _l6("IO2", "2*X8", 1)]
    report = compare_boms(sys_rows, case_rows)
    assert report["summary"]["l6_diff"] == 1
    d = [x for x in report["l6_level"] if x.get("field") == "IO2 规格"]
    assert d and d[0]["type"] == "part"
    assert "1*X16+1*X8" in d[0]["system"] and "2*X8" in d[0]["case"]


def test_riser_content_lower_spec_detected():
    """LLW 样本：技术员成本降配 1*X8，系统满配 1*X16+1*X8 → 两个槽位都报。"""
    sys_rows = [_l6("IO1", "1*X16+1*X8 FHFL", 1), _l6("IO2", "1*X16+1*X8 FHFL", 1)]
    case_rows = [_l6("IO1", "1*X8 FHFL", 1), _l6("IO2", "1*X8 FHFL", 1)]
    report = compare_boms(sys_rows, case_rows)
    assert report["summary"]["l6_diff"] == 2
    fields = {x.get("field") for x in report["l6_level"]}
    assert fields == {"IO1 规格", "IO2 规格"}


def test_riser_same_spec_wording_variance_no_diff():
    """同一规格写法差异（FHFL 后缀 / 槽位顺序）不算真差异。"""
    sys_rows = [_l6("IO1", "1*X16+1*X8 FHFL", 1), _l6("IO2", "1*X16+1*X8 FHFL", 1)]
    case_rows = [_l6("IO1", "1*X8+1*X16", 1), _l6("IO2", "1*X16+1*X8", 1)]
    report = compare_boms(sys_rows, case_rows)
    assert report["summary"]["l6_diff"] == 0


def test_riser_qty_diff_not_duplicated():
    """行数不同 → qty 层报 major，内容层不重复报。"""
    sys_rows = [_l6("IO1", "1*X16+1*X8 FHFL", 1), _l6("IO2", "1*X16+1*X8 FHFL", 1)]
    case_rows = [_l6("IO1", "1*X16+1*X8 FHFL", 1)]
    report = compare_boms(sys_rows, case_rows)
    riser = [x for x in report["l6_level"] if x.get("item") == "IO/Riser" or x.get("category") == "IO/Riser"]
    assert len(riser) == 1  # 只有 qty 层一条，内容层不重复报
    assert report["summary"]["l6_diff"] == 1
