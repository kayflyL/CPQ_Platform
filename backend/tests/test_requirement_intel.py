# -*- coding: utf-8 -*-
"""需求分析推理流核心逻辑单测（明确度 / 槽位覆盖）。

跑法（backend 目录）：
  python -X utf8 -m pytest tests/test_requirement_intel.py -q
"""

# ============================================================
# 明确度（clarity_evaluator）
# ============================================================

_SPEC_LIST_RULES = [
    {"id": "t_cat4_mem", "body": {"signal": {"type": "combined", "rules": [
        {"type": "category_count", "op": ">=", "value": 4},
        {"type": "has_memory_capacity", "value": True}]},
        "level": "explicit", "missing_if_not": [], "weight": 85}},
    {"id": "t_cat4_model", "body": {"signal": {"type": "combined", "rules": [
        {"type": "category_count", "op": ">=", "value": 4},
        {"type": "model_token_count", "op": ">=", "value": 1}]},
        "level": "explicit", "missing_if_not": [], "weight": 84}},
    {"id": "t_model3", "body": {"signal": {"type": "model_token_count", "op": ">=", "value": 3},
        "level": "explicit", "missing_if_not": [], "weight": 80}},
]

def _spec_list_ext():
    return {
        "keywords": ["KH50000", "DDR564G", "X710", "2U12", "480G", "1300W",
                     "cpu", "内存", "ssd", "raid", "网卡", "电源"],
        "categories": ["CPU", "Memory", "HDD/SSD", "Raid card", "Network(NIC) requirement"],
        "series": None, "form": "2U",
        "usage": "通用计算", "usage_inferred": False,
        "mem_signal": {"type": "DDR5", "total_gb": 564},
        "cpu_signal": None, "psu_signal": {"wattage": 1300},
        "chassis_categories": ["机箱", "电源"],
        "qty_map": {"CPU": 2, "Memory": 8, "HDD/SSD": 2, "Raid card": 1,
                    "Network(NIC) requirement": 1},
    }

def test_clarity_spec_list_is_explicit():
    from app.services.clarity_evaluator import evaluate_clarity
    level, missing, _ = evaluate_clarity(_spec_list_ext(), None, _SPEC_LIST_RULES)
    assert level == "explicit"
    assert missing == []

def test_clarity_fallback_derives_real_missing_fields():
    from app.services.clarity_evaluator import evaluate_clarity
    ext = {
        "keywords": ["KH50000"], "categories": ["CPU"],
        "series": None, "form": None,
        "usage": None, "usage_inferred": False,
        "mem_signal": None, "cpu_signal": None, "psu_signal": None,
    }
    level, missing, explain = evaluate_clarity(ext, 200000, [])
    assert level == "partial"
    assert "需求描述不够具体" not in missing
    assert "系列" in missing and "形态" in missing

def test_clarity_fallback_all_standard_fields_explicit():
    from app.services.clarity_evaluator import evaluate_clarity
    ext = {
        "keywords": ["KH50000", "DDR564G"], "categories": ["CPU", "Memory"],
        "series": "Orion", "form": "2U",
        "usage": None, "usage_inferred": False,
        "mem_signal": {"type": "DDR5", "total_gb": 512},
    }
    level, missing, explain = evaluate_clarity(ext, 200000, [])
    assert level == "explicit"
    assert missing == []
    assert explain.get("fallback_explicit") is True

def test_clarity_fallback_no_signal_is_partial_not_usage_question():
    # 目录驱动引导下"用途"不再是反问字段（类型由客户从目录里选）→ 不再因无用途判 unclear
    from app.services.clarity_evaluator import evaluate_clarity
    ext = {
        "keywords": [], "categories": [],
        "series": None, "form": None,
        "usage": None, "usage_inferred": False,
        "mem_signal": None,
    }
    level, missing, _ = evaluate_clarity(ext, None, [])
    assert level == "partial"
    assert "用途" not in missing

# ============================================================
# 数量解析（P0 回归）：×N 后缀假阳性 / N×M 前缀 / qty_per_token 同段关联
# ============================================================

_TEST_LEXICON = {
    "CPU": ["cpu", "processor", "处理器", "epyc", "xeon", "至强", "intel", "amd"],
    "Memory": ["memory", "ram", "内存", "ddr", "rdimm"],
    "HDD/SSD": ["hdd", "ssd", "nvme", "硬盘", "磁盘", "sata"],
    "GPU": ["gpu", "显卡", "图形卡", "rtx", "l40", "w7900", "a100", "h100"],
    "Raid card": ["raid", "阵列卡"],
    "Network(NIC) requirement": ["nic", "网络", "网卡"],
}

def test_slot_coverage_complete_ai_explicit():
    # 完整 4U AI 需求 → 13/13 槽位已填 → explicit，不反问
    from app.services.clarity_evaluator import evaluate_slot_coverage
    ext = {"categories": ["CPU", "Memory", "HDD/SSD", "GPU", "Network(NIC) requirement", "Raid card"],
           "qty_map": {"CPU": 2, "Memory": 24, "GPU": 2, "HDD/SSD": 6},
           "series": "Orion", "form": "4U",
           "cpu_signal": {"model": "9654"}, "mem_signal": {"type": "DDR5"},
           "drive_groups": [{"term": "1.92T"}], "gpu_groups": [{"tokens": ["A800"]}],
           "raid_groups": [{"model": "9560-16i"}], "psu_signal": {"wattage": 2700},
           "multi_spec_filters": {"Network(NIC) requirement": [{}]},
           "usage": "AI / 加速计算服务器",
           "server_type_name": "AI / 加速计算服务器", "server_model": "ES24V3-P",
           "purchase_qty": 1, "warranty_years": 3}
    level, missing, explain = evaluate_slot_coverage(ext)
    assert level == "explicit" and missing == []
    assert explain["coverage"] == "13/13"

def test_slot_coverage_sparse_partial():
    # 只给 2U+CPU → L0 缺 服务器类型/数量 ≥ ask_threshold(2) → partial 反问
    from app.services.clarity_evaluator import evaluate_slot_coverage
    ext = {"categories": ["CPU"], "qty_map": {"CPU": 2}, "series": "Orion", "form": "2U"}
    level, missing, explain = evaluate_slot_coverage(ext)
    assert level == "partial"
    assert "服务器类型" in missing and "数量" in missing

def test_slot_coverage_storage_not_l0_explicit():
    # 通用 2U 无盘：存储不是 L0，不计入 missing → explicit
    from app.services.clarity_evaluator import evaluate_slot_coverage
    ext = {"categories": ["CPU", "Memory"], "qty_map": {"CPU": 2, "Memory": 8},
           "series": "Orion", "form": "2U",
           "cpu_signal": {"model": "9654"}, "mem_signal": {"type": "DDR5"},
           "server_type_name": "通用计算服务器", "server_model": "R2100", "purchase_qty": 1}
    level, missing, _ = evaluate_slot_coverage(ext)
    assert level == "explicit"
