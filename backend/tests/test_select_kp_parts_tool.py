# -*- coding: utf-8 -*-
"""配件选配冒烟回归：登记行在库内无精确对应时由唯一大脑在 kp_reason 节点回合锁定真实料号。

select_kp_parts 是任务期工具（B2 接地，2026-09-12 去台账）：落料凭据 = 料号名，
服务端按「类目 + 名称」回库精确核对（库里没有业务料号），核不上就拒（no_such_part）；
选定按行身份（row_id；无身份的行退回 类目|描述）持久化本节点私有状态 kp_reason.picks，
客户改行自动失配作废。本文件只验证：任务期闸门、逐行库内核对、行键持久、
apply_kp_picks 落地、目标层「AI 反问」策略消费与大脑回合收敛语义；
不发起真实模型请求（run_stream_chat_loop 打桩）、不碰数据库（库内料号用 _INDEX 顶替）。
"""
import os
import sys
import pytest

from app.services import skill_tool_context
from app.services import skill_tools_kp
from app.services import skill_tools_misc
from app.services import skill_tools_select
from app.services import skill_turn_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 库内料号（本文件的假库）：落料时按「类目 + 名称」在这里核对；part_id 只是行号
_INDEX = {
    "cpu": {
        "101": {"part_id": "101", "name": "兆芯 KH-50000 32核", "price": 4500.0, "currency": "RMB"},
        "兆芯 kh-50000 32核": {"part_id": "101", "name": "兆芯 KH-50000 32核", "price": 4500.0, "currency": "RMB"},
        "102": {"part_id": "102", "name": "兆芯 KH-40000 16核", "price": 2800.0, "currency": "RMB"},
        "兆芯 kh-40000 16核": {"part_id": "102", "name": "兆芯 KH-40000 16核", "price": 2800.0, "currency": "RMB"},
    },
    "memory": {
        "201": {"part_id": "201", "name": "三星 64GB DDR5 5600", "price": 1800.0, "currency": "RMB"},
        "三星 64gb ddr5 5600": {"part_id": "201", "name": "三星 64GB DDR5 5600", "price": 1800.0, "currency": "RMB"},
    },
}


@pytest.fixture(autouse=True)
def _fake_part_library(monkeypatch):
    """select_parts 落料要回库核对：本文件不碰 DB，用 _INDEX 当库（名称忽略大小写与空格）。"""
    import re as _re

    from app.services import data_tools

    def _rows(cat: str) -> list:
        out, seen = [], set()
        for ent in (_INDEX.get(str(cat or "").strip().lower()) or {}).values():
            pid = str(ent.get("part_id") or "")
            if not pid or pid in seen:
                continue
            seen.add(pid)
            out.append({"part_id": pid, "name": str(ent.get("name") or ""),
                        "category": str(cat), "price": ent.get("price"),
                        "currency": str(ent.get("currency") or "RMB"),
                        "specs": dict(ent.get("specs") or {})})
        return out

    def _by_name(category, name, *, series="", price_ok=True, _repo=None):
        want = _re.sub(r"\s+", "", str(name or "")).lower()
        rows = [r for r in _rows(category)
                if _re.sub(r"\s+", "", r["name"]).lower() == want]
        return {"ok": True, "category": category, "db_category": category,
                "source": "kp_library/name_lookup", "rows": rows, "total": len(rows)}

    def _by_id(part_id, *, price_ok=True, _repo=None):
        pid = str(part_id or "").strip()
        for c in _INDEX:
            for r in _rows(c):
                if r["part_id"] == pid:
                    return {"ok": True, "source": "kp_library/id_lookup",
                            "rows": [r], "total": 1}
        return {"ok": True, "source": "kp_library/id_lookup", "rows": [], "total": 0}

    monkeypatch.setattr(data_tools, "lookup_parts_by_name", _by_name)
    monkeypatch.setattr(data_tools, "lookup_part_by_id", _by_id)


def _picks(engine: dict) -> dict:
    """kp_reason 节点私有状态里的已锁定行（节点隔离：不再挂在共享 ext 上）。"""
    return ((engine.get("node_state") or {}).get("kp_reason") or {}).get("picks") or {}


def _recs(engine: dict) -> dict:
    """kp_reason 节点私有状态里的 AI 建议料（待客户确认，未落地）。"""
    return ((engine.get("node_state") or {}).get("kp_reason") or {}).get("recommend") or {}


def _call_select(args: dict, *, task_active: bool = True, ext=None, saved=None,
                 rows=None, required_cats=None, engine=None, caps=None) -> dict:
    from app.services import skill_chat
    # ext/engine 都不复制：工具必须原地写引擎共享的同一对象（副本会丢落表，同 fill 的实测坑）
    if saved is None:
        saved = {}
    if engine is None:
        engine = {}
    skill_tool_context.TOOL_CTX.set({
        "ext": ext if ext is not None else {}, "task_active": task_active,
        "engine": engine,
        "kp_rows_ctx": rows if rows is not None else [
            {"row_key": "CPU|兆芯 50000 32核 处理器", "category": "CPU",
             "description": "兆芯 50000 32核 处理器", "qty": 1, "specified": True},
            {"row_key": "Memory|DDR5 64G", "category": "Memory",
             "description": "DDR5 64G", "qty": 1, "specified": True},
        ],
        "kp_required_cats": set(required_cats or []),
        "kp_baseline_caps": caps or {},
        "save": lambda: saved.update(done=True),
    })
    return skill_tools_select.tool_select_parts(args)


def test_select_parts_rejects_qty_over_machine_capability():
    """物理上限闸：机型登记 8 内存槽，qty=12 直接拒（qty_over_capacity）并要大脑
    换更大单条容量；qty=8 放行。无边界类目/未登记能力不设此闸。"""
    res = _call_select({"picks": [{"row": "Memory|DDR5 64G", "part_id": "201",
                                   "qty": 12, "reason": "r"}]},
                       caps={"max_dimm": 8})
    assert res["results"][0]["error"] == "qty_over_capacity"
    assert res["results"][0]["ok"] is False

    ok = _call_select({"picks": [{"row": "Memory|DDR5 64G", "part_id": "201",
                                  "qty": 8, "reason": "r"}]},
                      caps={"max_dimm": 8})
    assert ok["results"][0].get("ok") is True

    # 机型没登记内存槽数（上下文无 caps）→ 不拦（缺数据不设闸）
    no_cap = _call_select({"picks": [{"row": "Memory|DDR5 64G", "part_id": "201",
                                      "qty": 12, "reason": "r"}]})
    assert no_cap["results"][0].get("ok") is True


def test_select_kp_parts_blocked_before_task():
    """进任务前工具不可用：普通对话没有配件锁定权。"""
    res = _call_select({"picks": [{"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101",
                                   "reason": "r"}]}, task_active=False)
    assert res.get("ok") is False
    assert res.get("error") == "task_not_active"


def test_select_kp_parts_empty_row_list_requires_explicit_new_row():
    """行清单为空不是死路：极模糊需求（登记表里没有部件行）时 AI=配置器仍要能声明要配的行。

    P3-3 契约（由代码强制，不是劝告句）：
      ① 解析不到 row_id 又没显式 new_row=true → row_unknown（不许靠措辞“认领”一行，也不许悄悄铸行）；
      ② new_row=true 必须有 category + spec，只给类目名 → spec_required（不铸幽灵行）；
      ③ 声明成功也别想凭空锁料号：料号名在库里核不上 → no_such_part。
    """
    res = _call_select({"picks": [{"row": "x", "reason": "r"}]}, rows=[])
    assert res.get("error") != "no_unmatched_rows", "空行清单不该是工具级拒绝，而是逐行判定"
    assert [r["ok"] for r in res["results"]] == [False]
    assert res["results"][0]["error"] == "row_unknown"

    res_cat = _call_select({"picks": [{"row": "GPU", "category": "GPU",
                                       "new_row": True, "reason": "r"}]},
                           rows=[], engine={})
    assert res_cat["results"][0]["error"] == "spec_required", "只给类目名不铸行"

    res_spec = _call_select({"picks": [{"row": "NVIDIA H100 80G", "spec": "NVIDIA H100 80G",
                                        "new_row": True, "reason": "r"}]},
                            rows=[], engine={})
    assert res_spec["results"][0]["error"] == "category_required", "新增行必须给出类目"

    engine: dict = {}
    res2 = _call_select({"picks": [{"row": "GPU|NVIDIA H100 80G", "new_row": True,
                                    "name": "任意料", "reason": "近替代"}]},
                        rows=[], engine=engine)
    assert res2["results"][0]["error"] == "no_such_part", "新行也要落库内真实存在的料号名"
    assert ((engine.get("node_state") or {}).get("kp_reason") or {}).get("config"), \
        "声明的新行要落进本节点私有状态（kp_config），不能丢"


def test_select_kp_parts_requires_args():
    res = _call_select({})
    assert res.get("ok") is False
    assert res.get("error") == "invalid_args"


def test_select_kp_parts_locks_pool_members_in_batch():
    """批量：part_id 精确命中 / name 忽略大小写命中 → 行键持久化 ext.kp_picks 并 save。"""
    ext, saved, engine = {}, {}, {}
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "reason": "核数一致"},
        {"row": "Memory|DDR5 64G", "name": "三星 64GB DDR5 5600", "reason": "容量匹配"},
    ]}, ext=ext, saved=saved, engine=engine)
    assert res.get("ok") is True
    assert [r["ok"] for r in res["results"]] == [True, True]
    assert _picks(engine)["CPU|兆芯 50000 32核 处理器"]["name"] == "兆芯 KH-50000 32核"
    assert _picks(engine)["CPU|兆芯 50000 32核 处理器"]["price"] == 4500.0
    assert _picks(engine)["Memory|DDR5 64G"]["part_id"] == "201"
    assert "kp_picks" not in ext, "节点状态不得再写进共享 ext"
    assert saved.get("done") is True


def test_select_kp_parts_partial_batch_and_out_of_pool():
    """库内没有这个料号 → 拒绝并回显原因；同批合法行仍落定（部分成功不整批作废）。"""
    ext, engine = {}, {}
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "name": "Intel Xeon 8480", "reason": "r"},
        {"row": "Memory|DDR5 64G", "part_id": "201", "reason": "ok"},
        {"row": "不存在的行键", "part_id": "1", "reason": "r"},
    ]}, ext=ext, engine=engine)
    assert res.get("ok") is False          # 有失败行 → 整体 not ok（触发大脑重试）
    by_row = {r["row"]: r for r in res["results"]}
    assert by_row["CPU|兆芯 50000 32核 处理器"]["error"] == "no_such_part"
    assert "Intel Xeon 8480" in by_row["CPU|兆芯 50000 32核 处理器"]["message"]
    assert by_row["不存在的行键"]["error"] == "row_unknown"
    assert by_row["Memory|DDR5 64G"]["ok"] is True
    assert list(_picks(engine).keys()) == ["Memory|DDR5 64G"]


def test_select_kp_parts_required_unspecified_records_recommendation():
    """必填类目且客户未明确登记（specified=False）：只登记推荐，不落地为锁定，须调 ask_user 确认。"""
    ext, saved, engine = {}, {}, {}
    rows = [{"row_key": "CPU|CPU", "category": "CPU", "description": "CPU",
             "qty": 1, "specified": False}]
    res = _call_select({"picks": [
        {"row": "CPU|CPU", "part_id": "101", "qty": 2, "reason": "核数一致"}]},
        ext=ext, saved=saved, required_cats=["CPU"], rows=rows, engine=engine)
    assert res.get("ok") is True
    assert res["results"][0].get("ok") is True
    assert res["results"][0].get("recommended") is not None
    assert not _picks(engine), "未登记具体型号的必填行不得落地为已锁定行"
    rec = _recs(engine)["CPU|CPU"]
    assert rec["name"] == "兆芯 KH-50000 32核"
    assert rec["qty"] == 2
    assert saved.get("done") is True


def test_select_kp_parts_required_specified_still_locks():
    """必填类目但客户已明确登记具体型号（specified=True）：直接锁定真实料号。"""
    ext, saved, engine = {}, {}, {}
    rows = [{"row_key": "CPU|兆芯 50000 32核 处理器", "category": "CPU",
             "description": "兆芯 50000 32核 处理器", "qty": 1, "specified": True}]
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "qty": 2, "reason": "核数一致"}]},
        ext=ext, saved=saved, required_cats=["CPU"], rows=rows, engine=engine)
    assert res.get("ok") is True
    assert res["results"][0].get("selected") is not None
    assert _picks(engine)["CPU|兆芯 50000 32核 处理器"]["name"] == "兆芯 KH-50000 32核"
    assert _picks(engine)["CPU|兆芯 50000 32核 处理器"]["qty"] == 2
    assert saved.get("done") is True


def test_select_kp_parts_non_ask_still_locks():
    """非反问类目照旧落地锁定（行为回归）。"""
    ext, engine = {}, {}
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "reason": "r"}]},
        ext=ext, required_cats=["Memory"], engine=engine)
    assert res.get("ok") is True
    assert _picks(engine)["CPU|兆芯 50000 32核 处理器"]["name"] == "兆芯 KH-50000 32核"


def test_kp_field_ask_policy_from_target_layer():
    """目标层「AI 反问」开关：kp_parts.ask=true → 大脑不代选（占位行交客户）；缺省 False。"""
    from app.services.skill_plan_runtime import _artifact_field_ask
    assert _artifact_field_ask({}, "kp_parts") is False
    on = {"target": {"artifacts": [{"fields": [
        {"key": "kp_parts", "label": "配件表", "ask": True}]}]}}
    assert _artifact_field_ask(on, "kp_parts") is True
    # 旧消费方不受泛化影响
    from app.services.skill_plan_runtime import _model_field_ask
    model_on = {"target": {"artifacts": [{"fields": [
        {"key": "server_model", "label": "服务器型号", "ask": True}]}]}}
    assert _model_field_ask(model_on) is True
    assert _model_field_ask(on) is False


def test_apply_kp_picks_replaces_placeholders():
    """占位行 + kp_picks → 真实料号行（数量保持、快照价格落行）；行键失配保持占位。"""
    from app.services.part_selector import apply_kp_picks, requirement_rows_to_parts
    kp_rows = [{"part_category": "CPU", "description": "兆芯 50000 32核 处理器", "qty": 2}]
    parts = requirement_rows_to_parts(kp_rows)
    assert parts[0]["unmatched"] is True
    picks = {"CPU|兆芯 50000 32核 处理器": {
        "part_id": "101", "name": "兆芯 KH-50000 32核", "price": 4500.0,
        "currency": "RMB", "reason": "核数一致"}}
    out, applied = apply_kp_picks(parts, picks)
    assert applied == 1
    row = out[0]
    assert row["unmatched"] is False
    assert row["pn"] == "兆芯 KH-50000 32核"
    assert row["unit_price"] == 4500.0
    assert row["qty"] == 2
    assert "核数一致" in row["grounded_spec"]
    # 客户改过描述 → 行键失配，pick 自动作废，保持占位白盒
    out2, applied2 = apply_kp_picks(parts, {"CPU|客户改口后的描述": picks[
        "CPU|兆芯 50000 32核 处理器"]})
    assert applied2 == 0
    assert out2[0]["unmatched"] is True


def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_kp_pick_lands_in_node_state_not_shared_ext():
    """选定落本节点分区：既不写共享 ext（登记表冻结），也不写被弃用的旧副本。"""
    ext, engine = {"server_type": "通用计算服务器"}, {}
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 32核 处理器", "part_id": "101", "reason": "核数一致"}]},
        ext=ext, engine=engine)
    assert res.get("ok") is True
    assert _picks(engine)["CPU|兆芯 50000 32核 处理器"]["name"] == "兆芯 KH-50000 32核"
    assert "kp_picks" not in ext and not ext.get("server_model"), "不许往共享 ext 写节点工作状态"


def test_brain_attempts_retries_rejected_rows_then_settles():
    """行被池校验拒绝 → 真实返回喂回重试（≤3 次），失败的行不落定；末轮照样收口。"""
    from unittest.mock import patch
    from app.services import skill_chat

    calls = {"n": 0}

    async def fake_loop(msg, **kwargs):
        calls["n"] += 1
        res = skill_tools_select.tool_select_parts({"picks": [
            {"row": "CPU|兆芯 50000 32核 处理器", "name": "Not-In-Pool", "reason": "r"}]})
        return {"tool_calls_log": [{"name": "select_kp_parts", "result": res}]}

    async def settle(result):
        return {"action": "retry", "feedback": "bad"}

    engine = {"node_state": {}}
    skill_tool_context.TOOL_CTX.set({"ext": {}, "task_active": True, "engine": engine,
                             "kp_rows_ctx": [], "save": lambda: None})
    with patch.object(skill_turn_engine, "run_stream_chat_loop", fake_loop):
        _result, action = _run(skill_turn_engine.run_brain_attempts("客户消息", loop_kwargs={}, settle=settle))
    assert calls["n"] == 3, "工具被拒最多重试 3 次"
    assert not _picks(engine), "被拒的行不得落定"
    assert action == "retry"


# ── 2026-09-05 大脑提问卡（ask_user）+ 已锁定行上下文 ─────────────────────

def _call_ask(args: dict, *, task_active: bool = True, asks=None) -> dict:
    from app.services import skill_chat
    if asks is None:
        asks = []
    skill_tool_context.TOOL_CTX.set({"ext": {}, "task_active": task_active, "brain_asks": asks})
    return skill_tools_misc.tool_ask_user(args)


def test_ask_user_blocked_before_task():
    res = _call_ask({"question": "q", "options": [{"label": "a"}]}, task_active=False)
    assert res.get("ok") is False and res.get("error") == "task_not_active"


def test_ask_user_registers_structured_question():
    asks: list = []
    res = _call_ask({"question": "1.92T 用哪种接口？",
                     "options": [{"label": "SATA"}, {"label": "NVMe", "description": "更快"}],
                     "row": "HDD/SSD|1.92T"}, asks=asks)
    assert res.get("ok") is True and len(asks) == 1
    ask = asks[0]
    assert ask["row"] == "HDD/SSD|1.92T"
    assert [o["label"] for o in ask["options"]] == ["SATA", "NVMe"]


def test_ask_user_one_card_per_turn():
    """一回合一卡（与缺口卡单焦点序列同口径）：已有待答问题再调即拒绝。"""
    asks = [{"question": "先答这个", "options": [{"label": "x"}], "row": ""}]
    res = _call_ask({"question": "又来", "options": [{"label": "y"}]}, asks=asks)
    assert res.get("ok") is False and res.get("error") == "one_ask_per_turn"
    assert len(asks) == 1


def test_ask_user_rejects_invalid_shapes():
    assert _call_ask({"options": [{"label": "a"}]}).get("error") == "invalid_args"
    assert _call_ask({"question": "q", "options": []}).get("error") == "invalid_args"
    assert _call_ask({"question": "q", "options": [{"desc": "无label"}]}).get("error") == "invalid_args"


def test_kp_bridge_ctx_publishes_rows_with_answers_only():
    """节点插件把待选型行清单（row_key/类目/描述/数量 + 客户回答）桥接进工具上下文。

    已锁定行不再下发；库内编码（part_id）不进提示词——防幻觉靠事实清单，不靠转译。
    """
    from app.services.skill_node_plugins import plugin_for
    from app.services.skill_node_state import add_row_answer
    engine = {
        "ext": {"kp_rows": [{"part_category": "CPU", "description": "兆芯 50000 32核 处理器", "qty": 2}]},
        "kp_parts": [
            {"category": "Memory", "request_spec": "DDR5 64G", "qty": 8,
             "name": "三星 64GB DDR5 5600", "unmatched": False},
            {"category": "HDD/SSD", "request_spec": "1.92T", "qty": 1, "unmatched": True},
        ],
        "flow_configs": {},
    }
    add_row_answer(engine, "HDD/SSD|1.92T", "SATA 接口")
    ctx: dict = {}
    plugin_for("kp_reason").bridge_ctx(engine, ctx)
    rows = ctx.get("kp_rows_ctx") or []
    assert [r["category"] for r in rows] == ["HDD/SSD"], "已锁定行不再下发（无需再处理）"
    assert rows[0]["row_key"] == "HDD/SSD|1.92T"
    assert rows[0]["answer"] == "SATA 接口", "客户回答叠加成该行的检索文本"
    assert all("part_id" not in r for r in rows), "库内编码不进提示词"
    assert "kp_rows_ctx" in ctx


def test_kp_row_merge_signal_records_answer_without_touching_frozen_doc():
    """行绑定的提问卡点击直传：客户回答记进本节点私有状态，登记表（冻结文档）一字不改。

    行键取自登记原文 → 补一句话不会让该行已锁定的选型失配作废（旧实现改描述=改键=丢选型）。
    """
    from app.services.slot_contract import apply_structured_slots
    from app.services.skill_node_state import KP_PICKS, KP_ROW_ANSWERS
    ext = {"kp_rows": [{"part_category": "HDD/SSD", "description": "1.92T", "qty": 1}]}
    kp_st = {KP_PICKS: {"HDD/SSD|1.92T": {"name": "旧选件", "price": 1}}}
    notes = apply_structured_slots(
        ext, {"kp_row_merge": {"row": "HDD/SSD|1.92T", "answer": "SATA 接口"}}, "",
        kp_state=kp_st)
    assert notes and "SATA 接口" in notes[0]
    # 上游冻结文档只读：描述原样，行键原样，旧 pick 仍然有效
    assert ext["kp_rows"][0]["description"] == "1.92T"
    assert kp_st[KP_PICKS]["HDD/SSD|1.92T"]["name"] == "旧选件"
    # 回答落在本节点分区，按登记行键可查
    assert kp_st[KP_ROW_ANSWERS]["HDD/SSD|1.92T"] == ["SATA 接口"]
    # 行键不存在 → 静默无操作
    notes2 = apply_structured_slots(
        ext, {"kp_row_merge": {"row": "不存在的行", "answer": "x"}}, "", kp_state=kp_st)
    assert not [n for n in notes2 if "补充" in n]
    assert "不存在的行" not in kp_st[KP_ROW_ANSWERS]


def test_search_kp_parts_offset_and_response_format(monkeypatch):
    """检索工具分页 + concise/detailed：offset 跳过、truncated/next_offset、concise 裁剪规格。"""
    from app.services import data_tools, skill_chat, part_search
    full = [{"part_id": str(i), "name": f"CPU-{i}", "price": float(i), "currency": "RMB",
             "specs": {f"k{j}": f"v{j}" for j in range(12)}} for i in range(1, 6)]
    def fake_hybrid(category, *, text="", spec_filters=None, series="", limit=8,
                     offset=0, price_ok=True, mode="query", _repo=None):
        tot = len(full)
        page = full[offset:offset + limit]
        return {"ok": True, "category": category, "rows": page, "total": tot,
                "truncated": tot > offset + len(page), "offset": offset,
                "next_offset": (offset + len(page) if tot > offset + len(page) else None),
                "source": "test"}
    monkeypatch.setattr(part_search, "hybrid_search", fake_hybrid)
    saved = {}
    skill_tool_context.TOOL_CTX.set({"ext": {}, "task_active": True, "kp_series": "",
                              "price_ok": True,
                              "save": lambda: saved.update(done=True)})
    res = skill_tools_kp.tool_query_parts({"category": "CPU", "offset": 2, "limit": 2,
                                           "response_format": "concise"})
    assert res["ok"] is True
    assert [r["name"] for r in res["results"]] == ["CPU-3", "CPU-4"]
    assert res["offset"] == 2
    assert res["total"] == 5
    assert res["truncated"] is True
    assert res["next_offset"] == 4
    assert all(len(r["specs"]) <= 8 for r in res["results"]), "concise 应裁剪 specs"
    res2 = skill_tools_kp.tool_query_parts({"category": "CPU", "offset": 4, "limit": 2,
                                            "response_format": "detailed"})
    assert [r["name"] for r in res2["results"]] == ["CPU-5"]
    assert res2["truncated"] is False
    assert res2["next_offset"] is None
    assert len(res2["results"][0]["specs"]) == 12, "detailed 应保留完整 specs"



def test_search_kp_parts_row_batch(monkeypatch):
    """rows 批量按行召回：一次覆盖多行，每行用自己的类目+行描述去库召回候选，
    返回紧凑批量视图；未变更的单类目检索路径不受影响。"""
    from app.services import data_tools, skill_chat, part_search
    by_cat = {
        "CPU": [{"part_id": "101", "name": "兆芯 KH-50000 96C", "price": 9000.0,
                 "currency": "RMB", "specs": {"core": "96C", "ghz": "2.2"}}],
        "Memory": [{"part_id": "201", "name": "三星 64GB DDR5 5600", "price": 1800.0,
                    "currency": "RMB", "specs": {"cap": "64GB", "type": "DDR5"}}],
        "HDD/SSD": [],
    }

    def fake_hybrid(category, *, text="", spec_filters=None, series="", limit=30,
                     offset=0, price_ok=True, mode="query", _repo=None):
        rows = by_cat.get(category, [])
        return {"ok": True, "category": category, "rows": rows, "total": len(rows),
                "truncated": False, "source": "test_recall"}

    monkeypatch.setattr(part_search, "hybrid_search", fake_hybrid)
    saved = {}
    skill_tool_context.TOOL_CTX.set({
        "ext": {}, "task_active": True, "kp_series": "",
        "price_ok": True,
        "kp_rows_ctx": [
            {"row_key": "CPU|兆芯 50000 96C", "row_id": "r1", "category": "CPU",
             "description": "兆芯 50000 96C", "qty": 2, "specified": True},
            {"row_key": "Memory|DDR5 64G", "row_id": "r2", "category": "Memory",
             "description": "DDR5 64G", "qty": 12, "specified": True},
            {"row_key": "HDD/SSD|1.92T", "row_id": "r3", "category": "HDD/SSD",
             "description": "1.92T", "qty": 1, "specified": True},
        ],
        "save": lambda: saved.update(done=True),
    })
    res = skill_tools_kp.tool_query_parts({"rows": "all", "limit": 6})
    assert res["ok"] is True
    assert res["mode"] == "row_batch"
    b = {x["row_key"]: x for x in res["batch"]}
    assert len(res["batch"]) == 3
    assert b["CPU|兆芯 50000 96C"]["candidates"][0]["name"] == "兆芯 KH-50000 96C"
    assert b["CPU|兆芯 50000 96C"]["candidates"][0]["part_id"] == "101"
    assert b["Memory|DDR5 64G"]["candidates"][0]["part_id"] == "201"
    # 零召回行明示原因，不退化类目全量
    assert b["HDD/SSD|1.92T"]["candidates"] == []
    assert "零命中" in b["HDD/SSD|1.92T"]["reason"]
    # 检索不留台账（2026-09-12 去索引）：召回结果直接可用，落料时按料号名回库核对
    assert "kp_search_index" not in (skill_tool_context.TOOL_CTX.get() or {})
    assert saved.get("done") is True
    # 显式行 id 过滤：只召回指定行
    res2 = skill_tools_kp.tool_query_parts({"rows": ["r2"], "limit": 6})
    assert [x["row_key"] for x in res2["batch"]] == ["Memory|DDR5 64G"]






def test_select_kp_parts_specified_substitute_requires_ask():
    """客户已明确登记具体规格但库内无精确料（AI 标 substitute=true）→ 只登记推荐，不落地锁定，须反问。

    运行时反问判定（2026-09-09 定调）：已登记具体规格 + 库内有精确料 → 直接锁定不反问；
    已登记具体规格但库内无精确料（只能近替代）→ 必须反问客户选替代/缺失处理，不许静默锁替代料。
    """
    ext, saved, engine = {}, {}, {}
    rows = [{"row_key": "CPU|兆芯 50000 96C", "category": "CPU",
             "description": "兆芯 50000 96C", "qty": 2, "specified": True}]
    res = _call_select({"picks": [
        {"row": "CPU|兆芯 50000 96C", "part_id": "101", "qty": 2, "substitute": True,
         "reason": "库内无 96C 精确料，近替代"}]},
        ext=ext, saved=saved, rows=rows, engine=engine)
    assert res.get("ok") is True
    assert res["results"][0].get("recommended") is not None
    assert "selected" not in res["results"][0]
    assert not _picks(engine), "已登记但库无精确料的必填行不得静默锁定替代"
    rec = _recs(engine)["CPU|兆芯 50000 96C"]
    assert rec["name"] == "兆芯 KH-50000 32核"
    assert rec["qty"] == 2
    assert saved.get("done") is True
