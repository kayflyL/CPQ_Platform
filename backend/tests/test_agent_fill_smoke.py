# -*- coding: utf-8 -*-
"""登记环节冒烟回归：登记表由唯一大脑在 agent_fill 节点回合亲自落表。

2026-09-02 重构：run_agent_fill（提交后隐藏二次 LLM）已删除。登记的唯一入口 =
fill_requirement 任务期工具（大脑在 agent_fill 节点回合里调用）+ 确定性落表。
本文件只验证：任务期闸门、确定性落表语义、目录存在性冻结守卫；不发起真实模型请求。
"""
import os
import sys
from unittest.mock import patch
from app.services import skill_tool_context
from app.services import skill_tools_fill
from app.services import skill_tools_misc
from app.services import skill_turn_engine

# 独立运行（python -X utf8 tests/test_agent_fill_smoke.py）时把 backend 根加进 sys.path；
# pytest 走 conftest.py，不依赖这行。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_capability_spec_validate_ok():
    from app.services import capability_spec
    assert capability_spec.validate_specs() == []


def _call_fill(args: dict, *, task_active: bool, ext: dict | None = None) -> dict:
    from app.services import skill_chat
    saved = {}
    skill_tool_context.TOOL_CTX.set({
        "ext": dict(ext or {}), "task_active": task_active,
        "save": lambda: saved.update(done=True),
    })
    return skill_tools_fill.tool_fill_requirement(args)


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
    from app.services.skill_tools_fill import fill_tool_parameters
    params = fill_tool_parameters()
    props = params["properties"]
    assert "server_type" in props
    assert "kp_rows" in props                     # 部件清单是登记表字段之一
    assert params["properties"]["replace"]["type"] == "boolean"
    # part_category 必须是目标表大类（enum 硬约束），禁止中文/自定义写法混入
    pc = props["kp_rows"]["items"]["properties"]["part_category"]
    assert isinstance(pc.get("enum"), list) and pc["enum"]
    assert "内存" not in pc["enum"] and "显卡" not in pc["enum"]
    # 目录字段（类型/系列/形态）必须带 enum，且描述引导 AI 自行选值+反问；机型不加 enum
    for k in ("server_type", "platform_type", "chassis_form"):
        assert isinstance(props[k].get("enum"), list) and props[k]["enum"], k
        assert "ask_user" not in props[k]["description"]
    assert "enum" not in props["server_model"]
    # 目录缺口的确认优先级写在左栏任务规则（2026-09-12 起节点层不承载指令 prose）
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    flow = ReasoningFlowRepository().get_active_flow("requirement_analysis")
    left = str(((flow or {}).get("graph") or {}).get("manual_rules") or "")
    assert "优先确认「服务器类型」" in left, "目录缺口的确认优先级必须写在左栏任务规则里"
    assert "系统自动向客户弹目录候选卡" not in props["server_type"]["description"]


def test_fill_contract_brief_generated_from_target_layer():
    """登记契约简报由目标层生成（字段契约+KP大类+在售目录），零业务内容硬编码——
    换目标层自动跟随是 agent_fill 可复用的接口要求。"""
    from app.services.skill_tools_fill import _fill_contract_brief
    from app.services.catalog_options import catalog_whitelist
    brief = _fill_contract_brief()
    assert "server_type" in brief and "kp_rows" in brief
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
    ext = {"server_model": "ES220 V3", "server_type": "通用计算服务器"}
    with patch.object(cap, "_model_in_catalog", return_value=True):
        cap._freeze_requirement(ctx, ext, "需求原文")
    assert ext.get("server_model") == "ES220 V3"

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


def test_brain_attempts_wallclock_budget_caps_attempts():
    """墙钟预算：到点不再发起新的重试尝试，跳出时状态对用户可见（不静默）。"""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import patch
    from app.services import skill_chat

    loop_calls: list = []
    statuses: list = []

    async def fake_loop(msg, **kwargs):
        loop_calls.append(msg)
        # 模拟「调了但没收敛」的回合 → 本该进入第 2 次尝试
        return {"ok": False, "answer": "", "tool_calls_log": [
            {"name": "fill_requirement", "args": {}, "result": {"ok": False, "error": "模拟失败"}}]}

    async def emit_status(text):
        statuses.append(str(text))

    async def settle(result):
        return {"action": "retry", "feedback": "再次被拒"}

    # 单调时钟每次调用 +500s：deadline=t1+420=920，attempt1 检查时 t2=1000 已超 → 到点跳出
    counter = {"n": 0.0}

    def fake_monotonic():
        counter["n"] += 500.0
        return counter["n"]

    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop), \
             patch.object(skill_turn_engine, "time", SimpleNamespace(monotonic=fake_monotonic)):
            return await skill_turn_engine.run_brain_attempts(
                "客户消息", loop_kwargs={}, settle=settle, emit_status=emit_status)

    _result, action = asyncio.run(scenario())
    assert len(loop_calls) == 1                      # 预算到点：第 2/3 次尝试没有发起
    assert action == "timeout"
    assert any("耗时较长" in s for s in statuses)     # 到点状态可见（不静默）
    assert not any("重试中" in s for s in statuses)   # 直接到点，没走到重试分支


def test_agent_fill_ai_picks_catalog_value_and_ask_user_beats_system_card():
    """问题2主线：AI 一手需求一手目标表，目录字段自己从值域选（模糊时推断再 ask_user 确认）。

    系统不再发目录缺口卡：只要 AI 已登记 ask_user 提问，engine_gaps 必须是
    brain_ask（AI 自己的选项卡），而不是 target_incomplete（系统目录卡）。"""
    import asyncio
    from app.services import skill_chat
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    flow = ReasoningFlowRepository().get_active_flow("requirement_analysis")
    assert flow, "需求分析 active flow 未播种"

    async def fake_loop(msg, **kwargs):
        ctx = skill_tool_context.TOOL_CTX.get()
        ext = ctx["ext"]
        # AI 自己判断：类型用户已明说直接登记；平台为推断值、未明说 → 先调 ask_user 确认，不先填猜测值
        ext["server_type"] = "通用计算服务器"
        ctx.setdefault("brain_asks", []).append({
            "question": "平台建议选 Polaris，是否确认？",
            "options": [{"label": "Polaris"}, {"label": "Orion"}],
            "slot": "platform_type"})
        return {"ok": True, "answer": "", "tool_calls_log": []}

    async def sink(payload):
        pass

    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop):
            return await skill_turn_engine.run_skill_agent_turn(
                thread_id="t_reg", role_key="tech", persona="测试人设",
                full_text="需要一台通用计算服务器，CPU 用兆芯", history=[],
                ext={}, mem={}, flow=flow, event_sink=sink,
                price_ok=True, opportunity_id="o_reg")

    engine = asyncio.run(scenario())
    assert engine.get("awaiting_input") is True
    gaps = engine.get("engine_gaps") or []
    assert gaps, "应产出一个待确认卡"
    assert gaps[0].get("reason_code") == "brain_ask", "AI 的 ask_user 要优先于系统目录卡"
    assert any(o.get("label") == "Polaris" for o in gaps[0].get("options") or [])
    ext = engine.get("ext") or {}
    assert ext.get("server_type") == "通用计算服务器", "客户明说的类型直接登记"
    assert not ext.get("platform_type"), "客户没明说的目录字段先 ask_user 确认，不先填猜测值"
    assert gaps[0].get("slot") == "platform_type", "确认卡把该字段 slot 带上（客户点选即自动落槽）"


def test_ask_user_slot_binds_catalog_confirmation_then_applies():
    """目录字段未明说 → AI 用 ask_user 带 slot 升格选项卡；点选后按 (slot,value) 自动落槽。

    这是「先问后填、别既填又追问」的机制底座：卡带 slot，点击后不再需要大脑重读答案重填。
    """
    import asyncio
    from app.services import skill_chat
    from app.services.capabilities import _apply_extracted_slots
    from app.services.skill_plan_runtime import validate_step_end

    skill_tool_context.TOOL_CTX.set({"task_active": True, "ext": {}, "brain_asks": []})
    res = skill_tools_misc.tool_ask_user({
        "question": "平台建议选 Polaris？",
        "options": [{"label": "Polaris"}, {"label": "Orion"}],
        "slot": "platform_type",
    })
    asks = skill_tool_context.TOOL_CTX.get().get("brain_asks") or []
    assert res.get("ok") is True and asks and asks[0].get("slot") == "platform_type"

    ext = {"server_type": "通用计算服务器", "purchase_qty": 1}
    _apply_extracted_slots(ext, {"platform_type": "Polaris"}, allow_overwrite=True)
    assert ext.get("platform_type") == "Polaris"

    async def scenario(fill):
        ctx = {"ext": dict(fill, chassis_form="2U", purchase_qty=1), "flow_configs": {}}
        return await validate_step_end(ctx, "agent_fill")

    # 只有值、没有客户确认记录 → 前提闸门拦住：带着推断值进配件选配会让下游每行都无料可锁。
    v = asyncio.run(scenario({"server_type": "通用计算服务器", "platform_type": "Polaris"}))
    assert v.get("ok") is False, "推断的平台没经客户拍板就放行"
    assert "平台" in str(v.get("hint") or ""), "拦截要指名是哪个前提字段"

    # 客户点选确认卡 → 落 confirmed_slots（点击通路与打字精确命中同源）→ 放行。
    ext.setdefault("confirmed_slots", {})["platform_type"] = "Polaris"
    v = asyncio.run(scenario({"server_type": "通用计算服务器", "platform_type": "Polaris",
                              "confirmed_slots": {"platform_type": "Polaris"}}))
    assert v.get("ok") is True
