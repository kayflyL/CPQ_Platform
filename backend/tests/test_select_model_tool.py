# -*- coding: utf-8 -*-
"""机型选配冒烟回归：多候选未锁定时由唯一大脑在 model_reason 节点回合从引擎候选池选定。

select_model 是任务期工具（B2 接地）：取值域 = 引擎确定性构建的候选池，池外型号一律
拒绝。本文件只验证：任务期闸门、池内接地校验、落槽、目标层「AI 反问」策略消费与
大脑回合收敛语义；不发起真实模型请求（run_stream_chat_loop 打桩）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_POOL = [
    {"server_model_id": 11, "id": 111, "name": "ES22V3-P", "series": "Polaris", "form": "2U"},
    {"server_model_id": 22, "id": 222, "name": "ESA24V3-P", "series": "Polaris", "form": "2U"},
]


def _call_select(args: dict, *, task_active: bool = True, pool=None, ext=None) -> dict:
    from app.services import skill_chat
    saved = {}
    # ext 不复制：工具必须原地写引擎共享的同一对象（副本会丢落表，同 fill 的实测坑）
    skill_chat._TOOL_CTX.set({
        "ext": ext if ext is not None else {}, "task_active": task_active,
        "model_pool": _POOL if pool is None else pool,
        "save": lambda: saved.update(done=True),
    })
    return skill_chat.tool_select_model(args)


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
    """池内命中（名称忽略大小写 / id 精确）→ 落槽 server_model 并返回选定结果。"""
    ext = {}
    res = _call_select({"model": "es22v3-p", "reason": "预算内最匹配"}, ext=ext)
    assert res.get("ok") is True
    assert res["selected"]["name"] == "ES22V3-P"
    assert ext.get("server_model") == "ES22V3-P"

    ext2 = {}
    res2 = _call_select({"model_id": "22", "reason": "x"}, ext=ext2)
    assert res2.get("ok") is True
    assert ext2.get("server_model") == "ESA24V3-P"


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


def test_model_brain_records_pick_in_engine_ctx():
    """大脑回合把选定结果写回 engine_ctx（model_pick/reason/narration），引擎据此重跑确定性阶段。"""
    from unittest.mock import patch
    from app.services import skill_chat

    async def fake_loop(msg, **kwargs):
        res = skill_chat.tool_select_model({"model": "ESA24V3-P", "reason": "双路更适合虚拟化"})
        return {"tool_calls_log": [{"name": "select_model", "result": res}]}

    brain = skill_chat.make_agent_brain(persona="测试角色")
    engine_ctx = {"ext": {}, "baselines_pool": _POOL}
    # 生产链路里 handle_skill_chat_turn 先把 ext/save 放进 _TOOL_CTX（brain 回合合并继承）
    skill_chat._TOOL_CTX.set({"ext": engine_ctx["ext"], "save": lambda: None})
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("model_reason", {}, engine_ctx))
    assert engine_ctx["model_pick"]["name"] == "ESA24V3-P"
    assert engine_ctx["model_pick_reason"] == "双路更适合虚拟化"
    assert engine_ctx["ext"]["server_model"] == "ESA24V3-P"


def test_model_brain_respects_declined_pick():
    """大脑主动不调用工具（无法决断）→ 不重试不逼选，model_pick 缺失，引擎回退弹卡。"""
    from unittest.mock import patch
    from app.services import skill_chat

    calls = {"n": 0}

    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        return {"tool_calls_log": []}  # 没调工具 = 主动放弃选择

    brain = skill_chat.make_agent_brain(persona="测试角色")
    engine_ctx = {"ext": {}, "baselines_pool": _POOL}
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("model_reason", {}, engine_ctx))
    assert "model_pick" not in engine_ctx
    assert calls["n"] == 1


def test_model_brain_retries_rejected_pick_then_gives_up():
    """调了工具但被池校验拒绝 → 喂回真实返回重试（≤3 次），仍失败不落选定。"""
    from unittest.mock import patch
    from app.services import skill_chat

    calls = {"n": 0}

    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        res = skill_chat.tool_select_model({"model": "Not-In-Pool", "reason": "r"})
        return {"tool_calls_log": [{"name": "select_model", "result": res}]}

    brain = skill_chat.make_agent_brain(persona="测试角色")
    engine_ctx = {"ext": {}, "baselines_pool": _POOL}
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("model_reason", {}, engine_ctx))
    assert calls["n"] == 3
    assert "model_pick" not in engine_ctx


def test_model_brain_rebinds_ext_after_phase_copy():
    """阶段函数（normalize/model）会 dict(ext) 复制后重赋 ctx["ext"]——brain 回合必须
    把 _TOOL_CTX["ext"] 重绑到引擎当前对象，否则 select_model 写进被弃用的旧副本，
    重跑 phase_model_reason 读不到 server_model，锁定静默丢失（E2E 实测踩坑）。"""
    from unittest.mock import patch
    from app.services import skill_chat

    async def fake_loop(msg, **kwargs):
        res = skill_chat.tool_select_model({"model": "ES22V3-P", "reason": "r"})
        return {"tool_calls_log": [{"name": "select_model", "result": res}]}

    stale = {"server_type": "通用计算服务器"}   # 回合开始时的对象（handle_skill_chat_turn 绑定它）
    current = dict(stale)                       # 模拟阶段函数的复制重赋
    engine_ctx = {"ext": current, "baselines_pool": _POOL}
    skill_chat._TOOL_CTX.set({"ext": stale, "save": lambda: None})
    brain = skill_chat.make_agent_brain(persona="测试角色")
    with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
        _run(brain("model_reason", {}, engine_ctx))
    assert current.get("server_model") == "ES22V3-P", "工具落表必须写进引擎当前 ext，而非旧副本"
