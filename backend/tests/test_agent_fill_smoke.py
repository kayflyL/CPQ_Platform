# -*- coding: utf-8 -*-
"""登记环节冒烟回归：登记表由唯一大脑在 agent_fill 节点回合亲自落表。

2026-09-02 重构：run_agent_fill（提交后隐藏二次 LLM）已删除。登记的唯一入口 =
fill_requirement 任务期工具（大脑在 make_agent_brain 回合里调用）+ 确定性落表。
本文件只验证：任务期闸门、确定性落表语义、目录存在性冻结守卫；不发起真实模型请求。
"""
import os
import sys
from unittest.mock import patch

# 独立运行（python -X utf8 tests/test_agent_fill_smoke.py）时把 backend 根加进 sys.path；
# pytest 走 conftest.py，不依赖这行。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_capability_spec_validate_ok():
    from app.services import capability_spec
    assert capability_spec.validate_specs() == []


def _call_fill(args: dict, *, task_active: bool, ext: dict | None = None) -> dict:
    from app.services import skill_chat
    saved = {}
    skill_chat._TOOL_CTX.set({
        "ext": dict(ext or {}), "task_active": task_active,
        "save": lambda: saved.update(done=True),
    })
    return skill_chat.tool_fill_requirement(args)


def test_fill_requirement_blocked_before_task():
    """进任务前工具不可用：普通对话没有登记表，提前填表必须被闸门拒绝。"""
    res = _call_fill({"slots": {"server_type": "存储服务器"}}, task_active=False)
    assert res.get("ok") is False
    assert res.get("error") == "task_not_active"


def test_fill_requirement_registers_slots_when_task_active():
    """任务期登记：客户原话字段落表，返回登记结果与当前缺口（数据，供大脑续话）。"""
    res = _call_fill({"slots": {"server_type": "通用计算服务器", "purchase_qty": 2}},
                     task_active=True)
    assert res.get("ok") is True
    assert res.get("changed") is True
    assert res.get("current", {}).get("server_type") == "通用计算服务器"
    assert res.get("current", {}).get("purchase_qty") == 2


def test_fill_requirement_default_fills_empty_slots_only():
    """默认只填空槽：已确认值不被二次推理改写（「通用计算」被改成「存储」类事故的机制防线）。"""
    res = _call_fill({"slots": {"server_type": "存储服务器"}},
                     task_active=True, ext={"server_type": "通用计算服务器"})
    assert res.get("ok") is True
    assert res.get("current", {}).get("server_type") == "通用计算服务器"


def test_fill_requirement_replace_overwrites_on_correction():
    """replace=true = 客户改口：允许覆盖已登记值。"""
    res = _call_fill({"slots": {"server_type": "存储服务器"}, "replace": True},
                     task_active=True, ext={"server_type": "通用计算服务器"})
    assert res.get("ok") is True
    assert res.get("current", {}).get("server_type") == "存储服务器"


def test_fill_requirement_rejects_bad_args():
    res = _call_fill({"slots": "通用计算"}, task_active=True)
    assert res.get("ok") is False
    assert res.get("error") == "invalid_args"


def test_fill_tool_parameters_generated_from_slot_contract():
    """工具 schema 从登记表字段契约动态生成（前端改配置自动跟随，不写死字段词表）。"""
    from app.services.skill_chat import fill_tool_parameters
    params = fill_tool_parameters()
    props = params["properties"]["slots"]["properties"]
    assert "server_type" in props
    assert "kp_rows" in props                     # 部件清单是登记表字段之一
    assert params["properties"]["replace"]["type"] == "boolean"


def test_fill_contract_brief_generated_from_target_layer():
    """登记契约简报由目标层生成（字段契约+KP大类+在售目录），零业务内容硬编码——
    换目标层自动跟随是 agent_fill 可复用的接口要求。"""
    from app.services.skill_chat import _fill_contract_brief
    from app.services.catalog_options import catalog_whitelist
    brief = _fill_contract_brief()
    assert "server_type" in brief and "kp_rows" in brief
    assert "replace=true" in brief
    # 形状示例值必须来自在售目录实时数据（目录改了示例跟着变），而非代码写死
    wl = catalog_whitelist({}, {}, "")
    cand_vals = [str(v) for src in ("types", "series", "forms") for v in (wl.get(src) or []) if str(v).strip()]
    assert cand_vals, "在售目录为空？"
    assert any(v in brief for v in cand_vals)
    # 不含硬编码的业务需求原文
    assert "兆芯50000" not in brief


def test_freeze_keeps_catalog_model_and_drops_fabricated():
    """冻结守卫：目录真实机型保留（点选/早前轮次登记不再被误剥）；目录外的按臆造剔除并留痕。"""
    from app.services import capabilities as cap
    ctx: dict = {}
    ext = {"server_model": "ES22V3-P", "server_type": "通用计算服务器"}
    with patch.object(cap, "_model_in_catalog", return_value=True):
        cap._freeze_requirement(ctx, ext, "需求原文")
    assert ext.get("server_model") == "ES22V3-P"

    ext2 = {"server_model": " invented-X99 ", "server_type": "通用计算服务器"}
    ctx2: dict = {}
    with patch.object(cap, "_model_in_catalog", return_value=False):
        cap._freeze_requirement(ctx2, ext2, "需求原文")
    assert "server_model" not in ext2
    codes = [a.get("code") for a in ctx2.get("assumptions") or []]
    assert "model_dropped" in codes


def test_enrich_agent_semantic_domestic_compliance():
    """国产/信创由 AI 语义层登记 compliance.domestic_only；引擎只做 intent 归一。"""
    from app.services import semantic_contract as sc
    from app.services.capabilities import _enrich_agent_semantic
    ext = {"_seed": True}  # ext 空 dict 时 set_value 因 `ext or {}` 重绑定会写不进，先给个非空键
    sc.set_value(ext, "compliance", {"domestic_only": True})
    _enrich_agent_semantic(ext, None, "需要国产化信创服务器")
    assert sc.compliance(ext).get("domestic_only") is True
    assert sc.intent(ext) == "domestic_compliance"


def test_fill_brain_wallclock_budget_caps_attempts():
    """墙钟预算 180s：到点不再发起新的重试尝试，跳出时状态对用户可见（不静默）。"""
    import asyncio
    from types import SimpleNamespace
    from app.services import skill_chat

    loop_calls: list = []
    statuses: list = []

    async def fake_loop(msg, **kwargs):
        loop_calls.append(msg)
        # 模拟「调了但没收敛」的回合 → 收敛守卫本想进入第 2 次尝试
        return {"ok": False, "answer": "", "tool_calls_log": [
            {"name": "fill_requirement", "args": {}, "result": {"ok": False, "error": "模拟失败"}}]}

    async def sink(payload):
        sub = (payload or {}).get("sub") or {}
        if sub.get("kind") == "tool":
            statuses.append(str(sub.get("text") or ""))

    # 单调时钟每次调用 +400s：deadline=t1+300=500，attempt1 检查时 t2=600 已超 → 到点跳出
    counter = {"n": 0.0}

    def fake_monotonic():
        counter["n"] += 400.0
        return counter["n"]

    async def scenario():
        brain = skill_chat.make_agent_brain(persona="测试人设", event_sink=sink)
        with patch.object(skill_chat, "run_stream_chat_loop", fake_loop), \
             patch.object(skill_chat, "time", SimpleNamespace(monotonic=fake_monotonic)):
            await brain("agent_fill", {}, {"ext": {}, "requirement_text": "两台通用服务器"})

    asyncio.run(scenario())
    assert len(loop_calls) == 1                      # 预算到点：第 2/3 次尝试没有发起
    assert any("耗时较长" in s for s in statuses)     # 到点状态可见（Claude Code 式不静默）
    assert not any("重试中" in s for s in statuses)   # 直接到点，没走到重试分支
