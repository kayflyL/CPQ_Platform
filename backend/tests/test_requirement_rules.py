# -*- coding: utf-8 -*-
"""需求分析规则域（requirement）：平台归置 + 场景配置基线（知识化注入口径，2026-09-14）。

分层：
- 规则本体住 CRE（rules.compatibility_rules，domain=requirement，DB 唯一来源、无代码种子）；
- 求值语义（contains 命中/互斥）仍由 selection_engine 原语承载并在此锁定；
- 消费 = 知识注入：requirement_knowledge 渲染知识块进 brain 系统提示
  （_KpNode.prepare 不再摆基线桌）；词典卡另有影子校验（见 test_platform_derive）。

夹具 = 2026-09-14 从库里导出的 6 条 requirement 规则原样（求值语义锁定，与 DB 漂移会在这里暴露）。
"""
import asyncio
from unittest.mock import patch

from app.services.selection_engine import eval_assign_value, registration_rule_context
from app.services.requirement_knowledge import (
    PLATFORM_GROUP, SCENE_GROUP, knowledge_for_node, merge_node_bindings, render_group)


def _plat(name: str, signals: list, platform: str, desc: str, evidence: str) -> dict:
    return {"name": name, "type": "derive", "category": "平台归置", "domain": "requirement", "status": "active",
            "body": {"when": {"any": [{"field": "kp.CPU.spec.text", "op": "contains", "value": w}
                                      for w in signals]},
                     "then": {"action": "derive", "field": "opportunity.platform_type", "value": platform},
                     "desc": desc, "evidence": evidence}}


def _scene(name: str, signals: list, title: str, items: list, desc: str, evidence: str) -> dict:
    return {"name": name, "type": "recommend", "category": "场景配置基线", "domain": "requirement", "status": "active",
            "body": {"when": {"any": [{"field": "config.scenario_blob", "op": "contains", "value": w}
                                      for w in signals]},
                     "then": {"action": "baseline", "title": title, "items": items},
                     "desc": desc, "evidence": evidence}}


_REQ_RULES = [
    _plat("平台：CPU 兆芯/KH → Polaris", ["兆芯", "KH", "kh"], "Polaris", "客户点名兆芯（KH 系列）CPU → 整机平台推导为 Polaris；推导值属推断，须经客户确认",
          "库内实测：兆芯 KH50000 库存只适配 Polaris 平台"),
    _plat("平台：CPU AMD/EPYC/霄龙 → Orion", ["AMD", "EPYC", "霄龙"], "Orion", "客户点名 AMD（EPYC/霄龙）→ 整机平台推导为 Orion；推导值属推断，须经客户确认",
          "目录实测：Orion 在售机型 CPU 全为 EPYC"),
    _plat("平台：CPU Intel/至强 → Intel", ["Intel", "intel", "至强", "Xeon", "xeon"], "Intel", "客户点名 Intel（至强/Xeon）→ 整机平台推导为 Intel 系；推导值属推断，须经客户确认",
          "业务确认：至强/Intel 阵营归 Intel 系平台（待目录复核补实证）"),
    _scene("场景基线：AI 训练服务器", ["训练", "GPU服务器", "算力"], "AI 训练服务器", [
        {"category": "网卡", "text": "每 GPU 配 1 张 200G RDMA（训练必备）"},
        {"category": "内存", "text": "≥ 2×GPU 总显存（每卡约 4 条）"},
        {"category": "CPU", "text": "⌈GPU 数 ÷ 4⌉ 颗，每卡 ≥ 6 物理核"},
        {"category": "NVMe 缓存", "text": "≥ 2× 数据集规模"},
        {"category": "电源", "text": "N+1 冗余"}],
        "训练场景配置基线：AI 推荐配件时照此校准数量与必备件；客户明确给过数量时以客户为准",
        "NVIDIA 认证指南（内存≥2×显存、每 GPU ≥6 物理核）· DGX H100 参考架构（计算网每卡 1×400G，按预算降 200G）"),
    _scene("场景基线：AI 推理服务器", ["推理", "问答", "RAG", "在线服务"], "AI 推理服务器", [
        {"category": "网卡", "text": "每 GPU 1 张 100G/200G RDMA（推理可按带宽预算降档）"},
        {"category": "内存", "text": "≥ 1×GPU 总显存（推理 1×即可）"},
        {"category": "CPU", "text": "⌈GPU 数 ÷ 4⌉ 颗，每卡 ≥ 6 物理核"}],
        "推理场景配置基线：网络/内存较训练降档，CPU 口径与训练一致",
        "浪潮 NF5688G7/M6 参考配置 · NVIDIA 推理 sizing（推理内存 1×显存）"),
    _scene("场景基线：通用服务器", ["通用", "虚拟化", "数据库", "办公", "文件存储"], "通用服务器", [
        {"category": "系统盘", "text": "2 块 SSD 组 RAID 1（双盘镜像）"},
        {"category": "电源", "text": "1+1 冗余电源"},
        {"category": "网络", "text": "千兆管理口 + 万兆业务口（各 1）"}],
        "通用/虚拟化场景基线：可靠性三件套（RAID1 系统盘、1+1 电源、管理业务分网）",
        "业务确认：通用场景基线（与在售通用机型标配对齐）"),
]


def _rules_by(name_part: str) -> dict:
    return next(r for r in _REQ_RULES if name_part in r["name"])


def _requirement_rules() -> list:
    return [dict(r) for r in _REQ_RULES]


def _ext(server_type: str = "通用计算服务器", cpu_spec: str = "", requirement: str = "") -> dict:
    rows = []
    if cpu_spec:
        rows.append({"part_category": "CPU", "request_spec": cpu_spec, "qty": 2})
    return {"server_type": server_type, "platform_type": "", "kp_rows": rows,
            "requirement_text": requirement}


# ===== 平台归置求值（求值语义锁定） =====

def test_platform_derive_all_three_camps():
    rules = [r for r in _requirement_rules() if r["category"] == "平台归置"]
    ctx = registration_rule_context(_ext(cpu_spec="2× EPYC 9654"))
    assert eval_assign_value(rules, ctx, "opportunity.platform_type") == "Orion"
    ctx = registration_rule_context(_ext(cpu_spec="2× Intel 8558U 至强"))
    assert eval_assign_value(rules, ctx, "opportunity.platform_type") == "Intel"
    ctx = registration_rule_context(_ext(cpu_spec="兆芯 KH50000"))
    assert eval_assign_value(rules, ctx, "opportunity.platform_type") == "Polaris"


def test_platform_signals_do_not_cross_match():
    """EPYC 不含 intel/xeon 子串；至强 不含 AMD —— 各阵营信号互斥。"""
    rules = [r for r in _requirement_rules() if r["category"] == "平台归置"]
    assert eval_assign_value(
        rules, registration_rule_context(_ext(cpu_spec="EPYC 9754")), "opportunity.platform_type"
    ) == "Orion"


# ===== 场景基线：信号命中语义锁定（渲染对信号语义的依赖） =====

def _baseline_rules() -> list:
    return [r for r in _requirement_rules() if r["category"] == "场景配置基线"]


def test_training_baseline_signals_do_not_hit_inference():
    """「大模型推理」不含训练信号（训练信号已去「大模型」）——训练/推理互斥是语义适用前提。"""
    from app.services.selection_engine import _body, eval_when
    blob_ctx = {"config": {"scenario_blob": "跑大模型推理问答"}}
    hits = [r["name"] for r in _baseline_rules()
            if eval_when(blob_ctx, _body(r).get("when"))]
    assert hits == ["场景基线：AI 推理服务器"]


def test_general_baseline_signals_via_server_type():
    """server_type「通用计算服务器」本身带通用信号（场景信号寻址已登记 server_type）。"""
    from app.services.selection_engine import _body, eval_when
    blob_ctx = {"config": {"scenario_blob": "通用计算服务器 虚拟化 + 数据库"}}
    hits = [r["name"] for r in _baseline_rules()
            if eval_when(blob_ctx, _body(r).get("when"))]
    assert hits == ["场景基线：通用服务器"]


# ===== 知识块渲染（原则卡） =====

def test_scene_group_render_carries_items_and_usage():
    """原则卡知识块：标题（信号）+ 类目=要点列表 + 依据 + 组级用法行（客户为准口径）。"""
    text = render_group(SCENE_GROUP, _baseline_rules())
    assert text.startswith("【需求理解知识·场景配置基线】")
    assert "AI 训练服务器（信号：训练/GPU服务器/算力）：网卡=每 GPU 配 1 张 200G RDMA（训练必备）" in text
    assert "电源=N+1 冗余" in text
    assert "依据：NVIDIA 认证指南" in text
    assert "客户明确给过数量时以客户为准" in text


def test_scene_render_excludes_non_baseline_rules():
    """平台归置规则不混进原则卡知识块（组分桶隔离）。"""
    text = render_group(SCENE_GROUP, _requirement_rules())
    assert "Polaris" not in text
    assert text.count("【需求理解知识·") == 1


def test_empty_group_renders_empty():
    """无可渲染规则 → 空串（绑定空组不注入空标题）。"""
    assert render_group(SCENE_GROUP, []) == ""


# ===== 节点拼装（绑定选择性） =====

def test_kp_node_gets_both_groups_agent_fill_platform_only():
    """默认绑定：agent_fill 只读平台词典（P1 平台冲突源头修复），kp 两组全读。"""
    rules = _requirement_rules()
    fill = knowledge_for_node("agent_fill", rules=rules,
                              bindings={"agent_fill": [PLATFORM_GROUP],
                                        "kp_reason": [PLATFORM_GROUP, SCENE_GROUP]})
    assert "【需求理解知识·平台归置】" in fill
    assert "场景配置基线" not in fill
    kp = knowledge_for_node("kp_reason", rules=rules,
                            bindings={"agent_fill": [PLATFORM_GROUP],
                                      "kp_reason": [PLATFORM_GROUP, SCENE_GROUP]})
    assert "【需求理解知识·平台归置】" in kp
    assert "【需求理解知识·场景配置基线】" in kp


# ===== kp 步骤准备（基线摆桌已退役） =====

async def _noop(ctx, cfg, broadcast=None):
    return None


def test_kp_prepare_no_longer_tables_baseline():
    """基线不再摆桌进 hint（知识进 brain 系统提示）；hint 只报行清单事实。"""
    from app.services.skill_node_plugins import _KpNode
    with patch("app.services.skill_phases.phase_kp_reason", _noop):
        res = asyncio.run(_KpNode().prepare(
            {"ext": _ext(server_type="AI训练"), "requirement_text": "GPU 服务器"}, {}))
    assert res["ok"] is True
    assert "行业配置基线" not in res["hint"]
    assert "AI 训练服务器" not in res["hint"]


def test_kp_prepare_hint_reports_row_summary():
    from app.services.skill_node_plugins import _KpNode
    with patch("app.services.skill_phases.phase_kp_reason", _noop):
        res = asyncio.run(_KpNode().prepare(
            {"ext": _ext(), "kp_summary": {"kp_count": 3, "unmatched_count": 1}}, {}))
    assert res["ok"] is True
    assert "已落地 3 行" in res["hint"] and "待选型 1 行" in res["hint"]


# ── 节点抽屉·规则层：单节点绑定合并（纯函数；写库路径由 e2e 覆盖） ──────────────
def test_merge_node_bindings_adds_node_keeps_others():
    cur = {"agent_fill": ["平台归置"], "kp_reason": ["平台归置", "场景配置基线"]}
    out = merge_node_bindings(cur, "compose", ["场景配置基线", "未知组"], [7, "7", "x", 9])
    assert out == {
        "agent_fill": {"groups": ["平台归置"], "rule_ids": []},
        "kp_reason": {"groups": ["平台归置", "场景配置基线"], "rule_ids": []},
        "compose": {"groups": ["场景配置基线"], "rule_ids": [7, 9]},  # int 归一去重、非法丢弃
    }


def test_merge_node_bindings_empty_unbinds_without_touching_others():
    cur = {"agent_fill": ["平台归置"], "kp_reason": {"groups": ["平台归置"], "rule_ids": [3]}}
    out = merge_node_bindings(cur, "kp_reason", [], [])
    assert out == {"agent_fill": {"groups": ["平台归置"], "rule_ids": []}}


def test_merge_node_bindings_overwrite_and_deep_copy():
    cur = {"agent_fill": ["场景配置基线"]}
    out = merge_node_bindings(cur, "agent_fill", ["平台归置"], [])
    assert out == {"agent_fill": {"groups": ["平台归置"], "rule_ids": []}}
    cur["agent_fill"].append("平台归置")
    assert out["agent_fill"]["groups"] == ["平台归置"]  # 深拷贝：写入值不受调用方后续改动影响


# ── 注入语义：组绑定 ∪ 单条勾选；旧列表形状绑定读时归一 ────────────────────────
def test_knowledge_union_of_group_binding_and_single_rule():
    rules = [
        {**_plat("兆芯", ["兆芯", "KH"], "Polaris", "d", "e"), "id": 1},
        {**_plat("AMD", ["AMD", "EPYC"], "Orion", "d", "e"), "id": 2},
        {**_scene("AI训练", ["AI训练"], "AI 训练基线", [{"category": "GPU", "text": "按需"}], "d", "e"), "id": 3},
        {**_scene("通用", ["通用"], "通用基线", [{"category": "内存", "text": "均衡"}], "d", "e"), "id": 4},
    ]
    bindings = {"kp_reason": {"groups": ["平台归置"], "rule_ids": [4]}}
    text = knowledge_for_node("kp_reason", rules=rules, bindings=bindings)
    assert "Polaris" in text and "Orion" in text          # 整组：平台归置 2 条全进
    assert "通用基线" in text and "AI 训练基线" not in text  # 单条：只进了 id=4
    assert "场景配置基线" in text                            # 单条触达的组照常出块带用法行


def test_knowledge_old_list_shape_binding_normalized():
    rules = [{**_plat("兆芯", ["兆芯"], "Polaris", "d", "e"), "id": 1}]
    text = knowledge_for_node("agent_fill", rules=rules,
                              bindings={"agent_fill": ["平台归置"]})  # DB 旧形状
    assert "Polaris" in text
