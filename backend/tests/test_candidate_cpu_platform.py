# -*- coding: utf-8 -*-
"""CPU 候选件按平台/厂商过滤（R20 厂商分家）：Polaris=兆芯，海光/飞腾/鲲鹏不是 Polaris。

防跨厂商替代：需求点名海光 → 只留海光家族（库无则 unmatched），绝不落兆芯 KH/KX；
需求只写"信创/国产"或平台=Polaris → 只留兆芯家族；Orion/Intel 各自只留本家。
规则来自 cpu_vendor_map（这里显式传入，避免单测依赖 DB）。
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

_RULES = [
    {"vendor": "amd", "series": "Orion", "pattern": r"AMD|EPYC", "flags": "i"},
    {"vendor": "zhaoxin", "series": "Polaris", "pattern": r"(?:^|[^A-Za-z0-9])(?:KH|KX|ZX)|兆芯|zhaoxin|开胜|开先", "flags": "i"},
    {"vendor": "intel", "series": "Intel", "pattern": r"INTEL|XEON", "flags": "i"},
    {"vendor": "hygon", "series": "", "pattern": r"海光|hygon|C86", "flags": "i"},
    {"vendor": "phytium", "series": "", "pattern": r"飞腾|phytium|腾锐|腾云", "flags": "i"},
    {"vendor": "kunpeng", "series": "", "pattern": r"鲲鹏|kunpeng|\b920\b", "flags": "i"},
    {"vendor": "loongson", "series": "", "pattern": r"龙芯|loongson", "flags": "i"},
]


def _models(rows):
    return [r["model"] for r in (rows or [])]


def test_kh_requirement_only_zhaoxin():
    # 中文前缀 + 连字符型号：KH-50000 必须只留兆芯，不落 AMD/海光
    got = _filter_cpu_parts_for_platform(_PARTS, "2U服务器全套配置KH-50000", None, _RULES)
    assert _models(got) == ["KH50000 48C", "KH40000 32C"]


def test_kh_requirement_with_polaris_platform():
    got = _filter_cpu_parts_for_platform(_PARTS, "2U服务器全套配置KH-50000", "Polaris", _RULES)
    assert _models(got) == ["KH50000 48C", "KH40000 32C"]


def test_hygon_requirement_never_zhaoxin():
    # 海光需求：只留海光家族（有件则海光；无海光件应 unmatched，绝不回退兆芯）
    got = _filter_cpu_parts_for_platform(_PARTS, "海光服务器 C86 7390*2", None, _RULES)
    assert _models(got) == ["Hygon C86 7390"]
    got2 = _filter_cpu_parts_for_platform(_PARTS, "海光 7390*2", "Polaris", _RULES)
    assert _models(got2) == ["Hygon C86 7390"]


# 需求是否"信创/国产"由需求节点按平台系列规则归一为 series（platform_series_map/
# compliance_map 有"信创→Polaris"）；本过滤器只依据已归一 series 过滤，不再识别原文国产词。
def test_generic_xinchuang_polaris_only_zhaoxin():
    got = _filter_cpu_parts_for_platform(_PARTS, "信创服务器", "Polaris", _RULES)
    assert _models(got) == ["KH50000 48C", "KH40000 32C"]
    # 国产/信创但上游未归一系列 → 视为无信号，保持全部（防误杀；归属由上游归一负责）
    got2 = _filter_cpu_parts_for_platform(_PARTS, "国产 CPU 服务器", None, _RULES)
    assert _models(got2) == _models(_PARTS)


def test_orion_intel_respect_platform():
    assert _models(_filter_cpu_parts_for_platform(_PARTS, "AMD 9654*2", "Orion", _RULES)) == ["AMD EPYC 9124"]
    assert _models(_filter_cpu_parts_for_platform(_PARTS, "Xeon 6330*2", "Intel", _RULES)) == ["Intel Xeon 6330"]


def test_no_signal_keeps_all():
    assert len(_models(_filter_cpu_parts_for_platform(_PARTS, "随便配一台", None, _RULES))) == len(_PARTS)
