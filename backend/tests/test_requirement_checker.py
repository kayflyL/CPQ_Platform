# -*- coding: utf-8 -*-
"""review 节点方案校对（audit_plan）单测：阻塞式 通过/不通过 + 必改项。

硬校验：缺关键件（CPU/内存）、平台冲突（需求显式厂商/信创/AMD/Intel vs 方案系列）、严重超预算。
（原 requirement_check 差异报告 check_plan 已随节点删除，测试一并移除）
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/

from app.services.requirement_checker import audit_plan


def _audit_plan(series="Orion"):
    return {"series": series, "cfg": {"bom_excel_rows": [
        {"category": "Key Parts", "part_category": "CPU", "qty": 2},
        {"category": "Key Parts", "part_category": "Memory", "qty": 8},
    ]}}


def test_audit_plan_ok():
    # 有 CPU/内存、平台匹配 → 校对通过
    plan = {"series": "Orion", "cfg": {"bom_excel_rows": [
        {"category": "Key Parts", "part_category": "CPU", "qty": 2},
        {"category": "Key Parts", "part_category": "Memory", "qty": 8},
    ]}}
    a = audit_plan(plan, "CPU：AMD EPYC 9654 *2\n内存：64G *8")
    assert a["status"] == "ok" and a["issues"] == []


def test_audit_plan_missing_cpu_mem():
    plan = {"series": "Orion", "cfg": {"bom_excel_rows": [
        {"category": "Key Parts", "part_category": "GPU", "qty": 1},
    ]}}
    a = audit_plan(plan, "GPU：A800 *1")
    assert a["status"] == "blocked"
    assert any("CPU" in i for i in a["issues"]) and any("内存" in i for i in a["issues"])


def test_audit_plan_platform_conflict():
    # 海光需求配了 AMD/Orion → blocked（跨厂商硬错误，海光 ≠ Polaris/兆芯）
    a = audit_plan(_audit_plan("Orion"), "CPU：海光 7390 *2\n内存：64G *8")
    assert a["status"] == "blocked"
    assert any("海光" in i for i in a["issues"])
    assert not any("应为 Polaris" in i for i in a["issues"])


def test_audit_plan_hygon_not_polaris():
    # 海光需求即使配了 Polaris（兆芯）也 blocked——Polaris 不能替代海光
    a = audit_plan(_audit_plan("Polaris"), "CPU：海光 7390 *2\n内存：64G *8")
    assert a["status"] == "blocked"
    assert any("海光" in i for i in a["issues"])


def test_audit_plan_zhaoxin_polaris_ok():
    # 兆芯 KH-50000 需求配 Polaris → 无平台冲突
    a = audit_plan(_audit_plan("Polaris"), "2U服务器全套配置KH-50000")
    assert not any("平台" in i for i in a["issues"])
    a2 = audit_plan(_audit_plan("Orion"), "2U服务器全套配置KH-50000")
    assert any("应为 Polaris" in i for i in a2["issues"])
