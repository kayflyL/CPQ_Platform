# -*- coding: utf-8 -*-
"""P5-B1：跨回合断点一致性守卫。

断点只有一个出处——上一回合的暂停载荷 `mem.engine_pause`（事实与原因码，无话术）。
本回合一开回合就读它：停在哪（resume_from）、进度是什么（resume.steps_done）。
与 `mem.steps_done` 不一致时以载荷为准，并把两侧差异记成事实（resume_mismatch）——不猜。
"""
import pytest

from app.services import skill_turn_engine
from app.services.skill_plan_runtime import pause_payload


def _runtime(mem: dict):
    return skill_turn_engine._SkillTurnRuntime(
        thread_id="t_pause", role_key="tech", persona="你是测试同事",
        full_text="需要一台服务器", history=[], ext={}, mem=mem, flow={})


def _prepared(mem: dict) -> dict:
    rt = _runtime(mem)
    rt._prepare()
    return rt.engine


def test_pause_payload_is_the_resume_source_when_in_sync():
    """载荷与 mem 一致：进度取同一份，不产生差异事实，但留下 resume_from（停在哪/为什么）。"""
    pause = pause_payload(kind="brain_ask", step="kp_reason", label="配件选型",
                          reason_code="missing_critical", steps_done=["input", "agent_fill"])
    engine = _prepared({"engine_pause": pause, "steps_done": ["agent_fill", "input"]})
    assert engine["steps_done"] == {"input", "agent_fill"}
    assert engine["resume_from"] == {"kind": "brain_ask", "step": "kp_reason",
                                     "reason_code": "missing_critical", "resumable": True}
    assert "resume_mismatch" not in engine


def test_pause_payload_wins_and_mismatch_is_recorded_as_facts():
    """不一致：以载荷为准（它是回合终态快照），两侧差异只记事实，不做任何话术加工。"""
    pause = pause_payload(kind="brain_ask", step="agent_fill",
                          reason_code="missing_critical", steps_done=["input"])
    engine = _prepared({"engine_pause": pause, "steps_done": ["input", "kp_reason", "compose"]})
    assert engine["steps_done"] == {"input"}, "载荷的进度才是断点，mem 的旧进度不得覆盖"
    assert engine["resume_mismatch"] == {"pause": ["input"], "mem": ["compose", "input", "kp_reason"]}


def test_without_pause_falls_back_to_mem_progress():
    """没暂停（上一回合正常收口）：进度仍来自 mem，且不编造 resume_from。"""
    engine = _prepared({"steps_done": ["input", "agent_fill"]})
    assert engine["steps_done"] == {"input", "agent_fill"}
    assert "resume_from" not in engine and "resume_mismatch" not in engine
