# -*- coding: utf-8 -*-
"""暂停载荷对象化（P4-1）守卫：中断点只有一份对象，且不许再各拼一半。

1. 工厂形状固定（只有事实 + 原因码，没有话术字段）；
2. 编排壳里所有暂停/等待广播都必须走 _emit_pause（不许再手搓 pipeline_waiting）；
3. 办公室状态词由载荷派生，对象原样带给看板。
"""
import asyncio
import pathlib

from app.services import skill_turn_engine
from app.services.office_events import publish_pipeline_office_event
from app.services.office_hub import office_hub
from app.services.skill_plan_runtime import engine_result_of, pause_payload

_FACT_KEYS = {"kind", "step", "label", "reason_code", "pending", "resumable", "at", "resume"}


def test_pause_payload_is_facts_only():
    p = pause_payload(kind="brain_ask", step="kp_reason", label="配件选型",
                      pending=[{"slot": "brain_ask", "reason_code": "brain_ask", "options": 0}],
                      steps_done=["agent_fill", "model_reason"])
    assert set(p) == _FACT_KEYS, p
    assert p["reason_code"] == "brain_ask"
    assert p["pending"] == [{"slot": "brain_ask", "reason_code": "brain_ask", "options": 0}]
    assert p["resume"] == {"steps_done": ["agent_fill", "model_reason"],
                           "awaiting": "user_input"}
    blob = repr(p)
    for word in ("question", "message", "话术", "提示词"):
        assert word not in blob, word


def test_every_pause_broadcast_goes_through_single_emitter():
    src = pathlib.Path(skill_turn_engine.__file__).read_text(encoding="utf-8")
    leaked = [s for s in ('_emit_pipeline_phase("pipeline_waiting"',
                          '_emit_pipeline_phase("pipeline_paused"') if s in src]
    assert not leaked, "暂停广播绕过载荷对象：" + repr(leaked)
    assert src.count("await self._emit_pause(") >= 5, "暂停点少了：载荷没覆盖全部出口"


def test_abort_step_records_pause_object():
    rt = skill_turn_engine._SkillTurnRuntime(
        thread_id="t_pause", role_key="tech", persona="p", full_text="f",
        history=[], ext={}, mem={}, flow={})
    rt.engine = {"steps_done": {"agent_fill"}}
    rt.narration, rt.node_narration = [], {}
    rt._cur_step = {"key": "kp_reason", "label": "配件选型"}
    events = []

    async def sink(payload):
        events.append(payload)

    rt.event_sink = sink
    assert asyncio.run(rt._abort_step("kp_reason", "llm_timeout")) == "failed"
    pause = rt.engine["engine_pause"]
    assert pause["kind"] == "failure" and pause["reason_code"] == "llm_timeout"
    assert pause["step"] == "kp_reason" and pause["label"] == "配件选型"
    assert pause["resume"] == {"steps_done": ["agent_fill"], "awaiting": "user_input"}
    assert [e["type"] for e in events] == ["pipeline_paused"]
    assert events[0]["pause"] == pause
    assert engine_result_of(rt.engine)["pause"] == pause


def test_office_status_derives_from_pause_payload():
    role = "pause_guard_role"

    async def scenario():
        await publish_pipeline_office_event(
            {"type": "pipeline_paused", "thread_id": "t_pause_office",
             "colleague_role_key": role,
             "pause": pause_payload(kind="failure", step="kp_reason",
                                    reason_code="llm_timeout")})
        return office_hub.snapshot([role]).get(role) or {}

    snap = asyncio.run(scenario())
    assert snap.get("status") == "waiting_input"
    assert snap.get("activity") == "流程暂停"
    assert (snap.get("pause") or {}).get("reason_code") == "llm_timeout"


def test_approval_pause_uses_the_same_payload_object():
    """P5-B3：审批中断也走同一份载荷工厂（kind=approval），不再手搓第二套中断形状。"""
    # 2026-09-11 拆分后同事回合实现分布在 colleague_turn_* 家族；断言扫全家族，
    # 避免「实现搬了家 → 守卫静默失效」。
    from app.services import (colleague_prompt, colleague_turn_io,
                              colleague_turn_runners, colleague_turn_service)
    src = "\n".join(pathlib.Path(m.__file__).read_text(encoding="utf-8")
                    for m in (colleague_prompt, colleague_turn_io,
                              colleague_turn_runners, colleague_turn_service))
    assert 'pause_payload(kind="approval"' in src, "审批中断没有走载荷工厂（两套形状回来了）"
    p = pause_payload(kind="approval", pending=[{"governance_id": 7, "tool": "submit_approval"}],
                      steps_done=[])
    assert set(p) == _FACT_KEYS and p["kind"] == "approval"
    assert p["pending"][0]["governance_id"] == 7
    assert p["resume"]["awaiting"] == "user_input"


def test_e2e_pause_kind_registry_stays_in_sync_with_emitters():
    """P5-C1：e2e 报告只把「登记过的 kind」当正常——登记表必须等于真实发射点。

    新增一个暂停出口却忘了登记 → e2e 报告会把它标成「未登记的 kind」，看着像 bug；
    反过来删了出口却留着登记 → 登记表变成谎言。两边都钉死（防返工）。
    """
    import ast
    import json as _json
    import re

    from app.services import (colleague_prompt as _cp, colleague_turn_io as _cio,
                              colleague_turn_runners as _ctr,
                              colleague_turn_service as _cts)

    emitted = set()
    for src in (pathlib.Path(skill_turn_engine.__file__).read_text(encoding="utf-8"),
                *[pathlib.Path(m.__file__).read_text(encoding="utf-8")
                  for m in (_cp, _cio, _ctr, _cts)]):
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, ast.Call):
                continue
            fname = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if fname == "_emit_pause" and node.args:
                for sub in ast.walk(node.args[0]):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        emitted.add(sub.value)
            if fname == "pause_payload":
                for kw in node.keywords:
                    if (kw.arg == "kind" and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)):
                        emitted.add(kw.value.value)
    emitted.discard("pipeline_paused")
    emitted.discard("pipeline_waiting")

    e2e = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "e2e_skill.py"
    reg = re.search(r"PAUSE_KINDS = \{([^}]*)\}", e2e.read_text(encoding="utf-8"))
    assert reg, "e2e_skill.py 里的 PAUSE_KINDS 登记表不见了"
    registered = set(re.findall(r'"([a-z_]+)"', reg.group(1)))

    assert emitted == registered, (
        "暂停 kind 登记表与真实发射点不一致："
        f"漏登记={sorted(emitted - registered)}，多登记={sorted(registered - emitted)}")

    # 夹具必须存在且能解析（真机跑之前先保证脚本不会读炸）
    sc = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "e2e_scenario_stall.json"
    assert sc.exists(), "P5-C1 的停滞场景夹具缺失"
    _json.loads(sc.read_text(encoding="utf-8"))
