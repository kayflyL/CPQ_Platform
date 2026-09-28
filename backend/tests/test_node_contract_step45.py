# -*- coding: utf-8 -*-
"""节点契约回归（Step4 冻结上游文档 / Step5 节点指令取抽屉）。
两条红线：
  * 每节点只写自己的表——上游「线索登记表」落定后即冻结，下游写了要判红；
  * 节点干什么活由抽屉（description/goal）说了算，主循环不留任何节点专属文案。
"""
import asyncio
import os
import sys
from unittest.mock import patch
from app.services import skill_tool_context
from app.services import skill_turn_engine
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
def test_freeze_flags_downstream_write_and_ignores_owner():
    """属主节点落定后打快照；下游节点改写登记表 → 判红并点名差异字段。"""
    from app.services.skill_node_state import doc_freeze_violation, mark_doc_frozen
    engine: dict = {}
    ext = {"server_type": "通用计算服务器", "purchase_qty": 1}
    # 还没落定：谈不上冻结
    assert doc_freeze_violation(engine, "kp_reason", ext) == ""
    # 非属主打点无效
    mark_doc_frozen(engine, "kp_reason", ext)
    assert doc_freeze_violation(engine, "kp_reason", ext) == ""
    # 属主落定 → 快照
    mark_doc_frozen(engine, "agent_fill", ext)
    assert doc_freeze_violation(engine, "agent_fill", ext) == ""      # 属主自己写不算越界
    assert doc_freeze_violation(engine, "kp_reason", ext) == ""       # 没写就没越界
    ext["kp_rows"] = [{"part_category": "CPU", "description": "2颗兆芯50000"}]
    viol = doc_freeze_violation(engine, "kp_reason", ext)
    assert "kp_rows" in viol and "kp_reason" in viol
    # 引擎内部下划线键不算登记内容
    ext.clear()
    mark_doc_frozen(engine, "agent_fill", ext)
    ext["_kp_rows_frozen"] = 1
    assert doc_freeze_violation(engine, "kp_reason", ext) == ""
def test_row_answer_does_not_break_row_key_or_pick():
    """客户对某行的补充回答只进本节点分区，行键取自登记原文 → 已锁定选型不失效。"""
    from app.services.skill_node_state import KP_PICKS, KP_ROW_ANSWERS, add_row_answer, row_answer_text
    from app.services.slot_contract import apply_structured_slots
    ext = {"kp_rows": [{"part_category": "CPU", "description": "2颗兆芯50000", "qty": 2}]}
    kp_st = {KP_PICKS: {"CPU|2颗兆芯50000": {"name": "兆芯 KH50000 96C"}}}
    apply_structured_slots(ext, {"kp_row_merge": {"row": "CPU|2颗兆芯50000", "answer": "2.2GHz 96C"}},
                           "", kp_state=kp_st)
    assert ext["kp_rows"][0]["description"] == "2颗兆芯50000"          # 登记表一字不动
    assert kp_st[KP_PICKS]["CPU|2颗兆芯50000"]["name"] == "兆芯 KH50000 96C"
    assert kp_st[KP_ROW_ANSWERS]["CPU|2颗兆芯50000"] == ["2.2GHz 96C"]
    assert add_row_answer({"node_state": {"kp_reason": kp_st}}, "CPU|2颗兆芯50000", "2.2GHz 96C") is False
    assert row_answer_text({"node_state": {"kp_reason": kp_st}}, "CPU|2颗兆芯50000") == "2.2GHz 96C"
def test_empty_registration_is_not_marked_done_and_hint_is_fed_back():
    """必填闸门：空表不许标 done（历史「空表也标完成 → 线程砖死」），引擎校验失败回喂大脑补做。"""
    from app.services import skill_chat
    from app.services import skill_step_runtime
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    flow = ReasoningFlowRepository().get_active_flow("requirement_analysis")
    assert flow
    msgs: list = []
    async def fake_loop(msg, **kwargs):
        msgs.append(msg)
        return {"answer": "好的", "tool_calls_log": []}      # 只旁白、零工具 → 登记表仍空
    async def sink(payload):
        pass
    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop):
            return await skill_turn_engine.run_skill_agent_turn(
                thread_id="t_gate", role_key="tech", persona="测试人设",
                full_text="需要一台服务器", history=[], ext={}, mem={}, flow=flow,
                event_sink=sink, price_ok=True, opportunity_id="o_gate")
    engine = asyncio.run(scenario())
    assert "agent_fill" not in (engine.get("steps_done") or set()), "空表不得标 done"
    assert len(msgs) >= 2, "校验失败要回喂大脑重试，而不是直接收工"
    assert "【系统反馈" in msgs[1] and "还缺" in msgs[1], "机制缺口只回喂大脑，不抛给客户"
def test_rejected_tool_call_does_not_skip_step_validation():
    """工具被拒但已有收口正文：直接交引擎校验，步骤是否完成由产物说了算。
    历史故障：选型已 8/8 落地，只因一次多余的工具调用被拒就跳过校验 → 步骤不标 done →
    终检拿旧快照判缺 → 客户拿到零选项的「死卡」。
    2026-09-16 收紧：有正文不再回喂重试到上限（趋势分析三份连体报告事故——探索型
    失败调用是常态，一律重开会把已完成的产物整个丢弃重生成），校验始终执行。
    """
    from app.services import skill_chat
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    flow = ReasoningFlowRepository().get_active_flow("requirement_analysis")
    assert flow
    calls = {"n": 0}
    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        return {"answer": "已全部锁定", "tool_calls_log": [
            {"name": "select_parts", "result": {"ok": False, "error": "not_searched",
                                                "message": "该料号不在接地索引内"}}]}
    ext = {"server_type": "通用计算服务器", "platform_type": "Polaris", "chassis_form": "2U",
           "purchase_qty": 1, "warranty_years": 3,
           "kp_rows": [{"part_category": "CPU", "description": "2颗兆芯50000", "qty": 2}]}
    mem = {"ext": ext, "steps_done": ["agent_fill", "model_reason"],
           "node_state": {"kp_reason": {"picks": {"CPU|2颗兆芯50000": {
               "name": "兆芯 KH50000 96C", "part_id": "1", "price": 100.0, "currency": "RMB"}}}},
           "locked_baseline": {"name": "ZS220 V2", "series": "Polaris", "form": "2U",
                               "server_model_id": 1}}
    async def sink(payload):
        pass
    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop):
            return await skill_turn_engine.run_skill_agent_turn(
                thread_id="t_rej", role_key="tech", persona="测试人设", full_text="继续",
                history=[], ext=ext, mem=mem, flow=flow, event_sink=sink,
                price_ok=True, opportunity_id="o_rej")
    engine = asyncio.run(scenario())
    assert calls["n"] == 1, "已有收口正文不得因历史工具拒绝重开（产物说了算，不空转）"
    assert "kp_reason" in (engine.get("steps_done") or set()), \
        "产物齐了就该标 done，不能因一次工具被拒而跳过校验"
def test_done_summary_comes_from_artifact_not_node_name():
    """节点完成摘要由产物生成：产物空就说空，不许按节点名硬编码文案（历史：agent_fill 报「配件选型完成」）。"""
    from app.services.skill_node_artifacts import done_summary
    empty = done_summary({}, "agent_fill", {"kind": "requirement_slots", "title": "线索登记表", "data": {}})
    assert "已完成" not in empty and "产物为空" in empty
    filled = done_summary({}, "agent_fill", {"kind": "requirement_slots", "title": "线索登记表",
                                            "data": {"server_type": "通用计算服务器", "purchase_qty": 1}})
    assert "2 项已登记" in filled
    rows = done_summary({}, "kp_reason", {"kind": "kp_table", "title": "配件表",
                                         "data": {"rows": [1, 2, 3]}})
    assert "配件表" in rows and "3 行" in rows
    locked = done_summary({}, "model_reason", {"kind": "l6_chassis", "title": "机箱表",
                                              "data": {"rows": [1]}}, {"locked": "ZS220 V2"})
    assert "ZS220 V2" in locked and "1 行" in locked
    # 未注册产物的节点：如实说不装懂，不编「已完成」
    assert "未注册产物" in done_summary({}, "whatever", None)
def test_kp_turn_prompt_is_drawer_driven_and_rows_carry_answers():
    """主循环不再有节点专属文案：指令来自左栏任务规则；行清单带客户补充回答。"""
    from app.services import skill_chat
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    flow = ReasoningFlowRepository().get_active_flow("requirement_analysis")
    assert flow, "需求分析 active flow 未播种"
    assert str((flow.get("graph") or {}).get("manual_rules") or "").strip(), \
        "左栏任务规则为空，本用例前提不成立（指令唯一出处=左栏）"
    seen: dict = {}
    calls = {"n": 0}
    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        seen.setdefault("msgs", []).append(msg)
        seen.setdefault("ctxs", []).append(str(kwargs.get("context_block") or ""))
        seen["sys"] = str(kwargs.get("system_prompt") or "")
        return {"answer": "正在逐项选型", "tool_calls_log": []}
    ext = {"server_type": "通用计算服务器", "platform_type": "Polaris", "chassis_form": "2U",
           "purchase_qty": 1, "warranty_years": 3,
           "kp_rows": [{"part_category": "CPU", "description": "2颗兆芯50000", "qty": 2}]}
    mem = {"ext": ext, "steps_done": ["agent_fill", "model_reason"],
           "node_state": {"kp_reason": {"row_answers": {"CPU|2颗兆芯50000": ["2.2GHz 96C"]}}},
           "locked_baseline": {"name": "ZS220 V2", "series": "Polaris", "form": "2U",
                               "server_model_id": 1}}
    async def sink(payload):
        pass
    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop):
            return await skill_turn_engine.run_skill_agent_turn(
                thread_id="t_mission", role_key="tech", persona="测试人设",
                full_text="CPU：2颗兆芯50000 处理器（2.2GHz/96C）", history=[],
                ext=ext, mem=mem, flow=flow, event_sink=sink,
                price_ok=True, opportunity_id="o_mission")
    engine = asyncio.run(scenario())
    assert calls["n"] >= 1
    # 左栏任务规则进了 system（指令唯一出处；query_parts 等协议句在规则 15）
    assert "query_parts" in seen["sys"]
    # 主循环里的节点专属硬编码文案已退役
    assert "【配件选配的落地方式】" not in seen["sys"]
    # 行清单下发（2026-09-11 P2：改下发**全量**行清单，含已了结行与状态），
    # 且带上客户对该行的补充回答（检索用），登记表未被改写
    all_ctx = "\n".join(seen["ctxs"])
    assert "配件行清单" in all_ctx
    assert "全量" in all_ctx and "已了结" in all_ctx
    assert "row_id" in all_ctx
    assert "2颗兆芯50000" in all_ctx
    assert "2.2GHz 96C" in all_ctx, "客户对该行的补充回答要随行清单下发给大脑（检索用）"
    assert ext["kp_rows"][0]["description"] == "2颗兆芯50000"
    assert engine.get("contract_warnings") in (None, []), engine.get("contract_warnings")
# ── Step 4：登记表对下游只读（类型级，不靠约定）──────────────────────────────
def test_frozen_doc_view_blocks_every_write_path():
    """下游拿到的登记表视图：读随意，写（=、setdefault、update、pop、clear）一律当场报错。"""
    import pytest
    from app.services.skill_node_state import DocWriteForbidden, FrozenDocView, unwrap_doc
    raw = {"server_type": "通用计算服务器", "purchase_qty": 1}
    view = FrozenDocView(raw, "kp_reason")
    assert view["server_type"] == "通用计算服务器"
    assert dict(view) == raw and "purchase_qty" in view and len(view) == 2
    assert "FrozenDocView" in repr(view) and unwrap_doc(view) == raw
    assert isinstance(view, dict), "必须是 dict 子类：既有 isinstance(x, dict) 判断不被改变"
    for op in (lambda: view.__setitem__("server_type", "别的"),
               lambda: view.setdefault("x", 1),
               lambda: view.update({"y": 2}),
               lambda: view.pop("purchase_qty"),
               lambda: view.clear()):
        with pytest.raises(DocWriteForbidden):
            op()
    assert raw == {"server_type": "通用计算服务器", "purchase_qty": 1}, "底层文档一字未改"
def test_downstream_node_turn_gets_readonly_registration_doc():
    """非属主节点回合：工具上下文里是只读视图，写登记表当场失败，底表不变。"""
    from app.services import skill_chat
    from app.services.skill_node_state import DocWriteForbidden, FrozenDocView
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    flow = ReasoningFlowRepository().get_active_flow("requirement_analysis")
    assert flow
    seen: dict = {}
    async def fake_loop(msg, **kwargs):
        ext = skill_tool_context.TOOL_CTX.get().get("ext")
        seen["is_view"] = isinstance(ext, FrozenDocView)
        try:
            ext["server_model"] = "臆造机型"          # 下游回填上游 → 必须当场失败
            seen["wrote"] = True
        except DocWriteForbidden:
            seen["wrote"] = False
        return {"answer": "好的", "tool_calls_log": []}
    async def sink(payload):
        pass
    ext = {"server_type": "通用计算服务器", "platform_type": "Polaris", "chassis_form": "2U",
           "purchase_qty": 1, "warranty_years": 3,
           "kp_rows": [{"part_category": "CPU", "description": "2颗兆芯50000", "qty": 2}]}
    mem = {"steps_done": ["agent_fill"],
           "locked_baseline": {"name": "ZS220 V2", "series": "Polaris", "form": "2U"}}
    async def scenario():
        with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop):
            return await skill_turn_engine.run_skill_agent_turn(
                thread_id="t_ro", role_key="tech", persona="测试人设",
                full_text="继续", history=[], ext=ext, mem=mem, flow=flow,
                event_sink=sink, price_ok=True, opportunity_id="o_ro")
    engine = asyncio.run(scenario())
    assert seen.get("is_view") is True, "下游节点必须拿到只读视图"
    assert seen.get("wrote") is False, "写登记表必须当场失败"
    assert "server_model" not in ext
    assert not isinstance(engine.get("ext"), FrozenDocView), "回合收尾要还原成原始文档（落盘用）"
def test_frozen_snapshot_moves_across_turns_and_ignores_the_customers_own_click():
    """快照跨轮搬运（引擎内存对象每轮重建，只能从记忆搬）：跨轮回填必须照样判红；
    客户自己点选登记字段 = 客户改**自己的**表，重打点后不再判红。"""
    from app.services.skill_node_state import doc_freeze_violation, freeze_snapshot, mark_doc_frozen
    turn1: dict = {}
    ext = {"server_type": "通用计算服务器", "kp_rows": []}
    mark_doc_frozen(turn1, "agent_fill", ext)
    mem = {"frozen_docs": freeze_snapshot(turn1)}
    assert mem["frozen_docs"], "快照必须能被搬进记忆，否则判红只活在当轮"
    turn2 = {"frozen_docs": freeze_snapshot(mem)}
    assert doc_freeze_violation(turn2, "kp_reason", ext) == ""
    ext["kp_rows"] = [{"part_category": "CPU", "description": "2颗兆芯50000"}]
    assert "kp_rows" in doc_freeze_violation(turn2, "kp_reason", ext), "跨轮回填必须照样判红"
    mark_doc_frozen(turn2, "agent_fill", ext)          # 客户点选确认 → 快照前移
    assert doc_freeze_violation(turn2, "kp_reason", ext) == ""
