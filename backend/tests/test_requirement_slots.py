# -*- coding: utf-8 -*-
"""RequirementSlots 契约：目录上下文 / schema / 语义校验 / 确定性合并 / 覆盖度。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_requirement_slots.py -q
"""
from unittest.mock import MagicMock, patch

from app.services.requirement_slots import (
    FORM_WHITELIST,
    LLM_UNDERSTAND_SCHEMA,
    _model_grounded,
    apply_llm_merge,
    build_catalog_context,
    compute_coverage,
    slots_to_enhance,
    validate_slots,
)

CATALOG = {
    "server_types": ["AI / 加速计算服务器", "通用计算服务器", "存储服务器"],
    "models_by_type": {"AI / 加速计算服务器": ["ESA 4U-8卡", "ZSA 2U-8卡"]},
    "series": ["Orion", "Polaris", "Intel", "工作站"],
    "forms": FORM_WHITELIST,
    "family_words": {"CPU": ["epyc", "xeon", "kh50000"], "GPU": ["h100", "a100", "rtx"]},
    "slots_spec": [
        {"key": "series", "label": "所属系列", "level": "L0"},
        {"key": "form", "label": "机箱形态", "level": "L1"},
        {"key": "gpu", "label": "GPU", "level": "L1"},
    ],
}


# ============================================================
# build_catalog_context —— 实时目录白名单（DB 读失败降级）
# ============================================================

def test_build_catalog_context_from_db():
    fake_types = [{"id": 1, "name": "AI / 加速计算服务器"}, {"id": 2, "name": "通用计算服务器"}]
    fake_models = {
        "AI / 加速计算服务器": [{"name": "ESA 4U-8卡", "lifecycle_status": "active"},
                              {"name": "ZSA 2U-8卡", "lifecycle_status": "active"}],
        "通用计算服务器": [{"name": "R2100", "lifecycle_status": "active"}],
    }
    cfg_repo = MagicMock()
    cfg_repo.get_value.side_effect = lambda k, d=None: {
        "server_series": [{"value": "Orion", "label": "Orion"}],
        "model_family_words": {"CPU": ["epyc"]},
        "requirement_slots": {"slots": [{"key": "series", "label": "所属系列", "level": "L0"}]},
    }.get(k, d)
    with patch("app.services.catalog_guide.load_catalog", return_value=(fake_types, fake_models)), \
         patch("app.repository.system_config_repo.SystemConfigRepository", return_value=cfg_repo):
        ctx = build_catalog_context()
    assert ctx["server_types"] == ["AI / 加速计算服务器", "通用计算服务器"]
    assert ctx["models_by_type"]["AI / 加速计算服务器"] == ["ESA 4U-8卡", "ZSA 2U-8卡"]
    assert ctx["series"] == ["Orion"]
    assert ctx["family_words"] == {"CPU": ["epyc"]}
    assert ctx["slots_spec"] == [{"key": "series", "label": "所属系列", "level": "L0"}]


def test_build_catalog_context_db_failure_falls_back():
    with patch("app.services.catalog_guide.load_catalog", side_effect=RuntimeError("db down")), \
         patch("app.repository.system_config_repo.SystemConfigRepository", side_effect=RuntimeError("db down")):
        ctx = build_catalog_context()
    assert ctx["source"] == "fallback"
    assert ctx["series"]  # 兜底系列非空
    assert ctx["slots_spec"]  # 兜底槽位非空
    assert ctx["server_types"] == []


# ============================================================
# validate_slots —— 白名单 / 型号接地 / 数量 / 覆盖度矛盾
# ============================================================

def _valid_data():
    return {
        "series": {"value": "Orion", "confidence": 0.9, "source": "text", "evidence": "需求提到 AMD"},
        "form": {"value": "2U", "confidence": 0.8, "source": "text", "evidence": "需求提到 2U"},
        "cpu": {"model": "EPYC 9254", "qty": 2, "confidence": 0.7, "source": "infer", "evidence": "需求提到两颗 EPYC"},
        "budget": {"value": 300000, "confidence": 0.9, "source": "text", "evidence": "预算30万"},
    }


def test_validate_slots_ok():
    errors, warnings = validate_slots(_valid_data(), CATALOG, "两台 AMD EPYC 9254 2U 服务器，预算30万")
    assert errors == []


def test_validate_slots_series_not_in_whitelist():
    data = _valid_data()
    data["series"] = {"value": "Huawei", "confidence": 0.9, "source": "infer", "evidence": "x"}
    errors, _ = validate_slots(data, CATALOG, "服务器")
    assert any("系列" in e and "Huawei" in e for e in errors)


def test_validate_slots_form_not_in_whitelist():
    data = _valid_data()
    data["form"] = {"value": "3U", "confidence": 0.9, "source": "text", "evidence": "x"}
    errors, _ = validate_slots(data, CATALOG, "服务器")
    assert any("形态" in e and "3U" in e for e in errors)


def test_validate_slots_server_type_not_in_whitelist():
    data = _valid_data()
    data["server_type"] = {"value": "量子服务器", "confidence": 0.9, "source": "infer", "evidence": "x"}
    errors, _ = validate_slots(data, CATALOG, "服务器")
    assert any("服务器类型" in e and "量子服务器" in e for e in errors)


def test_validate_slots_rejects_hallucinated_model():
    data = _valid_data()
    data["cpu"] = {"model": "XYZ-9000X", "qty": 2, "confidence": 0.9, "source": "infer", "evidence": "x"}
    errors, _ = validate_slots(data, CATALOG, "一台 2U 服务器")
    assert any("编造" in e and "XYZ-9000X" in e for e in errors)


def test_validate_slots_model_grounded_by_family_word():
    data = _valid_data()
    # 需求没写型号，但命中家族词 epyc → 放行
    data["cpu"] = {"model": "EPYC 9754", "qty": 2, "confidence": 0.7, "source": "infer", "evidence": "AMD 平台"}
    errors, _ = validate_slots(data, CATALOG, "一台 AMD 2U 服务器")
    assert errors == []


def test_validate_slots_qty_out_of_range():
    data = _valid_data()
    data["cpu"]["qty"] = 999
    errors, _ = validate_slots(data, CATALOG, "AMD EPYC 9254")
    assert any("cpu.qty" in e for e in errors)


def test_validate_slots_coverage_confidence_contradiction_warns():
    data = _valid_data()
    # 覆盖度高（series/form/cpu/budget 都填了）但置信度全低 → 软告警
    for k in ("series", "form"):
        data[k]["confidence"] = 0.3
    data["cpu"]["confidence"] = 0.2
    data["budget"]["confidence"] = 0.3
    errors, warnings = validate_slots(data, CATALOG, "AMD EPYC 9254")
    assert errors == []
    assert any("置信度" in w for w in warnings)


# ============================================================
# slots_to_enhance —— 契约 → EXTRACT_ENHANCE_SCHEMA 形状
# ============================================================

def test_slots_to_enhance_maps_and_strips_meta():
    data = {
        "server_type": {"value": "AI / 加速计算服务器", "confidence": 0.9, "source": "text", "evidence": "e"},
        "series": {"value": "Orion", "confidence": 0.9, "source": "text", "evidence": "e"},
        "form": {"value": "2u", "confidence": 0.9, "source": "text", "evidence": "e"},
        "cpu": {"model": "EPYC 9254", "qty": 2, "confidence": 0.9, "source": "infer", "evidence": "e"},
        "memory": {"per_stick_gb": 32, "qty": 8, "type": "DDR5", "confidence": 0.8, "source": "text", "evidence": "e"},
        "storage": [{"capacity": "960G", "qty": 2, "interface": "NVMe", "confidence": 0.8, "source": "text", "evidence": "e"}],
        "gpu": [{"model": "H100", "qty": 8, "confidence": 0.8, "source": "text", "evidence": "e"}],
        "psu": {"wattage": 2700, "qty": 2, "confidence": 0.8, "source": "infer", "evidence": "e"},
        "intent_summary": "AI 训练服务器",
        "missing": ["网卡"],
        "questions": ["需要几块网卡？"],
    }
    enh = slots_to_enhance(data)
    assert enh["form"] == "2U"
    assert enh["series"] == "Orion"
    assert enh["cpu"] == {"model": "EPYC 9254", "qty": 2}
    assert enh["memory"] == {"per_stick_gb": 32, "qty": 8, "type": "DDR5"}
    assert enh["drives"] == [{"capacity": "960G", "qty": 2, "interface": "NVMe"}]
    assert enh["gpu"] == [{"model": "H100", "qty": 8}]
    assert enh["psu"] == {"wattage": 2700, "qty": 2}
    assert "server_type" not in enh          # server_type 单独合并，不在 enhance schema
    assert "confidence" not in enh["cpu"]    # 元数据剥离
    assert "intent_summary" not in enh


# ============================================================
# apply_llm_merge —— 规则赢、只补缺
# ============================================================

def test_apply_llm_merge_fills_missing_but_rule_wins():
    ext = {"series": "Orion", "form": None, "keywords": ["9254"]}
    data = {
        "series": {"value": "Polaris", "confidence": 0.9, "source": "infer", "evidence": "x"},
        "form": {"value": "2U", "confidence": 0.9, "source": "text", "evidence": "x"},
        "server_type": {"value": "AI / 加速计算服务器", "confidence": 0.9, "source": "text", "evidence": "x"},
        "budget": {"value": 300000, "confidence": 0.9, "source": "text", "evidence": "x"},
    }
    with patch("app.services.requirement_intel_service._load_series_values",
               return_value=["Orion", "Polaris", "Intel", "工作站"]):
        changes = apply_llm_merge(ext, data, "AI 训练 2U 服务器", CATALOG)
    assert ext["form"] == "2U"                       # 规则缺失 → LLM 补
    assert ext["series"] == "Orion"                  # 规则已抽 → 不覆盖（LLM 说 Polaris 也不改）
    assert ext["server_type_name"] == "AI / 加速计算服务器"
    assert ext["budget"] == 300000
    assert any("form=2U" in c for c in changes)
    assert any("server_type=AI / 加速计算服务器" in c for c in changes)


def test_apply_llm_merge_server_type_not_in_whitelist_skipped():
    ext = {"keywords": []}
    data = {"server_type": {"value": "量子服务器", "confidence": 0.9, "source": "infer", "evidence": "x"}}
    changes = apply_llm_merge(ext, data, "服务器", CATALOG)
    assert "server_type_name" not in ext
    assert not any("server_type" in c for c in changes)


# ============================================================
# compute_coverage —— 覆盖度明细
# ============================================================

def test_compute_coverage():
    data = {
        "series": {"value": "Orion", "confidence": 0.9, "source": "text", "evidence": "e"},
        "gpu": [{"model": "H100", "qty": 8, "confidence": 0.9, "source": "text", "evidence": "e"}],
    }
    cov = compute_coverage(data, CATALOG)
    assert cov["filled"] == 2
    assert cov["total"] == 3
    assert cov["coverage_ratio"] == round(2 / 3, 2)
    assert "机箱形态" in cov["missing"]


def test_compute_coverage_flat_slot_counts_filled():
    # cpu 是扁平对象（无 value 键），qty=4 应视为已填
    spec_cat = {**CATALOG, "slots_spec": [
        {"key": "cpu", "label": "CPU", "level": "L0"},
        {"key": "gpu", "label": "GPU", "level": "L1"}]}
    data = {"cpu": {"qty": 4, "confidence": 0.7, "source": "text", "evidence": "四路"}}
    cov = compute_coverage(data, spec_cat)
    assert cov["filled"] == 1
    assert cov["total"] == 2


# ============================================================
# _model_grounded
# ============================================================

def test_model_grounded_variants():
    assert _model_grounded("EPYC 9254", "需要两颗 EPYC 9254", CATALOG) is True   # 原文出现
    assert _model_grounded("EPYC 9754", "AMD 平台", CATALOG) is True              # 家族词 epyc
    assert _model_grounded("RTX 4090", "游戏渲染", CATALOG) is True               # 家族词 rtx
    assert _model_grounded("XYZ-9000X", "一台服务器", CATALOG) is False           # 编造
    assert _model_grounded("", "随便", CATALOG) is True                           # 空 = 不校验
