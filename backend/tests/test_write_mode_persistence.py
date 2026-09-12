# -*- coding: utf-8 -*-
"""写模式与草稿持久化守卫（2026-09-12 B1-B4）。

背景：落库闸门过去读的是 business_mode——全仓只有读、没有任何写入点，三个 persist_*
于是永远返回 None（对话期间什么都不落）。B1 把写模式改成由入口显式决定；B2 每轮把需求
草稿写回真实表、回合开始再从草稿播种 ext；B3 机型/配件一落定就写方案配置草稿；
B4 交付原地提交那张需求草稿，不再 initiate_requirement 新开一版。

这些断言拦四件事：写模式判反（试运行落了库）、非 draft 偷偷落库、交付又新开版本、
草稿读不回（客户在详情页手改的，对话下一轮又看不见）。
"""
import ast
import contextvars
import inspect

from app.services import portal_flow_adapter as adapter
from app.services import skill_node_runtime
from app.services import skill_turn_engine
from app.services.colleague_turn_runners import PREVIEW_ENTRY_POINTS, _skill_write_mode
from app.services.portal_flow_adapter import (
    _can_persist_draft, _write_mode, seed_ext_from_requirement_draft)

OPP = "opp-write-mode-1"
EXT = {"server_type": "AI服务器", "platform_type": "Polaris", "chassis_form": "4U",
       "purchase_qty": 2, "warranty_years": 3,
       "kp_rows": [{"part_category": "内存", "description": "64G", "qty": 8}]}
PLAN = {"model": "ZS22V2-P",
        "cfg": {"bom_excel_rows": [
            {"category": "L6", "catalogue": "ZS22V2-P", "description": "整机", "qty": 1},
            {"category": "Key Parts", "catalogue": "MEM-64G", "description": "64G RDIMM", "qty": 8},
        ]},
        "summary": {"l6_cost": 1000.0, "kp_cost": 200.0, "total_cost": 1200.0}}


# ── B1 写模式由入口显式决定 ──────────────────────────────────────────

def test_entry_point_decides_write_mode():
    """试运行入口 → preview（哪怕带着商机也不落库）；有商机 → draft；都没有 → none。"""
    assert _skill_write_mode("skill_studio_preview", OPP) == "preview"
    assert _skill_write_mode("skill_studio_preview", None) == "preview"
    assert _skill_write_mode("workflow_launcher", OPP) == "draft"
    assert _skill_write_mode(None, OPP) == "draft"
    assert _skill_write_mode(None, None) == "none"
    assert _skill_write_mode("", "   ") == "none"
    assert "skill_studio_preview" in PREVIEW_ENTRY_POINTS


def test_ctx_write_mode_and_legacy_fallback():
    """ctx 显式值优先；历史 ctx 没这个字段时按「有商机才落草稿」兜底。"""
    assert _write_mode({"write_mode": "preview", "opportunity_id": OPP}) == "preview"
    assert _write_mode({"write_mode": "none", "opportunity_id": OPP}) == "none"
    assert _write_mode({"write_mode": "draft", "opportunity_id": OPP}) == "draft"
    assert _write_mode({"opportunity_id": OPP}) == "draft"
    assert _write_mode({}) == "none"
    assert _can_persist_draft({"write_mode": "draft", "opportunity_id": OPP}) is True
    assert _can_persist_draft({"write_mode": "draft"}) is False
    assert _can_persist_draft({"write_mode": "preview", "opportunity_id": OPP}) is False


def test_dead_business_mode_gate_is_gone():
    """business_mode 全仓没有写入点：它不许再当闸门（那正是三个 persist_* 永远返回 None 的根）。"""
    # 光有 business_mode 不落库（没有商机）；有商机就该落——旧代码在后者也永远是 False。
    assert _can_persist_draft({"business_mode": "opportunity_flow"}) is False
    assert _can_persist_draft({"business_mode": "opportunity_flow", "opportunity_id": OPP}) is True
    assert "business_mode" not in inspect.getsource(adapter.persist_requirement_from_ctx)


def test_preview_and_none_never_touch_the_database(monkeypatch):
    """写模式非 draft：三个落库入口一律返回 None，且一个写函数都不许被调到。"""
    calls: list = []
    for name in ("save_requirement_draft", "submit_requirement_draft", "save_bom_scheme_draft"):
        monkeypatch.setattr(adapter, name,
                            lambda *a, _n=name, **k: calls.append(_n), raising=True)
    for mode in ("preview", "none"):
        ctx = {"write_mode": mode, "opportunity_id": OPP, "ext": dict(EXT),
               "requirement_text": "客户原话", "plans": [PLAN]}
        assert adapter.persist_requirement_from_ctx(ctx) is None
        assert adapter.persist_requirement_and_bom_from_ctx(ctx) is None
        assert adapter.persist_bom_scheme_from_ctx(ctx) is None
    assert calls == []


# ── B2 每轮写回需求草稿 ─────────────────────────────────────────────

def test_draft_mode_writes_requirement_slots_every_turn(monkeypatch):
    """draft：登记回合收尾就把登记表快照原地写回草稿（每轮都写，不攒到交付）。"""
    seen: dict = {}
    monkeypatch.setattr(adapter, "_attach_entity_card", lambda *a, **k: None)

    def fake_save(opp, slots, text, created_by=""):
        seen.update(opp=opp, slots=slots, text=text, by=created_by)
        return {"version": 7}

    monkeypatch.setattr(adapter, "save_requirement_draft", fake_save)
    out = adapter.persist_requirement_from_ctx(
        {"write_mode": "draft", "opportunity_id": OPP, "ext": dict(EXT),
         "requirement_text": "客户原话"}, "张三")
    assert out == {"version": 7}
    assert seen["opp"] == OPP and seen["text"] == "客户原话" and seen["by"] == "张三"
    assert seen["slots"]["server_type"] == "AI服务器"
    assert seen["slots"]["kp_rows"][0]["part_category"] == "Memory"  # KP 大类入库前归一


def test_seed_ext_from_requirement_draft_round_trip(monkeypatch):
    """B2 读回：草稿是真相（详情页手改过，下一轮按改后的走）；空草稿不覆盖本轮现场。"""
    monkeypatch.setattr(adapter, "load_requirement_draft", lambda opp: {"slots": {
        "server_type": "通用计算服务器", "purchase_qty": 5,
        "kp_rows": [{"part_category": "Memory", "description": "32G", "qty": 4,
                     "catalogue": "", "note": ""}]}})
    ext = dict(EXT)
    assert seed_ext_from_requirement_draft(ext, OPP) is True
    assert ext["server_type"] == "通用计算服务器"
    assert ext["purchase_qty"] == 5
    assert ext["kp_rows"][0]["description"] == "32G"
    # 草稿里没有的键不动（不拿空表覆盖本轮现场）
    monkeypatch.setattr(adapter, "load_requirement_draft", lambda opp: None)
    ext2 = dict(EXT)
    assert seed_ext_from_requirement_draft(ext2, OPP) is False
    assert ext2["server_type"] == "AI服务器"
    assert seed_ext_from_requirement_draft(ext2, "") is False


def test_fill_node_wire_result_writes_draft_back(monkeypatch):
    """B2 挂钩点：登记节点每轮收尾就写回草稿；ext 不是 dict 时安全空转。"""
    from app.services import skill_node_plugins as plugins
    hits: list = []
    monkeypatch.setattr(adapter, "persist_requirement_from_ctx",
                        lambda engine, operator="": hits.append((engine.get("opportunity_id"), operator)))
    node = plugins._FillNode()
    node.wire_result({"ext": dict(EXT), "opportunity_id": OPP, "operator_name": "张三"}, {})
    assert hits == [(OPP, "张三")]
    node.wire_result({"ext": None, "opportunity_id": OPP}, {})
    assert hits == [(OPP, "张三")]


# ── B3 机型/配件落定写方案配置草稿 ───────────────────────────────────

def test_scheme_progress_writes_draft_only_in_draft_mode(monkeypatch):
    """B3：用唯一组装口径（build_plans）组出 L6+KP 段原地写草稿；非 draft 只读不写。"""
    monkeypatch.setattr(skill_node_runtime, "build_plans", lambda ctx, cfg: [PLAN])
    seen: dict = {}

    def fake_save(opp, configs, created_by="", name=None, config_relation="compose",
                  primary_config=""):
        seen.update(opp=opp, configs=configs, by=created_by, name=name,
                    rel=config_relation, primary=primary_config)
        return {"id": "scheme-1"}

    monkeypatch.setattr(adapter, "save_bom_scheme_draft", fake_save)
    ctx = {"write_mode": "draft", "opportunity_id": OPP, "ext": dict(EXT),
           "flow_configs": {"compose": {}}}
    assert adapter.save_scheme_progress_from_ctx(ctx, "张三") == {"id": "scheme-1"}
    assert seen["opp"] == OPP and seen["by"] == "张三"
    cfg = seen["configs"][0]
    assert cfg["name"] == "CFG1" and cfg["qty"] == 2
    assert cfg["l6_rows"] and cfg["kp_rows"][0]["catalogue"] == "MEM-64G"
    # 无 plans → 不写空方案
    monkeypatch.setattr(skill_node_runtime, "build_plans", lambda ctx, cfg: [])
    assert adapter.save_scheme_progress_from_ctx(ctx, "张三") is None
    # 非 draft → 一个写函数都不碰
    monkeypatch.setattr(skill_node_runtime, "build_plans", lambda ctx, cfg: [PLAN])
    assert adapter.save_scheme_progress_from_ctx(
        {"write_mode": "preview", "opportunity_id": OPP, "ext": dict(EXT)}, "") is None


# ── B4 交付原地提交那张草稿 ─────────────────────────────────────────

def test_delivery_submits_the_same_draft_in_place(monkeypatch):
    """B4：交付 = 提交对话期间那张草稿（用 save 返回的 version），不再新开一版。"""
    recorded: dict = {}
    monkeypatch.setattr(adapter, "_attach_entity_card", lambda *a, **k: None)
    monkeypatch.setattr(adapter, "save_requirement_draft",
                        lambda opp, slots, text, created_by="": {"version": 7})

    def fake_submit(opp, version, created_by=""):
        recorded.update(opp=opp, version=version, by=created_by)
        return {"version": version, "status": "current"}

    monkeypatch.setattr(adapter, "submit_requirement_draft", fake_submit)
    monkeypatch.setattr(adapter, "save_bom_scheme_draft",
                        lambda opp, configs, by="", name=None, rel="compose", primary="": {
                            "id": "bom-1", "configs": configs})
    ctx = {"write_mode": "draft", "opportunity_id": OPP, "ext": dict(EXT),
           "requirement_text": "客户原话", "plans": [PLAN]}
    out = adapter.persist_requirement_and_bom_from_ctx(ctx, "张三")
    assert recorded == {"opp": OPP, "version": 7, "by": "张三"}
    assert out["id"] == "bom-1"
    assert out["configs"][0]["l6_rows"] and out["configs"][0]["kp_rows"]
    # 只看代码引用（文档里可以提这个名字），确认交付路径不再新开版本。
    tree = ast.parse(inspect.getsource(adapter.persist_requirement_and_bom_from_ctx))
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} | {
        n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "initiate_requirement" not in used


# ── 贯通：写模式一路传到引擎 ctx，draft 才播种 ───────────────────────

def test_write_mode_flows_through_the_turn_stack(monkeypatch):
    """write_mode 从入口一路传到引擎 ctx；只有 draft 才从草稿播种 ext。"""
    from app.services import skill_chat
    from app.services.colleague_turn_runners import _run_skill_chat
    for fn in (skill_turn_engine.run_skill_agent_turn, skill_chat.handle_skill_chat_turn,
               _run_skill_chat):
        assert "write_mode" in inspect.signature(fn).parameters, fn

    seeded: list = []
    monkeypatch.setattr(adapter, "seed_ext_from_requirement_draft",
                        lambda ext, opp: seeded.append(opp) or True)

    def _runtime(write_mode, opportunity_id):
        return skill_turn_engine._SkillTurnRuntime(
            thread_id="t_seed", role_key="tech", persona="p", full_text="f",
            history=[], ext=dict(EXT), mem={}, flow={},
            opportunity_id=opportunity_id, write_mode=write_mode)

    ctx = contextvars.copy_context()  # TOOL_CTX 是 ContextVar：在副本里跑，不污染别的测试
    rt = _runtime("draft", OPP)
    ctx.run(rt._prepare)
    assert rt.engine.get("write_mode") == "draft"
    assert seeded == [OPP]
    seeded.clear()
    rt2 = _runtime("preview", OPP)
    ctx.run(rt2._prepare)
    assert rt2.engine.get("write_mode") == "preview"
    assert seeded == []
