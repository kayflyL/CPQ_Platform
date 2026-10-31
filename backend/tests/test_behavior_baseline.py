# -*- coding: utf-8 -*-
"""⑥ 行为基线考卷：固定输入 → 结构事实。改规则/改提示词，先考一遍再真脑复核。

考卷索引（每题 = 流 × 固定输入 × 结构事实 × 挡住的历史事故）：
  EXAM-1 需求分析·多候选必停轮发卡：库内 3 款 GPU、用户没拍板 → 协议槽被占（choice 卡）
         + AI pick 只进推荐不进锁定；用户点选后复调 → 放行落定=点选款。
         〔挡 10-30 事故：AI 列 4 款不弹卡、4 秒自选非推荐款落定〕
  EXAM-2 需求分析·节点产物非空：登记落表后 agent_fill 的产物载荷非空（登记表可点开）。
         〔挡 10-30 事故①：产物只有长子域有，其他节点点开是空的〕
  EXAM-3 三流·抽屉三区非空（后端代理）：干活节点全有产物插头（W1 零警告）+ 流有左栏规则
         （W3 零警告）。〔挡：新流抽屉目标层/规则层全空〕
  EXAM-4 趋势·产物契约域化：input/output 节点声明 requirement_text/data_report 插头且
         契约文本非空。〔挡：趋势节点产物点不开〕
  EXAM-5 交付·流定义结构事实：发布校验零 error + 左栏规则非空（E1/W3 基线）。
已登记他卷不重复的：空表不收工/拒绝调用不跳步（test_node_contract_step45）、闸四态
（test_decision_gate）、暂停载荷（test_pause_payload）、登记冒烟（test_agent_fill_smoke）。
本卷全部 mock 供给者/假库，不发起真实模型请求、不触真库（协议槽走内存后端）。
"""
import asyncio
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

DEC = [{"slot": "gpu", "match_category": "GPU",
        "question": "GPU 在库有多款候选，选哪款？", "min_candidates": 2}]

# 假配件库：3 款 GPU 候选（10-30 事故同款场景形状）
_GPU_LIB = {
    "101": {"part_id": "101", "name": "沐曦 C500 64G", "price": 7500.0, "currency": "RMB"},
    "102": {"part_id": "102", "name": "壁仞 BR100 64G", "price": 9800.0, "currency": "RMB"},
    "103": {"part_id": "103", "name": "天数智芯 150S 64G", "price": 8200.0, "currency": "RMB"},
}


@pytest.fixture(autouse=True)
def _exam_env(monkeypatch):
    """考卷环境：问答协议走内存后端（不触真库）；决策闸供给者接 3 款 GPU 候选假库；
    落料回库核对走假库（名称忽略大小写与空格）。"""
    from app.services import data_tools, human_query as hq, skill_decision_gate as dg

    monkeypatch.setattr(hq, "_STORAGE", "memory")
    monkeypatch.setattr(hq, "_MEM", {})

    import re as _re

    def _rows():
        return [{"part_id": pid, "name": ent["name"], "category": "GPU",
                 "price": ent["price"], "currency": ent["currency"], "specs": {}}
                for pid, ent in _GPU_LIB.items()]

    def search_candidates(category, text, series, price_ok, limit):
        assert category == "GPU"
        return _rows()

    def pick_fresh(picks, category, spec, row):
        return False  # 考卷里用户信号走协议归档（answer_query），不经 KP_PICKS 预置

    dg.set_candidate_provider(search_candidates, pick_fresh)

    def _by_name(category, name, *, series="", price_ok=True, _repo=None):
        want = _re.sub(r"\s+", "", str(name or "")).lower()
        rows = [r for r in _rows() if _re.sub(r"\s+", "", r["name"]).lower() == want]
        return {"ok": True, "category": category, "db_category": category,
                "source": "kp_library/name_lookup", "rows": rows, "total": len(rows)}

    monkeypatch.setattr(data_tools, "lookup_parts_by_name", _by_name)
    yield
    dg.set_candidate_provider(None, None)


_CTX_TOKEN = [None]  # 考卷夹具的 TOOL_CTX token 暂存（各题 finally 取用复位）


def _set_ctx(thread_id: str, engine: dict, ext: dict, rows: list, saved: dict):
    from app.services import skill_tool_context
    _CTX_TOKEN[0] = skill_tool_context.TOOL_CTX.set({
        "thread_id": thread_id, "ext": ext, "task_active": True,
        "engine": engine, "kp_rows_ctx": rows, "kp_required_cats": set(),
        "kp_baseline_caps": {}, "save": lambda: saved.update(done=True),
    })


# ── EXAM-1 需求分析·多候选必停轮发卡（10-30 事故的机制化考题）─────────────────


def test_exam1_multi_candidate_cards_then_user_pick_settles():
    from app.services import human_query as hq
    from app.services import skill_tool_context
    from app.services import skill_tools_select
    from app.services.skill_node_state import KP_PICKS, KP_RECOMMEND

    engine = {"flow_configs": {"kp_reason": {"decisions": DEC}}}
    ext, saved = {}, {}
    rows = [{"row_key": "GPU|64G 显存", "category": "GPU", "description": "64G 显存",
             "qty": 1, "specified": True}]
    _set_ctx("t_exam1", engine, ext, rows, saved)
    try:
        res = skill_tools_select.tool_select_parts(
            {"picks": [{"row": "GPU|64G 显存", "part_id": "103",
                        "name": "天数智芯 150S 64G", "reason": "r"}]})
        # ① 闸拦下：结果带 decision_required，AI 的 pick 只记推荐不落锁定
        dr = res.get("decision_required")
        assert dr and dr.get("slot") == "gpu", "多候选无用户信号必须发卡"
        picks = ((engine.get("node_state") or {}).get("kp_reason") or {}).get(KP_PICKS) or {}
        assert not picks, "发卡后 AI pick 不得落锁定"
        recs = ((engine.get("node_state") or {}).get("kp_reason") or {}).get(KP_RECOMMEND) or {}
        assert recs, "AI pick 应记推荐默认项（客户点选兜底）"
        # ② 协议槽被占：choice 卡已立、锚在 gpu 槽（fail-closed：重试撞槽=拒）
        q = hq.open_query_of("t_exam1")
        assert q and q.get("kind") == "choice", "协议槽必须有 choice 卡"
        assert (q.get("meta") or {}).get("slot") == "gpu"
        labels = [o.get("label") for o in (q.get("options") or [])]
        assert len(labels) >= 2 and labels[0] == "天数智芯 150S 64G", "AI pick 置首标推荐"
        # ③ 用户点选（协议答案=用户信号）→ 复调放行，落定=点选款
        hq.answer_query("t_exam1", query_id=q["query_id"], selections=["沐曦 C500 64G"])
        res2 = skill_tools_select.tool_select_parts(
            {"picks": [{"row": "GPU|64G 显存", "part_id": "101",
                        "name": "沐曦 C500 64G", "reason": "r"}]})
        picks2 = ((engine.get("node_state") or {}).get("kp_reason") or {}).get(KP_PICKS) or {}
        assert picks2, "用户拍板后必须放行落定"
        landed = next(iter(picks2.values()))
        assert landed.get("name") == "沐曦 C500 64G", "落定款=用户点选款，不是 AI 原推荐"
    finally:
        skill_tool_context.TOOL_CTX.reset(_CTX_TOKEN[0])


def test_exam1b_ctx_reset_smoke():
    """占位防呆：TOOL_CTX 必须经 token 复位（ContextVar 语义）。"""
    from app.services import skill_tool_context
    token = skill_tool_context.TOOL_CTX.set({"ext": {}})
    skill_tool_context.TOOL_CTX.reset(token)


# ── EXAM-2 需求分析·节点产物非空（登记落表 → 产物载荷可点开）──────────────────


def test_exam2_agent_fill_artifact_nonempty():
    from app.services import skill_tools_fill
    from app.services.skill_node_artifacts import node_payload

    ext, saved = {}, {}
    from app.services import skill_tool_context
    token = skill_tool_context.TOOL_CTX.set({
        "ext": ext, "task_active": True, "save": lambda: saved.update(done=True)})
    try:
        res = skill_tools_fill.tool_fill_requirement(
            {"slots": {"server_type": "通用计算服务器", "purchase_qty": 2}})
        assert res.get("ok") is True and ext, "登记必须落表"
    finally:
        skill_tool_context.TOOL_CTX.reset(token)
    payload = node_payload({"ext": ext}, "agent_fill", "线索登记表", "")
    if not (payload.get("artifact") or payload.get("output")):
        # 产物契约域化的本意：真实流声明插头（slot=requirement_slots）+ 引擎事实 → 产物非空。
        # 合成引擎缺声明时按真实流的节点配置重考一次（声明缺失本身会被 EXAM-3 的 W1 抓住）。
        from app.repository.reasoning_flow_repo import ReasoningFlowRepository
        flow = ReasoningFlowRepository().get_active_flow("requirement_analysis")
        cfg = (flow.get("node_configs") or {}).get("agent_fill") or {}
        payload = node_payload({"ext": ext, "flow_configs": {"agent_fill": cfg}},
                               "agent_fill", "线索登记表", "")
    assert payload.get("artifact") or payload.get("output"), "登记节点产物载荷不得为空"


# ── EXAM-3 三流·抽屉三区非空（后端代理：W1/W3 零警告）─────────────────────────


@pytest.mark.parametrize("flow_key", ["requirement_analysis", "trend_analysis",
                                      "delivery_to_quotation"])
def test_exam3_drawer_three_zones_nonempty(flow_key):
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    from app.services import flow_validation as fv
    flow = ReasoningFlowRepository().get_active_flow(flow_key)
    assert flow, f"{flow_key} 无在用流"
    graph = flow.get("graph") or {}
    issues = fv.validate_flow(graph, flow.get("node_configs") or {},
                              graph.get("manual_rules") or "", flow_key=flow_key)
    w1 = [i for i in issues if i.get("code") == "W1"]
    w3 = [i for i in issues if i.get("code") == "W3"]
    assert not w1, f"{flow_key} 有干活节点缺产物插头（目标层空）：{w1}"
    assert not w3, f"{flow_key} 左栏规则为空（规则层空）"
    errs = [i for i in issues if i.get("severity") == "error"]
    assert not errs, f"{flow_key} 发布校验存在 error：{errs}"


# ── EXAM-4 趋势·产物契约域化（input/output 插头声明 + 契约文本非空）─────────────


def test_exam4_trend_artifact_contracts():
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    from app.services.skill_target_contract import first_artifact, format_contract
    flow = ReasoningFlowRepository().get_active_flow("trend_analysis")
    assert flow
    cfgs = flow.get("node_configs") or {}
    art_in = first_artifact(cfgs.get("input") or {})
    art_out = first_artifact(cfgs.get("output") or {})
    assert art_in.get("slot") == "requirement_text", "趋势 input 必须声明问题原文插头"
    assert art_out.get("slot") == "data_report", "趋势 output 必须声明趋势结论插头"
    assert format_contract(art_out).strip(), "趋势结论契约文本不得为空"


# ── EXAM-5 交付·流定义结构事实（E1 零 error + 规则非空）────────────────────────


def test_exam5_delivery_flow_definition_baseline():
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    from app.services import flow_validation as fv
    flow = ReasoningFlowRepository().get_active_flow("delivery_to_quotation")
    assert flow
    graph = flow.get("graph") or {}
    issues = fv.validate_flow(graph, flow.get("node_configs") or {},
                              graph.get("manual_rules") or "", flow_key="delivery_to_quotation")
    assert not [i for i in issues if i.get("severity") == "error"], "交付流定义必须零 error"
    assert str(graph.get("manual_rules") or "").strip(), "交付流左栏规则（大脑纪律）不得为空"
