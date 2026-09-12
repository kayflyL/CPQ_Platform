# -*- coding: utf-8 -*-
"""每节点独立单测（Step 7）：节点机制 = 插件，编排壳不认识任何节点名。

四类断言：
  1) 注册表自洽：有旁白键的插件 = 大脑节点；未注册节点走默认插件（惰性、不拦路）；
  2) 每节点校验只看自己的产物（伪上游 + 桩数据，不碰别的节点状态）；
  3) 编排壳里没有「按节点名的分支」——新增节点 = 注册插件，主循环零改动；
  4) 产物槽/实时发射器是产物槽的属性，不是节点名的属性。
"""
import asyncio
import os
import pathlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import skill_chat, skill_plan_runtime
from app.services import skill_tool_context
from app.services import skill_tools_select
from app.services import skill_turn_engine
from app.services.skill_node_plugins import (
    DefaultNodePlugin, all_plugins, brain_node_keys, first_delivery_gap, plugin_for,
    register)
from app.services.skill_node_state import KP_PICKS, kp_state, node_state

WORKFLOW_NODES = ("input", "agent_fill", "model_reason", "kp_reason", "compose", "output")


def _run(coro):
    return asyncio.run(coro)


def _fake_name_lookup(monkeypatch, rows: list):
    """select_parts 落料按料号名回库核对：单测不碰 DB，用给定料号顶替（2026-09-12 去台账）。"""
    from app.services import data_tools

    def _by_name(category, name, *, series="", price_ok=True, _repo=None):
        want = re.sub(r"\s+", "", str(name or "")).lower()
        hit = [r for r in rows if str(r.get("category") or "") == str(category)
               and re.sub(r"\s+", "", str(r.get("name") or "")).lower() == want]
        return {"ok": True, "category": category, "source": "kp_library/name_lookup",
                "rows": [dict(r) for r in hit], "total": len(hit)}

    monkeypatch.setattr(data_tools, "lookup_parts_by_name", _by_name)


# ── 1. 注册表自洽 + 未知节点惰性 ─────────────────────────────────────────────

def test_registry_declares_every_brain_node():
    """有大脑回合的节点必须注册插件；确定性节点（入口/交付/组装）走默认插件即可。"""
    for key in ("agent_fill", "model_reason", "kp_reason"):
        assert plugin_for(key).key == key, f"{key} 没有注册插件"
    for key in ("input", "output"):
        assert isinstance(plugin_for(key), DefaultNodePlugin)
    assert brain_node_keys() == {p.key for p in all_plugins() if p.narration_key}
    assert brain_node_keys() >= {"agent_fill", "model_reason", "kp_reason"}


def test_unknown_node_plugin_is_inert_and_never_blocks():
    plugin = plugin_for("某个还不存在的节点")
    assert isinstance(plugin, DefaultNodePlugin)
    assert plugin.narration_key == ""
    assert _run(plugin.validate({}))["ok"] is True
    assert plugin.delivery_gap({}) is None
    assert plugin.artifact_contract({}) == ""


def test_register_is_the_only_extension_point():
    class _Probe(DefaultNodePlugin):
        key = "_probe_node"
        narration_key = "probe_narration"

    register(_Probe())
    try:
        assert plugin_for("_probe_node").narration_key == "probe_narration"
        assert "_probe_node" in brain_node_keys()
    finally:
        from app.services import skill_node_plugins as np
        np._PLUGINS.pop("_probe_node", None)


def test_first_delivery_gap_returns_none_when_everything_is_settled():
    """没有卡住的节点 → 不出「出路卡」（避免零选项死卡）。"""
    assert first_delivery_gap({}) is None


# ── 2. 每节点校验：只看自己的产物 ────────────────────────────────────────────

def test_fill_node_validate_is_the_required_field_gate():
    plugin = plugin_for("agent_fill")
    v = _run(plugin.validate({"ext": {}}))
    assert v["ok"] is False, "必填字段没登记完就放行"
    filled = {"server_type": "通用计算服务器", "platform_type": "Orion",
              "chassis_form": "2U", "purchase_qty": 1}
    # 目录前提（平台/系列）只有推断值、没有客户确认记录 → 拦住（见 test_premise_gate_*）
    blocked = _run(plugin.validate({"ext": filled}))
    assert blocked["ok"] is False and "前提" in blocked["hint"]
    assert _run(plugin.validate({"ext": {**filled, "confirmed_slots": {"platform_type": "Orion"}}}))["ok"] is True


def test_model_node_validate_needs_a_locked_baseline():
    plugin = plugin_for("model_reason")
    assert _run(plugin.validate({}))["ok"] is False
    assert _run(plugin.validate({"ext": {"server_model": "ZS22V2-P"}}))["ok"] is True


def test_compose_node_validate_needs_plans():
    plugin = plugin_for("compose")
    assert _run(plugin.validate({}))["ok"] is False
    assert _run(plugin.validate({"plans": [{"model": "ZS22V2-P"}]}))["ok"] is True


def test_compose_node_refuses_to_skip_predecessors():
    """跳步 = 组装出空方案：前置没完成时先说清缺谁。"""
    v = _run(plugin_for("compose").prepare({"steps_done": {"agent_fill"}}, {}, None))
    assert v["ok"] is False
    assert "model_reason" in v["hint"] and "kp_reason" in v["hint"]


def test_kp_node_validate_needs_every_registered_row_landed(monkeypatch):
    _fake_name_lookup(monkeypatch, [
        {"part_id": "101", "name": "兆芯 KH-50000 32核", "category": "CPU",
         "price": 4500.0, "currency": "RMB"},
    ])
    from app.services.skill_node_plugins import plugin_for as pf
    ext = {"kp_rows": [{"part_category": "CPU", "description": "兆芯 50000 32核 处理器",
                        "qty": 2}]}
    engine: dict = {"ext": ext, "node_state": {}}
    engine["flow_configs"] = {}
    v = _run(pf("kp_reason").validate(engine))
    assert v["ok"] is False and "未落地" in v["hint"]
    token = skill_tool_context.TOOL_CTX.set({
        "ext": ext, "engine": engine, "task_active": True,
        "kp_rows_ctx": [{"row_key": "CPU|兆芯 50000 32核 处理器", "category": "CPU",
                         "description": "兆芯 50000 32核 处理器", "qty": 2, "specified": True}],
        "save": lambda: None,
    })
    try:
        assert skill_tools_select.tool_select_parts({"picks": [
            {"row": "CPU|兆芯 50000 32核 处理器", "name": "兆芯 KH-50000 32核",
             "reason": "核数一致"}]})["ok"]
    finally:
        skill_tool_context.TOOL_CTX.reset(token)
    assert kp_state(engine)[KP_PICKS], "落地没写进本节点分区"
    v2 = _run(pf("kp_reason").validate(engine))
    assert v2["ok"] is True, v2


def test_kp_node_bridge_only_publishes_its_own_context():
    """节点上下文桥接只下发本节点要用的东西（行清单 + 机型平台），不塞共享状态。"""
    engine = {"kp_parts": [{"category": "CPU", "request_spec": "2颗兆芯50000", "qty": 2,
                            "unmatched": True}],
              "ext": {"kp_rows": []}, "node_state": {},
              "_locked_baseline": {"series": "Polaris"},
              "flow_configs": {"kp_reason": {}}}
    ctx: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx)
    assert ctx["kp_series"] == "Polaris"
    assert ctx["kp_rows_ctx"][0]["row_key"] == "CPU|2颗兆芯50000"
    assert "node_state" not in ctx, "别把节点状态当上下文下发"


# ── 3. 编排壳不认识节点名（换插头/加节点零改主循环）─────────────────────────

def test_orchestration_shell_has_no_node_name_dispatch():
    """编排壳里不得有「按节点名的分支」：机制全部经插件钩子。"""
    keys = "|".join(WORKFLOW_NODES)
    pat = re.compile(r'^\s*(if|elif)\b[^\n]*==\s*["\'](' + keys + r')["\']')
    offenders = []
    for mod in (skill_chat, skill_plan_runtime):
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        offenders += [f"{mod.__name__}: {ln.strip()}"
                      for ln in src.splitlines() if pat.search(ln)]
    assert not offenders, "编排壳里出现按节点名的分支：" + repr(offenders)


# ── 4. 产物槽/实时发射器 = 产物槽的属性 ─────────────────────────────────────

def test_live_emitters_are_keyed_by_slot_not_node_name():
    from app.services.skill_node_artifacts import LIVE_EMITTERS
    assert set(LIVE_EMITTERS) <= set(__import__(
        "app.services.skill_node_artifacts", fromlist=["BUILDERS"]).BUILDERS)
    src = pathlib.Path(__import__("app.services.skill_node_artifacts",
                                  fromlist=["x"]).__file__).read_text(encoding="utf-8")
    assert '== "agent_fill"' not in src, "实时产物不该按节点名判断"


def test_answers_to_brain_questions_reach_the_engine():
    """客户对大脑提问的回答必须随消息进引擎。

    否则引擎看不见答案 → 同一个问题一轮换一次措辞再问一遍（实测连弹三轮），
    客户怎么点都不推进。答案只在聊天兜底分支拼接 = 在所有走引擎的入口被吞。
    """
    src = pathlib.Path(skill_chat.__file__).read_text(encoding="utf-8")
    # 2026-09-10 函数级拆分：答案归路搬进 _ChatTurnRuntime._run_task，标记随代码形态更新
    marker = "if self.ask_answers and self.click_note:"
    assert marker in src, "点选/口答没有进引擎的归路"
    assert src.index("full_text = build_requirement_text", src.index(marker)) > src.index(marker)


def test_shell_pauses_instead_of_delivering_a_half_done_step():
    """节点没落地就不许往下走：卡在某步必须如实暂停，绝不能落穿到组装/交付。

    历史事故：配件表 0 行（大脑只旁白没落地）仍落穿到 compose/output，
    交付了零配件的「BOM 方案草稿」且报完成——违反「不许静默丢弃」。
    """
    assert skill_turn_engine.step_gate_verdict([{"step": "kp_reason"}], "kp_reason") == "pause"
    assert skill_turn_engine.step_gate_verdict([{"step": "agent_fill"}], "kp_reason") == "advance"
    assert skill_turn_engine.step_gate_verdict([], "output") == "deliver"
    src = pathlib.Path(skill_turn_engine.__file__).read_text(encoding="utf-8")
    assert "step_gate_verdict(pending, step_key)" in src, "编排壳没接闸门函数"


def test_node_state_partitions_do_not_leak_between_nodes():
    container: dict = {}
    assert node_state(container, "kp_reason") is not node_state(container, "compose")
