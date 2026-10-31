# -*- coding: utf-8 -*-
"""流声明校验器单测：条款逐条 + 模式开关 + 抽屉保存闸。全内存不触库。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_office import flow_validation as fv


def _node(key, type_="agent", label="节点"):
    return {"id": key, "type": type_, "label": label}


def _graph(nodes, edges=None, manual_rules=""):
    return {"nodes": nodes, "edges": edges or [], "manual_rules": manual_rules}


_PLUGGED_CFG = {"target": {"artifacts": [{"slot": "data_report", "kind": "document", "name": "报告"}]},
                "enabled_tools": ["query_data"]}


def test_empty_graph_is_error():
    issues = fv.validate_flow({}, {})
    assert any(i["code"] == "E1" and i["severity"] == "error" for i in issues)


def test_missing_output_node_is_error():
    issues = fv.validate_flow(_graph([_node("a", "input")]), {})
    assert any(i["code"] == "E1" and "output" in i["message"] for i in issues)


def test_node_without_label_is_error():
    issues = fv.validate_flow(_graph([_node("a", "input", "  "), _node("b", "output")]), {})
    assert any(i["code"] == "E2" and i["node"] == "a" for i in issues)


def test_worker_without_plug_is_warning():
    issues = fv.validate_flow(
        _graph([_node("a", "input"), _node("w", "agent"), _node("b", "output")]), {"w": {}})
    assert any(i["code"] == "W1" and i["node"] == "w" for i in issues)


def test_unknown_slot_is_error():
    bad = {"target": {"artifacts": [{"slot": "no_such_slot"}]}, "enabled_tools": ["t"]}
    issues = fv.validate_flow(
        _graph([_node("a", "input"), _node("w", "agent"), _node("b", "output")]), {"w": bad})
    assert any(i["code"] == "E3" and i["severity"] == "error" and i["node"] == "w" for i in issues)


def test_known_slot_passes_clean():
    issues = fv.validate_flow(
        _graph([_node("a", "input"), _node("w", "agent"), _node("b", "output")],
               manual_rules="规则"),
        {"w": dict(_PLUGGED_CFG)})
    assert not [i for i in issues if i["node"] == "w"]


def test_edge_to_missing_node_is_error():
    issues = fv.validate_flow(
        _graph([_node("a", "input"), _node("b", "output")],
               edges=[{"id": "e1", "source": "a", "target": "ghost"}]), {})
    assert any(i["code"] == "E4" for i in issues)


def test_empty_manual_rules_is_warning():
    issues = fv.validate_flow(_graph([_node("a", "input"), _node("b", "output")]), {})
    assert any(i["code"] == "W3" and i["severity"] == "warning" for i in issues)


def test_validate_node_declared_but_unregistered_slot():
    issues = fv.validate_node("w", "agent", {"target": {"artifacts": [{"slot": "ghost"}]}})
    # 有插头不再报 W1；槽未注册报 E3；agent 无白名单报 W2
    assert {i["code"] for i in issues} == {"E3", "W2"}


def test_non_worker_node_has_no_plug_terms():
    assert fv.validate_node("b", "output", {}) == []
    assert fv.validate_node("n0", "input", {}) == []


def test_deterministic_engine_node_needs_no_whitelist():
    issues = fv.validate_node(
        "c", "compose", {"target": {"artifacts": [{"slot": "plans"}]}})
    assert not [i for i in issues if i["code"] == "W2"]


def test_tooling_node_without_whitelist_is_warning():
    issues = fv.validate_node(
        "w", "agent", {"target": {"artifacts": [{"slot": "data_report"}]}})
    assert any(i["code"] == "W2" for i in issues)


def test_mode_defaults_to_report(monkeypatch):
    monkeypatch.delenv("FLOW_VALIDATION_MODE", raising=False)
    assert fv.mode() == "report"
    assert fv.is_enforce() is False


def test_enforce_mode(monkeypatch):
    monkeypatch.setenv("FLOW_VALIDATION_MODE", "enforce")
    assert fv.is_enforce() is True


def test_transaction_runtime_flow_skips_plug_terms():
    """事务内核已注册的流（delivery_to_quotation）产物契约=artifact_card，不受 W1/E3 约束。"""
    issues = fv.validate_flow(
        _graph([_node("a", "input"), _node("w", "agent"), _node("b", "output")],
               manual_rules="规则"),
        {"w": {"target": {"artifacts": [{"slot": "quotation"}]},
               "enabled_tools": ["submit_cost_sheet"]}},
        flow_key="delivery_to_quotation")
    assert not [i for i in issues if i["code"] in ("W1", "E3")]


def test_runtime_of_unknown_flow_is_skill():
    assert fv.runtime_of("") == "skill"
    assert fv.runtime_of("no_such_flow") == "skill"
