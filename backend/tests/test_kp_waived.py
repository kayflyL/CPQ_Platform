# -*- coding: utf-8 -*-
"""A（kp_waived）：行的第三个结局——库内无料、客户已知悉仍保持原需求。

语义边界（与 kp_absent 的区别）：
  * absent「不要这个类目」→ 整行丢弃，不进 BOM；
  * waived「要，但库里没有，客户认了」→ 行保留 + 标注，终检放行、组装照跑。
豁免只能来自客户拍板（点选带 waived 的 ask_user 选项），引擎不替客户认账。
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# 库内真实料号（本文件的假库，2026-09-12 去台账）：行卡候选当场按类目召回；
# 客户点名的型号按料号名精确核对（库里没有就只剩「保持原需求」这条出路）。
_LIBRARY = {
    "nic": [
        {"part_id": "701", "name": "X710 万兆双口", "price": 900.0, "currency": "RMB",
         "specs": {"Ports": "2", "Speed": "10G"}},
    ],
}


@pytest.fixture(autouse=True)
def _fake_part_library(monkeypatch):
    from app.services import data_tools

    def _recall(category, *, desc="", series="", limit=30, price_ok=True, _repo=None):
        rows = [dict(r) for r in (_LIBRARY.get(str(category or "").strip().lower()) or [])]
        return {"ok": True, "category": category, "db_category": category,
                "source": "part_recall", "rows": rows[:limit], "total": len(rows),
                "probes": [], "spec_keys": []}

    def _by_name(category, name, *, series="", price_ok=True, _repo=None):
        want = re.sub(r"\s+", "", str(name or "")).lower()
        rows = [r for r in (_LIBRARY.get(str(category or "").strip().lower()) or [])
                if re.sub(r"\s+", "", str(r.get("name") or "")).lower() == want]
        return {"ok": True, "category": category, "source": "kp_library/name_lookup",
                "rows": [dict(r) for r in rows], "total": len(rows)}

    monkeypatch.setattr(data_tools, "part_recall", _recall)
    monkeypatch.setattr(data_tools, "lookup_parts_by_name", _by_name)


def test_waived_option_signal_binds_the_row_key():
    """行卡上的 waived 选项 → kp_waived 行键信号（不带 pick、不带 absent）。"""
    from app.services.skill_plan_runtime import ask_option_signal
    sig = ask_option_signal("GPU|NVIDIA 4090", {"label": "保持原需求（库里没有）", "waived": True})
    assert sig == {"kp_waived": ["GPU|NVIDIA 4090"]}


def test_waived_row_is_kept_marked_and_not_counted_as_landed():
    """豁免行保留在配件表里（客户原话规格不丢）+ 标注状态，且不再算「未落地」。"""
    from app.services.part_selector import apply_kp_waived
    parts = [{"category": "GPU", "request_spec": "NVIDIA 4090", "unmatched": True, "qty": 2},
             {"category": "CPU", "request_spec": "兆芯50000", "unmatched": True, "qty": 2}]
    out, marked = apply_kp_waived(parts, ["GPU|NVIDIA 4090"])
    assert marked == 1
    gpu = next(p for p in out if p["category"] == "GPU")
    assert gpu["waived"] is True and gpu["unmatched"] is False
    assert gpu["request_spec"] == "NVIDIA 4090", "客户原话规格不许丢"
    assert "客户已知悉" in gpu["grounded_spec"]
    assert next(p for p in out if p["category"] == "CPU")["unmatched"] is True, "别的行不受影响"


def test_waived_state_is_per_row_and_survives_a_different_row_in_same_category():
    """同一类目多行（4 千兆 + 2 万兆）：只豁免点过的那一行，另一行照旧要求落地。"""
    from app.services.part_selector import apply_kp_waived
    parts = [{"category": "NIC", "request_spec": "2个万兆", "unmatched": True, "qty": 2},
             {"category": "NIC", "request_spec": "4个千兆", "unmatched": True, "qty": 4}]
    out, marked = apply_kp_waived(parts, ["NIC|2个万兆"])
    assert marked == 1
    assert [bool(p.get("waived")) for p in out] == [True, False]


def test_waived_state_round_trips_through_the_structured_slot_channel():
    """点击通路（apply_structured_slots + kp_state）落进本节点私有状态，跨轮可读。"""
    from app.services.skill_node_state import KP_NODE, waived_row_keys
    from app.services.slot_contract import apply_structured_slots
    kp_st: dict = {}
    ext: dict = {}
    notes = apply_structured_slots(ext, {"kp_waived": ["GPU|NVIDIA 4090"]}, "", kp_state=kp_st)
    assert waived_row_keys({"node_state": {KP_NODE: kp_st}}) == {"GPU|NVIDIA 4090"}
    assert any("保持原需求" in n for n in notes), notes
    assert not ext.get("kp_rows"), "上游登记表不许被回填"


def test_waived_is_not_absent_and_does_not_silently_drop_the_category():
    """waived 走的是「行保留」这条路：类目级 absent 列表必须保持干净（两者语义不同）。"""
    from app.services.skill_node_state import KP_ABSENT, KP_NODE
    from app.services.slot_contract import apply_structured_slots
    kp_st: dict = {}
    apply_structured_slots({}, {"kp_waived": ["GPU|NVIDIA 4090"]}, "", kp_state=kp_st)
    assert not kp_st.get(KP_ABSENT)


def test_kp_table_artifact_marks_waived_rows_white_box():
    """产物白盒：豁免行带 waived 标记与文案（前端据此标注，不当已落地料号渲染）。"""
    from app.services.skill_node_artifacts import _kp_table_row
    row = _kp_table_row({"category": "GPU", "request_spec": "NVIDIA 4090", "waived": True, "qty": 2})
    assert row["waived"] is True and "客户已知悉" in row["waived_note"]
    plain = _kp_table_row({"category": "CPU", "name": "KH50000", "qty": 2})
    assert plain["waived"] is False and plain["waived_note"] == ""


def test_done_summary_says_how_many_rows_are_waived():
    """完成摘要从产物生成：出现豁免行就如实说出来，不报「全部落地」。"""
    from app.services.skill_node_artifacts import done_summary
    art = {"kind": "kp_table", "title": "配件表",
           "data": {"rows": [{"part_category": "CPU", "waived": False},
                             {"part_category": "GPU", "waived": True}]}}
    s = done_summary({}, "kp_reason", art)
    assert "2 行" in s and "1 行库内无料" in s


def test_phase_kp_reason_keeps_a_waived_row_out_of_the_landed_count():
    """整段装配（phase_kp_reason）：豁免行留在行表 + 标注，且不冒充已落地料号。

    计数是白盒承诺：kp_count 只数真实料号行，豁免行单独计数（waived_count），
    终检按「登记行三结了结」放行。
    """
    import asyncio

    from app.services.skill_phases import phase_kp_reason
    ext = {"kp_rows": [{"part_category": "CPU", "description": "兆芯50000", "qty": 2},
                       {"part_category": "GPU", "description": "NVIDIA H100 80G", "qty": 2}],
           "server_type_name": "通用计算服务器"}
    ctx = {"ext": ext,
           "node_state": {"kp_reason": {
               "picks": {"CPU|兆芯50000": {"name": "KH50000 96C", "price": 1.0}},
               "waived": ["GPU|NVIDIA H100 80G"]}},
           "_locked_baseline": {"name": "ZS220 V2", "series": "Polaris"}}
    asyncio.run(phase_kp_reason(ctx, {}, None))
    summary = ctx["kp_summary"]
    assert summary["kp_count"] == 1, summary
    assert summary["unmatched_count"] == 0, summary
    assert summary["waived_count"] == 1, summary
    gpu = next(p for p in ctx["kp_parts"] if p["category"] == "GPU")
    assert gpu["waived"] is True and gpu["unmatched"] is False
    assert gpu["request_spec"] == "NVIDIA H100 80G", "客户原话规格要留在行上"
    from app.services.skill_plan_runtime import final_gate
    assert final_gate(ctx, composing=True)["ok"] is True


def test_phase_kp_reason_still_blocks_a_row_that_is_neither_landed_nor_waived():
    """对照：同一个类目既没落地也没豁免 → 终检照样拦（豁免不是万能后门）。"""
    import asyncio

    from app.services.skill_phases import phase_kp_reason
    ext = {"kp_rows": [{"part_category": "CPU", "description": "兆芯50000", "qty": 2},
                       {"part_category": "GPU", "description": "NVIDIA H100 80G", "qty": 2}],
           "server_type_name": "通用计算服务器"}
    ctx = {"ext": ext,
           "node_state": {"kp_reason": {"picks": {"CPU|兆芯50000": {"name": "KH50000 96C", "price": 1.0}}}},
           "_locked_baseline": {"name": "ZS220 V2", "series": "Polaris"}}
    asyncio.run(phase_kp_reason(ctx, {}, None))
    assert ctx["kp_summary"]["unmatched_count"] == 1
    from app.services.skill_plan_runtime import final_gate
    gate = final_gate(ctx, composing=True)
    assert gate["ok"] is False and "GPU" in gate["hint"]
    assert "waived" in gate["hint"], "拦截文案要给出「保持原需求」这条出路"
# 行身份（P3-3）：行卡按引擎铸造的 row_id 绑行（不再从「类目|描述」文本里切类目）
ROW_ID = "kp-gpu0001"
MEM_ID = "kp-mem0001"


def _named_row_engine(category="GPU", desc="NVIDIA B200 192G", row_id=None):
    return {"ext": {"kp_rows": [{"part_category": category, "description": desc}]},
            "kp_parts": [{"category": category, "request_spec": desc, "qty": 2,
                          "origin": "reg:" + category, "row_id": row_id or ROW_ID, "rev": "r1"}]}


def test_row_card_for_a_customer_named_row_always_offers_keep_original():
    """插座兜底：客户点名登记的行（且该类目**大脑查过**），行卡**必然**带
    「保持原需求」出路（需求明确但库内无料 = 必须让客户在「换料 / 改前提 / 就这样」里选）。"""
    from app.services.skill_node_plugins import ROW_KEEP_ORIGINAL_LABEL, _KpNode
    from app.services.skill_plan_runtime import ask_option_signal
    row = ROW_ID
    opts = _KpNode().extra_ask_options(_named_row_engine(), {"row": row, "options": []}, row)
    assert len(opts) == 1 and opts[0]["waived"] is True
    assert opts[0]["label"] == ROW_KEEP_ORIGINAL_LABEL
    # 补出来的选项与大脑给的走同一条信号解释，不自己造信号
    assert ask_option_signal(row, opts[0]) == {"kp_waived": [row]}


def test_row_card_backstop_stays_silent_when_the_named_model_is_in_the_library():
    """客户点名的型号库里真有 → 不补「保持原需求」：有料可换就不给「留白」这条逃生路。"""
    from app.services.skill_node_plugins import _KpNode
    row = "kp-nic0001"
    engine = _named_row_engine(category="NIC", desc="X710 万兆双口", row_id=row)
    opts = _KpNode().extra_ask_options(engine, {"row": row, "options": []}, row)
    assert [o["label"] for o in opts] == ["X710 万兆双口"], opts


def test_row_card_backstop_stays_silent_for_rows_the_customer_did_not_specify():
    """客户没点名、等 AI 推荐的行不补这条出路：否则等于给待推荐的行
    开一条绕过选型的逃生口（用户定调：模糊需求要给推荐，不是留白）。"""
    from app.services.skill_node_plugins import _KpNode
    # 登记行里只写了类目名（= 客户没点名具体规格，等 AI 推荐）
    engine = {"ext": {"kp_rows": [{"part_category": "Memory", "description": "memory"}]},
              "kp_parts": [{"category": "Memory", "request_spec": "memory", "qty": 1,
                            "origin": "reg:Memory", "row_id": MEM_ID, "rev": "r1"}]}
    row = MEM_ID
    assert _KpNode().extra_ask_options(engine, {"row": row, "options": []}, row) == []


def test_row_card_backstop_does_not_duplicate_the_brains_own_waived_option():
    """大脑自己给了保持原需求 → 不再补第二条（选项唯一）。"""
    from app.services.skill_node_plugins import _KpNode
    row = ROW_ID
    ask = {"row": row, "options": [{"label": "保持原需求", "waived": True}]}
    assert _KpNode().extra_ask_options(_named_row_engine(), ask, row) == []


def test_row_card_backstop_supplies_candidates_when_the_brain_sent_no_usable_option():
    """大脑只丢了个问题、选项一条都不带信号 → 插座补上库内候选（客户有得点），
    而不是弹一张点了没反应的零选项卡。候选当场回库按行描述召回。"""
    from app.services.skill_node_plugins import _KpNode
    from app.services.skill_plan_runtime import ask_option_signal
    engine = {
        "ext": {"kp_rows": [{"part_category": "NIC", "description": "2个万兆网口"}]},
        "kp_parts": [{"category": "NIC", "request_spec": "2个万兆网口", "qty": 2,
                      "origin": "reg:NIC", "row_id": "kp-nic0002", "rev": "r1"}],
    }
    row = "kp-nic0002"
    opts = _KpNode().extra_ask_options(engine, {"row": row, "options": []}, row)
    labels = [o["label"] for o in opts]
    assert labels[0] == "X710 万兆双口", labels
    assert ask_option_signal(row, opts[0])["kp_manual_pick"]["part_id"] == "701"
    # 客户点名的规格（2个万兆网口）在库里没有同名牌 → 第三条出路必须在
    assert labels[-1] == "保持原需求（库里暂无此料，本行按原需求留白）"
    # 大脑自己给了可用选项就不抢（不重复补候选），只补它漏掉的「保持原需求」
    keep = {"row": row, "options": [{"label": "X710", "pick": {"name": "X710 万兆双口"}}]}
    extra = _KpNode().extra_ask_options(engine, keep, row)
    assert [o["label"] for o in extra] == ["保持原需求（库里暂无此料，本行按原需求留白）"]


def test_waived_categories_resolve_a_row_id_through_the_identity_ledger():
    """终检按类目核对豁免行：豁免键是 row_id（P3-2）时走身份台账反查类目。

    回归靶心：旧实现多留了一行提前 return，直接把 row_id 当类目返回 → 终检认不出该类目
    已了结，客户明明点了「保持原需求」却仍被拦下。旧式行键（类目|描述）照旧切第一段。
    """
    from app.services.skill_node_state import KP_NODE, waived_categories
    st = {"node_state": {KP_NODE: {
        "waived": ["kp-gpu0001"],
        "row_ids": {"reg:GPU": {"row_id": "kp-gpu0001", "category": "GPU",
                                "description": "NVIDIA 4090", "rev": "r1"}}}}}
    assert waived_categories(st) == {"GPU"}
    legacy = {"node_state": {KP_NODE: {"waived": ["GPU|NVIDIA 4090"]}}}
    assert waived_categories(legacy) == {"GPU"}
