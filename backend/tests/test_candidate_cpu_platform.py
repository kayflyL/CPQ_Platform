# -*- coding: utf-8 -*-
"""CPU 候选件按平台过滤（R20 厂商分家）：Polaris=兆芯，海光/飞腾/鲲鹏不是 Polaris。

防跨厂商替代：需求点名海光 → 只留海光家族（库无则 unmatched），绝不落兆芯 KH/KX；
需求只写"信创/国产"或平台=Polaris → 只留兆芯家族；Orion/Intel 各自只留本家。
"""
from app.api.candidate_search import _filter_cpu_parts_for_platform

_PARTS = [
    {"model": "KH50000 48C", "name": "兆芯 开胜 KH50000 48C"},
    {"model": "KH40000 32C", "name": "兆芯 KH40000 32C"},
    {"model": "AMD EPYC 9124", "name": "AMD EPYC 9124"},
    {"model": "Intel Xeon 6330", "name": "Intel Xeon 6330"},
    {"model": "Hygon C86 7390", "name": "海光 C86 7390"},
    {"model": "Phytium S2500", "name": "飞腾 S2500"},
]


def _models(rows):
    return [r["model"] for r in (rows or [])]


def test_kh_requirement_only_zhaoxin():
    # 中文前缀 + 连字符型号：KH-50000 必须只留兆芯，不落 AMD/海光
    got = _filter_cpu_parts_for_platform(_PARTS, "2U服务器全套配置KH-50000")
    assert _models(got) == ["KH50000 48C", "KH40000 32C"]


def test_kh_requirement_with_polaris_platform():
    got = _filter_cpu_parts_for_platform(_PARTS, "2U服务器全套配置KH-50000", "Polaris")
    assert _models(got) == ["KH50000 48C", "KH40000 32C"]


def test_hygon_requirement_never_zhaoxin():
    # 海光需求：只留海光家族（有件则海光；无海光件应 unmatched，绝不回退兆芯）
    got = _filter_cpu_parts_for_platform(_PARTS, "海光服务器 C86 7390*2")
    assert _models(got) == ["Hygon C86 7390"]
    got2 = _filter_cpu_parts_for_platform(_PARTS, "海光 7390*2", "Polaris")
    assert _models(got2) == ["Hygon C86 7390"]


def test_generic_xinchuang_polaris_only_zhaoxin():
    got = _filter_cpu_parts_for_platform(_PARTS, "信创服务器", "Polaris")
    assert _models(got) == ["KH50000 48C", "KH40000 32C"]
    got2 = _filter_cpu_parts_for_platform(_PARTS, "国产 CPU 服务器")
    assert _models(got2) == ["KH50000 48C", "KH40000 32C"]


def test_orion_intel_respect_platform():
    assert _models(_filter_cpu_parts_for_platform(_PARTS, "AMD 9654*2", "Orion")) == ["AMD EPYC 9124"]
    assert _models(_filter_cpu_parts_for_platform(_PARTS, "Xeon 6330*2", "Intel")) == ["Intel Xeon 6330"]


def test_no_signal_keeps_all():
    assert len(_models(_filter_cpu_parts_for_platform(_PARTS, "随便配一台", None))) == len(_PARTS)
