# -*- coding: utf-8 -*-
"""open_part / open_row 只读钻取回归（Agentic Search 的 open 在配件检索上的落地）。

背景（2026-09-12 去台账）：检索侧此前只有「广搜」（query_parts）、没有「点开看」——模型要看全
某颗料的规格、或回看某一行当前状态与库内候选，唯一手段是**再发一次广搜**。Mistral Agentic
Search 的对照实验指出：这种 repeated broad search 既费 token 又降准确率，定向钻取
（open/navigate/read/grep）才是质量与效率的双升点（导航 +6.7~8.7pp、token −24%~34%）。

本文件锁住两条不变量：
1. 钻取**只读**：open_part/open_row 只读库与上下文，不写任何状态、不留任何台账；
2. 钻取**说真话**：库里没有就报 no_such_part（绝不凭记忆报料号）、候选零召回就如实说零召回。

全 mock（不碰 DB / LLM），可 pytest 跑。
"""
import os
import sys

from app.services import data_tools, skill_tool_context, skill_tools_open
from app.services import part_recall as part_recall_module
from app.services import part_selector

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 10 个规格键（concise 只给前 8 个）＋一个超过 28 字符的值（concise 会截断）
_FULL_SPECS = {
    "Capacity": "64GB", "Type": "DDR5", "Speed": "5600MHz", "Rank": "2R",
    "Voltage": "1.1V", "ECC": "Yes", "Form": "RDIMM", "Vendor": "Samsung",
    "PN": "M321R8GA0BB0-CQK-EXTRA-LONG-SUFFIX-12345", "Temp": "0-85C",
}

# 库内料号（本文件的假库）：id 只是行号；打开与落料都按「类目 + 名称」核对
_LIB = {
    "Memory": [{"id": 201, "model": "三星 64GB DDR5 5600", "applicable": {},
                "price": 1800.0, "currency": "RMB", "specs": dict(_FULL_SPECS)}],
    "Cable": [{"id": 301, "model": "通用电源线", "applicable": {},
               "price": 20.0, "currency": "RMB", "specs": {}}],
    # 同名跨类目：回候选让 AI 确认，不猜
    "GPU": [{"id": 250, "model": "NVIDIA H100 80G", "applicable": {},
             "price": 210000.0, "currency": "RMB", "specs": {"Memory": "80GB"}}],
    "NIC": [{"id": 251, "model": "NVIDIA H100 80G", "applicable": {},
             "price": 210000.0, "currency": "RMB", "specs": {"Memory": "80GB"}}],
}

_ROW = {"row_key": "Memory|DDR5 64G", "row_id": "kp-abc12345", "category": "Memory",
        "description": "DDR5 64G", "qty": 2, "specified": True}


class _FakeRepo:
    """假配件库：只实现回库核对/类目索引用到的两个方法。"""

    def __init__(self, *_a, **_k):
        pass

    def get_categories(self):
        return [{"category": c, "id": i, "count": len(v)}
                for i, (c, v) in enumerate(_LIB.items())]

    def get_by_category_with_specs(self, category):
        return [dict(r) for r in _LIB.get(category, [])]

    def close(self):
        pass


def _fake_recall(rows_by_cat):
    def _recall(category, *, desc="", series="", limit=30, price_ok=True, _repo=None):
        rows = list((rows_by_cat or {}).get(category, []))
        return {"ok": True, "category": category, "rows": rows[:limit],
                "total": len(rows), "truncated": False, "source": "test_recall"}

    return _recall


def _wire(monkeypatch, *, rows_by_cat=None, task_active=True, rows=None, engine=None,
          price_ok=True) -> dict:
    """把回库核对与候选召回换成假库（不碰 DB），并注入工具上下文。"""
    monkeypatch.setattr(part_selector, "KPRepository", _FakeRepo)
    monkeypatch.setattr(part_recall_module, "_category_aliases", lambda: {})
    monkeypatch.setattr(data_tools, "part_recall", _fake_recall(rows_by_cat))
    ctx = {"task_active": task_active,
           "engine": engine if engine is not None else {},
           "kp_rows_ctx": [_ROW] if rows is None else rows,
           "price_ok": price_ok,
           "save": lambda: None}
    skill_tool_context.TOOL_CTX.set(ctx)
    return ctx


# ── open_part ─────────────────────────────────────────────────────────

def test_open_part_blocked_before_task(monkeypatch):
    """进任务前不可用：普通对话没有读库料的通道。"""
    _wire(monkeypatch, task_active=False)
    res = skill_tools_open.tool_open_part({"part_id": "201"})
    assert res["ok"] is False and res["error"] == "task_not_active"


def test_open_part_needs_an_id(monkeypatch):
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_part({})
    assert res["ok"] is False and res["error"] == "invalid_args"


def test_open_part_returns_full_specs_not_the_concise_cut(monkeypatch):
    """concise 只给 8 键、值截 28 字符；open_part 给全量——这是「点开看」的全部意义。"""
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_part({"part_id": "201"})
    assert res["ok"] is True
    assert res["category"] == "Memory"
    assert res["name"] == "三星 64GB DDR5 5600"
    assert res["price"] == 1800.0
    assert res["spec_count"] == len(_FULL_SPECS) == 10 > 8
    assert set(res["specs"]) == set(_FULL_SPECS)
    assert res["specs"]["PN"] == _FULL_SPECS["PN"] and len(res["specs"]["PN"]) > 28


def test_open_part_accepts_the_part_name(monkeypatch):
    """按料号名打开（库里没有业务料号，名字才是凭据）；大小写与空格不影响核对。"""
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_part({"name": "三星 64gb  DDR5 5600"})
    assert res["ok"] is True and res["part_id"] == "201"


def test_open_part_hides_price_when_price_not_allowed(monkeypatch):
    _wire(monkeypatch, price_ok=False)
    res = skill_tools_open.tool_open_part({"part_id": "201"})
    assert res["ok"] is True and "price" not in res


def test_open_part_says_when_the_category_has_no_structured_specs(monkeypatch):
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_part({"part_id": "301"})
    assert res["ok"] is True and res["spec_count"] == 0
    assert "无结构规格" in res["message"]


def test_open_part_reports_a_name_that_is_not_in_the_library(monkeypatch):
    """库里没有就如实说没有（白盒：消息带上那个名字），不凭记忆报料号。"""
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_part({"name": "不存在的料号 X9"})
    assert res["ok"] is False and res["error"] == "no_such_part"
    assert "不存在的料号 X9" in res["message"]


def test_open_part_reports_an_unknown_category(monkeypatch):
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_part({"name": "三星 64GB DDR5 5600", "category": "CPU"})
    assert res["ok"] is False and res["error"] == "unknown_category"
    assert "CPU" in res["message"]


def test_open_part_asks_for_the_category_when_the_name_is_ambiguous(monkeypatch):
    """同名列在两个类目 → 回候选要求带 category，不替 AI 猜哪一颗。"""
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_part({"name": "NVIDIA H100 80G"})
    assert res["ok"] is False and res["error"] == "ambiguous_part"
    assert sorted(c["category"] for c in res["candidates"]) == ["GPU", "NIC"]
    ok = skill_tools_open.tool_open_part({"name": "NVIDIA H100 80G", "category": "GPU"})
    assert ok["ok"] is True and ok["category"] == "GPU" and ok["part_id"] == "250"


def test_open_part_is_read_only(monkeypatch):
    """钻取只读：上下文一个键都不多、也不留任何台账。"""
    ctx = _wire(monkeypatch)
    before = set(ctx)
    skill_tools_open.tool_open_part({"part_id": "201"})
    skill_tools_open.tool_open_part({"name": "不存在的料号 X9"})
    after = skill_tool_context.TOOL_CTX.get() or {}
    assert set(after) == before
    assert "kp_search_index" not in after


# ── open_row ──────────────────────────────────────────────────────────

def test_open_row_blocked_before_task(monkeypatch):
    _wire(monkeypatch, task_active=False)
    res = skill_tools_open.tool_open_row({"row_id": "kp-abc12345"})
    assert res["ok"] is False and res["error"] == "task_not_active"


def test_open_row_needs_an_id(monkeypatch):
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_row({})
    assert res["ok"] is False and res["error"] == "invalid_args"


def test_open_row_without_pending_rows(monkeypatch):
    _wire(monkeypatch, rows=[])
    res = skill_tools_open.tool_open_row({"row_id": "kp-abc12345"})
    assert res["ok"] is False and res["error"] == "no_unmatched_rows"


def test_open_row_unknown_id_lists_available_rows(monkeypatch):
    _wire(monkeypatch)
    res = skill_tools_open.tool_open_row({"row_id": "kp-nope"})
    assert res["ok"] is False and res["error"] == "row_unknown"
    assert res["available"] == [{"row_id": "kp-abc12345", "category": "Memory",
                                 "description": "DDR5 64G"}]


def test_open_row_lists_library_candidates_live(monkeypatch):
    """单行决策上下文：状态 + 库内按该行描述**实时**召回的候选（不是留底台账）。"""
    _wire(monkeypatch, rows_by_cat={"Memory": [
        {"part_id": "201", "name": "三星 64GB DDR5 5600", "price": 1800.0,
         "currency": "RMB", "specs": {"Type": "DDR5"}}]})
    res = skill_tools_open.tool_open_row({"row_id": "kp-abc12345"})
    assert res["ok"] is True
    assert res["category"] == "Memory" and res["qty"] == 2 and res["specified"] is True
    assert res["status"] == "待处理" and res["candidate_count"] == 1
    assert res["candidates"][0]["part_id"] == "201"
    assert res["candidates"][0]["specs_brief"]["Type"] == "DDR5"
    assert "select_parts" not in res["message"], "锁定动作属于左栏规则，不属于工具消息"


def test_open_row_says_zero_when_the_library_has_nothing(monkeypatch):
    _wire(monkeypatch, rows_by_cat={})
    res = skill_tools_open.tool_open_row({"row_id": "kp-abc12345"})
    assert res["ok"] is True and res["candidate_count"] == 0
    assert "零命中" in res["message"]


def test_open_row_reports_locked_row_with_its_part(monkeypatch):
    engine = {"node_state": {"kp_reason": {"picks": {
        "Memory|DDR5 64G": {"part_id": "201", "name": "三星 64GB DDR5 5600", "qty": 2}}}}}
    _wire(monkeypatch, engine=engine)
    res = skill_tools_open.tool_open_row({"row_id": "kp-abc12345"})
    assert res["status"] == "已锁定" and res["part"] == "三星 64GB DDR5 5600"
    assert "已锁定" in res["message"]


def test_open_row_reports_recommended_row(monkeypatch):
    engine = {"node_state": {"kp_reason": {"recommend": {
        "Memory|DDR5 64G": {"part_id": "201", "name": "三星 64GB DDR5 5600"}}}}}
    _wire(monkeypatch, engine=engine)
    res = skill_tools_open.tool_open_row({"row": "Memory|DDR5 64G"})
    assert res["status"] == "推荐待确认" and res["part"] == "三星 64GB DDR5 5600"


def test_open_row_is_read_only(monkeypatch):
    ctx = _wire(monkeypatch)
    before = set(ctx)
    skill_tools_open.tool_open_row({"row_id": "kp-abc12345"})
    after = skill_tool_context.TOOL_CTX.get() or {}
    assert set(after) == before
    assert "kp_search_index" not in after


# ── 注册面 ────────────────────────────────────────────────────────────

def test_inspect_parts_registered_but_not_mechanism_tool():
    """统一只读钻取工具：注册表里在，机制保底表里不在（关掉不影响三件套闭环）。"""
    from app.services.agent_tool_specs import build_tool_registry, registered_tool_ids
    from app.services.skill_plan_runtime import MECHANISM_TOOLS
    ids = registered_tool_ids()
    assert "inspect_parts" in ids
    reg = build_tool_registry({"enabled_tools": ["query_parts", "inspect_parts"]})
    assert reg.names() == ["query_parts", "inspect_parts"]
    assert "inspect_parts" not in set(MECHANISM_TOOLS["kp_reason"])


def test_capability_spec_declares_the_inspect_tool():
    from app.services.capability_spec import default_tools, validate_specs
    assert "inspect_parts" in default_tools("kp_reason")
    assert validate_specs() == []


def test_navigate_and_grep_actions_are_behind_the_same_tool():
    """category（navigate）/ grep 已收敛进同一个 inspect_parts，不再各自占注册表。"""
    from app.services.agent_tool_specs import build_tool_registry, registered_tool_ids
    from app.services.skill_plan_runtime import MECHANISM_TOOLS
    ids = registered_tool_ids()
    assert "open_category" not in ids and "grep_parts" not in ids
    assert "inspect_parts" in ids
    reg = build_tool_registry({"enabled_tools": ["query_parts", "inspect_parts"]})
    assert reg.names() == ["query_parts", "inspect_parts"]
    assert "inspect_parts" not in set(MECHANISM_TOOLS["kp_reason"])


def test_brain_note_summary_is_generic_and_records_drill_facts():
    """跨轮工作记录 = 通用渲染：引擎不认工具名，但实参/结果事实要原样带上。"""
    import json
    from app.services.skill_memory import _brain_note_summary
    txt = _brain_note_summary("kp_reason", {"tool_calls_log": [
        {"name": "open_category", "args": {"category": "NIC"},
         "result": {"ok": True, "parts_in_library": 71, "spec_field_count": 3}},
        {"name": "grep_parts", "args": {"pattern": "9361"},
         "result": {"ok": True, "total": 21}},
        {"name": "open_part", "args": {"part_id": "334"}, "result": {"ok": True}},
        {"name": "open_row", "args": {"row_id": "r1"},
         "result": {"ok": True, "candidate_count": 4, "status": "待处理"}},
    ]})
    note = json.loads(txt)
    calls = {c["tool"]: c for c in note["tool_calls"]}
    assert calls["open_category"]["args"]["category"] == "NIC"
    assert calls["open_category"]["result"]["parts_in_library"] == 71
    assert calls["grep_parts"]["args"]["pattern"] == "9361"
    assert calls["grep_parts"]["result"]["total"] == 21
    assert calls["open_part"]["ok"] is True
    assert calls["open_row"]["result"]["candidate_count"] == 4
    assert calls["open_row"]["result"]["status"] == "待处理"


def test_memory_layer_knows_no_tool_names():
    """合规守卫：记忆/编排层不得内置工具清单——工具知识只住在工具契约里。"""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    for rel in ("app/services/skill_memory.py", "app/services/skill_turn_engine.py",
                "app/services/skill_step_runtime.py"):
        src = (root / rel).read_text(encoding="utf-8")
        for name in ("query_parts", "select_parts", "open_part", "open_row",
                     "open_category", "grep_parts", "choose_model", "fill_requirement"):
            assert name not in src, f"{rel} 出现工具名 {name}"


def test_engine_carries_brain_notes_across_turns():
    """工作记忆跨轮承接：上一回合的工具轨迹本回合要可见，否则检索轨迹每轮归零（窗口 3 条）。"""
    from app.services.skill_turn_engine import _SkillTurnRuntime
    rt = _SkillTurnRuntime(thread_id="t", role_key="r", persona="p", full_text="x", history=[],
                           ext={}, mem={"brain_notes": ["旧1", "旧2", "旧3", "旧4"]},
                           flow={"node_configs": {}, "graph": {"nodes": [], "manual_rules": ""}})
    rt._prepare()
    assert rt.engine["brain_notes"] == ["旧2", "旧3", "旧4"]


# ── 统一入口 inspect_parts ────────────────────────────────────────────

def test_inspect_parts_dispatches_by_action(monkeypatch):
    _wire(monkeypatch)
    assert skill_tools_open.tool_inspect_parts({"action": "part", "part_id": "201"})["ok"] is True
    assert skill_tools_open.tool_inspect_parts({"action": "row", "row_id": "kp-abc12345"})["ok"] is True
    assert skill_tools_open.tool_inspect_parts({"action": "category", "category": "Memory"})["ok"] is True
    assert skill_tools_open.tool_inspect_parts({"action": "grep", "pattern": "DDR5"})["ok"] is True


def test_inspect_parts_requires_a_known_action(monkeypatch):
    _wire(monkeypatch)
    res = skill_tools_open.tool_inspect_parts({})
    assert res["ok"] is False and res["error"] == "invalid_args"
    bad = skill_tools_open.tool_inspect_parts({"action": "nope"})
    assert bad["ok"] is False and bad["error"] == "invalid_args"

