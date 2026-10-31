# -*- coding: utf-8 -*-
"""决策闸（P1.5）单测：闸判定四态 + 协议用户信号 + 校验条款 E6。全 mock 不触库。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from ai_office import flow_validation as fv
from ai_office import human_query as hq
from ai_office import skill_decision_gate as dg

DEC = [{"slot": "gpu", "match_category": "GPU",
        "question": "GPU 在库有多款候选，选哪款？", "min_candidates": 2}]

_GPU_ROWS = [{"model": n, "specs": "64G"} for n in ("沐曦 C500", "壁仞166C", "天数智芯150S 64G")]


@pytest.fixture(autouse=True)
def _memory_storage(monkeypatch):
    monkeypatch.setattr(hq, "_STORAGE", "memory")
    monkeypatch.setattr(hq, "_MEM", {})


@pytest.fixture(autouse=True)
def _wire_gate():
    """闸机制只认回调（画边界解耦）：测试装假供给者，替代原先对 part_search/part_selector
    的 monkeypatch。默认无候选+无用户 pick；需要候选的用例经 _three_gpus 覆写检索侧。"""
    def search_candidates(category, text, series, price_ok, limit):
        return []

    def pick_fresh(picks, category, spec, row):
        pk = (picks or {}).get(str((row or {}).get("row_id") or ""))
        return isinstance(pk, dict)

    dg.set_candidate_provider(search_candidates, pick_fresh)
    yield
    dg.set_candidate_provider(None, None)


@pytest.fixture
def _three_gpus():
    def search_candidates(category, text, series, price_ok, limit):
        assert category == "GPU"
        return list(_GPU_ROWS)
    dg.set_candidate_provider(search_candidates, lambda *a, **k: False)


def test_card_when_multi_candidate_and_no_signal(_three_gpus):
    v = dg.part_lock_verdict(thread_id="t_card", decisions=DEC, category="GPU",
                             spec="64G 显存", pick_name="天数智芯150S 64G")
    assert v["verdict"] == "card"
    assert v["entry"]["kind"] == "choice"
    labels = [o["label"] for o in v["options"]]
    assert labels[0] == "天数智芯150S 64G"          # AI 的 pick 置首并标推荐（默认项）
    assert v["options"][0]["recommended"] is True
    assert len(labels) == 3
    assert v["entry"]["meta"] == {"slot": "gpu"}    # 用户信号按 slot 归档的锚点


def test_allow_when_single_candidate():
    dg.set_candidate_provider(lambda *a, **k: [{"model": "唯一款"}], lambda *a, **k: False)
    v = dg.part_lock_verdict(thread_id="t_single", decisions=DEC, category="GPU",
                             spec="64G", pick_name="唯一款")
    assert v["verdict"] == "allow"


def test_allow_after_user_signal(_three_gpus):
    # 先在协议里立问 + 用户作答（answer_query 只由 /answers 端点调 = 用户信号）
    entry = hq.open_query("t_signal", kind="choice", title="q", options=[{"label": "A"}],
                          meta={"slot": "gpu"})
    hq.answer_query("t_signal", query_id=entry["query_id"], selections=["沐曦 C500"])
    v = dg.part_lock_verdict(thread_id="t_signal", decisions=DEC, category="GPU",
                             spec="64G 显存", pick_name="沐曦 C500")
    assert v["verdict"] == "allow"


def test_fail_open_on_search_error():
    def boom(*a, **k):
        raise RuntimeError("search down")
    dg.set_candidate_provider(boom, lambda *a, **k: False)
    v = dg.part_lock_verdict(thread_id="t_fail", decisions=DEC, category="GPU",
                             spec="64G", pick_name="x")
    assert v["verdict"] == "allow" and v.get("degraded") is True


def test_allow_without_thread_id():
    v = dg.part_lock_verdict(thread_id="", decisions=DEC, category="GPU",
                             spec="64G", pick_name="x")
    assert v["verdict"] == "allow" and v.get("degraded") is True


def test_no_declaration_is_allow(_three_gpus):
    v = dg.part_lock_verdict(thread_id="t_nodecl", decisions=[], category="GPU",
                             spec="64G", pick_name="x")
    assert v["verdict"] == "allow"


def test_user_signal_scoped_by_slot(_three_gpus):
    """其他 slot 的回答不构成本决策点的用户信号。"""
    entry = hq.open_query("t_scope", kind="choice", title="q", options=[{"label": "A"}],
                          meta={"slot": "memory"})
    hq.answer_query("t_scope", query_id=entry["query_id"], selections=["A"])
    v = dg.part_lock_verdict(thread_id="t_scope", decisions=DEC, category="GPU",
                             spec="64G 显存", pick_name="x")
    assert v["verdict"] == "card"      # memory 的回答挡不住 gpu 的决策闸


def test_refuse_when_query_open_pending(_three_gpus):
    """卡已发等拍板（开放问题未答）时重试 → 拒绝自填。
    2026-10-31 E2E 实锤的漏洞：首次发卡后大脑重试，open_query 撞单开槽走 fail-open
    放行了自填锁定——协议状态必须 fail-closed。"""
    hq.open_query("t_pending", kind="choice", title="q", options=[{"label": "A"}],
                  meta={"slot": "gpu"})
    v = dg.part_lock_verdict(thread_id="t_pending", decisions=DEC, category="GPU",
                             spec="64G 显存", pick_name="x")
    assert v["verdict"] == "refuse" and v["reason"] == "decision_pending"


def test_refuse_when_other_question_open(_three_gpus):
    hq.open_query("t_other", kind="choice", title="q", options=[{"label": "A"}],
                  meta={"slot": "memory"})
    v = dg.part_lock_verdict(thread_id="t_other", decisions=DEC, category="GPU",
                             spec="64G 显存", pick_name="x")
    assert v["verdict"] == "refuse" and v["reason"] == "other_question_open"


# ── kp 阶段降级闸（确定性落料路径）────────────────────────────────────────

def _gpu_part(name="天数智芯150S 64G"):
    return {"category": "GPU", "request_spec": "64G 显存", "description": "64G 显存",
            "name": name, "row_id": "row-gpu-1", "qty": 1}


def test_demote_strips_self_picked_name():
    parts = [_gpu_part(), {"category": "Memory", "request_spec": "512G", "name": "64G DDR5"}]
    out = dg.decision_demote_parts(parts, DEC, picks={})
    gpu = out[0]
    assert "name" not in gpu and gpu.get("unmatched") is True
    assert gpu.get("decision_pending") == "gpu"
    assert gpu.get("demoted_name") == "天数智芯150S 64G"   # AI 自选留痕（可追溯）
    assert out[1]["name"] == "64G DDR5"                    # 非声明类目不受影响


def test_demote_spares_user_picked_row():
    picks = {"row-gpu-1": {"row_id": "row-gpu-1", "category": "GPU",
                           "request_spec": "64G 显存", "name": "沐曦 C500"}}
    parts = [_gpu_part(name="沐曦 C500")]
    out = dg.decision_demote_parts(parts, DEC, picks=picks)
    assert out[0].get("name") == "沐曦 C500"   # 用户点选过 → 放行


def test_demote_spares_waived_and_undeclared():
    waived = {"category": "GPU", "request_spec": "64G", "name": "x", "waived": True}
    undeclared = {"category": "NIC", "request_spec": "万兆", "name": "某网卡"}
    out = dg.decision_demote_parts([waived, undeclared], DEC, picks={})
    assert out[0].get("name") == "x" and not out[0].get("unmatched")
    assert out[1].get("name") == "某网卡"


# ── 校验条款 E6：决策点声明完备性 ─────────────────────────────────────────

def _flow(node_cfg):
    return {"nodes": [{"id": "a", "type": "input", "label": "入"},
                      {"id": "w", "type": "agent", "label": "配"},
                      {"id": "b", "type": "output", "label": "出"}],
            "edges": [], "manual_rules": "r"}, node_cfg


def test_validator_e6_incomplete_decision():
    graph, cfgs = _flow({"w": {"decisions": [{"slot": "gpu", "match_category": "GPU"}]}})
    issues = fv.validate_flow(graph, cfgs)
    assert any(i["code"] == "E6" and "question" in i["message"] for i in issues)


def test_validator_e6_complete_passes():
    graph, cfgs = _flow({"w": {"decisions": [{"slot": "gpu", "match_category": "GPU",
                                              "question": "选哪款？", "min_candidates": 2}]}})
    issues = fv.validate_flow(graph, cfgs)
    assert not [i for i in issues if i["code"] == "E6"]
