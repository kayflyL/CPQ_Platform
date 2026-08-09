# -*- coding: utf-8 -*-
"""需求分析推理流核心逻辑单测（目录驱动引导 / 会话语义 / 明确度 / 信号抽取）。

跑法（backend 目录）：
  python -X utf8 -m pytest tests/test_requirement_intel.py -q
"""
import asyncio

from app.services.requirement_intel_service import _merge_clarify_text, _merge_clarify_defaults
from app.services import reasoning_executor as rex

def test_executor_select_baseline_no_nameerror():
    """线上 executor 节点回归（R9 修复）：select_baseline 走 build_variant_signals，
    曾因 reasoning_executor 漏导入抛 NameError → 前端卡机型选型节点。
    必须用 _dispatch（真实节点路径），golden 线性脚本路径覆盖不到。"""
    from app.repository.reasoning_flow_repo import _default_node_configs
    from app.services import reasoning_executor as rex

    async def _noop(_):
        return None

    async def _run():
        cfgs = _default_node_configs()
        ctx = {"requirement_text": """机箱:4U8卡机架式
CPU: AMD 9654 * 2
内存:DDR564G *8
硬盘:SATASSD480G*2
硬盘:Intel P5510 U.2NVME 3.84*2
RAID卡:9361-8i*1
网卡:100G双口MCX5*1
显卡:AMD R9700*8"""}
        await rex._dispatch("extract", ctx, cfgs["extract"], _noop)
        # 真实链路 extract 后接场景判定（窄化后类型/系列由 scene_decide 提供，不再从文本推断）
        await rex._dispatch("scene_decide", ctx, cfgs.get("scene_decide") or {}, _noop)
        payload = await rex._dispatch("select_baseline", ctx, cfgs["select_baseline"], _noop)
        return payload

    payload = asyncio.run(_run())
    assert payload.get("count", 0) >= 1  # 不再 NameError，且能出机型方案
    names = [m.get("name") for m in payload.get("matches") or []]
    assert any("直通" in n or "直连" in n for n in names)  # 8卡具体配置单 → 直通/直连排第一

def test_max_clarify_rounds_defined_and_synced():
    # M1 回归：两处 MAX_CLARIFY_ROUNDS 必须都有定义且一致。
    # 曾因编辑把赋值行替换成注释丢失（requirement_intel_service 漏修），
    # 导致 supplement 请求在 round+1 处 NameError → pipeline 崩溃 → 前端挂旧反问 → 死循环。
    from app.services.requirement_intel_service import MAX_CLARIFY_ROUNDS as R_INTEL
    from app.services.reasoning_executor import MAX_CLARIFY_ROUNDS as R_EXEC
    assert R_INTEL == 6
    assert R_EXEC == 6
    assert R_INTEL == R_EXEC

# ============================================================
# _merge_clarify_text —— 会话累积语义（M1 1.1）
# ============================================================

def test_merge_new_conversation_clears_supplements():
    # 无 supplement、非 force_complete = 全新对话 → 无条件清空旧补充（修"重复上一轮"）
    full, acc = _merge_clarify_text(
        "我想要一台服务器", "我想要一台服务器",
        "补充：AI 训练 / 推理\n补充：A100 ×8", None, False)
    assert acc == ""
    assert full == "我想要一台服务器"

def test_merge_supplement_appends():
    full, acc = _merge_clarify_text(
        "我想要一台服务器", "我想要一台服务器",
        "补充：AI 训练 / 推理", {"text": "A100 ×8"}, False)
    assert acc == "补充：AI 训练 / 推理\n补充：A100 ×8"
    assert full == "我想要一台服务器\n补充：AI 训练 / 推理\n补充：A100 ×8"

def test_merge_force_complete_keeps_supplements():
    # 点跳过 = 用当前已答信息出方案 → 保留已累积补充
    full, acc = _merge_clarify_text(
        "我想要一台服务器", "我想要一台服务器",
        "补充：AI 训练 / 推理\n补充：A100 ×8", None, True)
    assert acc == "补充：AI 训练 / 推理\n补充：A100 ×8"

def test_merge_original_changed_clears_old_supplements():
    # 原文变了 = 新一轮提问 → 旧补充丢弃，只留本轮
    full, acc = _merge_clarify_text(
        "换个需求", "我想要一台服务器",
        "补充：AI 训练 / 推理", {"text": "4U 机架"}, False)
    assert acc == "补充：4U 机架"
    assert "AI 训练" not in full

def test_merge_supplement_budget_only_keeps_acc():
    full, acc = _merge_clarify_text(
        "我想要一台服务器", "我想要一台服务器",
        "补充：AI 训练 / 推理", {"text": None, "budget": 100000}, True)
    assert acc == "补充：AI 训练 / 推理"

# ============================================================
# _is_default_reply —— "不确定/你推荐" = 放弃指定（目录引导里走推荐默认）
# ============================================================

def test_is_default_reply():
    assert rex._is_default_reply("还没定") is True
    assert rex._is_default_reply("你推荐就行") is True
    assert rex._is_default_reply("内存越大越好") is True
    assert rex._is_default_reply("不限预算") is True
    assert rex._is_default_reply("A100 ×8") is False
    assert rex._is_default_reply("") is False

# ============================================================
# _merge_clarify_defaults —— 答"还没定"跳过当前字段（M1 1.3b）
# ============================================================

def test_merge_defaults_new_conversation_clears():
    out = _merge_clarify_defaults(
        ["GPU型号"], ["GPU型号"], None, is_new_conversation=True)
    assert out == []

def test_merge_defaults_default_reply_marks_last_asked():
    out = _merge_clarify_defaults(
        ["GPU型号"], ["GPU型号"], {"text": "还没定"}, is_new_conversation=False)
    assert "GPU型号" in out

def test_merge_defaults_concrete_reply_keeps_unchanged():
    out = _merge_clarify_defaults(
        ["GPU型号"], ["GPU型号"], {"text": "NVIDIA H100 80G ×8"}, is_new_conversation=False)
    assert out == ["GPU型号"]

def test_merge_defaults_no_last_asked_keeps_unchanged():
    out = _merge_clarify_defaults(
        ["GPU型号"], [], {"text": "还没定"}, is_new_conversation=False)
    assert out == ["GPU型号"]

def test_merge_defaults_dedup():
    out = _merge_clarify_defaults(
        ["GPU型号"], ["GPU型号", "CPU型号"], {"text": "你推荐"}, is_new_conversation=False)
    assert out == ["GPU型号", "CPU型号"]

# ============================================================
# 目录驱动引导（catalog_guide）—— 反问内容 100% 来自产品目录
# ============================================================

from app.services.catalog_guide import (
    advance_stage, build_question, load_ask_config, match_option,
    is_default_reply, kp_categories_for_type_name,
)

def _fake_catalog():
    types = [
        {"id": 1, "name": "通用计算服务器"},
        {"id": 2, "name": "AI / 加速计算服务器"},
        {"id": 3, "name": "存储服务器"},
    ]
    models = {
        "通用计算服务器": [
            {"id": 6, "name": "ES22V3-P", "lifecycle_status": "new"},
            {"id": 8, "name": "ZS22V2-P", "lifecycle_status": "active"},
        ],
        "AI / 加速计算服务器": [
            {"id": 16, "name": "ESA24V3-P", "lifecycle_status": "active"},
            {"id": 17, "name": "ZSA24V2-P", "lifecycle_status": "active"},
        ],
        "存储服务器": [
            {"id": 10, "name": "ZS25V2-P", "lifecycle_status": "active"},
        ],
    }
    return types, models

ASK_CFG = load_ask_config(None)
FLOW_CFG = {
    "match_kp": {
        "type_packages": [
            {"type_keyword": "AI", "categories": ["CPU", "GPU", "Memory", "HDD/SSD"]},
            {"type_keyword": "存储", "categories": ["CPU", "Memory", "HDD/SSD", "Raid card"]},
            {"type_keyword": "通用", "categories": ["CPU", "Memory", "HDD/SSD"]},
        ],
    },
}

def _empty_state():
    return {"stage": "", "type_name": None, "model_id": None, "offered": {}}

def test_match_option_normalized():
    assert match_option("AI / 加速计算服务器", ["AI / 加速计算服务器", "通用计算服务器"]) == "AI / 加速计算服务器"
    assert match_option("存储服务器", ["通用计算服务器", "存储服务器"]) == "存储服务器"
    assert match_option("随便", ["通用计算服务器"]) is None

def test_is_default_reply_catalog():
    assert is_default_reply("你推荐") is True
    assert is_default_reply("不确定") is True
    assert is_default_reply("你定") is True
    assert is_default_reply("AI / 加速计算服务器") is False
    assert is_default_reply("") is False

def test_advance_type_selected_goes_to_model():
    types, models = _fake_catalog()
    out = advance_stage(_empty_state(), "存储服务器", ASK_CFG, types, models)
    assert out["stage"] == "model"
    assert out["type_name"] == "存储服务器"
    assert out["model_id"] is None

def test_advance_type_default_done_with_recommended():
    # 客户答"你推荐"→ 用推荐类型 + 代表性机型，直接 done（不再追问）
    types, models = _fake_catalog()
    out = advance_stage({"stage": "type", **{k: None for k in ("type_name", "model_id")}, "offered": {}},
                        "你推荐", ASK_CFG, types, models)
    assert out["stage"] == "done"
    assert out["type_name"] == "通用计算服务器"   # recommended_type 空 → 第一个
    assert out["model_id"] == 6                 # 通用计算第一个机型（representative 空 → 第一个）

def test_advance_type_spec_reply_skips_to_done():
    # 客户在选类型环节直接贴规格 → 跳层级 done（extract 拾取规格）
    types, models = _fake_catalog()
    out = advance_stage(_empty_state(), "CPU：EPYC 9554 ×2 内存：64G ×8", ASK_CFG, types, models)
    assert out["stage"] == "done"

def test_advance_type_unrecognized_uses_recommended_then_asks_model():
    types, models = _fake_catalog()
    out = advance_stage(_empty_state(), "就要个便宜的", ASK_CFG, types, models)
    assert out["stage"] == "model"
    assert out["type_name"] == "通用计算服务器"

def test_advance_model_selected_goes_to_kp():
    types, models = _fake_catalog()
    st = {"stage": "model", "type_name": "AI / 加速计算服务器", "model_id": None, "offered": {}}
    out = advance_stage(st, "ESA24V3-P", ASK_CFG, types, models)
    assert out["stage"] == "kp"
    assert out["model_id"] == 16

def test_advance_model_default_done():
    types, models = _fake_catalog()
    st = {"stage": "model", "type_name": "AI / 加速计算服务器", "model_id": None, "offered": {}}
    out = advance_stage(st, "你推荐", ASK_CFG, types, models)
    assert out["stage"] == "done"
    assert out["model_id"] == 16  # AI 类型第一个在售机型

def test_advance_kp_any_reply_done():
    # KP 环节任何实质回复都视为按格式填了（规格由 extract 拾取，缺的字段方案卡标注需手填）
    types, models = _fake_catalog()
    st = {"stage": "kp", "type_name": "AI / 加速计算服务器", "model_id": 16, "offered": {}}
    out = advance_stage(st, "CPU：EPYC 9554 ×2", ASK_CFG, types, models)
    assert out["stage"] == "done"
    assert out["model_id"] == 16

def test_build_question_type_lists_real_types():
    types, models = _fake_catalog()
    q, opts, offered, fmt = build_question("", _empty_state(), ASK_CFG, types, models, None)
    assert "通用计算服务器" in opts
    assert "AI / 加速计算服务器" in opts
    assert "存储服务器" in opts
    assert "不确定/你推荐" in opts
    assert offered["type"]  # 记录本轮推的选项（供下轮匹配）
    assert "服务器类型" in q

def test_build_question_model_lists_real_models():
    types, models = _fake_catalog()
    st = {"stage": "model", "type_name": "AI / 加速计算服务器", "model_id": None, "offered": {}}
    q, opts, offered, fmt = build_question("model", st, ASK_CFG, types, models, None)
    assert "ESA24V3-P" in opts and "ZSA24V2-P" in opts
    assert "不确定/你推荐" in opts
    assert "通用计算服务器" not in opts  # 只推该类型下的机型

def test_build_question_kp_gives_format_and_categories():
    types, models = _fake_catalog()
    st = {"stage": "kp", "type_name": "AI / 加速计算服务器", "model_id": 16, "offered": {}}
    q, opts, offered, fmt = build_question("kp", st, ASK_CFG, types, models, FLOW_CFG)
    assert "CPU：型号 ×数量" in q
    assert "GPU：型号 ×数量" in q
    assert "GPU" in fmt
    assert "可选项配件品类" in q

def test_kp_categories_from_flow_config():
    cats = kp_categories_for_type_name("存储服务器", FLOW_CFG)
    assert "Raid card" in cats and "HDD/SSD" in cats

# ============================================================
# clarity_check —— 目录引导 done / 默认回答 / force_complete
# ============================================================

def _stub_clarity(monkeypatch, missing=None):
    import app.services.clarity_evaluator as ce
    missing = missing or ["GPU型号", "系列", "形态", "用途", "预算"]

    def fake_evaluate(ext, config=None):
        return "unclear", list(missing), {"coverage": "0/10", "slots": [], "missing_l0": missing}

    monkeypatch.setattr(ce, "evaluate_slot_coverage", fake_evaluate)

    async def no_broadcast(payload):
        pass

    return no_broadcast

def test_clarity_check_catalog_done_is_explicit(monkeypatch):
    # 目录引导走完（type→model→kp）→ 视为信息足够，直接出方案
    no_broadcast = _stub_clarity(monkeypatch)
    ctx = {"requirement_text": "我想要一台服务器",
           "ext": {}, "budget": None, "clarify_round": 3,
           "force_complete": False, "clarify_defaults": [],
           "catalog_stage": "done"}
    payload = asyncio.run(rex._dispatch("clarity_check", ctx, {}, no_broadcast))
    assert payload["level"] == "explicit"
    assert payload["missing_fields"] == []
    assert ctx["clarity_explain"].get("catalog_complete") is True

def test_clarity_check_defaults_remove_only_marked_fields(monkeypatch):
    no_broadcast = _stub_clarity(monkeypatch)
    ctx = {"requirement_text": "我想要一台服务器\n补充：还没定",
           "ext": {}, "budget": None, "clarify_round": 1, "force_complete": False,
           "clarify_defaults": ["GPU型号"]}
    payload = asyncio.run(rex._dispatch("clarity_check", ctx, {}, no_broadcast))
    assert payload["level"] == "unclear"
    assert "GPU型号" not in payload["missing_fields"]
    assert "系列" in payload["missing_fields"]

def test_clarity_check_defaults_all_satisfied_explicit(monkeypatch):
    no_broadcast = _stub_clarity(monkeypatch)
    ctx = {"requirement_text": "我想要一台服务器\n补充：还没定",
           "ext": {}, "budget": None, "clarify_round": 3, "force_complete": False,
           "clarify_defaults": ["GPU型号", "系列", "形态", "用途", "预算"]}
    payload = asyncio.run(rex._dispatch("clarity_check", ctx, {}, no_broadcast))
    assert payload["level"] == "explicit"
    assert payload["missing_fields"] == []
    assert ctx["clarity_explain"].get("defaults_satisfied") is True

def test_clarity_check_force_complete_still_works(monkeypatch):
    no_broadcast = _stub_clarity(monkeypatch)
    ctx = {"requirement_text": "我想要一台服务器\n补充：还没定",
           "ext": {}, "budget": None, "clarify_round": 0, "force_complete": True,
           "clarify_defaults": []}
    payload = asyncio.run(rex._dispatch("clarity_check", ctx, {}, no_broadcast))
    assert payload["level"] == "partial"
    assert payload["missing_fields"] == []
    assert ctx["clarity_capped"] is True

# ============================================================
# ask_user —— 目录驱动发问（need_input 带真实目录选项 + 格式模板）
# ============================================================

def test_ask_user_type_question_broadcast(monkeypatch):
    import app.services.catalog_guide as cg
    monkeypatch.setattr(cg, "load_catalog", _fake_catalog)

    async def collect(payload):
        collected.append(payload)

    collected = []
    ctx = {"requirement_text": "我想要一台服务器", "catalog_stage": "",
           "catalog_state": _empty_state(), "flow_configs": FLOW_CFG,
           "clarify_round": 0, "clarity_capped": False, "missing_fields": []}
    payload = asyncio.run(rex._dispatch("ask_user", ctx, {}, collect))
    assert payload["question"]
    msg = collected[0]
    assert msg["type"] == "need_input"
    assert "通用计算服务器" in msg["options"]
    assert msg["stage"] == ""
    assert ctx["awaiting_input"] is True

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
    # 完整 4U AI 需求 → 10/10 槽位已填 → explicit，不反问
    from app.services.clarity_evaluator import evaluate_slot_coverage
    ext = {"categories": ["CPU", "Memory", "HDD/SSD", "GPU", "Network(NIC) requirement", "Raid card"],
           "qty_map": {"CPU": 2, "Memory": 24, "GPU": 2, "HDD/SSD": 6},
           "series": "Orion", "form": "4U",
           "cpu_signal": {"model": "9654"}, "mem_signal": {"type": "DDR5"},
           "drive_groups": [{"term": "1.92T"}], "gpu_groups": [{"tokens": ["A800"]}],
           "raid_groups": [{"model": "9560-16i"}], "psu_signal": {"wattage": 2700},
           "multi_spec_filters": {"Network(NIC) requirement": [{}]},
           "usage": "AI / 加速计算服务器"}
    level, missing, explain = evaluate_slot_coverage(ext)
    assert level == "explicit" and missing == []
    assert explain["coverage"] == "10/10"

def test_slot_coverage_sparse_partial():
    # 只给 2U+CPU → L0 缺 应用场景/内存 ≥ ask_threshold(2) → partial 反问
    from app.services.clarity_evaluator import evaluate_slot_coverage
    ext = {"categories": ["CPU"], "qty_map": {"CPU": 2}, "series": "Orion", "form": "2U"}
    level, missing, explain = evaluate_slot_coverage(ext)
    assert level == "partial"
    assert "应用场景" in missing and "内存" in missing

def test_slot_coverage_storage_default_ok():
    # 通用 2U 无盘：存储 default_ok → 不计数，explicit（系统给默认盘）
    from app.services.clarity_evaluator import evaluate_slot_coverage
    ext = {"categories": ["CPU", "Memory"], "qty_map": {"CPU": 2, "Memory": 8},
           "series": "Orion", "form": "2U",
           "cpu_signal": {"model": "9654"}, "mem_signal": {"type": "DDR5"}}
    level, missing, _ = evaluate_slot_coverage(ext)
    assert level == "explicit"

def test_parse_series_confirm():
    from app.services.requirement_intel_service import _parse_series_confirm
    offer = {"series": "Orion", "mode": "confirm"}
    assert _parse_series_confirm("是", offer) == "Orion"
    assert _parse_series_confirm("可以，就它", offer) == "Orion"
    assert _parse_series_confirm("不是，换一个", offer) == "__ask__"
    # Polaris 只配兆芯：说"海光"不再映射 Polaris（无对应系列 → None）；说"兆芯"才映射 Polaris
    assert _parse_series_confirm("我要兆芯", {}) == "Polaris"
    assert _parse_series_confirm("我要开胜", {}) == "Polaris"
    assert _parse_series_confirm("我要海光", {}) is None
    assert _parse_series_confirm("随便", {}) is None

def test_enrich_supplement_workload_label_maps_type():
    """工作负载标签（AI / 机器学习）→ 追加映射类型，理解节点才抽得到。"""
    from app.services.requirement_intel_service import _enrich_supplement_text
    cfg = {"llm_ask": {"workload_categories": [
        {"label": "AI / 机器学习", "desc": "训练还是推理？", "type": "AI / 加速计算服务器"},
    ]}}
    out = _enrich_supplement_text("AI / 机器学习", cfg)
    assert "AI / 加速计算服务器" in out

def test_enrich_supplement_scale_label_appends_parseable_spec():
    """分档标签（中型）→ 追加可解析规格（CPU：32核），理解才抽得到、不重复问。"""
    from app.services.requirement_intel_service import _enrich_supplement_text
    cfg = {"llm_ask": {"scale_tiers": {"CPU": [
        {"label": "小型", "recommend": "16核"},
        {"label": "中型", "recommend": "32核"},
    ]}}}
    out = _enrich_supplement_text("中型", cfg)
    assert "CPU：32核" in out
    # 自由文本原样返回
    assert _enrich_supplement_text("我要32G*8条内存", cfg) == "我要32G*8条内存"
    assert _enrich_supplement_text("2U机架式", cfg) == "2U机架式"

def test_enrich_supplement_multiple_matches_dedup():
    """同一回复命中多个分档时，追加内容去重、只追加一次。"""
    from app.services.requirement_intel_service import _enrich_supplement_text
    cfg = {"llm_ask": {"scale_tiers": {"内存": [
        {"label": "标准", "recommend": "32G*8条"},
        {"label": "标准", "recommend": "32G*8条"},
    ]}}}
    out = _enrich_supplement_text("标准", cfg)
    assert out.count("内存：32G*8条") == 1
