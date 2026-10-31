# -*- coding: utf-8 -*-
"""事件契约快照（ABI 事件协议分册的执法面）：两台运行时广播载荷的键集锁定。

键集变更必须先改《docs/引擎ABI-v0.md》再改这里——前端画布/任务条按这些键渲染，
静默加删键就是"画布全灰/输出物为空"那族事故的入口（2026-10-21 交付流实锤）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.skill_node_artifacts import node_payload


def test_pipeline_start_payload_shape():
    from app.services.transaction_turn import _pipeline_start_payload
    p = _pipeline_start_payload("标题", "交付流",
                                [{"key": "n0", "label": "接收"}, {"key": "n1", "label": "落位"}], "t1")
    assert p["type"] == "pipeline_start"
    assert set(p) == {"type", "title", "steps", "thread_id"}
    assert set(p["steps"][0]) == {"key", "label"}
    assert p["title"] == "标题"


def test_pipeline_start_title_falls_back_to_flow_label():
    from app.services.transaction_turn import _pipeline_start_payload
    assert _pipeline_start_payload("  ", "交付流", [], "t")["title"] == "交付流"


def test_step_running_payload_shape():
    from app.services.transaction_turn import _step_running_payload
    p = _step_running_payload("n1", "落位", "t1")
    assert set(p) == {"type", "step", "label", "status", "summary", "thread_id"}
    assert p["status"] == "running"
    assert p["summary"] == ""


def test_step_done_payload_shape():
    from app.services.transaction_turn import _step_done_payload
    p = _step_done_payload("n1", "落位", True, 1234, "submit_cost_sheet：完成", {"title": "卡"}, "t1")
    assert set(p) == {"type", "step", "label", "status", "duration_ms",
                      "output", "summary", "input", "artifact", "thread_id"}
    assert p["status"] == "done"
    assert p["artifact"]["kind"] == "artifact_card"
    assert p["output"] == "submit_cost_sheet：完成"
    empty = _step_done_payload("n1", "落位", False, 5, "", None, "t1")
    assert empty["status"] == "running"
    assert empty["artifact"] is None
    assert empty["output"] is None


def test_state_events_shape():
    """状态语义只在引擎算一次（te.state_events），壳只搬运——载荷键集同样入快照。"""
    from app.services import transaction_engine as te
    steps = [{"key": "n1", "label": "落位", "skip_note": ""}]
    evs = te.state_events(steps, {}, "t1")  # 空案台 → 全 pending → 无事件
    assert evs == []


def test_skill_node_payload_shape():
    p = node_payload({"flow_configs": {}}, "n1", "节点", "")
    assert set(p) == {"type", "step", "label", "status", "input", "output", "summary", "artifact"}
    assert p["type"] == "node_trace"
    assert p["status"] == "done"
    assert "本节点未注册产物" in p["summary"]  # 白盒不装懂：无插头如实说空


def test_skill_step_progress_payload_shape():
    """step_progress（大脑过程状态）——2026-10-31 考卷发现 ABI 漏登记后补入分册一并提取构造器。"""
    from app.services.skill_step_runtime import _step_progress_payload
    p = _step_progress_payload("react", "重试中")
    assert set(p) == {"type", "step", "sub"}
    assert p["type"] == "step_progress" and p["step"] == "react"
    assert p["sub"] == {"kind": "tool", "text": "重试中"}
