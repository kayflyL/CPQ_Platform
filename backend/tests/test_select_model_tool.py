# -*- coding: utf-8 -*-
"""机型选配冒烟回归：多候选未锁定时由唯一大脑在 model_reason 节点回合从引擎候选池选定。

select_model 是任务期工具（B2 接地）：取值域 = 引擎确定性构建的候选池，池外型号一律
拒绝。本文件只验证：任务期闸门、池内接地校验、选定结果写入模型选型产物（model_pick/引擎
model_selection）、目标层「AI 反问」策略消费与大脑回合收敛语义；不发起真实模型请求
（run_stream_chat_loop 打桩）。

2026-09-10 契约：model_reason 只写自己的产物（model_pick/baseline/model_selection），
不回填线索登记表 ext.server_model（登记表冻结）。
"""
import os
import sys
from app.services import skill_tool_context
from app.services import skill_tools_model
from app.services import skill_turn_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_POOL = [
    {"server_model_id": 11, "id": 111, "name": "ES22V3-P", "series": "Polaris", "form": "2U"},
    {"server_model_id": 22, "id": 222, "name": "ESA24V3-P", "series": "Polaris", "form": "2U"},
]


def _call_select(args: dict, *, task_active: bool = True, pool=None, ext=None) -> dict:
    from app.services import skill_chat
    saved = {}
    skill_tool_context.TOOL_CTX.set({
        "ext": ext if ext is not None else {}, "task_active": task_active,
        "model_pool": _POOL if pool is None else pool,
        "save": lambda: saved.update(done=True),
    })
    return skill_tools_model.tool_select_model(args)


def test_select_model_blocked_before_task():
    """进任务前工具不可用：普通对话没有机型锁定权。"""
    res = _call_select({"model": "ES22V3-P", "reason": "r"}, task_active=False)
    assert res.get("ok") is False
    assert res.get("error") == "task_not_active"


def test_select_model_rejects_empty_pool():
    res = _call_select({"model": "ES22V3-P", "reason": "r"}, pool=[])
    assert res.get("ok") is False
    assert res.get("error") == "empty_pool"


def test_select_model_locks_pool_member_by_name_or_id():
    """池内命中（名称忽略大小写 / id 精确）→ 返回选定结果，不回填登记表 server_model。"""
    ext = {}
    res = _call_select({"model": "es22v3-p", "reason": "预算内最匹配"}, ext=ext)
    assert res.get("ok") is True
    assert res["selected"]["name"] == "ES22V3-P"
    assert "server_model" not in ext, "model_reason 只写自己的产物，不回填登记表"

    ext2 = {}
    res2 = _call_select({"model_id": "22", "reason": "x"}, ext=ext2)
    assert res2.get("ok") is True
    assert res2["selected"]["name"] == "ESA24V3-P"
    assert "server_model" not in ext2


def test_select_model_rejects_out_of_pool():
    """接地：池外型号（LLM 幻觉/客户指定未上架）一律拒绝并回显候选清单。"""
    res = _call_select({"model": "ZHAOXIN-KH-X99", "reason": "r"})
    assert res.get("ok") is False
    assert res.get("error") == "not_in_pool"
    assert "ES22V3-P" in res.get("candidates", [])


def test_select_model_requires_args():
    res = _call_select({"reason": "r"})
    assert res.get("ok") is False
    assert res.get("error") == "invalid_args"


def test_model_field_ask_policy_from_target_layer():
    """目标层「AI 反问」开关：server_model.ask=true → 大脑不代选（弹卡交客户）；缺省 False。"""
    from app.services.skill_plan_runtime import _model_field_ask
    assert _model_field_ask({}) is False
    on = {"target": {"artifacts": [{"fields": [
        {"key": "server_model", "label": "服务器型号", "ask": True}]}]}}
    off = {"target": {"artifacts": [{"fields": [
        {"key": "server_model", "label": "服务器型号", "ask": False}]}]}}
    assert _model_field_ask(on) is True
    assert _model_field_ask(off) is False


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def _wire(result: dict, engine: dict) -> None:
    """把一轮大脑结果交节点插件接线（产品路径：run_skill_agent_turn 的 settle 就是这么调的）。"""
    from app.services.skill_node_plugins import plugin_for
    plugin_for("model_reason").wire_result(engine, result)


def _choose(name: str, reason: str = "r") -> dict:
    from app.services import skill_chat
    skill_tool_context.TOOL_CTX.set({"ext": {}, "task_active": True, "model_pool": _POOL,
                             "save": lambda: None})
    return skill_tools_model.tool_select_model({"model": name, "reason": reason})


def test_model_wire_result_locks_own_artifact_not_registration():
    """大脑经 choose_model 选定 → 落本节点产物（baseline/model_selection）并据此锁定。"""
    res = _choose("ESA24V3-P", "双路更适合虚拟化")
    engine = {"ext": {}, "baselines_pool": _POOL}
    _wire({"tool_calls_log": [{"name": "choose_model", "result": res}]}, engine)
    assert engine["_locked_baseline"]["name"] == "ESA24V3-P"
    assert engine["model_selection"]["series"] == "Polaris"
    assert engine["model_pick_reason"] == "双路更适合虚拟化"
    assert "server_model" not in engine["ext"], "选定结果写进自节点产物，不回填登记表"


def test_model_wire_result_ignores_declined_and_out_of_pool():
    """大脑不调工具 / 池外被拒 → 不落锁（引擎回退弹机型候选卡，绝不臆造机型）。"""
    engine = {"ext": {}, "baselines_pool": _POOL}
    _wire({"tool_calls_log": []}, engine)
    assert "_locked_baseline" not in engine

    bad = _choose("Not-In-Pool")
    assert bad.get("ok") is False
    engine2 = {"ext": {}, "baselines_pool": _POOL}
    _wire({"tool_calls_log": [{"name": "choose_model", "result": bad}]}, engine2)
    assert "_locked_baseline" not in engine2 and "model_pick" not in engine2


def test_model_wire_result_never_writes_registration_ext():
    """阶段函数 dict(ext) 复制重赋也不丢选定：落锁只看引擎产物，不依赖 ext 对象身份。"""
    from app.services import skill_chat
    stale = {"server_type": "通用计算服务器"}
    engine = {"ext": dict(stale), "baselines_pool": _POOL}
    skill_tool_context.TOOL_CTX.set({"ext": stale, "task_active": True, "model_pool": _POOL,
                             "save": lambda: None})
    res = skill_tools_model.tool_select_model({"model": "ES22V3-P", "reason": "r"})
    _wire({"tool_calls_log": [{"name": "choose_model", "result": res}]}, engine)
    assert engine["_locked_baseline"]["name"] == "ES22V3-P"
    assert not stale.get("server_model") and not engine["ext"].get("server_model")


def test_brain_attempts_retries_rejected_tool_then_settles_last_round():
    """工具被拒 → 真实返回喂回重试（≤3 次）；末轮不再因被拒而跳过收口校验。"""
    from unittest.mock import patch
    from app.services import skill_chat

    calls = {"n": 0}
    settled = {"n": 0}

    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        res = _choose("Not-In-Pool")
        return {"tool_calls_log": [{"name": "choose_model", "result": res}]}

    async def settle(result):
        settled["n"] += 1
        return {"action": "retry", "feedback": "still bad"}

    with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop):
        _result, action = _run(skill_turn_engine.run_brain_attempts(
            "客户消息", loop_kwargs={}, settle=settle))
    assert calls["n"] == 3, "工具被拒最多重试 3 次"
    assert settled["n"] == 1, "末轮照样交 settle 判定（本步是否完成由产物说了算）"
    assert action == "retry"
