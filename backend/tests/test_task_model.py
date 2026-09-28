# -*- coding: utf-8 -*-
"""Claude Code 式任务模型契约：入口同意制提示词 / 步骤单源 / 中途消息排队。"""
from app.services import skill_tools_fill
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_skill_steps_view_single_source():
    """步骤清单单源：pipeline_start 与角色提议话术共用，画布 label/description 覆盖生效。"""
    from app.services.skill_plan_runtime import skill_steps_view
    cfg = {"model_reason": {"label": "机型锁定", "description": "按需求从在售目录中选定机型骨架"}}
    steps = skill_steps_view(cfg)
    assert [s["step"] for s in steps] == [
        "input", "agent_fill", "model_reason", "kp_reason", "compose", "output"]
    mr = next(s for s in steps if s["step"] == "model_reason")
    assert mr["label"] == "机型锁定" and mr["description"] == "按需求从在售目录中选定机型骨架"
    assert "description" not in next(s for s in steps if s["step"] == "kp_reason")
    # 客户可见里程碑：跳过对话里自然发生的 input/agent_fill
    uf = skill_steps_view(cfg, user_facing_only=True)
    assert [s["step"] for s in uf] == ["model_reason", "kp_reason", "compose", "output"]


def test_requirement_prompt_consent_contract():
    """同意制契约已移除：requirement_prompt 不再背着说服/提交散文；阶段提示只留 ACTIVE 任务态。"""
    from app.services import colleague_turn_service as svc
    from app.services.skill_tools_fill import requirement_prompt
    # 阶段提示（ACTIVE）：任务态指令，不再有提交/确认轮
    manifest = {"node_configs": {}}
    hint = svc._skill_phase_hint(manifest, svc.SKILL_SESSION_ACTIVE)
    assert "直接推进流程" in hint
    # 无 IDLE/PROPOSING 阶段：非 ACTIVE 一律不产出提示
    assert svc._skill_phase_hint(manifest, "proposing") == ""
    # requirement_prompt 只剩登记表视图+价格守卫，不再重复说服/提交散文
    p = requirement_prompt({})
    assert "客户已同意" not in p
    assert "主动提议" not in p
    assert "【配置流程步骤】" not in p


def test_requirement_prompt_pre_task_hides_target_form():
    """进任务前不碰目标表：slots=None（任务未开始）不暴露登记表内容。"""
    from app.services.skill_tools_fill import requirement_prompt
    p = requirement_prompt(None)
    assert "存储服务器" not in p and "ES220 V3" not in p
    assert "本轮没有登记表" in p                     # 只报事实：任务未开始，本轮无登记表
    assert "禁止" not in p                          # 纪律属于左栏提示词，不回代码
    # 任务回合（slots 传入）才暴露登记表视图
    p_task = requirement_prompt({"server_type": "存储服务器", "server_model": "ES220 V3"})
    assert "存储服务器" in p_task and "ES220 V3" in p_task


def test_midrun_message_queued_not_rejected(monkeypatch):
    """任务执行中的消息=排队引导（串行续跑），不再是「请等它完成」式拒绝。"""
    from app.services import colleague_turn_service as svc

    svc._THREAD_TURN_LOCKS.pop("t1", None)
    svc._THREAD_TURN_QUEUE.pop("t1", None)
    try:
        async def main():
            lock = svc._THREAD_TURN_LOCKS.setdefault("t1", asyncio.Lock())
            await lock.acquire()

            broadcasts = []

            async def fake_broadcast(tid, payload):
                broadcasts.append((tid, payload))
            monkeypatch.setattr(svc.assistant_hub, "broadcast", fake_broadcast)

            # 中途消息：应进入排队（不落库拒绝消息，只广播排队提示）
            await svc.run_colleague_turn("t1", "补一句：内存要 256G", None, [],
                                         {"role_key": "assistant"})
            assert len(svc._THREAD_TURN_QUEUE["t1"]) == 1
            queued = svc._THREAD_TURN_QUEUE["t1"][0]
            assert queued["user_text"] == "补一句：内存要 256G"
            assert queued["option_slot"] is None and queued["colleague"]["role_key"] == "assistant"
            assert broadcasts and all(p.get("type") in ("chat_status", "queue_state")
                                      for _, p in broadcasts)
            # 排队可见化（P0-③）：入队即广播队列深度，前端显示「已排队 ×N」
            depths = [p.get("depth") for _, p in broadcasts if p.get("type") == "queue_state"]
            assert depths == [1]

            # 释放锁 → drain 把排队消息原样重放进同一入口
            calls = []

            async def fake_turn(**kw):
                calls.append(kw)
            monkeypatch.setattr(svc, "run_colleague_turn", fake_turn)
            lock.release()
            await svc._drain_thread_queue("t1")
            assert len(calls) == 1 and calls[0]["user_text"] == "补一句：内存要 256G"
            assert "t1" not in svc._THREAD_TURN_QUEUE

        asyncio.run(main())
    finally:
        svc._THREAD_TURN_LOCKS.pop("t1", None)
        svc._THREAD_TURN_QUEUE.pop("t1", None)


def test_stop_clears_thread_queue():
    from app.services.colleague_turn_service import _clear_thread_queue, _THREAD_TURN_QUEUE
    _THREAD_TURN_QUEUE["t2"] = [{"user_text": "x"}]
    _clear_thread_queue("t2")
    assert "t2" not in _THREAD_TURN_QUEUE
