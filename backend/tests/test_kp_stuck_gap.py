# -*- coding: utf-8 -*-
"""插座兜底（stuck_gap）：配件选型卡住时，节点自己把该行交客户拍板。

背景（2026-09-10 实测）：大脑回喂耗尽后既没落地该行、也没升格提问，编排壳只能把
「机制提示」当问句抛回客户——客户既没有可点的卡，机制文案还泄漏成了客户话术。
修法不是话术兜底，而是让插座（节点插件）声明自己能给的**结构性命中卡**：
选项全是数据（当场按行描述回库召回的库内候选 + 客户点名型号无料时的「保持原需求」），
信号仍走唯一出口 ask_option_signal。

2026-09-12 去台账：候选与「库里没有点名的型号」都由插座当场回库核对（_fake_part_library
顶替库），不再读「大脑本轮检索留底」的索引。
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# 行身份（P3-3）：行卡按引擎铸造的 row_id 绑行；未铸造身份的旧行才退回复合行键「类目|描述」
ROW_ID = "kp-gpu0001"

# 库内真实料号（本文件的假库）：行卡候选按类目当场召回；客户点名型号按料号名精确核对
_LIBRARY = {
    "gpu": [
        {"part_id": "250", "name": "NVIDIA H100 80G", "price": 210000, "currency": "RMB",
         "specs": {"Memory": "80GB", "Link": "NVLink"}},
        {"part_id": "251", "name": "NVIDIA A800 80G", "price": 150000, "currency": "RMB",
         "specs": {"Memory": "80GB"}},
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


def _engine(row_spec="NVIDIA B200 192G 两张", qty=2, category="GPU", registered=True):
    """构造卡住现场：一行未落地 + 该类目在假库里的候选（客户点名型号则查无此名）。"""
    ext = {"kp_rows": [{"part_category": category, "description": "NVIDIA B200 192G 两张",
                        "qty": 2}]} if registered else {}
    return {"ext": ext,
            "kp_parts": [{"category": category, "request_spec": row_spec, "unmatched": True,
                          "qty": qty, "origin": "reg:" + category, "row_id": ROW_ID, "rev": "r1"}],
            "_locked_baseline": {"series": "Orion"}}


def test_stuck_gap_offers_grounded_candidates_plus_keep_original():
    """客户点名型号库内无料 → 卡上既有库内候选（能落地），也有「保持原需求」（能收口）。"""
    from app.services.skill_node_plugins import ROW_KEEP_ORIGINAL_LABEL, plugin_for
    gap = plugin_for("kp_reason").stuck_gap(_engine())
    assert gap and gap["reason_code"] == "kp_pick" and gap["parts_card"] is True
    assert gap["row"] == ROW_ID
    labels = [o["label"] for o in gap["options"]]
    assert labels[:2] == ["NVIDIA H100 80G", "NVIDIA A800 80G"], labels
    assert labels[-1] == ROW_KEEP_ORIGINAL_LABEL


def test_stuck_gap_options_are_interpreted_by_the_single_signal_exit():
    """选项信号只能来自唯一出口：点料 → kp_manual_pick；保持原需求 → kp_waived。"""
    from app.services.skill_node_plugins import ROW_KEEP_ORIGINAL_LABEL, plugin_for
    gap = plugin_for("kp_reason").stuck_gap(_engine())
    by_label = {o["label"]: o for o in gap["options"]}
    pick = by_label["NVIDIA H100 80G"]["signal"]["kp_manual_pick"]
    assert pick["row"] == ROW_ID and pick["part_id"] == "250"
    assert pick["qty"] == 2 and pick["price"] == 210000
    assert by_label[ROW_KEEP_ORIGINAL_LABEL]["signal"] == {"kp_waived": [ROW_ID]}


def test_stuck_gap_never_invents_a_keep_original_escape_for_ai_chosen_rows():
    """客户没点名、等 AI 推荐的行不补「保持原需求」——否则等于给待选型行开逃生口。"""
    from app.services.skill_node_plugins import ROW_KEEP_ORIGINAL_LABEL, plugin_for
    gap = plugin_for("kp_reason").stuck_gap(_engine(row_spec="GPU", registered=False))
    labels = [o["label"] for o in gap["options"]]
    assert labels and ROW_KEEP_ORIGINAL_LABEL not in labels


def test_stuck_gap_is_silent_when_the_library_has_nothing_to_offer():
    """库内该类目召不回候选、行又不是客户点名 → 不产卡：宁缺毋滥，不把整库端上来。"""
    from app.services.skill_node_plugins import plugin_for
    assert plugin_for("kp_reason").stuck_gap(_engine(category="FPGA", registered=False)) is None


def test_stuck_gap_keeps_the_escape_when_the_category_has_no_candidate():
    """库内召不回候选、但该行是客户点名的 → 唯一出路「保持原需求」必须还在。"""
    from app.services.skill_node_plugins import ROW_KEEP_ORIGINAL_LABEL, plugin_for
    gap = plugin_for("kp_reason").stuck_gap(_engine(category="FPGA"))
    assert [o["label"] for o in gap["options"]] == [ROW_KEEP_ORIGINAL_LABEL]
    assert gap["options"][0]["signal"] == {"kp_waived": [ROW_ID]}


def test_stuck_gap_is_silent_when_every_row_landed():
    from app.services.skill_node_plugins import plugin_for
    eng = _engine()
    eng["kp_parts"][0]["unmatched"] = False
    assert plugin_for("kp_reason").stuck_gap(eng) is None


def test_first_stuck_gap_finds_the_socket_through_the_registry():
    """编排壳不认识节点名：靠注册表把所有插座的 stuck_gap 问一遍。"""
    from app.services.skill_node_plugins import first_stuck_gap
    gap = first_stuck_gap(_engine())
    assert gap and gap["slot"] == "kp_row" and gap["options"]
    assert first_stuck_gap({"kp_parts": []}) is None


def test_ask_option_signal_never_writes_a_field_that_is_not_on_the_form():
    """兜底 slot（brain_ask）只是客户的一句口答，不许被当成字段信号写进登记表。"""
    from app.services.skill_plan_runtime import ask_option_signal
    assert ask_option_signal("", {"label": "通用计算服务器"}, "brain_ask") == {}
    # 真正的登记表字段照旧直传（客户点选 = 把该字段登记为确认值）
    sig = ask_option_signal("", {"slot": "server_type", "value": "通用计算服务器", "label": "通用计算服务器"})
    assert sig == {"server_type": "通用计算服务器"}

def test_row_card_for_a_row_id_ref_resolves_the_category_by_identity():
    """行引用是引擎铸造的 row_id（文本里没有竖线）→ 类目由身份解析，卡照样出得来。

    P3-3 回归靶心（实测探针）：卡片改绑 row_id 后，旧实现仍按「类目|描述」切竖线取类目，
    结果候选为空、豁免无路、absent 甚至把 `True` 写进登记表。类目只能由身份解析。
    """
    from app.services.skill_node_plugins import ROW_KEEP_ORIGINAL_LABEL, _KpNode
    from app.services.skill_plan_runtime import ask_option_signal
    eng = _engine()
    opts = _KpNode().extra_ask_options(eng, {"row": ROW_ID, "options": []}, ROW_ID)
    labels = [o["label"] for o in opts]
    assert labels[:2] == ["NVIDIA H100 80G", "NVIDIA A800 80G"], labels
    assert labels[-1] == ROW_KEEP_ORIGINAL_LABEL
    assert ask_option_signal(ROW_ID, opts[0], "kp_row",
                             category="GPU")["kp_manual_pick"]["part_id"] == "250"
    assert ask_option_signal(ROW_ID, opts[-1], "kp_row", category="GPU") == {"kp_waived": [ROW_ID]}
    # absent 的 schema 是「类目名」：给了就原样尊重
    assert ask_option_signal(ROW_ID, {"absent": "GPU"}) == {"kp_absent": ["GPU"]}
    # 脏数据（absent 非字符串）→ 按身份给出类目，绝不把 True 写进登记表
    assert ask_option_signal(ROW_ID, {"absent": True}, category="GPU") == {"kp_absent": ["GPU"]}
    # 身份也解析不到、文本又不是复合行键 → 宁缺毋滥（不产信号，而不是产一个假类目）
    assert ask_option_signal("kp-未知", {"absent": True}) == {}


def test_unstamped_rows_still_bind_by_the_row_list_identity():
    """旧行（还没铸造 origin 身份）→ 卡仍按**行清单对外给的那个 id** 绑行。

    行清单对未铸造身份的行给的是 kp_row_id（类目|描述 派生）——卡与清单口径必须一致，
    否则同一行在清单里叫 A、在卡上叫 B，点击落键就落到别的行上去了。
    """
    from app.services.part_selector import kp_row_id
    from app.services.skill_node_plugins import plugin_for
    eng = _engine()
    for k in ("origin", "row_id", "rev"):
        eng["kp_parts"][0].pop(k, None)
    expect = kp_row_id("GPU", "NVIDIA B200 192G 两张")
    gap = plugin_for("kp_reason").stuck_gap(eng)
    assert gap["row"] == expect
    assert gap["options"][0]["signal"]["kp_manual_pick"]["row"] == expect
