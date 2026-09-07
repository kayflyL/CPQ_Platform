# -*- coding: utf-8 -*-
"""Claude Code 式任务模型契约：入口同意制提示词 / 步骤单源 / 中途消息排队。"""
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
    """同意制契约：提交必须以客户同意为前提；流程步骤块数据驱动（有则注入，无则不出现）。"""
    from app.services.skill_chat import requirement_prompt
    p = requirement_prompt(
        {}, flow_steps=[{"step": "model_reason", "label": "机型选型",
                         "description": "按需求从在售目录中选定机型骨架"},
                        {"step": "kp_reason", "label": "配件选型"},
                        {"step": "compose", "label": "BOM 组装"},
                        {"step": "output", "label": "产出交接"}])
    assert "客户已同意" in p                      # 提交门槛=同意
    assert "主动提议" in p                          # 咨询式对话须提议而非自作主张
    assert "【配置流程步骤】" in p and "机型选型" in p and "产出交接" in p
    assert "按需求从在售目录中选定机型骨架" in p    # 画布 description 进提议素材
    assert "机型选型：配件选型" not in p.replace("机型选型：按需求", "")  # 无描述的步骤不带空冒号尾巴
    # 未给步骤（如配置缺失）时不应出现空流程块
    p2 = requirement_prompt({})
    assert "【配置流程步骤】" not in p2
    assert "客户已同意" in p2                       # 同意制不依赖步骤块存在


def test_requirement_prompt_pre_task_hides_target_form():
    """进任务前不碰目标表：slots=None（普通聊天/提议轮）不暴露登记表内容。"""
    from app.services.skill_chat import requirement_prompt
    p = requirement_prompt(None)
    assert "存储服务器" not in p and "ES22V3-P" not in p
    assert "禁止提前登记或填表" in p                 # 白盒声明：任务未开始没有登记表
    # 任务回合（slots 传入）才暴露登记表视图
    p_task = requirement_prompt({"server_type": "存储服务器", "server_model": "ES22V3-P"})
    assert "存储服务器" in p_task and "ES22V3-P" in p_task


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
            assert broadcasts and all(p.get("type") == "chat_status" for _, p in broadcasts)

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
