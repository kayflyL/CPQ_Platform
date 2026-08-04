# -*- coding: utf-8 -*-
"""scene_analysis 节点单测：场景判定（AI/存储/通用）× 系列 × 形态，带证据白盒。

- 纯函数单测：analyze_scene（显式传 server_types，不依赖 DB，跑得快）
- 图级回归：run_graph_executor 走 active flow，验证 8 卡双机型 / 兆芯不落 AMD
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))  # backend/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[0]))  # backend/tests

import pytest
from app.services.scene_analyzer import analyze_scene

# 与 l6.server_types 对齐的测试目录（纯函数显式注入，避免 DB 依赖）
_TYPES = [
    {"id": 1, "name": "通用计算服务器"},
    {"id": 2, "name": "AI / 加速计算服务器"},
    {"id": 3, "name": "存储服务器"},
]


def _scene(ext, text="", opp=None, cat=None, fc=False):
    return analyze_scene(ext, text, config=None, opportunity=opp,
                         catalog_type_name=cat, server_types=_TYPES, force_complete=fc)


# ── 纯函数：场景判定 ──────────────────────────────────────────────
def test_r20_bare_8gpu_ai_no_series():
    """裸 8 卡 GPU（无 CPU/系列）：→ AI 场景；系列未知（Orion/Polaris 双机型都推）；多卡→4U。"""
    sc = _scene(
        {"categories": ["Memory", "HDD/SSD", "GPU", "Network(NIC) requirement"],
         "keywords": ["5090", "32G"], "qty_map": {"GPU": 8}},
        "内存:32G*16 系统盘:2*480GB 数据盘:2*3.84TB GPU:Rtx 5090 32G*8 网卡:双口25g spf+")
    assert sc["determined"] is True
    assert sc["scene_name"] == "AI / 加速计算服务器"
    assert sc["series"] is None          # 平台不可辨 → 双机型都推
    assert sc["form"] == "4U"            # 多卡 GPU 推断 4U
    assert sc["evidence"]                # 白盒证据非空
    assert sc["missing"] == []


def test_r12_zhaoxin_general_polaris():
    """兆芯 2U（有系列）：→ 通用场景 + Polaris，不落 AMD。"""
    sc = _scene(
        {"categories": ["CPU", "Memory", "HDD/SSD", "Network(NIC) requirement"],
         "series": "Polaris", "form": "2U", "keywords": ["KH5000", "48C"]},
        "机箱:2U12机架式 CPU:KH5000 48C*2 内存:DDR5 5600 32G*8 系统盘:SATA SSD 480G*2 数据盘:SATA HDD 8T*4")
    assert sc["scene_name"] == "通用计算服务器"
    assert sc["series"] == "Polaris"
    assert sc["determined"] is True


def test_r1_amd_general_orion():
    """AMD 9654 2U：→ 通用 + Orion。"""
    sc = _scene(
        {"categories": ["CPU", "Memory", "HDD/SSD", "Raid card", "Network(NIC) requirement"],
         "series": "Orion", "form": "2U", "server_type_name": "通用计算服务器"},
        "机箱：2U机架式 CPU：AMD 9654 * 2")
    assert sc["scene_name"] == "通用计算服务器"
    assert sc["series"] == "Orion"
    assert sc["form"] == "2U"


def test_storage_strong_word():
    """明确存储场景词 → 存储。"""
    sc = _scene({"categories": ["CPU", "Memory", "HDD/SSD"], "qty_map": {"HDD/SSD": 12}},
                "2U 存储服务器 12*8T 氦气盘")
    assert sc["scene_name"] == "存储服务器"
    assert "存储" in "".join(sc["evidence"])


def test_storage_weak_word_needs_drive_qty():
    """弱词「大容量」但盘量不足（4 盘）→ 不判存储，回退默认通用（避免误判）。"""
    sc = _scene({"categories": ["CPU", "Memory", "HDD/SSD"], "qty_map": {"HDD/SSD": 4}},
                "2U 服务器 4*8T 大容量")
    assert sc["scene_name"] == "通用计算服务器"
    assert sc["determined"] is True


def test_generic_requirement_plus_ai_industry_not_overreach():
    """通用需求 + 商机行业 AI：行业线索只作偏好，不单独决定场景（避免乱推 AI 机型）。"""
    sc = _scene({"categories": ["CPU", "Memory", "HDD/SSD"], "series": "Orion", "form": "2U"},
                "2U 服务器 32G*8 双万兆", opp={"industry": "AI/互联网"})
    assert sc["scene_name"] == "通用计算服务器"


def test_gpu_requirement_plus_ai_industry_boost():
    """GPU 需求 + 商机行业 AI：需求已定 AI，行业线索增强证据。"""
    sc = _scene({"categories": ["CPU", "Memory", "GPU"], "series": "Orion", "form": "2U",
                 "qty_map": {"GPU": 2}},
                "2U 服务器 2*GPU 32G*8", opp={"industry": "AI/互联网"})
    assert sc["scene_name"] == "AI / 加速计算服务器"
    assert any("商机" in e for e in sc["evidence"])


def test_catalog_type_authoritative():
    """目录引导已选类型 → 权威，直接确定该场景。"""
    sc = _scene({"categories": ["Memory", "HDD/SSD"]}, "2U 服务器 32G*8",
                cat="AI / 加速计算服务器")
    assert sc["determined"] is True
    assert sc["scene_name"] == "AI / 加速计算服务器"
    assert sc["confidence"] == 100


def test_empty_requirement_undetermined():
    """真·无信号 → 无法确定，missing=['场景']，交给反问。"""
    sc = _scene({}, "服务器")
    assert sc["determined"] is False
    assert "场景" in sc["missing"]


def test_empty_requirement_force_complete_fallback():
    """无信号但跳过反问（force_complete）→ 按默认场景硬出，不阻塞。"""
    sc = _scene({}, "服务器", fc=True)
    assert sc["determined"] is True
    assert sc["scene_name"] == "通用计算服务器"


def test_form_override_gpu_2u_to_4u():
    """需求写 2U 但 GPU≥4：目录无 2U 多卡机型 → 按能力纠正为 4U（带证据）。"""
    sc = _scene({"categories": ["GPU", "Memory"], "form": "2U", "qty_map": {"GPU": 8}},
                "2U 8卡 GPU 服务器")
    assert sc["form"] == "4U"
    assert any("4U" in e for e in sc["evidence"])


def test_single_consumer_gpu_is_general():
    """单张消费级/专业级显卡（1*RTX PRO 4500，R6）→ 通用场景（AI 需 ≥2 卡或数据中心 GPU）。"""
    sc = _scene({"categories": ["CPU", "Memory", "HDD/SSD", "GPU"], "series": "Orion",
                 "form": "2U", "server_type_name": "通用计算服务器", "qty_map": {"GPU": 1}},
                "2* AMD EPYC 9254 1* 960G NMVE 1* RTX PRO 4500 Server 32G")
    assert sc["scene_name"] == "通用计算服务器"


def test_single_datacenter_gpu_is_ai():
    """单张数据中心 GPU（1*H100，R2）→ AI 场景。"""
    sc = _scene({"categories": ["CPU", "Memory", "HDD/SSD", "GPU"], "series": "Orion",
                 "form": "4U", "server_type_name": "AI / 加速计算服务器", "qty_map": {"GPU": 1}},
                "1* NVIDIA H100 PCIe 80GB")
    assert sc["scene_name"] == "AI / 加速计算服务器"
    assert any("数据中心 GPU" in e for e in sc["evidence"])


def test_series_hint_inference_when_ext_missing():
    """extract 没给系列，但文本含 EPYC → 按 series_hints 推断 Orion。"""
    sc = _scene({"categories": ["CPU", "Memory"], "form": "2U"},
                "2U 服务器 2*AMD EPYC 9554 32G*16")
    assert sc["series"] == "Orion"


# ── 图级回归：8 卡 / 兆芯 不再乱推机型 ───────────────────────────
def _run_graph(text, force=True):
    import asyncio
    from app.repository.reasoning_flow_repo import DEFAULT_GRAPH, _default_node_configs
    from app.services.reasoning_executor import run_graph_executor

    async def _run():
        # 用模块常量构造 flow（不依赖 DB 用户可调 max_plans），保证测试确定性
        flow = {"graph": DEFAULT_GRAPH, "node_configs": _default_node_configs()}
        events = []

        async def bc(p):
            events.append(p)

        ctx = await run_graph_executor("test-run", text, flow, bc,
                                       initial_ctx={"force_complete": force})
        return ctx, events

    return asyncio.run(_run())


@pytest.mark.parametrize("req,ai_names,general_names", [
    # 裸 8 卡 AI：应同时推 ESA24V3-P 与 ZSA24V2-P，绝不混入 2U 通用机型
    ("内存:32G*16 系统盘:2*480GB 数据盘:2*3.84TB GPU:Rtx 5090 32G*8 网卡:双口25g spf+",
     ["ESA24V3-P", "ZSA24V2-P"], ["ES22V3-P", "ZS22V2-P", "ZS25V2-P"]),
], ids=["r20-8gpu-both-ai"])
def test_graph_8gpu_recommends_both_ai_models(req, ai_names, general_names):
    ctx, events = _run_graph(req)
    scene = ctx.get("scene") or {}
    assert scene.get("determined") is True
    assert scene.get("scene_name") == "AI / 加速计算服务器"
    names = [b.get("name") or "" for b in (ctx.get("baselines") or [])]
    for ai in ai_names:
        assert any(ai in n for n in names), f"缺 AI 机型 {ai}，实际 {names}"
    for g in general_names:
        assert not any(g in n for n in names), f"混入通用机型 {g}，实际 {names}"


@pytest.mark.parametrize("req,expected_models,bad_models", [
    # 兆芯 2U：只推 ZS22V2-P（Polaris），绝不落 AMD（ES22V3-P）
    ("机箱:2U12机架式 CPU:KH5000 48C*2 内存:DDR5 5600 32G*8 系统盘:SATA SSD 480G*2 数据盘:SATA HDD 8T*4 网卡:4口千兆电口*1 网卡:双10G光口*1 电源:根据功耗选择",
     ["ZS22V2-P"], ["ES22V3-P", "ESA24V3-P", "ZSA24V2-P", "ZS25V2-P"]),
    # AMD 2U：只推 ES22V3-P（Orion），不落兆芯
    ("机箱：2U机架式 CPU：AMD 9654 * 2 内存：DDR5 32 * 16 硬盘：SATA SSD 960G * 2 RAID卡：9560-8I * 1 网卡：CX5 25G 双口 含光模块 * 2",
     ["ES22V3-P"], ["ZS22V2-P", "ZSA24V2-P"]),
], ids=["r12-zhaoxin-only", "r1-amd-only"])
def test_graph_series_platform_not_cross(req, expected_models, bad_models):
    ctx, _ = _run_graph(req)
    scene = ctx.get("scene") or {}
    assert scene.get("determined") is True
    names = [b.get("name") or "" for b in (ctx.get("baselines") or [])]
    for m in expected_models:
        assert any(m in n for n in names), f"缺 {m}，实际 {names}"
    for bm in bad_models:
        assert not any(bm in n for n in names), f"跨平台乱推 {bm}，实际 {names}"


def test_graph_scene_undetermined_routes_to_ask_user():
    """真·无信号需求：scene 无法确定 → cond_scene 路由到 ask_user（不空跑出方案）。"""
    ctx, events = _run_graph("帮我看看服务器", force=False)
    assert ctx.get("awaiting_input") is True
    assert any(e.get("type") == "need_input" for e in events)
