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


def _extract(text):
    from app.services.requirement_intel_service import extract_keywords
    return extract_keywords(
        text, lexicon=_TEST_LEXICON, keyword_limit=12,
        qty_units=[{"unit": "卡", "category": "GPU"}, {"unit": "条", "category": "Memory"},
                   {"unit": "颗", "category": "CPU"}, {"unit": "块", "category": "CPU"}],
        qty_multipliers=["*", "×"],
        model_token_regex=r"^(?=.*[0-9])([A-Za-z]{2,}[0-9A-Za-z\-]{2,}|[A-Za-z][0-9]{3,}|[0-9]{4,}|[0-9][0-9A-Za-z.\-]{2,})$",
    )


def test_qty_parse_free_text_config1():
    # 典型配置1 自由文本：×N 后跟容量/型号 → 数量在 × 前，不得当后缀绑错品类
    ext = _extract('4U AI服务器，8×NVIDIA RTX 5090 32G 涡轮卡，2×AMD EPYC 9745，'
                   '16×64G DDR5 5600，2×7.68T NVMe SSD，2×960G SATA SSD，'
                   'LSI 9560-8i RAID卡，25G双口网卡，预算50万')
    assert ext["qty_map"] == {"GPU": 8, "CPU": 2, "Memory": 16, "HDD/SSD": 2}
    assert ext["qty_per_token"].get("9745") == 2   # CPU 型号不得被 16×64G 串扰
    assert ext["qty_per_token"].get("5090") == 8
    assert ext["qty_per_token"].get("960g") == 2   # 容量 token 绑对数量


def test_qty_parse_format_guided():
    # 目录引导的格式填写（容量 ×条数 / 型号 ×数量）
    ext = _extract('4U AI服务器，内存：64G ×16，CPU：AMD EPYC 9745 ×2，GPU：NVIDIA RTX 5090 ×8，'
                   '硬盘：7.68T NVMe ×2，960G SATA ×2，RAID：LSI 9560-8i，预算50万')
    assert ext["qty_map"] == {"Memory": 16, "CPU": 2, "GPU": 8, "HDD/SSD": 2}
    assert ext["qty_per_token"].get("5090") == 8
    assert ext["qty_per_token"].get("960g") == 2


def test_qty_parse_capacity_multiple():
    # 8×32G DDR5 → 8 条（旧 bug：×32 被当 32 绑定，或 64 被绑到 CPU）
    ext = _extract('2U 双路 EPYC 9554，8×32G DDR5 内存，2×960G SSD，预算10万')
    assert ext["qty_map"].get("Memory") == 8
    assert ext["qty_map"].get("HDD/SSD") == 2
    assert ext["qty_per_token"].get("32g") == 8


def test_mem_signal_qty_x_cap():
    # "16×64G"（条数×单条容量）→ 总量 1024（旧版只读到 64）
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("内存：16×64G DDR5 5600")
    assert s is not None and s["total_gb"] == 1024
    # 正序 "64G ×16" 保持
    s2 = _extract_mem_signal("内存：64G ×16")
    assert s2 is not None and s2["total_gb"] == 1024


# ============================================================
# 盘组解析（多盘场景）—— 每段「容量+接口+数量」独立成组
# ============================================================

def test_extract_drive_groups_multi_drive():
    from app.services.requirement_intel_service import _extract_drive_groups
    groups = _extract_drive_groups(
        "2×7.68T NVMe SSD，2×960G SATA SSD", {"7.68t": 2, "960g": 2})
    assert groups == [
        {"term": "7.68T", "qty": 2, "kind": "NVMe", "media": "SSD"},   # media 介质信号（R12/I58）
        {"term": "960G", "qty": 2, "kind": "SATA", "media": "SSD"},
    ]


def test_extract_drive_groups_no_capacity_skipped():
    from app.services.requirement_intel_service import _extract_drive_groups
    # "12盘位"/"硬盘背板" 不是具体盘配置 → 不产生盘组
    assert _extract_drive_groups("4U 12盘位，带硬盘背板", {}) == []
    # 内存容量段（无盘关键字）也不产生盘组
    assert _extract_drive_groups("16×64G DDR5 5600", {"64g": 16}) == []


def test_extract_drive_groups_qty_default():
    from app.services.requirement_intel_service import _extract_drive_groups
    # 无数量 → 默认 1；接口不明 → None
    assert _extract_drive_groups("480G SSD", {}) == [{"term": "480G", "qty": 1, "kind": "SATA", "media": "SSD"}]


# ============================================================
# GPU/内存多规格分组 —— 每段独立成组 + 上下文延续
# ============================================================

def test_extract_gpu_groups_multi():
    from app.services.requirement_intel_service import _extract_gpu_groups, MODEL_TOKEN_PATTERN
    qpt = {"5090": 8, "r9700": 4, "h100": 2}
    g = _extract_gpu_groups(
        "8×NVIDIA RTX 5090 32G 涡轮卡，4×AMD R9700", qpt, ["gpu", "rtx", "h100"], MODEL_TOKEN_PATTERN)
    assert g == [
        {"tokens": ["RTX 5090"], "qty": 8, "cap": 32},   # 复合型号 + 显存容量（R10/I50）
        {"tokens": ["R9700"], "qty": 4},                 # 无 GPU 标签但紧跟上一段 → 延续
    ]


def test_extract_gpu_groups_context_break():
    from app.services.requirement_intel_service import _extract_gpu_groups, MODEL_TOKEN_PATTERN
    # CPU/硬盘标签中断 GPU 延续
    g = _extract_gpu_groups(
        "GPU：NVIDIA H100 ×2，CPU：AMD EPYC 9654 ×2，硬盘：2×960G SATA",
        {"h100": 2, "9654": 2, "960g": 2}, ["gpu", "rtx", "h100"], MODEL_TOKEN_PATTERN)
    assert g == [{"tokens": ["H100"], "qty": 2}]


def test_extract_mem_groups_multi_with_continuation():
    from app.services.requirement_intel_service import _extract_mem_groups
    g = _extract_mem_groups("内存：64G ×8，32G ×8", {"64g": 8, "32g": 8})
    assert g == [{"term": "64G", "qty": 8}, {"term": "32G", "qty": 8}]


def test_extract_mem_groups_single():
    from app.services.requirement_intel_service import _extract_mem_groups
    assert _extract_mem_groups("16×64G DDR5 5600", {"64g": 16}) == [{"term": "64G", "qty": 16}]
    # 非内存段不产生
    assert _extract_mem_groups("硬盘：2×960G SATA", {"960g": 2}) == []


# ============================================================
# 型号家族词自动同步（model_family_sync）—— 保守抽取、拒绝噪声
# ============================================================

def test_candidate_words_keeps_real_models():
    from app.services.model_family_sync import _candidate_words
    # 字母开头 + 含数字 + 4-10 位 → 真实型号 token
    assert "h100" in _candidate_words("NVIDIA H100 80G")
    assert "r9700" in _candidate_words("AMD R9700")
    assert "kh50000" in _candidate_words("KH50000 48C")
    assert "rtx5090" in _candidate_words("NVIDIA RTX5090 涡轮卡")
    # 品牌/通用词（无数字）与容量/纯数字（32G/5090/5090 纯数字开头）不收录
    words = _candidate_words("NVIDIA RTX5090 涡轮卡 server edition 32G 5090")
    assert "nvidia" not in words and "server" not in words and "edition" not in words
    assert "5090" not in words and "32g" not in words


# ============================================================
# _extract_mem_signal —— DDR564G 代际数字误读修复（真BUG）
# ============================================================

def test_mem_signal_ddr5_64g_x8():
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("内存:DDR564G*8")
    assert s is not None
    assert s["type"] == "DDR5"
    assert s["total_gb"] == 512


def test_mem_signal_ddr4_32g_x4():
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("内存 DDR432G*4")
    assert s["type"] == "DDR4"
    assert s["total_gb"] == 128


def test_mem_signal_plain_cap_mul():
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("内存:64G*8")
    assert s["total_gb"] == 512


def test_mem_signal_spaced_ddr():
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("内存 DDR5 64G * 8")
    assert s["type"] == "DDR5"
    assert s["total_gb"] == 512


def test_mem_signal_total_only():
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("内存 512G")
    assert s["total_gb"] == 512


def test_mem_signal_ignores_disk_capacity():
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("硬盘:U.21.92T*2\n硬盘:SATA SSD 480G*2\n内存:DDR564G*8")
    assert s is not None
    assert s["total_gb"] == 512


# ============================================================
# 2026-08-03 第一轮训练修复回归：字段分段 / 无单位内存 / 多盘不粘连
# ============================================================

def test_split_requirement_fields_single_line():
    # 聊天/表格粘贴把多行折成单行：冒号字段必须切成独立段（防硬盘容量污染内存解析）
    from app.services.requirement_intel_service import _split_requirement_fields
    fields = _split_requirement_fields(
        "机箱：2U机架式 CPU：AMD 9654 * 2 内存：DDR5 32 * 16 硬盘：SATA SSD 960G * 2 "
        "硬盘：U.2 NVME 7.68T * 2 RAID卡：9560-8I * 1 网卡：CX5 25G 双口 含光模块 * 2 电源：根据功耗选择")
    assert fields == [
        "机箱：2U机架式",
        "CPU：AMD 9654 * 2",
        "内存：DDR5 32 * 16",
        "硬盘：SATA SSD 960G * 2",
        "硬盘：U.2 NVME 7.68T * 2",
        "RAID卡：9560-8I * 1",
        "网卡：CX5 25G 双口 含光模块 * 2",
        "电源：根据功耗选择",
    ]


def test_mem_signal_unitless_cap_x_qty():
    # "内存：DDR5 32 * 16"（无 GB 后缀）→ 大数=容量、小数=条数 → 512GB
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("内存：DDR5 32 * 16")
    assert s is not None
    assert s["type"] == "DDR5"
    assert s["total_gb"] == 512


def test_mem_signal_single_line_disk_not_contaminated():
    # 单行粘连：内存行后面跟硬盘行，960G*2 不得再被算进内存总量（旧 bug → 1920GB → 64G×30）
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal(
        "机箱：2U机架式 CPU：AMD 9654 * 2 内存：DDR5 32 * 16 硬盘：SATA SSD 960G * 2 "
        "硬盘：U.2 NVME 7.68T * 2 RAID卡：9560-8I * 1 网卡：CX5 25G 双口 含光模块 * 2 电源：根据功耗选择")
    assert s["total_gb"] == 512


def test_mem_groups_unitless_no_crash():
    # P0 崩溃回归：内存段无 G/T 容量（"内存：DDR5 32 * 16"）不再 AttributeError
    from app.services.requirement_intel_service import _extract_mem_groups
    g = _extract_mem_groups("内存：DDR5 32 * 16", {"32g": 16})
    assert g == [{"term": "32G", "qty": 16}]
    # 反序无单位："16 * 32"（16 条 × 32G）同样归一
    g2 = _extract_mem_groups("内存：16 * 32", {})
    assert g2 == [{"term": "32G", "qty": 16}]


def test_extract_drive_groups_single_line_multi_drive():
    # 单行粘连：两条硬盘字段都解析出来，且接口各自正确（旧 bug：只出 960G 且被误判 NVMe）
    from app.services.requirement_intel_service import _extract_drive_groups
    groups = _extract_drive_groups(
        "硬盘：SATA SSD 960G * 2 硬盘：U.2 NVME 7.68T * 2", {"960g": 2, "7.68t": 2})
    assert groups == [
        {"term": "960G", "qty": 2, "kind": "SATA", "media": "SSD"},
        {"term": "7.68T", "qty": 2, "kind": "NVMe"},
    ]


def test_extract_drive_groups_kind_not_contaminated():
    # 同段含两种接口词时，接口按容量就近判定（960G 是 SATA，不得因段内有 NVME 变 NVMe）
    from app.services.requirement_intel_service import _extract_drive_groups
    groups = _extract_drive_groups("硬盘：SATA SSD 960G * 2，U.2 NVME 7.68T * 2", {"960g": 2, "7.68t": 2})
    assert groups == [
        {"term": "960G", "qty": 2, "kind": "SATA", "media": "SSD"},
        {"term": "7.68T", "qty": 2, "kind": "NVMe"},
    ]


# ============================================================
# 2026-08-03 第二轮训练修复回归：功耗/预算误判、GPU 线缆、盘组归一、内存延续污染、RAID 级别
# ============================================================

def test_budget_ignores_uppercase_wattage():
    # "360W"（CPU TDP）不是预算——大写 W=瓦，小写 w=万（"20w"）
    from app.services.requirement_intel_service import _extract_budget
    assert _extract_budget("2* AMD EPYC 9554 ... 360W") is None
    assert _extract_budget("2* 2000W 80 Plus Platinum") is None
    assert _extract_budget("预算 20w") == 200000.0
    assert _extract_budget("预算20万") == 200000.0
    assert _extract_budget("预算200k") == 200000.0


def test_psu_signal_prefers_explicit_context():
    # "2* 2000W 80 Plus Platinum" 应取 2000（不能因 CPU 行 "360W" 在前而取 360）
    from app.services.requirement_intel_service import _extract_psu_signal
    text = "2* AMD EPYC 9554 360W\n2* 2000W 80 Plus Platinum"
    assert _extract_psu_signal(text) == {"wattage": 2000, "qty": 2}  # 2* 2000W → 2 颗电源
    # 无上下文且多个 W 数字 → 不猜（360W 是 CPU TDP）
    assert _extract_psu_signal("CPU 360W 双路，机箱 1300W") is None
    # 显式电源上下文 + 单数字
    assert _extract_psu_signal("电源1300W") == {"wattage": 1300}
    assert _extract_psu_signal("1300W电源") == {"wattage": 1300}


def test_drive_groups_capacity_with_space_and_or():
    # "7.68 TB"（空格）归一为 7.68T 且数量 4；"1.6T or 1.92T" 只出一组（备选不重复）
    from app.services.requirement_intel_service import _extract_drive_groups
    groups = _extract_drive_groups(
        "2* 480GB SATA SSD\n4* 7.68 TB Enterprise-class SSD\n1* 1.6T or 1.92T Enterprise-class storage",
        {"480gb": 2, "7.68": 4, "1.6t": 1, "1.92t": 1})
    assert groups == [
        {"term": "480G", "qty": 2, "kind": "SATA", "media": "SSD"},
        {"term": "7.68T", "qty": 4, "kind": None, "media": "SSD"},
        {"term": "1.6T", "qty": 1, "kind": None},
    ]


def test_gpu_groups_power_cable_not_gpu():
    # "2* H100 power cable" 是线缆不是 GPU（R2：GPU 组不因 H100 触发词被线缆行污染）
    from app.services.requirement_intel_service import _extract_gpu_groups, MODEL_TOKEN_PATTERN
    g = _extract_gpu_groups(
        "1* NVIDIA H100 PCIe 80GB\n2* H100 power cable",
        {"h100": 1}, ["gpu", "rtx", "h100"], MODEL_TOKEN_PATTERN)
    assert g == [{"tokens": ["H100"], "qty": 1, "cap": 80}]  # 显存容量信号（R10/I50）


def test_mem_groups_not_polluted_by_gpu_nic():
    # 内存延续不吞 GPU（H100 80GB）与网卡（25G SFP28）段；"Frame" 含 "ram" 子串不误触发
    from app.services.requirement_intel_service import _extract_mem_groups
    text = ("16* 32GB DDR5 ECC RDIMM（512GB）\n1* NVIDIA H100 PCIe 80GB\n"
            "2* ConnectX-6 Dx dual 25G SFP28 (support Jumbo Frame (MTU)")
    g = _extract_mem_groups(text, {"32gb": 16, "80gb": 1, "25g": 2})
    assert g == [{"term": "32G", "qty": 16}]  # 容量归一 32GB→32G


def test_raid_level_not_raid_card_category():
    # "（RAID1）" 是 RAID 级别不是阵列卡需求；"RAID卡：9560-8i" 才触发 Raid card
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    kw = dict(lexicon=cat_lex, series_keyword_map=series_map, usage_keyword_map=usage_map,
              form_keyword_map=form_map, chassis_lexicon=chassis_lex,
              spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
              qty_multipliers=cfg.get("qty_multipliers"), model_token_regex=cfg.get("model_token_regex"))
    ext1 = extract_keywords("2* 480GB SATA SSD （RAID1）", **kw)
    assert "Raid card" not in ext1["categories"]
    ext2 = extract_keywords("RAID卡：LSI 9560-8i", **kw)
    assert "Raid card" in ext2["categories"]


# ============================================================
# 2026-08-03 第三轮训练修复回归：CPU TDP 不当作电源、远距内存数量、
# RAID 卡段不当作硬盘、跨段数量、容量归一
# ============================================================

def test_psu_signal_rejects_cpu_tdp_context():
    # "3.1GHz/256MB 缓存/360W" 的 360W 是 CPU TDP，不得当电源（R3 修）
    from app.services.requirement_intel_service import _extract_psu_signal
    assert _extract_psu_signal("CPU:AMD Genoa 9554,3.1GHz/64 物理核/ 256MB 缓存/ 360W") is None
    assert _extract_psu_signal("电源要求1300W") == {"wattage": 1300}
    assert _extract_psu_signal("2* 2000W 80 Plus Platinum") == {"wattage": 2000, "qty": 2}


def test_mem_signal_far_qty():
    # "64GB DDR5-5600B RDIMM服务器内存*24"：*24 在内存字样后 → 总量 1536（R3 修）
    from app.services.requirement_intel_service import _extract_mem_signal
    s = _extract_mem_signal("内存:64GB DDR5-5600B RDIMM服务器内存*24")
    assert s["total_gb"] == 1536
    assert s["speed"] == 5600


def test_drive_groups_skip_raid_card_segment():
    # "LSI 9560-8i 12Gb SAS RAID 卡" 的 12Gb 是 SAS 速率，不是硬盘容量（R3 修）
    from app.services.requirement_intel_service import _extract_drive_groups
    groups = _extract_drive_groups(
        "RAID 列卡: LSI 9560-8i 12Gb SAS RAID 卡, 8 个 SAS 、4GB 缓存、PCIe4.0",
        {"12g": 1})
    assert groups == []


def test_drive_groups_qty_across_segment():
    # 容量在段1、数量 *2 在段2（"960GB企业级SSD，2.5寸热插拔*2"）→ 960G ×2（R3 修）
    from app.services.requirement_intel_service import _extract_drive_groups
    groups = _extract_drive_groups("系统固态硬盘:960GB企业级SSD，2.5寸热插拔*2", {"960gb": 2})
    assert groups == [{"term": "960G", "qty": 2, "kind": "SATA", "media": "SSD"}]


def test_mem_groups_term_normalized_and_qty():
    # "64GB DDR5-5600B RDIMM服务器内存*24" → {64G, 24}（容量归一 + 就近数量，R3 修）
    from app.services.requirement_intel_service import _extract_mem_groups
    g = _extract_mem_groups("内存:64GB DDR5-5600B RDIMM服务器内存*24", {"ddr5-5600b": 24})
    assert g == [{"term": "64G", "qty": 24}]
    # 前缀式 "16* 32GB" → 数量回退 32gb
    g2 = _extract_mem_groups("内存:16* 32GB DDR5", {"32gb": 16})
    assert g2 == [{"term": "32G", "qty": 16}]


# ============================================================
# 2026-08-03 第四轮训练修复回归：小写 x 乘号、2TB@128G each、bays 能力不配盘
# ============================================================

def test_qty_parse_lowercase_x_multiplier():
    # "2x 32 core 9005series of AMD EPYC" → CPU ×2（x 是乘号，32 是核数不是数量）
    # "2 x 25 GB SFP28" → 25 是速率不是内存数量；"RTX 5090" 的 x 在单词内不算乘号
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    kw = dict(lexicon=cat_lex, series_keyword_map=series_map, usage_keyword_map=usage_map,
              form_keyword_map=form_map, chassis_lexicon=chassis_lex,
              spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
              qty_multipliers=cfg.get("qty_multipliers"), model_token_regex=cfg.get("model_token_regex"))
    ext = extract_keywords(
        "2x 32 core 9005series of AMD EPYC, (2TB Memory RDIMM@128 GB each), 2 x 25 GB SFP28", **kw)
    assert ext["qty_map"].get("CPU") == 2
    assert ext["qty_map"].get("Memory") in (None, 16)  # 不得是 25
    # I20：2 x 25 GB SFP28 的 2 是端口数不是卡数 → sfp28 不进 qty_per_token（NIC 行端口解析出双口卡×1）
    assert ext["qty_per_token"].get("sfp28") is None
    # RTX 的 x 不是乘号
    ext2 = extract_keywords("8×NVIDIA RTX 5090 32G 涡轮卡", **kw)
    assert ext2["qty_map"].get("GPU") == 8
    assert ext2["qty_map"].get("GPU") != 5090


def test_mem_group_from_each_format():
    # "2TB Memory RDIMM@128 GB each" → 每根 128G、数量 16（总量÷每根）
    from app.services.requirement_intel_service import _mem_group_from_each, _extract_mem_signal
    assert _mem_group_from_each("(2TB Memory RDIMM@128 GB each)") == {"term": "128G", "qty": 16}
    s = _extract_mem_signal("(2TB Memory RDIMM@128 GB each)")
    assert s["total_gb"] == 2048


def test_bays_capability_not_disk():
    # "12/24 bays HDDSupport of NVMe" 是机箱能力描述，不是硬盘配置 → 不触发 HDD/SSD
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    ext = extract_keywords("Rackmount 2U, 12/24 bays HDDSupport of NVMe, Redundant PSU",
                           lexicon=cat_lex, series_keyword_map=series_map, usage_keyword_map=usage_map,
                           form_keyword_map=form_map, chassis_lexicon=chassis_lex,
                           spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
                           qty_multipliers=cfg.get("qty_multipliers"), model_token_regex=cfg.get("model_token_regex"))
    assert "HDD/SSD" not in ext["categories"]


def test_cores_unit_english():
    # spec rule unit=核 也能匹配英文 "32 core"（R4 修）
    from app.api.candidate_search import extract_spec_values
    rules = [{"category": "CPU", "spec_key": "Cores", "op": ">=", "value": 16, "unit": "核"}]
    out = extract_spec_values("2x 32 core 9005series of AMD EPYC", rules)
    assert out[0]["source"] == "extracted" and out[0]["value"] == 32.0



# ============================================================
# 2026-08-03 第五轮训练修复回归：后缀 *N 紧跟单位字母/数字、多网卡行、
# 接口+容量连写碎片、网卡字段分隔符 ";"
# ============================================================

def _prod_extract(text):
    """用生产 reasoning_flow 配置跑 extract_keywords（与 R4/R5 回归测试同款）。"""
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    return extract_keywords(text, lexicon=cat_lex, series_keyword_map=series_map,
                            usage_keyword_map=usage_map, form_keyword_map=form_map,
                            chassis_lexicon=chassis_lex,
                            spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
                            qty_multipliers=cfg.get("qty_multipliers"),
                            model_token_regex=cfg.get("model_token_regex"))


def test_qty_suffix_after_unit_letter_or_digit():
    # "3.0GHz* 2" / "32G* 4" / "RAID 0,1,10* 1" 的 *N 紧跟单位字母/数字，是后缀数量（R5 修）
    ext = _prod_extract("CPU: AMD 9124 26C/32T 3.0GHz* 2\n内存:DDR5 32G* 4\n"
                        "硬盘:SATASSD480G*2\n硬盘:U.2NVME7.68T*4\n阵列卡:RAID 0,1,10* 1")
    assert ext["qty_map"].get("CPU") == 2
    assert ext["qty_map"].get("Memory") == 4
    assert ext["qty_map"].get("HDD/SSD") == 2
    assert ext["qty_map"].get("Raid card") == 1
    assert ext["qty_per_token"].get("9124") == 2  # CPU 型号 token 绑对数量


def test_qty_suffix_excludes_wattage_and_capacity():
    # "2* 2000W" 的 2000 是瓦数不是数量（不得绑到前面品类）；"16×64G"/"2×7.68T" 仍是容量部分
    ext = _prod_extract("2* 2000W 80 Plus Platinum")
    assert "Network(NIC) requirement" not in ext["qty_map"]
    assert 2000 not in ext["qty_map"].values()
    ext2 = _prod_extract("16×64G DDR5 内存，2×7.68T NVMe SSD")
    assert ext2["qty_map"].get("Memory") == 16
    assert ext2["qty_map"].get("HDD/SSD") == 2


def test_nic_multi_line_spec_filters():
    # 需求同时多张网卡（千兆4口 / 25G双口 / 100G双口），按行各出一组 速率+端口 过滤（R5 修）
    ext = _prod_extract("网卡:千兆4口*1\n网卡:25G双口含光模块*1\n网卡;100G双口含光模块*1")
    nic = ext["multi_spec_filters"].get("Network(NIC) requirement")
    assert nic is not None and len(nic) == 3
    assert {f["filters"][0]["value"] for f in nic} == {"1G", "25G", "100G"}  # 三张卡速率齐
    assert all(f["filters"][1]["value"] in ("4", "2") for f in nic)          # 端口 4/2
    # 25G/100G 行要求含光模块 → name_contains 偏好；千兆4口行无
    by_speed = {f["filters"][0]["value"]: f for f in nic}
    assert by_speed["1G"].get("name_contains") is None
    assert by_speed["25G"].get("name_contains") == ["光模块"]
    assert by_speed["100G"].get("name_contains") == ["光模块"]
    assert by_speed["25G"]["filters"][1]["value"] == "2"


def test_nic_speed_after_semicolon_field_sep():
    # "网卡;100G双口含光模块*1" —— ";" 是字段分隔符不是行分隔符，100G 行不得被截断（R5 修）
    ext = _prod_extract("网卡;100G双口含光模块*1")
    nic = ext["multi_spec_filters"].get("Network(NIC) requirement")
    assert nic and len(nic) == 1
    assert nic[0]["filters"][0] == {"spec_key": "Link Speed", "op": "=", "value": "100G"}


def test_nic_phrase_with_trailing_trigger_word():
    # "25G双口网卡" —— 触发词在短语末尾，行片段要向前包含速率/端口（R5 修）
    ext = _prod_extract("25G双口网卡×1")
    nic = ext["multi_spec_filters"].get("Network(NIC) requirement")
    assert nic and nic[0]["filters"][0]["value"] == "25G"
    assert nic[0]["filters"][1]["value"] == "2"


def test_drive_cap_concat_token_not_model():
    # "SATASSD480G" / "U.2NVME7.68T" 是"接口+容量"连写碎片，不得当型号搜库报 unmatched（R5 修）
    ext = _prod_extract("硬盘:SATASSD480G*2 硬盘:U.2NVME7.68T*4")
    assert "SATASSD480G" not in ext["keywords"]
    assert "U.2NVME7.68T" not in ext["keywords"]
    # 盘组仍然正常解析
    assert [g["term"] for g in ext["drive_groups"]] == ["480G", "7.68T"]


def test_nic_line_concrete_model_kept_in_name_contains():
    # 用户写了具体网卡型号（CX5 / ConnectX-6）：型号进 name_contains 让 pick 精确匹配，
    # 不能被通用速率过滤（25G/100G）抢走（R5 保 R1/R4 行为）
    ext = _prod_extract("网卡：CX5 25G 双口 含光模块 * 2")
    nic = ext["multi_spec_filters"].get("Network(NIC) requirement")
    assert nic and "cx5" in nic[0]["name_contains"]
    assert "光模块" in nic[0]["name_contains"]
    ext2 = _prod_extract("2* ConnectX-6 Dx dual 25G SFP28")
    nic2 = ext2["multi_spec_filters"].get("Network(NIC) requirement")
    assert nic2 and any("connectx-6" in (t or "") for t in nic2[0]["name_contains"])


def test_pure_decimal_capacity_fragment_not_keyword():
    # "7.68T" 被 jieba/分词拆出的纯小数 "7.68" 不得当型号关键字——否则 stage1 搜库命中整件
    # 与盘组重复出两行 7.68T（R1 遗留，R5 顺手修）
    ext = _prod_extract("硬盘：U.2 NVME 7.68T * 2")
    assert "7.68" not in ext["keywords"]  # 纯小数碎片不占型号关键字位
    assert [g["term"] for g in ext["drive_groups"]] == ["7.68T"]


# ============================================================
# 2026-08-03 训练（9254/32G×2/960G NMVE/RTX PRO 4500/1300W×2）回归：
# NMVE 拼写归一、内存延续不吞盘/GPU 段、PSU 数量提取
# ============================================================

def test_drive_typo_nmve_normalized():
    # "1* 960G NMVE"（拼写颠倒）→ 归一 NVMe，盘组+品类都成立（训练发现：拼写错导致 NVMe 盘全丢）
    ext = _prod_extract("1* 960G NMVE")
    assert "HDD/SSD" in ext["categories"]
    assert ext["drive_groups"] == [{"term": "960G", "qty": 1, "kind": "NVMe"}]


def test_mem_groups_not_polluted_by_drive_and_gpu():
    # "2* 32G DDR5" 后面接硬盘行（960G NMVE）与 GPU 行（RTX PRO 4500 Server 32G），
    # 两行的容量（960G/32G）不得续进内存组（训练发现：内存被续成 32G×2+960G×1+32G×2 → 出 4 条+错配）
    from app.services.requirement_intel_service import _extract_mem_groups
    text = "2* 32G DDR5\n1* 960G NMVE\n1 *RTX PRO 4500 Server 32G"
    g = _extract_mem_groups(text, {"32g": 2, "960g": 1, "4500": 1},
                            interrupt_words=["rtx", "显卡", "gpu", "ssd", "nvme"])
    assert g == [{"term": "32G", "qty": 2}]
    # 完整 extract：同样只有一组内存，且盘组/GPU 组各自成立
    ext = _prod_extract(text)
    assert ext["mem_groups"] == [{"term": "32G", "qty": 2}]
    assert ext["drive_groups"] == [{"term": "960G", "qty": 1, "kind": "NVMe"}]
    assert ext["gpu_groups"] == [{"tokens": ["RTX PRO 4500"], "qty": 1, "cap": 32}]  # 复合型号（R10/I50）


def test_psu_signal_extracts_qty():
    # "2* 1300W冗余电源" / "1300W*2" → 瓦数+数量；"电源1300W" 无数量
    from app.services.requirement_intel_service import _extract_psu_signal
    assert _extract_psu_signal("2* 1300W冗余电源") == {"wattage": 1300, "qty": 2}
    assert _extract_psu_signal("1300W*2 电源") == {"wattage": 1300, "qty": 2}
    assert _extract_psu_signal("电源1300W") == {"wattage": 1300}


def test_cpu_bare_cores_after_model():
    # "AMD EPYC 9254 24 2.9 GHz 128 MB 200W" —— 型号后裸整数+GHz = 24 核（R6 修：否则默认 Cores>=16 落到 16 核 9124）
    from app.api.candidate_search import extract_spec_values
    rules = [{"category": "CPU", "spec_key": "Cores", "op": ">=", "value": 16, "unit": "核"}]
    out = extract_spec_values("2* AMD EPYC 9254 24 2.9 GHz 128 MB 200W", rules)
    assert out[0]["source"] == "extracted" and out[0]["value"] == 24.0
    # 有单位写法仍走单位；无 GHz 上下文的裸数字不猜
    out2 = extract_spec_values("2x 32 core 9005series of AMD EPYC", rules)
    assert out2[0]["value"] == 32.0
    out3 = extract_spec_values("AMD EPYC 9654 128 MB 200W", rules)
    assert out3[0]["source"] == "default"


# ============================================================
# R7 ESA24V3-P 典型报价单回归：PSU 显式上下文、机箱尺寸→4U、
# "个"数量词、x16/x8 不当乘号、数字+单词连写不当型号
# ============================================================

def test_psu_explicit_context_with_digits_between():
    # "2700W 2+2/3+1冗余高效铂金电源"：W 与 电源 之间有数字（2+2/3+1），旧 [^\d]{0,12} 取不到
    from app.services.requirement_intel_service import _extract_psu_signal
    # R28（2026-08-04 ESA24V3-P）：显式 N+M 冗余 → 数量 = N+M（2+2=4、3+1=4，4U 8卡机 4 个电源）
    assert _extract_psu_signal("2700W 2+2/3+1冗余高效铂金电源") == {"wattage": 2700, "qty": 4}
    assert _extract_psu_signal("2700W 3+1冗余电源") == {"wattage": 2700, "qty": 4}
    # 机箱宽度 448 不是电源（"电源\n宽448" 不得跨行）；"最大功率500W" 是 CPU 规格
    assert _extract_psu_signal("宽448x高175x深822mm") is None
    assert _extract_psu_signal("2个AMD EPYC 9004/9005系列处理器，最大功率500W") is None


def test_form_from_chassis_dimension():
    # "宽448x高175x深822mm" → 4U（175/44.45≈4）；"支持最高6400MT/s" 不得误判为高度
    ext = _prod_extract("宽448x高175x深822mm(含挂耳842mm)")
    assert ext["form"] == "4U"
    ext2 = _prod_extract("支持最高6400MT/s，宽448x高175x深822mm")
    assert ext2["form"] == "4U"


def test_qty_unit_ge_and_x16_not_qty():
    # "2个处理器"→CPU=2、"8个GPU卡"→GPU=8；"PCle5.0x16" 的 0x16 不得当数量（GPU≠0）
    ext = _prod_extract("2个AMD EPYC 9004/9005系列处理器\n24个DDR5内存插槽\n支持8个GPU卡除8GPU外最多支持1个PCle5.0x16+2个PCle5.0x8")
    assert ext["qty_map"].get("CPU") == 2
    assert ext["qty_map"].get("GPU") == 8
    assert ext["qty_map"].get("GPU") != 0
    assert "0x16" not in ext["qty_per_token"]


def test_digit_word_concat_not_model():
    # "8GPU"/"6400MT"/"822mm" 是数量+单词/尺寸连写，不是型号（防 8GPU 命中 曦云C550 8GPU模组）
    ext = _prod_extract("支持8个GPU卡除8GPU外最多支持6400MT/s，宽448x高175x深822mm")
    assert "8GPU" not in ext["keywords"]
    assert "6400MT" not in ext["keywords"]
    assert "822mm" not in ext["keywords"]


# ============================================================
# I40：内存速率优先取「实际内存行」段，能力声明行不抢先
# ============================================================

def test_mem_signal_speed_actual_line_beats_capability():
    from app.services.requirement_intel_service import _extract_mem_signal
    # 能力声明（支持…4800MT/s）在前，实际配置（64G 5600）在后 → 速率取 5600（I40）
    s = _extract_mem_signal("支持24通道DDR5内存，速率达4800MT/s；内存：64G DDR5-5600B RDIMM * 24")
    assert s is not None and s["speed"] == 5600, s


def test_mem_signal_speed_fallback_whole_text():
    from app.services.requirement_intel_service import _extract_mem_signal
    # 无实际内存行速率（只有能力声明）→ 回退全文首个命中 4800
    s = _extract_mem_signal("支持24通道DDR5内存，速率达4800MT/s；内存 512G")
    assert s is not None and s["speed"] == 4800, s


def test_mem_signal_speed_actual_line_kept_4800():
    from app.services.requirement_intel_service import _extract_mem_signal
    # 实际内存行本身就是 4800 → 保持 4800（能力声明 6400 不覆盖实际行）
    s = _extract_mem_signal("支持24通道DDR5 6400MT/s；内存：64G DDR5-4800B RDIMM * 24")
    assert s is not None and s["speed"] == 4800, s


# ============================================================
# R14：兆芯 CPU 品牌触发词 / KH-50000 连字符归一 / PSU 剔除 CPU-TDP 裸瓦数
# ============================================================

def test_cpu_brand_trigger_maps_to_cpu_category():
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    ext = extract_keywords("兆芯KH-50000 2.0GHz_450W*2", lexicon=cat_lex, series_keyword_map=series_map,
                           usage_keyword_map=usage_map, form_keyword_map=form_map,
                           chassis_lexicon=chassis_lex, spec_aliases=cfg.get("spec_aliases"),
                           qty_units=cfg.get("qty_units"), qty_multipliers=cfg.get("qty_multipliers"),
                           model_token_regex=cfg.get("model_token_regex"))
    assert "CPU" in ext["categories"], ext["categories"]
    assert ext["qty_map"].get("CPU") == 2, ext["qty_map"]
    assert ext["series"] == "Polaris"


def test_psu_bare_excludes_cpu_tdp_then_accepts_psu():
    from app.services.requirement_intel_service import _extract_psu_signal
    # 450W 是 CPU TDP（GHz 上下文），剔除后 1300W 唯一 → 电源 1300W×2（R14）
    s = _extract_psu_signal("兆芯KH-50000 2.0GHz_450W*2\n1300W*2")
    assert s is not None and s["wattage"] == 1300 and s["qty"] == 2, s
    # 只有 CPU TDP → None（不当电源）
    assert _extract_psu_signal("AMD 9654 3.1GHz_360W") is None


# ============================================================
# R15：U.2/U.3 接口与容量连写归一（复现BUG：U.21.92T 被粘成 21.92T）
# ============================================================

def test_drive_u2_capacity_concatenated():
    from app.services.requirement_intel_service import _extract_drive_groups
    g = _extract_drive_groups("硬盘:U.21.92T*2\n硬盘:U.23.84T*1\n硬盘:U.27.68T*4", None)
    terms = sorted((x["term"], x.get("kind"), x.get("qty")) for x in g)
    assert ("1.92T", "NVMe", 2) in terms, g
    assert ("3.84T", "NVMe", 1) in terms, g
    assert ("7.68T", "NVMe", 4) in terms, g


def test_drive_u2_spaced_or_word_untouched():
    # 有空格（"U.2 NVME 7.68T"）或接口后跟单词（"U.2NVME 3.84"）不受归一影响
    from app.services.requirement_intel_service import _extract_drive_groups
    g = _extract_drive_groups("硬盘:Intel P5510 U.2NVME 3.84*2", None)
    assert any(x["term"] == "3.84T" and x.get("kind") == "NVMe" and x.get("qty") == 2 for x in g), g
    g2 = _extract_drive_groups("硬盘:U.2 NVME 7.68T*2", None)
    assert any(x["term"] == "7.68T" and x.get("kind") == "NVMe" for x in g2), g2


# ============================================================
# R16：无接口 SSD 默认 SATA（≤960G）/ 双电源 qty / 内存代际跟 CPU
# ============================================================

def test_drive_no_interface_ssd_default_sata_threshold():
    from app.services.requirement_intel_service import _extract_drive_groups
    # ≤960G 无接口 SSD → SATA（系统盘档，I56）
    g = _extract_drive_groups("硬盘:960G SSD*2", None)
    assert any(x["term"] == "960G" and x.get("kind") == "SATA" for x in g), g
    # 大容量数据盘（7.68T）无接口 → 不强制 SATA（R2 回归）
    g2 = _extract_drive_groups("硬盘:7.68T Enterprise-class SSD*4", None)
    assert any(x["term"] == "7.68T" and x.get("kind") is None for x in g2), g2


def test_psu_dual_power_qty():
    from app.services.requirement_intel_service import _extract_psu_signal
    assert _extract_psu_signal("双电源") == {"qty": 2}
    assert _extract_psu_signal("冗余电源") == {"qty": 2}
    # 有瓦数 + 双电源 → 瓦数保留、qty 兜底 2
    s = _extract_psu_signal("1300W 双电源")
    assert s["wattage"] == 1300 and s["qty"] == 2, s


# ============================================================
# R17：招标格式（信创 CPU / 跨段容量 / 前缀量词 / 10-25GE / 7*24 / 5-35）
# ============================================================

def test_drive_merged_continuation_capacity_and_prefix_qty():
    from app.services.requirement_intel_service import _extract_drive_groups
    # "2块SATA SSD, 单块容量480GB"：容量在逗号后无盘标识续段 + 前缀量词 2块（R17）
    g = _extract_drive_groups(">配置 2块SATA SSD, 单块容量480GB, 企业级, 读密集型;", None)
    assert g == [{"term": "480G", "qty": 2, "kind": "SATA", "media": "SSD"}], g


def test_drive_merge_stops_at_component_boundary():
    from app.services.requirement_intel_service import _extract_drive_groups
    # 网卡行不得被卷进盘段（"960GB企业级SSD，2.5寸热插拔*2" 后面接网卡/RAID 行，R3/R17）
    g = _extract_drive_groups("系统固态硬盘:960GB企业级SSD，2.5寸热插拔*2\n网卡模块:10G万兆以太网卡\nRAID 卡: LSI 9560-8i", None)
    assert g == [{"term": "960G", "qty": 2, "kind": "SATA", "media": "SSD"}], g


def test_nic_ge_suffix_and_max_speed():
    from app.services.requirement_intel_service import _nic_line_filters
    line = _nic_line_filters("2块双口10/25GE网卡满配10GE光模块")
    assert any(f.get("spec_key") == "Link Speed" and f.get("value") == "25G" for f in line["filters"]), line
    assert line.get("qty") == 2, line
    line2 = _nic_line_filters("1块板载四口千兆网卡，电口")
    assert line2.get("qty") == 1 and any(f.get("spec_key") == "Ports" and f.get("value") == "4" for f in line2["filters"]), line2


def test_7x24_hour_not_drive_qty():
    # "5年7*24 小时" 的 24 不得绑到 HDD/SSD（R17 招标）
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    ext = extract_keywords("提供5年7*24 小时原厂维保服务。\n配置 2块SATA SSD, 单块容量480GB",
                           lexicon=cat_lex, series_keyword_map=series_map, usage_keyword_map=usage_map,
                           form_keyword_map=form_map, chassis_lexicon=chassis_lex,
                           spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
                           qty_multipliers=cfg.get("qty_multipliers"), model_token_regex=cfg.get("model_token_regex"))
    assert ext["qty_map"].get("HDD/SSD") != 24, ext["qty_map"]


# ============================================================
# R18：裸条数×容量内存（无内存字样）/ NVMe Gen 代际不当型号
# ============================================================

def test_mem_bare_stick_qty_without_mem_word():
    from app.services.requirement_intel_service import _extract_mem_groups, _extract_mem_signal
    # "24*32G" 无 内存/DDR 字样 → 仍识别为 32G×24（R18，cap≤128G 且条数≥2）
    g = _extract_mem_groups("24*32G", {"32g": 24})
    assert {"term": "32G", "qty": 24} in g, g
    s = _extract_mem_signal("24*32G")
    assert s is not None and s["total_gb"] == 768, s
    # 盘容量（480G+）不得误判为内存
    g2 = _extract_mem_groups("硬盘:2*480G SSD", {"480g": 2})
    assert g2 == [], g2


def test_nvme_gen_not_unmatched():
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    ext = extract_keywords("NVMe Gen5 7.68T盘4块x3", lexicon=cat_lex, series_keyword_map=series_map,
                           usage_keyword_map=usage_map, form_keyword_map=form_map,
                           chassis_lexicon=chassis_lex, spec_aliases=cfg.get("spec_aliases"),
                           qty_units=cfg.get("qty_units"), qty_multipliers=cfg.get("qty_multipliers"),
                           model_token_regex=cfg.get("model_token_regex"))
    # Gen5 跳过发生在 stage-1 匹配层（pick_kp_parts），extract 的 keywords 可含该 token；
    # 这里验证盘组解析正确，unmatched 由 golden R18 端到端兜底
    assert ext["drive_groups"] == [{"term": "7.68T", "qty": 3, "kind": "NVMe"}], ext["drive_groups"]


# ============================================================
# R19：RAID控制器中文词 / 240Vdc 电压 / 7x24 / RAID 行不当盘
# ============================================================

def test_raid_controller_chinese_keeps_category():
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    kw = dict(lexicon=cat_lex, series_keyword_map=series_map, usage_keyword_map=usage_map,
              form_keyword_map=form_map, chassis_lexicon=chassis_lex,
              spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
              qty_multipliers=cfg.get("qty_multipliers"), model_token_regex=cfg.get("model_token_regex"))
    # "RAID控制器"（中文控制器）是真阵列卡需求 → 保留 Raid card 品类（R19）
    ext = extract_keywords("8口12G SAS RAID控制器*2GB缓存*带FBWC(Raid 0,1,5,6)*1", **kw)
    assert "Raid card" in ext["categories"], ext["categories"]
    # "RAID1"（级别）不是阵列卡需求 → 不触发 Raid card（R2 回归）
    ext2 = extract_keywords("2*480GB SATA SSD（RAID1）", **kw)
    assert "Raid card" not in ext2["categories"], ext2["categories"]


def test_psu_voltage_240vdc_not_wattage():
    from app.services.requirement_intel_service import _extract_psu_signal
    # 240Vdc 是输入电压不是 240W；冗余电源 → qty=2（R19）
    s = _extract_psu_signal("白金级效率冗余电源_交流&240Vdc输入")
    assert s is not None
    assert s.get("wattage") is None or s["wattage"] != 240, s
    assert s.get("qty") == 2, s


def test_drive_raid_controller_line_not_drive():
    from app.services.requirement_intel_service import _extract_drive_groups
    # RAID 控制器的 "12G SAS" / "2GB缓存" 不得当硬盘（R19）
    g = _extract_drive_groups("8口12G SAS RAID控制器*2GB缓存*带FBWC(Raid 0,1,5,6)*1", None)
    assert g == [], g


# ============================================================
# R20：盘段碎片（接口速率 6G / 英寸 2.5in / 型号数字 PM893）不当容量
# ============================================================

def test_drive_fragment_interface_rate_inch_model():
    from app.services.requirement_intel_service import _extract_drive_groups
    # "6GSATA2.5in RI PM893 SSD"：6G(接口速率)/2.5in(英寸)/893(型号) 都不得当容量（R20）
    g = _extract_drive_groups("2*480GB 6GSATA2.5in RI PM893 SSD", {"480gb": 2, "6gsata2.5in": 2, "pm893": 2})
    # media 窗口(24字符)可能切在 "ssd" 前，但 kind=SATA 已从 "6GSATA" 判定（最终匹配正确）
    assert g == [{"term": "480G", "qty": 2, "kind": "SATA"}], g
    # "3.84TB PCle*Gen4X4 NVMe U.2 2.5in RI PM9A3 SSD"
    g2 = _extract_drive_groups("2*3.84TB PCle*Gen4X4 NVMe U.2 2.5in RI PM9A3 SSD",
                               {"3.84tb": 2, "gen4x4": 2, "2.5in": 2, "pm9a3": 2})
    assert g2 == [{"term": "3.84T", "qty": 2, "kind": "NVMe"}], g2


def test_drive_fragment_interface_rate_12g_sas_not_capacity():
    from app.services.requirement_intel_service import _extract_drive_groups
    # "12G SAS" 接口速率不当容量（R20，含 RAID 行外的普通场景）
    g = _extract_drive_groups("2*960G SATA SSD 12G SAS 背板", {"960g": 2})
    assert all(x["term"] != "12G" for x in g), g


# ============================================================
# R20：裸 8卡 AI（无 CPU/平台线索）→ ESA24V3-P 与 ZSA24V2-P 都推荐
# ============================================================

def test_bare_8gpu_no_cpu_recommends_both_models():
    from app.services.requirement_intel_service import extract_keywords, _fold_lexicons
    from app.repository.reasoning_flow_repo import _default_node_configs
    from app.api.candidate_search import select_models, build_variant_signals
    cfg = _default_node_configs()["extract"]
    cat_lex, chassis_lex, usage_map, series_map, form_map = _fold_lexicons(cfg["lexicons"])
    req = "GPU: Rtx 5090 32G*8\n内存:32G*16\n网卡:双口25g spf+"
    ext = extract_keywords(req, lexicon=cat_lex, series_keyword_map=series_map, usage_keyword_map=usage_map,
                           form_keyword_map=form_map, chassis_lexicon=chassis_lex,
                           spec_aliases=cfg.get("spec_aliases"), qty_units=cfg.get("qty_units"),
                           qty_multipliers=cfg.get("qty_multipliers"), model_token_regex=cfg.get("model_token_regex"))
    vs = build_variant_signals(ext, req)
    models = select_models(ext.get("usage"), ext.get("server_type_name"), ext.get("series"), ext.get("form"),
                           limit=6, variant_signals=vs)
    names = [m.get("name") or "" for m in models]
    assert any("ZSA24V2-P" in n for n in names), names
    assert any("ESA24V3-P" in n for n in names), names


# ============================================================
# R21：表格格式（数量列）/ 氦气盘 HDD / PCIe4.0 不当盘容量 / KH50000-72
# ============================================================

def test_table_row_quantity_normalized():
    from app.services.requirement_intel_service import _normalize_table_rows
    out = _normalize_table_rows("| 处理器 | 兆芯开胜 KH50000-72（72 核） | 4 |\n| 内存 | 64GB DDR5 5200 | 16 |")
    assert "KH50000-72（72 核） *4" in out, out
    assert "64GB DDR5 5200 *16" in out, out
    # 表头/分隔行不动
    out2 = _normalize_table_rows("| 配件类型 | 型号 | 数量 |\n| :--- | :--- | :--- |")
    assert "| 配件类型 | 型号 | 数量 |" in out2


def test_helium_drive_is_hdd():
    from app.services.requirement_intel_service import _extract_drive_groups
    g = _extract_drive_groups("8TB 企业级 3.5 寸 SATA 氦气盘 *12", {"8t": 12})
    assert g == [{"term": "8T", "qty": 12, "kind": "SATA", "media": "HDD"}], g


def test_pcie40_not_drive_capacity():
    from app.services.requirement_intel_service import _extract_drive_groups
    # "PCIe4.0" 的 4.0 不当盘容量（R21，R17 同款在盘解析复发）
    g = _extract_drive_groups("1.92TB PCIe4.0 NVMe 企业 SSD *2", {"1.92tb": 2})
    assert g == [{"term": "1.92T", "qty": 2, "kind": "NVMe", "media": "SSD"}], g


def test_nic_opt_module_after_comma_continuation():
    """R23：'网卡：10G 万兆网卡, PCIe4.0 适配 (含光模块) *3' 逗号续段含光模块 →
    该行 name_contains 补光模块（漏配光模块修复）；不影响无光模块的独立行。"""
    ext = _prod_extract("网卡：10G 万兆以太网网卡, PCIe4.0 适配 (含光模块) *3")
    nic = ext["multi_spec_filters"].get("Network(NIC) requirement") or []
    assert len(nic) == 1
    assert "光模块" in (nic[0].get("name_contains") or [])
    # 独立无光模块行不受影响（多行场景）
    ext2 = _prod_extract("网卡:千兆4口*1\n网卡:25G双口含光模块*1")
    by = {f["filters"][0]["value"]: f for f in ext2["multi_spec_filters"]["Network(NIC) requirement"]}
    assert by["1G"].get("name_contains") is None
    assert by["25G"].get("name_contains") == ["光模块"]


# ============================================================
# R28（2026-08-04 ESA24V3-P）：RAID 显式型号分组 / NIC SKU 归一 / TDP 噪音
# ============================================================

def test_raid_groups_explicit_models():
    # 需求逐行给阵列卡型号 → 按具体型号分组（不再落到品类代表件 9540-8i 泛配）
    from app.services.requirement_intel_service import _extract_raid_groups
    g = _extract_raid_groups(
        "RAID卡：LSI 9560 16i 8G缓存（用于NVMe U.2组建阵列）*1\n"
        "RAID卡：LSI 9364 8i 2G缓存（用于前置8盘位机械硬盘组建阵列）*1")
    assert g == [
        {"model": "9560-16i", "qty": 1, "cache": "8"},
        {"model": "9364-8i", "qty": 1, "cache": "2"},
    ], g


def test_raid_groups_no_model_empty():
    # 只写 RAID 级别（0,1,10）无型号 → 空组，交回 I22 applicable 兼容机型选件
    from app.services.requirement_intel_service import _extract_raid_groups
    assert _extract_raid_groups("阵列卡:RAID 0,1,10*1") == []


def test_raid_groups_hyphen_form():
    # "9560-16i" 连字符写法同样归一
    from app.services.requirement_intel_service import _extract_raid_groups
    g = _extract_raid_groups("RAID卡：LSI 9560-16i *1")
    assert g and g[0]["model"] == "9560-16i" and g[0]["qty"] == 1


def test_nic_x710da2blk_sku_normalized():
    # "X710DA2BLK"（BLK=包装后缀）→ name_contains 归一到 "x710da2"，
    # 匹配侧再去连字符命中配件库 "X710-DA2"（R28 ESA24V3-P）
    ext = _prod_extract("网卡：双口万兆 X710DA2BLK 光口含模块 *1")
    nic = ext["multi_spec_filters"].get("Network(NIC) requirement") or []
    assert nic and len(nic) == 1
    nc = nic[0].get("name_contains") or []
    assert any("x710da2" in (t or "").lower() for t in nc), nc
    assert "光模块" in nc, nc


def test_tdp_wattage_not_model_token():
    # "TDP360W"（CPU TDP 连写）不是型号 → 不进 keywords，不报 unmatched 噪音（R28）
    ext = _prod_extract("CPU：AMD EPYC 9654 96核 2.4GHz L3 384MB TDP360W *2")
    assert "TDP360W" not in ext["keywords"]


# ============================================================
# R29（2026-08-04 流程重构）：槽位覆盖度 / 系列确认
# ============================================================

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
