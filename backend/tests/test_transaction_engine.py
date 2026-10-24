# -*- coding: utf-8 -*-
"""transaction_engine / delivery_app / transaction_turn 单测。

内核机制用【合成应用】验证（证明内核不认识任何具体业务——Windows 式的成立性测试）；
交付应用用假仓库验证域探针；轮壳用 stub LLM 循环验证推进循环；分发器验证三分支路由。
全 fake repo + monkeypatch（不碰 DB / LLM——复现写请求会写真库，防呆规矩）。
"""
import asyncio
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.repository.assistant_repo as assistant_repo_mod  # noqa: E402
import app.repository.feed_repo as feed_repo_mod  # noqa: E402
import app.repository.flow_repo as flow_repo_mod  # noqa: E402
import app.repository.opportunity_repo as opportunity_repo_mod  # noqa: E402
import app.repository.reasoning_flow_repo as reasoning_flow_repo_mod  # noqa: E402
import pytest  # noqa: E402
from app.services import agent_write_confirm as wc  # noqa: E402
from app.services import delivery_core as dcore  # noqa: E402
from app.services import transaction_engine as te  # noqa: E402
from app.services import delivery_app as dapp  # noqa: E402
import app.services.transaction_turn as tt  # noqa: E402
import app.services.colleague_turn_runners as runners  # noqa: E402
from app.services.skill_tool_context import TOOL_CTX  # noqa: E402

USER = {"user_id": "u1", "name": "管理员", "role": "admin"}


def _repo_cls(getter):
    class _R:
        def __init__(self, *a, **k):
            pass

        def __getattr__(self, name):
            return getter(name)

        def close(self):
            pass
    return _R


@pytest.fixture
def world(monkeypatch):
    """可增量推演的假世界：thread/opportunity/sheets/quotes/staged/state + 流配置。"""
    w = SimpleNamespace(
        thread={"thread_id": "t1", "opportunity_id": None},
        opportunity=None,
        sheets=[], quotes=[], staged=[], state={},
        flow={"rules": "规则R", "steps": [
            {"key": "identify", "label": "识别与商机定位", "tools": ["import_cost_sheet", "create_opportunity"],
             "target": "商机 → 写入 opportunities", "output": "opportunity_id + customer_name",
             "completion": {"slot": "opp"}},
            {"key": "place_bom", "label": "方案落位", "tools": ["import_bom_scheme", "import_cost_sheet"],
             "completion": {"any_of": ["scheme", "sheet"]},
             "artifact_card": {"on_tool": "import_cost_sheet", "artifact_type": "cost_sheet_parse",
                               "title": "成本表解析结果", "summary": "$result.note",
                               "refs": {"opportunity_id": "$view.opp.opportunity_id", "sheet_id": "$result.sheet_id"}}},
            {"key": "place", "label": "落位", "tools": ["import_cost_sheet"],
             "completion": {"slot": "sheet"},
             "artifact_card": {"on_tool": "import_cost_sheet", "artifact_type": "cost_sheet_parse",
                               "title": "成本表解析结果", "summary": "$result.note",
                               "refs": {"opportunity_id": "$view.opp.opportunity_id", "sheet_id": "$result.sheet_id"}}},
            {"key": "derive_cost", "label": "推进成本核算", "tools": ["derive_cost_from_scheme"],
             "completion": {"slot": "sheet"}},
            {"key": "submit", "label": "提交", "tools": ["submit_cost_sheet"],
             "completion": {"slot": "quotation"},
             "artifact_card": {"on_tool": "submit_cost_sheet", "artifact_type": "quotation",
                               "title": "报价单（草稿）", "summary": "$result.note",
                               "refs": {"quotation_id": "$result.quotation_id"}}},
            {"key": "margin", "label": "加价", "tools": ["set_quote_margin"],
             "completion": {"flag": "margin"}},
            {"key": "output", "label": "出件", "tools": ["share_quote"],
             "completion": {"flag": "share"}},
        ]},
        quote_result={"ok": False, "error": "none"},
        # 分流旗标声明表（与 flow 127 线上配置同构：2026-10-22 架构修后映射在流程配置里）
        flag_rules=[
            {"tool": "import_cost_sheet", "set": {"lane": "cost"}},
            {"tool": "import_bom_scheme",
             "set": {"lane": "scheme",
                     "scheme": {"bom_scheme_id": "$result.bom_scheme_id",
                                "name": "$result.scheme_name"}}},
            {"tool": "derive_cost_from_scheme",
             "set": {"lane": "scheme", "derived": {"sheet_id": "$result.sheet_id"}}},
            {"tool": "set_quote_margin",
             "set": {"margin": {"pct": "$result.margin_pct",
                                "quotation_id": "$result.quotation_id"}}},
            {"tool": "share_quote",
             "set": {"share": {"share_path": "$result.share_path",
                               "quotation_id": "$result.quotation_id"}}},
        ],
    )

    def _get(name):
        def fn(*a, **k):
            if name == "get_thread":
                return dict(w.thread)
            if name == "get_reasoning_state":
                return json.dumps(w.state)
            if name == "update_reasoning_state":
                w.state.update(a[1] if len(a) > 1 else k.get("patch") or {})
                return None
            if name == "update_thread_opportunity_id":
                w.thread["opportunity_id"] = a[1] or None
                return None
            if name == "get_opportunity":
                return dict(w.opportunity) if w.opportunity else None
            if name == "list_cost_sheets":
                return [dict(s) for s in w.sheets]
            if name == "list_staged_attachments":
                return [dict(s) for s in w.staged]
            return None
        return fn

    monkeypatch.setattr(assistant_repo_mod, "AssistantRepository", _repo_cls(_get))
    monkeypatch.setattr(opportunity_repo_mod, "OpportunityRepository", _repo_cls(_get))
    monkeypatch.setattr(flow_repo_mod, "FlowRepository", _repo_cls(_get))
    monkeypatch.setattr(feed_repo_mod, "FeedRepository", _repo_cls(_get))

    class _FlowRepo:
        def __init__(self, *a, **k):
            pass

        def get_active_flow(self, key):
            if key == "synth":
                return {"graph": {"manual_rules": "", "nodes": [
                    {"id": "a", "type": "agent", "label": "A"},
                    {"id": "b", "type": "agent", "label": "B"}]},
                    "node_configs": {"a": {"enabled_tools": ["t1"], "completion": {"slot": "x.p1"}},
                                     "b": {"enabled_tools": ["t2"], "completion": {"slot": "x.p2"}}}}
            if key != "delivery_to_quotation":
                return None
            return {"flow_id": 1, "skill_key": key,
                    "graph": {"manual_rules": w.flow["rules"],
                              "edges": [dict(e) for e in (w.flow.get("edges") or [])],
                              "flag_rules": [dict(r) for r in (getattr(w, "flag_rules", None) or [])],
                              "nodes": [{"id": s["key"], "type": "agent", "label": s["label"]}
                                        for s in w.flow["steps"]]},
                    "node_configs": {s["key"]: {"enabled_tools": s["tools"],
                                                **({"target": {"artifacts": [s["target_artifact"]]}
                                                    if s.get("target_artifact") else {}}),
                                                   **({"completion": s["completion"]}
                                                      if s.get("completion") else {}),
                                                   **({"gated": s["gated"]}
                                                      if s.get("gated") else {}),
                                                   **({"artifact_card": s["artifact_card"]}
                                                      if s.get("artifact_card") else {})}
                                     for s in w.flow["steps"]}}
        close = lambda self: None

    monkeypatch.setattr(reasoning_flow_repo_mod, "ReasoningFlowRepository", _FlowRepo)
    monkeypatch.setattr(dcore, "margin_resolve_quotation",
                        lambda user, opp_id, quotation_id="": dict(w.quote_result))
    return w


# ── 内核机制（合成应用：内核不认识任何具体业务）─────────────────────────────


_SYNTH_CTX = {"p1": False, "p2": False}


def _synth_app():
    return te.TransactionApp(
        flow_key="synth", state_slot="synth_flow",
        context_fn=lambda tid, user: {"x": dict(_SYNTH_CTX)},
        digest_lines=lambda view: ["· 合成事实行"],
        flags_from_facts=lambda facts: ({"done": True} if any(
            isinstance(f.get("result"), dict) and f["result"].get("ok") for f in facts) else None),
    )


def test_kernel_pointer_walks_synthetic_probes(world):
    app = _synth_app()
    v = te.state_view(app, "t1", "assistant", USER)
    assert v["step_key"] == "a" and not v["complete"]
    _SYNTH_CTX["p1"] = True
    v = te.state_view(app, "t1", "assistant", USER)
    assert v["step_key"] == "b"
    _SYNTH_CTX["p2"] = True
    assert te.state_view(app, "t1", "assistant", USER)["complete"]
    _SYNTH_CTX.update({"p1": False, "p2": False})


def test_kernel_state_slot_roundtrip(world):
    app = _synth_app()
    te.save_state(app, "t1", "assistant", {"done": True})
    assert te.load_state(app, "t1", "assistant") == {"done": True}
    assert "synth_flow:assistant" in world.state
    te.clear_state(app, "t1", "assistant")
    assert te.load_state(app, "t1", "assistant") == {}


def test_kernel_digest_app_lines_plus_pending(world):
    app = _synth_app()
    wc._STORAGE = "memory"
    wc._MEM.clear()
    try:
        wc.stage("t1", "submit_cost_sheet", {"sheet_id": 3})
        d = te.digest(app, te.state_view(app, "t1", "assistant", USER))
    finally:
        wc._MEM.clear()
    assert d.startswith("【当前案台】")
    assert "· 合成事实行" in d
    assert "· 待确认: submit_cost_sheet" in d


def test_kernel_apply_facts_via_app_flag_table(world):
    app = _synth_app()
    te.apply_facts(app, "t1", "assistant", [{"tool": "t1", "result": {"ok": True}}])
    assert te.load_state(app, "t1", "assistant") == {"done": True}
    te.apply_facts(app, "t1", "assistant", [{"tool": "t1", "result": {"ok": False}}])
    assert te.load_state(app, "t1", "assistant") == {"done": True}  # 失败事实不回写


def test_kernel_flow_rules_parsing(monkeypatch):
    flow = {"graph": {"manual_rules": "R", "nodes": [
        {"id": "input", "type": "input", "label": "接收工件"},
        {"id": "work", "type": "agent", "label": "干活"},
        {"id": "out", "type": "output", "label": "出件"},
    ]}, "node_configs": {"input": {}, "work": {"enabled_tools": ["t1"]},
                         "out": {"enabled_tools": ["t2"]}}}

    class _FR:
        def __init__(self, *a, **k):
            pass
        get_active_flow = lambda self, key: flow
        close = lambda self: None

    monkeypatch.setattr(reasoning_flow_repo_mod, "ReasoningFlowRepository", _FR)
    out = te.load_flow_rules("any")
    assert out["rules"] == "R"
    assert [s["key"] for s in out["steps"]] == ["work", "out"]


def test_kernel_flow_rules_accepts_card_list(monkeypatch):
    """artifact_card 兼容单声明(dict)与声明列表(list)——列表形态曾被丢成 None 导致不发卡。"""
    flow = {"graph": {"manual_rules": "", "nodes": [
        {"id": "work", "type": "agent", "label": "干活"}]},
        "node_configs": {"work": {"enabled_tools": ["t1"],
                                  "artifact_card": [{"on_tool": "t1", "artifact_type": "quotation",
                                                     "title": "T", "summary": "S", "refs": {}}]}}}

    class _FR:
        def get_active_flow(self, key):
            return flow

        def close(self):
            pass

    monkeypatch.setattr(reasoning_flow_repo_mod, "ReasoningFlowRepository", _FR)
    out = te.load_flow_rules("any")
    assert isinstance(out["steps"][0]["artifact_card"], list)


def test_kernel_flow_rules_carries_field_contract(monkeypatch):
    """字段级契约随步骤下发：target.artifacts[0].fields 原样进 step['fields']。"""
    flow = {"graph": {"manual_rules": "", "nodes": [
        {"id": "identify", "type": "agent", "label": "识别"},
    ]}, "node_configs": {"identify": {
        "enabled_tools": ["create_opportunity"],
        "target": {"artifacts": [{
            "kind": "record", "name": "商机", "slot": "opportunities",
            "fields": [{"key": "customer_name", "label": "客户名称", "ask": True, "hint": "逐字使用"},
                       {"key": "memo", "label": "备注", "ask": False}],
        }]}}}}

    class _FR:
        def __init__(self, *a, **k):
            pass
        get_active_flow = lambda self, key: flow
        close = lambda self: None

    monkeypatch.setattr(reasoning_flow_repo_mod, "ReasoningFlowRepository", _FR)
    steps = te.load_flow_rules("any")["steps"]
    assert len(steps) == 1
    assert steps[0]["target"] == "商机 → 写入 opportunities"
    assert [f["key"] for f in steps[0]["fields"]] == ["customer_name", "memo"]


def test_format_step_contract_lists_ask_fields_with_hints():
    """契约文本：目标层 + 必填清单 + 缺口检查纪律；ask=false 字段不出现在必填行。"""
    step = {"target": "商机 → 写入 opportunities",
            "fields": [{"key": "customer_name", "label": "客户名称", "ask": True, "hint": "逐字使用"},
                       {"key": "sales_person", "label": "归属业务", "ask": True, "hint": "缺时问用户"},
                       {"key": "memo", "label": "备注", "ask": False}]}
    text = te.format_step_contract(step)
    assert "本步目标：商机 → 写入 opportunities" in text
    assert "必填字段：客户名称、归属业务" in text
    assert "缺口检查" in text and "不重复反问" in text
    assert "逐字使用" in text and "缺时问用户" in text
    assert "备注" not in text.split("·")[0]  # 非必填不进必填清单
    assert te.format_step_contract({"target": "", "fields": []}) == ""


# ── 注册表（安装清单）────────────────────────────────────────────────────


def test_registry_resolves_installed_app():
    assert te.resolve_app("delivery_to_quotation") is dapp.APP
    assert te.resolve_app("no_such_flow") is None


# ── 交付应用：域探针（假仓库）─────────────────────────────────────────────


def _dview(world):
    return te.state_view(dapp.APP, "t1", "assistant", USER)


def test_delivery_pointer_walks_each_artifact(world):
    assert _dview(world)["step_key"] == "identify"
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    assert _dview(world)["step_key"] == "place_bom"  # 双分支落位：成本/方案任一落定即过
    world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1, 2]}]
    assert _dview(world)["step_key"] == "submit"  # place_bom/place/derive_cost 三探针同查成本表，一起通过
    world.quote_result = {"ok": True, "quotation_id": "Q1", "quotation_name": "n", "version": 1}
    assert _dview(world)["step_key"] == "margin"
    world.state = {f"{dapp.STATE_SLOT}:assistant": {"margin": {"pct": 15, "quotation_id": "Q1"}}}
    assert _dview(world)["step_key"] == "output"
    world.state[f"{dapp.STATE_SLOT}:assistant"]["share"] = {"share_path": "/api/share/x"}
    assert _dview(world)["complete"]


def test_delivery_dangling_binding_counts_as_unbound(world):
    world.thread["opportunity_id"] = "GONE"
    world.opportunity = None
    assert _dview(world)["step_key"] == "identify"


def test_delivery_digest_carries_domain_facts(world):
    world.staged = [{"attachment_id": "ATT1", "original_filename": "成本表.xlsx"}]
    wc._STORAGE = "memory"
    wc._MEM.clear()
    try:
        wc.stage("t1", "submit_cost_sheet", {"sheet_id": 3})
        d = te.digest(dapp.APP, _dview(world))
    finally:
        wc._MEM.clear()
    assert "ATT1" in d and "成本表.xlsx" in d and "商机: 未绑定" in d
    assert "待确认: submit_cost_sheet" in d


def test_delivery_flags_from_facts(world):
    """旗标映射已声明化（2026-10-22 架构修）：内核 apply_facts 按流程配置的
    flag_rules 回写，$result 引用携带工具结果动态值；失败事实不回写。"""
    te.apply_facts(dapp.APP, "t1", "assistant",
                   [{"tool": "import_cost_sheet", "result": {"ok": True, "analysis_only": True}}])
    assert te.load_state(dapp.APP, "t1") == {"lane": "cost"}
    te.apply_facts(dapp.APP, "t1", "assistant",
                   [{"tool": "import_bom_scheme",
                     "result": {"ok": True, "bom_scheme_id": 7, "scheme_name": "方案S"}}])
    st = te.load_state(dapp.APP, "t1")
    assert st["lane"] == "scheme"
    assert st["scheme"] == {"bom_scheme_id": 7, "name": "方案S"}
    te.apply_facts(dapp.APP, "t1", "assistant",
                   [{"tool": "share_quote", "result": {"ok": False, "error": "x"}}])
    assert te.load_state(dapp.APP, "t1")["lane"] == "scheme"  # 失败事实不回写


def test_branch_reach_graph_walk():
    """分支一等公民（2026-10-22 架构修）：守卫在边上，可达性=图遍历——
    菱形汇聚（submit 双路可达）、链式不可达、守卫未定不算跳过。"""
    steps = [{"key": "identify"}, {"key": "bom"}, {"key": "cost"},
             {"key": "derive"}, {"key": "submit"}]
    edges = [
        {"id": "e0", "source": "identify", "target": "bom",
         "guard": {"flag": "lane", "equals": "scheme"}},
        {"id": "e1", "source": "identify", "target": "cost",
         "guard": {"flag": "lane", "equals": "cost"}},
        {"id": "e2", "source": "bom", "target": "derive"},
        {"id": "e3", "source": "cost", "target": "submit"},
        {"id": "e4", "source": "derive", "target": "submit"},
    ]
    r = te.branch_reach(steps, edges, {"flags": {"lane": "cost"}})
    assert r == {"identify": "reachable", "bom": "skipped", "cost": "reachable",
                 "derive": "skipped", "submit": "reachable"}
    r = te.branch_reach(steps, edges, {"flags": {"lane": "scheme"}})
    assert r == {"identify": "reachable", "bom": "reachable", "cost": "skipped",
                 "derive": "reachable", "submit": "reachable"}
    # 旗标未定（分流没判）：下游 undecided——不提前灰、也不冒充跳过
    r = te.branch_reach(steps, edges, {"flags": {}})
    assert r["bom"] == "undecided" and r["cost"] == "undecided"
    assert r["submit"] == "undecided" and r["identify"] == "reachable"


def test_branch_node_states_and_pointer(world):
    """node_states/指针走图：lane=cost 时方案落位/库价推导=skipped，
    指针跳过它们落 place；无边的流线性兼容不变。"""
    world.flow["steps"][1]["completion"] = {"any_of": ["scheme"]}
    world.flow["edges"] = [
        {"id": "e1", "source": "identify", "target": "place_bom",
         "guard": {"flag": "lane", "equals": "scheme"}},
        {"id": "e2", "source": "identify", "target": "place",
         "guard": {"flag": "lane", "equals": "cost"}},
        {"id": "e4", "source": "place", "target": "submit"},
    ]
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    world.state[f"{dapp.STATE_SLOT}:assistant"] = {"lane": "cost"}
    view = te.state_view(dapp.APP, "t1", "assistant", dict(USER))
    states = te.node_states(view["flow"]["steps"], view)
    assert states["place_bom"] == "skipped"
    assert states["identify"] == "done"
    assert view["step_key"] == "place"  # 指针跳过不可达节点
    # 无边 → 线性兼容
    world.flow["edges"] = []
    view2 = te.state_view(dapp.APP, "t1", "assistant", dict(USER))
    assert view2["step_key"] in ("place_bom", "place")


def test_desk_complete_boundary(world):
    """开工单边界判定：全探针通过=complete（同线程再发=新开工单，dispatch 据此干净重开）；
    链中任一探针不过=未交割（绝不重开，反问/等确认的续跑不受影响）。"""
    # 全链交割：商机+成本表+报价单+加价/分享旗标
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1]}]
    world.quote_result = {"ok": True, "quotation_id": "Q1"}
    wstate = {}
    import app.repository.assistant_repo as arm
    orig_repo_cls = arm.AssistantRepository

    class _StateRepo(orig_repo_cls):
        def get_reasoning_state(self, thread_id):
            return wstate.get("flags")

        def update_reasoning_state(self, thread_id, patch):
            merged = json.loads(wstate.get("flags") or "{}")
            merged.update(patch)
            wstate["flags"] = json.dumps(merged)

    arm.AssistantRepository = _StateRepo
    try:
        from app.services.transaction_engine import apply_facts
        apply_facts(dapp.APP, "t1", "assistant", [
            {"tool": "set_quote_margin", "result": {"ok": True, "margin_pct": 15, "quotation_id": "Q1"}},
            {"tool": "share_quote", "result": {"ok": True, "share_path": "/s/xyz"}},
        ])
        assert te.desk_complete(dapp.APP, "t1", "assistant", dict(USER)) is True
        # 撤一个旗标（链中）：未交割，绝不能重开
        wstate["flags"] = wstate["flags"].replace('"share":', '"other":')
        assert te.desk_complete(dapp.APP, "t1", "assistant", dict(USER)) is False
    finally:
        arm.AssistantRepository = orig_repo_cls


def test_kernel_emits_spec_fallback_cards(world, monkeypatch):
    """产物卡下沉：节点没配 artifact_card 时，卡从工具规格兜底（卡=工具的属性，
    一次声明所有工作流通用）。仅解析预览（analysis_only）静默不发卡。"""
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}
    monkeypatch.setattr(tt, "_tool_spec_card", lambda tool: {
        "on_tool": "import_cost_sheet", "artifact_type": "cost_sheet_parse",
        "title": "成本表解析结果", "summary": "$result.note",
        "refs": {"opportunity_id": "$view.opp.opportunity_id",
                 "sheet_id": "$result.sheet_id"}} if tool == "import_cost_sheet" else None)
    world.flow["steps"][0]["artifact_card"] = None  # 清掉节点覆盖，走规格兜底

    async def stub(msg, cfg, **kw):
        await kw["tool_guard"]("import_cost_sheet", {},
                               {"ok": True, "sheet_id": 3, "sheet_name": "s",
                                "configs": [1, 2], "analysis_only": True, "note": "仅解析预览"})
        return {"ok": True, "answer": "预览好了"}

    async def _pa(thread_id, colleague, card):
        captures["cards"].append(card)

    _patch_turn_env(monkeypatch, world, stub, captures)
    monkeypatch.setattr(tt, "_persist_artifact", _pa)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "这是成本表", None, [], {"role_key": "assistant"}, "", user=dict(USER)))
    # analysis_only → 静默，不落产物卡
    assert captures["cards"] == []


def test_kernel_emits_spec_fallback_cards_real(world, monkeypatch):
    """同上，但工具真实落草稿（无 analysis_only）→ 规格卡发射并随 node_trace 挂到节点上。"""
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}
    monkeypatch.setattr(tt, "_tool_spec_card", lambda tool: {
        "on_tool": "import_cost_sheet", "artifact_type": "cost_sheet_parse",
        "title": "成本表解析结果", "summary": "$result.note",
        "refs": {"opportunity_id": "$view.opp.opportunity_id",
                 "sheet_id": "$result.sheet_id"}} if tool == "import_cost_sheet" else None)

    async def stub(msg, cfg, **kw):
        await kw["tool_guard"]("import_cost_sheet", {},
                               {"ok": True, "sheet_id": 3, "sheet_name": "s",
                                "configs": [1, 2], "note": "已生成成本核算草稿（未提交）"})
        world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1, 2]}]
        return {"ok": True, "answer": "落好了"}

    async def _pa(thread_id, colleague, card):
        captures["cards"].append(card)

    _patch_turn_env(monkeypatch, world, stub, captures)
    monkeypatch.setattr(tt, "_persist_artifact", _pa)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "这是成本表", None, [], {"role_key": "assistant"}, "", user=dict(USER)))
    # 2 张：stub 在 identify 与后续迭代各跑了一次工具，每次真实 import 都按规格发卡
    assert len(captures["cards"]) == 2
    assert all(c["artifact_type"] == "cost_sheet_parse" for c in captures["cards"])
    trace = [b for b in captures["broadcasts"]
             if b["type"] == "node_trace" and b.get("artifact")]
    assert trace
    cards_on_trace = [t["artifact"]["data"]["card"] for t in trace]
    assert all(c["artifact_type"] == "cost_sheet_parse" for c in cards_on_trace)


def test_build_card_from_node_declaration(world):
    """产物卡从节点声明的 artifact_card 装配：refs 只存 id，$scope 路径取值。"""
    view = {"opp": {"opportunity_id": "OPP1"}}
    world.thread["opportunity_id"] = "OPP1"
    decl = {"on_tool": "import_cost_sheet", "artifact_type": "cost_sheet_parse",
            "title": "成本表解析结果", "summary": "$result.note",
            "refs": {"opportunity_id": "$view.opp.opportunity_id", "sheet_id": "$result.sheet_id"}}
    result = {"ok": True, "sheet_id": 3, "sheet_name": "s", "note": "已落草稿", "attachment_id": "A1"}
    card = te.build_card(decl, result, view)
    assert card["artifact_type"] == "cost_sheet_parse"
    assert card["refs"]["opportunity_id"] == "OPP1"   # 取自步后案台
    assert card["refs"]["sheet_id"] == 3
    assert card["summary"] == "已落草稿"
    # 非 $ 前缀 = 字面量
    decl2 = {"on_tool": "x", "artifact_type": "t", "title": "T", "summary": "S", "refs": {"k": "literal"}}
    assert te.build_card(decl2, {}, {})["refs"]["k"] == "literal"


def test_kernel_emits_artifact_cards(world, monkeypatch):
    """起点在 place 步（商机已绑、成本表未落），import 跑在本步、卡按本步声明发射。"""
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}

    async def _pa(thread_id, colleague, card):
        captures["cards"].append(card)

    async def stub(msg, cfg, **kw):
        await kw["tool_guard"]("import_cost_sheet", {},
                               {"ok": True, "sheet_id": 3, "sheet_name": "s", "configs": [1, 2]})
        return {"ok": True, "answer": "解析好了"}

    _patch_turn_env(monkeypatch, world, stub, captures)
    monkeypatch.setattr(tt, "_persist_artifact", _pa)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "这是成本表", None, [], {"role_key": "assistant"}, "", user=dict(USER)))
    assert [c["artifact_type"] for c in captures["cards"]] == ["cost_sheet_parse"]
    assert captures["cards"][0]["refs"]["sheet_id"] == 3
    assert captures["cards"][0]["refs"]["sheet_id"] == 3


def test_delivery_missing_flow_flags_incomplete(world):
    world.flow = {"rules": "", "steps": []}
    v = _dview(world)
    assert v["step"] is None and not v["complete"]


# ── 轮壳（stub LLM 循环）─────────────────────────────────────────────────


def _patch_turn_env(monkeypatch, world, stub, captures):
    monkeypatch.setattr(tt, "run_stream_chat_loop", stub)
    async def _persist(thread_id, colleague, text, **kw):
        captures["persisted"].append((text, kw.get("tool_steps")))
    monkeypatch.setattr(tt, "_persist_and_broadcast", _persist)
    monkeypatch.setattr(tt, "_short_term_history", lambda c, h: list(h or []))
    monkeypatch.setattr(tt, "build_chat_config",
                        lambda c: {"chat_system_prompt": "P", "response_profile": {}})
    monkeypatch.setattr(tt, "_style_hint", lambda cfg: "")
    monkeypatch.setattr(tt, "_handoff_hint", lambda c: "")
    monkeypatch.setattr(tt, "effective_price_ok", lambda c, user=None: True)
    monkeypatch.setattr(tt, "_effective_tool_ids", lambda c: [])

    class _Hub:
        async def broadcast(self, thread_id, payload):
            captures["broadcasts"].append(payload)
    monkeypatch.setattr(tt, "assistant_hub", _Hub())
    async def _pub(*a, **k):
        return None
    monkeypatch.setattr(tt, "publish_office_event", _pub)

    import app.services.skill_memory as sm
    monkeypatch.setattr(sm, "load_skill_session", lambda t, r: dict(captures["session"]))
    def _save(t, r, s):
        captures["session"].clear()
        captures["session"].update(s)
    monkeypatch.setattr(sm, "save_skill_session", _save)
    async def _trace(*a, **k):
        return None
    monkeypatch.setattr(tt, "_trace", _trace)


def _run(coro):
    return asyncio.run(coro)


def test_turn_advances_until_no_progress(world, monkeypatch):
    calls, captures = [], {"persisted": [], "broadcasts": [], "session": {}}

    async def stub(msg, cfg, **kw):
        calls.append({"msg": msg, "system": kw.get("system_prompt"),
                      "tools": kw.get("allowed_tool_ids"), "ctx": TOOL_CTX.get()})
        if len(calls) == 1:
            world.thread["opportunity_id"] = "OPP1"
            world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
            world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1]}]
        return {"ok": True, "answer": f"答复{len(calls)}"}

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "这是成本表", None, [], {"role_key": "assistant"}, "", user=dict(USER)))
    assert len(calls) == 2
    assert [t for t, _ in captures["persisted"]] == ["答复1", "答复2"]
    assert "import_cost_sheet" in calls[0]["tools"]
    assert "submit_cost_sheet" in calls[1]["tools"]
    assert "规则R" in calls[0]["system"] and "【当前案台】" in calls[0]["msg"]
    assert calls[0]["ctx"]["user"] == USER and calls[0]["ctx"]["price_ok"] is True


def test_turn_broadcasts_pipeline_events(world, monkeypatch):
    """过程事件协议对齐需求分析引擎：turn 开头 pipeline_start 骨架；步骤 running→done
    携工具事实摘要；一步过关连带的后续探针也补发 done；停在本步等用户时
    pipeline_waiting 给中断点事实（画布高亮/任务条计步/实时输出物全靠它）。"""
    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}
    calls = {"n": 0}

    async def stub(msg, cfg, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            await kw["tool_guard"]("import_cost_sheet", {},
                                   {"ok": True, "sheet_id": 3, "sheet_name": "s",
                                    "note": "已生成成本核算草稿（未提交）"})
            world.thread["opportunity_id"] = "OPP1"
            world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
            world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1]}]
            return {"ok": True, "answer": "解析好了"}
        return {"ok": True, "answer": "缺成本表ID，先确认"}  # 指针停在 submit 等用户

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "这是成本表", None, [], {"role_key": "assistant"}, "", user=dict(USER),
        title="交付转报价"))
    types = [b["type"] for b in captures["broadcasts"]]
    assert types[0] == "pipeline_start"
    assert captures["broadcasts"][0]["title"] == "交付转报价"
    assert [s["key"] for s in captures["broadcasts"][0]["steps"]] == \
        [s["key"] for s in world.flow["steps"]]
    traces = {(b["step"],): b for b in captures["broadcasts"] if b["type"] == "node_trace"}
    # identify 跑的工具：running→done 且事实摘要带进节点输出；
    # 探针连带过关的 place_bom/place/derive_cost 由补发机制标记 done——
    # 这些节点自己没有工具事实，摘要如实说明「未单独执行」（不冒领前序产物）
    assert traces[("identify",)]["status"] == "done"
    assert "import_cost_sheet" in traces[("identify",)]["summary"]
    assert traces[("place_bom",)]["status"] == "done"
    assert traces[("place",)]["status"] == "done"
    assert "未单独执行" in (traces[("place",)]["summary"] or "")
    assert traces[("derive_cost",)]["status"] == "done"
    # 停在 submit 等用户：running 事件在档，pipeline_waiting 给中断点
    assert traces[("submit",)]["status"] == "running"
    waiting = [b for b in captures["broadcasts"] if b["type"] == "pipeline_waiting"]
    assert waiting and waiting[-1]["pause"]["step"] == "submit"
    assert waiting[-1]["pause"]["reason_code"] == "brain_ask"


def test_node_states_skipped_by_condition_not_note():
    """状态语义唯一出口（2026-10-22 架构修）：skipped 按 skip_if 条件本身判定，
    与 skip_note 文案配不配无关——回合壳/画布只搬运 node_states 的结果。
    （回归点：回合壳曾拿文案真假当判定，没配文案的跳过节点被广播成 done 冒充完成绿）"""
    steps = [
        {"key": "a", "label": "A", "completion": {"slot": "x"}},
        {"key": "b", "label": "B", "completion": {"any_of": ["scheme"],
                                                  "skip_if": {"flag": "lane", "equals": "cost"}}},
        {"key": "c", "label": "greenC", "completion": {"flag": "share"}},
    ]
    view = {"flags": {"lane": "cost"}}
    assert te.node_states(steps, view) == {"a": "pending", "b": "skipped", "c": "pending"}
    evs = te.state_events(steps, view, "t1")
    ev_b = next(e for e in evs if e["step"] == "b")
    assert ev_b["status"] == "skipped"
    assert "跳过" in ev_b["summary"]
    steps[1]["completion"]["skip_note"] = "成本链不走方案落位"
    evs = te.state_events(steps, view, "t1")
    assert next(e for e in evs if e["step"] == "b")["summary"] == "成本链不走方案落位"
    ev_done = te.state_events(
        [{"key": "a", "label": "A", "completion": {"slot": "x"}}],
        {"x": {"v": 1}}, "t1")
    assert ev_done[0]["status"] == "done"


def test_turn_broadcasts_skipped_not_green(world, monkeypatch):
    """回合壳契约：分流跳过的节点广播 status=skipped（画布灰色虚线），
    绝不冒充 done 的完成绿——即使该节点没配 skip_note 文案。"""
    world.flow["steps"][1]["completion"] = {"any_of": ["scheme"],
                                            "skip_if": {"flag": "lane", "equals": "cost"}}
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    world.state["delivery_flow:assistant"] = {"lane": "cost"}

    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}
    calls = {"n": 0}

    async def stub(msg, cfg, **kw):
        calls["n"] += 1
        return {"ok": True, "answer": "在等确认"}

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "确认执行", None, [], {"role_key": "assistant"}, "", user=dict(USER),
        title="交付转报价"))
    traces = {(b["step"],): b for b in captures["broadcasts"] if b["type"] == "node_trace"}
    assert traces[("place_bom",)]["status"] == "skipped"
    assert "跳过" in (traces[("place_bom",)]["summary"] or "")
    assert traces[("identify",)]["status"] == "done"


def test_turn_direct_executes_confirmed_write(world, monkeypatch):
    """确认卡直达执行契约（2026-10-22 架构修）：用户点「确认执行」→ 轮壳按 staged
    记录直接调工具（confirm=true），大脑只做陈述、不重调工具——用户意图不再经过
    大脑转述参数的概率通路；结果作为事实回写案台并广播节点产物。"""
    from app.services import agent_tool_specs as ats
    wc._STORAGE = "memory"
    wc._MEM.clear()
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1]}]
    wc.stage("t1", "submit_cost_sheet", {"sheet_id": 3, "opportunity_id": "OPP1"},
             {"动作": "提交成本表并转为报价单草稿"})
    wc.note_user_message("t1")

    called = {}

    async def fake_handler(args):
        called["n"] = called.get("n", 0) + 1
        called["args"] = dict(args)
        # 写真实业务表（指针探针读的是案台，不是工具返回）：报价单在场 → submit 探针过；
        # 成功即消费待确认记录（真实工具经 _consume_pending 做同样的事）
        world.quote_result = {"ok": True, "quotation_id": "Q9", "version": "v1"}
        wc.consume("t1", "submit_cost_sheet")
        return {"ok": True, "sheet_id": 3, "quotation_id": "Q9", "converted": True,
                "note": "成本表已提交并转为报价单草稿"}

    monkeypatch.setattr(ats, "_TOOL_SPECS",
                        {**ats._TOOL_SPECS, "submit_cost_sheet": {"handler": fake_handler}})

    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}
    brain_msgs: list = []

    async def stub(msg, cfg, **kw):
        brain_msgs.append(msg)
        return {"ok": True, "answer": "已提交并转为报价单草稿，单号 Q9"}

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "确认执行", None, [], {"role_key": "assistant"}, "", user=dict(USER),
        title="交付转报价"))
    # 工具被轮壳直调且只直调一次：staged 参数 + confirm=true；
    # 大脑第一条消息拿到的是【已执行】陈述指令（不是重调参数的旧通路）
    assert called.get("n") == 1
    assert called.get("args", {}).get("confirm") is True
    assert called.get("args", {}).get("sheet_id") == 3
    assert "【已执行】" in brain_msgs[0]
    assert "submit_cost_sheet" in brain_msgs[0]
    # 节点产物广播带了直达执行的事实摘要
    traces = {(b["step"],): b for b in captures["broadcasts"] if b["type"] == "node_trace"}
    assert traces[("submit",)]["status"] == "done"
    assert "submit_cost_sheet" in (traces[("submit",)]["summary"] or "")


def test_turn_gate_nudges_when_brain_skips_tool(world, monkeypatch):
    """R3(b) 记录完备（2026-10-22 实测"说了点确认卡但卡没出"）：闸步停住、没有任何
    待确认记录 = 大脑没调闸工具就陈述了——强制重调一轮（【确认闸纪律】）；
    重调后仍无记录 → 回合末发机械话术（真报错，不让用户等一张永远不来的卡）。"""
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1]}]
    world.flow["steps"][4]["gated"] = True  # submit
    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}
    brain_msgs: list = []

    async def stub(msg, cfg, **kw):
        brain_msgs.append(msg)
        return {"ok": True, "answer": "请在下方卡片点「确认提交」"}  # 光说不调工具

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "继续", None, [], {"role_key": "assistant"}, "", user=dict(USER),
        title="交付转报价"))
    assert len(brain_msgs) == 2
    assert "【确认闸纪律】" in brain_msgs[1]
    assert "submit_cost_sheet" in brain_msgs[1]
    # 重调后仍无记录 → 机械兜底话术（真报错），绝不静默收场
    assert any("确认操作没有生成成功" in (t or "") for t, _kw in captures["persisted"])


def test_turn_gate_nudge_skips_legit_ask(world, monkeypatch):
    """R3(b) 例外：闸步上工具 needs_input = 大脑在合法地要参数，不逼重调
    （否则会逼大脑编参数——闸步的正当停法是"问用户"）。"""
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1]}]
    world.flow["steps"][4]["gated"] = True  # submit
    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}
    brain_msgs: list = []

    async def stub(msg, cfg, **kw):
        brain_msgs.append(msg)
        guard = kw.get("tool_guard")
        if guard and len(brain_msgs) == 1:
            # 工具真实通路：闸工具因缺参数返回 needs_input（fact_guard 采集）
            await guard("set_quote_margin", {},
                        {"ok": False, "needs_input": True, "missing": ["margin_pct"],
                         "error": "缺少加价率：这个报价单要按几个点加价？"})
        return {"ok": True, "answer": "请告诉我加价率百分比"}

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "继续", None, [], {"role_key": "assistant"}, "", user=dict(USER),
        title="交付转报价"))
    assert len(brain_msgs) == 1  # 没有逼重调
    assert not any("确认操作没有生成成功" in (t or "") for t, _kw in captures["persisted"])


def test_turn_replays_deferred_gate_call_on_step_advance(world, monkeypatch):
    """R3a 跨步记录完备（2026-10-22 实锤：识别步只解析预览 → 指针静默推进 →
    大脑对推进零感知，拿着旧结果承诺一张永远没人发的卡）：identify 步的闸调用
    被 deny 成 analysis_only（deferred_by_step 记账）→ 指针推进到 place → 轮壳
    原参数重放 → 工具走自己的确认闸（stage）→ 卡在下一轮答案之后落库（R2）。"""
    import json as _json
    from unittest.mock import patch
    from app.services import agent_tool_specs as ats
    import app.services.colleague_turn_io as cio
    import app.services.human_query as hq
    wc._STORAGE = "memory"
    wc._MEM.clear()
    hq._STORAGE = "db"  # 走 world 假仓库（reasoning_state 读写全被 fixture 接管）
    # 上一轮：identify 步调用被降级，调和器已记账（跨回合存活）
    wc.defer_call("t1", "import_cost_sheet", {"attachment_id": "att9", "customer_name": "王瑞"})
    world.flow["steps"][1]["completion"] = {"any_of": ["scheme"],
                                            "skip_if": {"flag": "lane", "equals": "cost"}}
    world.state["delivery_flow:assistant"] = {"lane": "cost"}
    world.state.pop("human_query:assistant", None)
    world.sheets = []

    replayed = {}

    async def fake_handler(args):
        replayed["args"] = dict(args)
        # 真实工具在所属步会走自己的确认闸：stage+needs_confirmation（此处同构）
        wc.stage("t1", "import_cost_sheet", dict(args),
                 {"动作": "解析成本表并落草稿（不提交）", "附件": "HK.xlsx"})
        return {"needs_confirmation": True,
                "preview": {"动作": "解析成本表并落草稿（不提交）", "附件": "HK.xlsx"}}

    monkeypatch.setattr(ats, "_TOOL_SPECS",
                        {**ats._TOOL_SPECS, "import_cost_sheet": {"handler": fake_handler}})

    captures = {"persisted": [], "broadcasts": [], "session": {}, "cards": []}
    brain_msgs: list = []

    async def stub(msg, cfg, **kw):
        brain_msgs.append(msg)
        if len(brain_msgs) == 1:
            # 第一轮：大脑建档（线程绑定商机）+ lane 判定完成 → 指针推进到 place
            world.thread["opportunity_id"] = "OPP1"
            world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
        return {"ok": True, "answer": f"第 {len(brain_msgs)} 条"}

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "继续", None, [], {"role_key": "assistant"}, "", user=dict(USER),
        title="交付转报价"))
    # 指针推进触发重放：原参数、一次即清账
    assert replayed.get("args", {}).get("attachment_id") == "att9"
    assert replayed["args"].get("customer_name") == "王瑞"
    assert wc.deferred_calls("t1") == {}
    # 工具自己走闸 → 待确认记录在场；授权问询（consent HumanQuery）已发射且开放
    assert wc.pending_count("t1") == 1
    assert wc.query_opened("t1", "import_cost_sheet")
    open_q = hq.open_query_of("t1")
    assert open_q and open_q["kind"] == "consent" and open_q["action"]["tool"] == "import_cost_sheet"
    # 大脑在下一轮拿到重放事实
    assert any("【闸调用已重放】" in m and "import_cost_sheet" in m for m in brain_msgs[1:])


def test_missing_prices_l6_config_level():
    """L6 缺价按配置级整价（l6_cost）数——页面口径：L6 是整机一口价，
    l6_rows 只是明细展示，不逐行数（2026-10-22 用户定）。KP 仍逐行。"""
    from app.services.delivery_app import _missing_prices
    strategy = {"kp_price": True, "l6_price": True}
    configs = [
        {"name": "CF1", "l6_cost": 12222,
         "kp_rows": [{"base_price": 5}],
         "l6_rows": [{"base_price": None}, {"base_price": None}]},
        {"name": "CF2", "l6_cost": 0, "kp_rows": [], "l6_rows": []},
    ]
    assert _missing_prices(configs, strategy) == {"kp_missing": 0, "l6_missing": 1}


def test_turn_injects_step_contract_into_prompt(world, monkeypatch):
    """步骤契约注入系统提示词：目标层 + 必填字段随 step 下发（反问点=契约缺口）。"""
    world.flow["steps"][0]["target_artifact"] = {
        "kind": "record", "name": "商机", "slot": "opportunities",
        "fields": [{"key": "customer_name", "label": "客户名称", "ask": True, "hint": "逐字使用"},
                   {"key": "sales_person", "label": "归属业务", "ask": True}]}
    calls, captures = [], {"persisted": [], "broadcasts": [], "session": {}}

    async def stub(msg, cfg, **kw):
        calls.append({"msg": msg, "system": kw.get("system_prompt"),
                      "tools": kw.get("allowed_tool_ids"), "ctx": TOOL_CTX.get()})
        world.thread["opportunity_id"] = "OPP1"
        world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
        world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1]}]
        world.quote_result = {"ok": True, "quotation_id": "Q1", "quotation_name": "n", "version": 1}
        return {"ok": True, "answer": "好"}

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "办成报价单", None, [], {"role_key": "assistant"}, "", user=dict(USER)))
    assert "本步目标：商机 → 写入 opportunities" in calls[0]["system"]
    assert "必填字段：客户名称、归属业务" in calls[0]["system"]
    assert calls[0]["ctx"]["step_key"] == "identify"
    assert [f["key"] for f in calls[0]["ctx"]["step_fields"]] == ["customer_name", "sales_person"]


def test_turn_completes_chain_marks_done(world, monkeypatch):
    world.thread["opportunity_id"] = "OPP1"
    world.opportunity = {"opportunity_id": "OPP1", "customer_name": "王瑞"}
    world.sheets = [{"id": 3, "name": "s", "status": "draft", "configs": [1]}]
    world.quote_result = {"ok": True, "quotation_id": "Q1", "quotation_name": "n", "version": 1}
    world.state = {f"{dapp.STATE_SLOT}:assistant": {"margin": {"pct": 15, "quotation_id": "Q1"}}}
    calls, captures = [], {"persisted": [], "broadcasts": [], "session": {"phase": "active"}}

    async def stub(msg, cfg, **kw):
        calls.append(msg)
        world.state[f"{dapp.STATE_SLOT}:assistant"]["share"] = {"share_path": "/api/share/x"}
        return {"ok": True, "answer": "链接在此"}

    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "出件", None, [], {"role_key": "assistant"}, "", user=dict(USER)))
    assert len(calls) == 1
    assert captures["session"].get("phase") == tt.SKILL_SESSION_DONE
    assert any(b.get("type") == "analysis_finished" for b in captures["broadcasts"])


def test_turn_falls_back_to_tool_turn_without_flow(world, monkeypatch):
    world.flow = {"rules": "", "steps": []}
    captures = {"persisted": [], "broadcasts": [], "session": {}, "fallback": []}

    async def _fallback(*a, **k):
        captures["fallback"].append(a)
    monkeypatch.setattr(runners, "_run_tool_turn", _fallback)
    async def stub(*a, **k):
        raise AssertionError("stub should not run")
    _patch_turn_env(monkeypatch, world, stub, captures)
    _run(tt._run_transaction_turn(
        dapp.APP, "t1", "在吗", None, [], {"role_key": "assistant"}, "", user=dict(USER)))
    assert len(captures["fallback"]) == 1


# ── 分发器（三分支路由）──────────────────────────────────────────────────


def test_dispatch_routes_real_bound_to_transaction(world, monkeypatch):
    captures = {"tx": [], "skill": [], "tool": []}

    async def _tx(app, *a, **k):
        captures["tx"].append(app)
    async def _skill(*a, **k):
        captures["skill"].append(a)
    async def _tool(*a, **k):
        captures["tool"].append(a)
    monkeypatch.setattr(tt, "_run_transaction_turn", _tx)
    monkeypatch.setattr(runners, "_run_skill_chat", _skill)
    monkeypatch.setattr(runners, "_run_tool_turn", _tool)

    _run(tt.dispatch_flow_turn({"entity_binding": "real_bound"}, flow_key="delivery_to_quotation",
                               thread_id="t1", user_text="u", context_summary=None, history=[],
                               colleague={"role_key": "assistant"}, memory_block=""))
    assert captures["tx"] == [dapp.APP] and not captures["skill"] and not captures["tool"]


def test_dispatch_fresh_unbinds_thread_opportunity(world, monkeypatch):
    captures = {"tx": []}

    async def _tx(app, *a, **k):
        captures["tx"].append(app)
    monkeypatch.setattr(tt, "_run_transaction_turn", _tx)
    world.thread["opportunity_id"] = "OPP-OLD"  # 上一单的绑定
    _run(tt.dispatch_flow_turn({"entity_binding": "real_bound"}, flow_key="delivery_to_quotation",
                               fresh=True, thread_id="t1", user_text="新开工单", context_summary=None,
                               history=[], colleague={"role_key": "assistant"}, memory_block=""))
    assert world.thread["opportunity_id"] is None  # 案台回到第一步，绑定一并清
    assert len(captures["tx"]) == 1


def test_dispatch_fresh_clears_state_slot(world, monkeypatch):
    captures = {"tx": []}

    async def _tx(app, *a, **k):
        captures["tx"].append(app)
    monkeypatch.setattr(tt, "_run_transaction_turn", _tx)
    world.state = {f"{dapp.STATE_SLOT}:assistant": {"margin": {"pct": 9}}}
    _run(tt.dispatch_flow_turn({"entity_binding": "real_bound"}, flow_key="delivery_to_quotation",
                               fresh=True, thread_id="t1", user_text="u", context_summary=None,
                               history=[], colleague={"role_key": "assistant"}, memory_block=""))
    assert te.load_state(dapp.APP, "t1", "assistant") == {}


def test_dispatch_unknown_real_bound_falls_to_tool_turn(world, monkeypatch):
    captures = {"tx": [], "skill": [], "tool": []}

    async def _tx(app, *a, **k):
        captures["tx"].append(app)
    async def _skill(*a, **k):
        captures["skill"].append(a)
    async def _tool(*a, **k):
        captures["tool"].append(a)
    monkeypatch.setattr(tt, "_run_transaction_turn", _tx)
    monkeypatch.setattr(runners, "_run_skill_chat", _skill)
    monkeypatch.setattr(runners, "_run_tool_turn", _tool)
    monkeypatch.setattr(te, "resolve_app", lambda key: None)

    _run(tt.dispatch_flow_turn({"entity_binding": "real_bound"}, flow_key="ghost_flow",
                               thread_id="t1", user_text="u", context_summary=None, history=[],
                               colleague={"role_key": "assistant"}, memory_block=""))
    assert captures["tool"] and not captures["tx"] and not captures["skill"]


def test_dispatch_sandbox_goes_to_skill_engine(world, monkeypatch):
    captures = {"tx": [], "skill": [], "tool": []}

    async def _tx(app, *a, **k):
        captures["tx"].append(app)
    async def _skill(*a, **k):
        captures["skill"].append(a)
    async def _tool(*a, **k):
        captures["tool"].append(a)
    monkeypatch.setattr(tt, "_run_transaction_turn", _tx)
    monkeypatch.setattr(runners, "_run_skill_chat", _skill)
    monkeypatch.setattr(runners, "_run_tool_turn", _tool)

    _run(tt.dispatch_flow_turn({"entity_binding": "sandbox"}, flow_key="requirement_analysis",
                               thread_id="t1", user_text="u", context_summary=None, history=[],
                               colleague={"role_key": "assistant"}, memory_block="",
                               session_phase="active", write_mode=""))
    assert captures["skill"] and not captures["tx"] and not captures["tool"]


def test_eval_completion_all_of_and_skip_if():
    """all_of 双条件（商机 AND 分流旗标）与 skip_if 短路（分流链路不经过的节点直接过关）。"""
    view = {"opp": {"opportunity_id": "OPP-1"}, "flags": {"lane": "cost"}, "sheet": {}}
    assert te._eval_completion({"all_of": ["opp", "flags.lane"]}, view) is True
    assert te._eval_completion({"all_of": ["opp", "flags.lane"]},
                               {"opp": {}, "flags": {}}) is False
    comp = {"any_of": ["scheme"], "skip_if": {"flag": "lane", "equals": "cost"}}
    assert te._eval_completion(comp, view) is True          # lane=cost → 短路过关
    assert te._eval_completion(comp, {"opp": {}, "flags": {"lane": "scheme"}}) is False
    assert te.skip_note(comp, view) == ""                   # 未短路无说明
    comp2 = dict(comp, skip_note="本链为成本表链，不经过方案落位")
    assert te.skip_note(comp2, view) == "本链为成本表链，不经过方案落位"
    assert te.skip_note(comp2, {"opp": {}, "flags": {"lane": "scheme"}}) == ""


if __name__ == "__main__":
    raise SystemExit("run with pytest")
