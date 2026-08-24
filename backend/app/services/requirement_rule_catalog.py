"""需求分析规则目录读取器。

规则目录是统一数据源，节点/能力只读取规则，不再把规则硬编码进节点配置。
所有函数都做延迟 import 和异常回退，读库失败时返回空值，由调用方走模块默认。
"""
from __future__ import annotations
from typing import Any, Optional

from app.repository.requirement_rule_repo import RequirementRuleRepository


def active_bodies(rule_type: str, enabled_types: Optional[list[str]] = None) -> list[dict]:
    """按类型取 active 规则的 body 列表；enabled_types 为节点引用白名单。"""
    if enabled_types is not None and rule_type not in enabled_types:
        return []
    try:
        repo = RequirementRuleRepository()
        try:
            rows = repo.list_by_type(rule_type, status="active")
            if rows:
                try:
                    repo.record_hits([r.get("id") for r in rows])
                except Exception:
                    pass
            return [dict(r.get("body") or {}) for r in rows if isinstance(r.get("body"), dict)]
        finally:
            repo.close()
    except Exception:
        return []


def cpu_mem_type_rules(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """CPU 型号 → 内存代际规则。"""
    return active_bodies("cpu_mem_generation", enabled_types)


def category_aliases(enabled_types: Optional[list[str]] = None) -> dict[str, list[str]]:
    """需求品类 → KP 分类别名。"""
    out: dict[str, list[str]] = {}
    for row in active_bodies("category_alias", enabled_types):
        category = str(row.get("category") or "").strip()
        aliases = row.get("aliases") or []
        if not category or not isinstance(aliases, list):
            continue
        out[category] = [str(x) for x in aliases if str(x).strip()]
    return out





# 部件家族 → 关键词（用于功耗/负载粗估；可被 power_calibration.part_family_keywords 覆盖。
# 数据落在规则库（默认值 + 规则覆盖），candidate_search 只读不内联。)
DEFAULT_PART_FAMILY_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "cpu": {"cat_upper": ["CPU"]},
    "memory": {"cat_upper": ["MEM"], "cat": ["内存"]},
    "nvme": {"name_upper": ["NVME"]},
    "disk": {"cat": ["硬盘", "SSD", "HDD", "DISK"]},
    "nic": {"cat_upper": ["NIC", "NETWORK"], "cat": ["网卡"]},
    "raid": {"cat_upper": ["RAID", "HBA"], "cat": ["阵列"]},
    "sata": {"name_upper": ["SATA"]},
    "sas": {"name_upper": ["SAS"]},
}


def part_family_keywords(enabled_types: Optional[list[str]] = None) -> dict[str, dict[str, list[str]]]:
    """部件家族关键词（默认值 + 规则/配置覆盖，后者覆盖前者）。"""
    out = {k: {kk: list(vv) for kk, vv in v.items()} for k, v in DEFAULT_PART_FAMILY_KEYWORDS.items()}
    for row in active_bodies("power_calibration", enabled_types):
        if isinstance(row, dict) and isinstance(row.get("part_family_keywords"), dict):
            pfm = row["part_family_keywords"]
            for fam, kws in pfm.items():
                if isinstance(kws, dict):
                    out[str(fam)] = {str(k): [str(x) for x in (v if isinstance(v, list) else [v])] for k, v in kws.items() if k in ("cat_upper", "cat", "name_upper")}
    return out
# 型号 token 排除规则（KP 候选检索 stage-1 用）：识别"规格碎片/部件词"而非型号，
# 命中即跳过精确命中、落后续代表件。数据默认在规则库（可被 kp_token_exclude 规则覆盖）。
DEFAULT_KP_TOKEN_EXCLUDE_PATTERNS: list[str] = [
    r"^\d+(?:\.\d+)?(?:[GTW]B?|MB|MHz|GHz)$",
    r"^\d+[A-Z]{1,2}$",
    r"^DDR[345]-?\d*[A-Z]*$",
    r"^\d+[A-Za-z]*series$",
    r"^(?:SATA|SAS|NVME?|U\.?2|SSD|HDD)[A-Za-z]*\d+(?:\.\d+)?[GT]B?$",
    r"^\d+\.\d+$",
    r"^\d+[A-Za-z]{2,}$",
    r"^\d+-\d+(?:度|℃|°C)?$",
    r"^\d+[xX]\d+$",
    r"^Gen[345]$",
    r"^Gen[345][xX]\d+$",
    r"^\d+[GT]?B?(?:SATA|SAS|NVME?|GB?)[A-Za-z0-9.]*$",
    r"^\d+\.\d+[A-Za-z]+$",
    r"^PCIe\d*(?:\.\d+)?$",
    r"^RAID\d+$",
    r"^GX\d+$",
    r"^\dU\d+$",
    r"^\d+i\d+[GT]?B?$",
]
DEFAULT_KP_TOKEN_IGNORE_WORDS: list[str] = ["rj45", "ipmi", "bmc", "mgmt", "management"]


def kp_token_exclude(enabled_types: Optional[list[str]] = None) -> dict[str, list[str]]:
    """型号 token 排除规则：patterns（命中即当非型号跳过）+ ignore_words（小写忽略词）。
    规则 body 可覆盖默认；缺失回退默认，保证候选检索不因配置缺失而改变行为。"""
    patterns = list(DEFAULT_KP_TOKEN_EXCLUDE_PATTERNS)
    ignore = list(DEFAULT_KP_TOKEN_IGNORE_WORDS)
    for row in active_bodies("kp_token_exclude", enabled_types):
        if not isinstance(row, dict):
            continue
        p = row.get("patterns")
        if isinstance(p, list):
            patterns = [str(x) for x in p if str(x).strip()]
        iw = row.get("ignore_words")
        if isinstance(iw, list):
            ignore = [str(x).lower() for x in iw if str(x).strip()]
    return {"patterns": patterns, "ignore_words": ignore}


def platform_series_map(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """平台系列 → 关键词映射（AMD→Orion / 兆芯→Polaris / Intel→Intel）。"""
    return [dict(x) for x in active_bodies("platform_series_map", enabled_types) if x]


def cpu_vendor_map(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """CPU 厂商/系列 → 件侧匹配正则（防跨厂商替代；AMD→Orion / 兆芯→Polaris / Intel→Intel）。"""
    return [dict(x) for x in active_bodies("cpu_vendor_map", enabled_types) if x]


def gpu_brand_map(enabled_types: Optional[list[str]] = None) -> dict[str, list[str]]:
    """GPU 品牌 → 替代件同义词（NVIDIA/AMD 等），用于推断用户点名的 GPU 厂商。

    规则 body 即 {brand: [synonyms]}，可多条合并。
    """
    out: dict[str, list[str]] = {}
    for row in active_bodies("gpu_brand_map", enabled_types):
        for brand, syns in row.items():
            if not brand or not isinstance(syns, list):
                continue
            out[str(brand)] = [str(x) for x in syns if str(x).strip()]
    return out


def spec_unit_patterns(enabled_types: Optional[list[str]] = None) -> dict[str, str]:
    """规格单位 → 匹配正则（GB/TB/W/核/MHz 等）。规则 body 即 {unit: regex}。

    规则库可覆盖；缺失时由调用方对未知单位做原样转义，不臆造。
    """
    out: dict[str, str] = {}
    for row in active_bodies("spec_unit_patterns", enabled_types):
        for unit, rx in row.items():
            if unit and rx:
                out[str(unit)] = str(rx)
    return out


def power_calibration(enabled_types: Optional[list[str]] = None) -> dict:
    """功耗/电源推断校准：CPU TDP 表、常项功耗、标准 PSU 档位、高功耗 GPU 词表等。

    规则 body 即一份校准字典（可多条合并，后者覆盖）。缺失返回 {}，调用方不臆测。
    """
    merged: dict = {}
    for row in active_bodies("power_calibration", enabled_types):
        if isinstance(row, dict):
            merged.update(row)
    return merged


def type_alias(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """服务器类型别名 → 目录规范类型名（AI加速 → 'AI / 加速计算服务器'）。"""
    return [dict(x) for x in active_bodies("type_alias", enabled_types) if x]


def raid_level_map(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """RAID 级别 → 阵列卡品类/规格提示。"""
    return [dict(x) for x in active_bodies("raid_level_map", enabled_types) if x]
def workload_map(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """工作负载关键词 → 显存/卡数/意图（跑大模型等）。"""
    return [dict(x) for x in active_bodies("workload_map", enabled_types) if x]


def compliance_map(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """国产化/合规 → 平台系列与配件厂商白名单/排除。"""
    return [dict(x) for x in active_bodies("compliance_map", enabled_types) if x]


def gpu_form_map(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """GPU 数量 → 机箱形态（单卡→2U，多卡→4U）。"""
    return [dict(x) for x in active_bodies("gpu_form_map", enabled_types) if x]


def type_packages(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """机型类型关键词 → 标准 KP 品类套餐。"""
    return [dict(x) for x in active_bodies("type_package", enabled_types) if x]


def spec_rules(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """规格匹配默认规则。"""
    return [dict(x) for x in active_bodies("spec_rule", enabled_types) if x]


def capacity_match(enabled_types: Optional[list[str]] = None) -> dict[str, Any]:
    """容量匹配默认策略。"""
    rows = active_bodies("capacity_match", enabled_types)
    return dict(rows[0]) if rows else {"strategy": "tolerance", "tolerance": 10}


def fallback_order(enabled_types: Optional[list[str]] = None) -> dict[str, Any]:
    """机型选型放宽顺序。"""
    rows = active_bodies("fallback_order", enabled_types)
    return dict(rows[0]) if rows else {"order": ["exact", "same_series", "same_form", "all"], "no_signal_strategy": "return_empty"}


def delegation_phrases(enabled_types: Optional[list[str]] = None) -> list[dict]:
    """客户委托话术（你推荐/随便/我不太懂等）→ 可配置的委托判定词。"""
    return [dict(x) for x in active_bodies("delegation_phrases", enabled_types) if x]


def check_rules(enabled_types: Optional[list[str]] = None) -> dict[str, Any]:
    """方案自检默认规则。"""
    rows = active_bodies("check_rule", enabled_types)
    return dict(rows[0]) if rows else {}


def model_action_phrases(enabled_types: Optional[list[str]] = None) -> dict[str, list[str]]:
    """机型选型节点用户意图词表（自己配/推荐/重选/取消）→ 每组关键词。

    规则 body 即 action → keywords 映射；可多条合并。
    """
    out: dict[str, list[str]] = {}
    for row in active_bodies("model_action_phrases", enabled_types):
        for action, words in row.items():
            if not action or not isinstance(words, list):
                continue
            out[action] = [str(x) for x in words if str(x).strip()]
    return out


def kp_action_phrases(enabled_types: Optional[list[str]] = None) -> dict[str, list[str]]:
    """配件选配节点用户意图词表（确认/重选机型/取消）→ 每组关键词。

    规则 body 即 action → keywords 映射；可多条合并。
    """
    out: dict[str, list[str]] = {}
    for row in active_bodies("kp_action_phrases", enabled_types):
        for action, words in row.items():
            if not action or not isinstance(words, list):
                continue
            out[action] = [str(x) for x in words if str(x).strip()]
    return out
