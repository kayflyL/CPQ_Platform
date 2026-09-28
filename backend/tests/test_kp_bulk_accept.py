# -*- coding: utf-8 -*-
"""套装整体接受项（pick_all → kp_accept_recommendations 批量晋升）——2026-09-13。

推荐路端到端的收口通道：select_parts 对 specified=false 行只能写 KP_RECOMMEND
（AI 无权代客户拍板），锁定唯一通道=客户点击带 pick 的选项。整体选项装不下逐颗料
的 pick → 专用信号把全部推荐态行一次性晋升为锁定（点击=客户亲口确认，多行版）。
"""
import asyncio
from types import SimpleNamespace

from app.services import skill_tool_context


def _rec_entry(name, qty, row_id=""):
    return {"row_id": row_id, "category": "CPU", "description": name, "rev": "",
            "part_id": "1", "name": name, "price": 1, "currency": "RMB",
            "reason": "AI 推荐", "qty": qty}


def test_bulk_accept_promotes_all_recommendations_to_picks():
    from app.services.skill_node_state import KP_PICKS, KP_RECOMMEND
    from app.services.slot_contract import apply_structured_slots
    kp_st = {KP_RECOMMEND: {"kp-1": _rec_entry("AMD 9354", 2, "kp-1"),
                            "kp-2": [_rec_entry("64G DDR5", 16, "kp-2")]},
             KP_PICKS: {"kp-0": _rec_entry("已锁行", 1, "kp-0")}}
    notes = apply_structured_slots({}, {"kp_accept_recommendations": True}, "", kp_state=kp_st)
    picks = kp_st[KP_PICKS]
    assert set(picks) == {"kp-0", "kp-1", "kp-2"}
    assert picks["kp-1"]["name"] == "AMD 9354" and picks["kp-1"]["qty"] == 2
    assert isinstance(picks["kp-2"], list)
    assert kp_st[KP_RECOMMEND] == {}
    assert any("批量锁定" in n for n in notes), notes


def test_bulk_accept_without_recommendations_is_a_noop():
    from app.services.skill_node_state import KP_PICKS
    from app.services.slot_contract import apply_structured_slots
    kp_st = {KP_PICKS: {}}
    notes = apply_structured_slots({}, {"kp_accept_recommendations": True}, "", kp_state=kp_st)
    assert notes == [] and kp_st[KP_PICKS] == {}


def test_ask_user_option_persists_pick_all_flag():
    from app.services.skill_tools_misc import tool_ask_user
    skill_tool_context.TOOL_CTX.set({"task_active": True, "brain_asks": []})
    out = tool_ask_user({"question": "整体落定？", "options": [
        {"label": "全部按推荐落定", "pick_all": True, "recommended": True},
        {"label": "CPU 换 9654", "pick": {"name": "AMD 9654"}}]})
    assert out.get("ok"), out
    opts = skill_tool_context.TOOL_CTX.get()["brain_asks"][0]["options"]
    assert opts[0].get("pick_all") is True
    assert "pick_all" not in opts[1] and opts[1].get("pick", {}).get("name") == "AMD 9654"


def test_ask_option_signal_binds_bulk_over_row_and_field_paths():
    from app.services.skill_plan_runtime import ask_option_signal
    # 引擎缺口路（A1 实跑路径）：row 为空、slot=brain_ask 非登记表字段，
    # pick_all 必须仍产出批量晋升信号（否则点击永远匹配不到 signal）
    assert ask_option_signal("", {"label": "全部按推荐落定", "pick_all": True}, "brain_ask") == \
        {"kp_accept_recommendations": True}
    # 绑行的 ask 里混入整体项：pick_all 优先于行绑定
    assert ask_option_signal("CPU|至强", {"label": "全部按推荐落定", "pick_all": True}, "") == \
        {"kp_accept_recommendations": True}
    # 无 pick_all 的 brain_ask 选项维持口头回答语义（空信号走对话）
    assert ask_option_signal("", {"label": "其他建议"}, "brain_ask") == {}


def test_emit_ask_card_binds_bulk_signal_not_row_merge():
    from app.services.skill_chat import _ChatTurnRuntime
    emitted = {}

    async def _emit(question, payload):
        emitted.update(payload)

    async def run():
        stub = SimpleNamespace(emit_input_card=_emit, result_ctx={})
        ask = {"question": "整体落定？", "slot": "", "row": "kp-1",
               "options": [{"label": "全部按推荐落定", "pick_all": True},
                           {"label": "CPU 换 9654", "pick": {"name": "AMD 9654", "qty": 2}}]}
        return await _ChatTurnRuntime._emit_ask_card(stub, ask)

    opts = asyncio.run(run())
    by_value = {o["value"]: o for o in opts}
    # 整体项绑批量晋升信号（优先于行绑定的 kp_row_merge），替代项照常逐颗 pick
    assert by_value["全部按推荐落定"]["signal"] == {"kp_accept_recommendations": True}
    assert by_value["CPU 换 9654"]["signal"]["kp_manual_pick"]["name"] == "AMD 9654"


def test_bulk_card_gets_permanent_self_pick_entry():
    """整体落定卡常驻自选入口（P2 批量流收口后行卡在快乐路上消失的补回）。

    注入项无任何信号标记 → ask_option_signal 空 → 点击落 ask_answers（口头回答），
    大脑按左栏规则 7 逐行 ask_user(row=…) 发行卡，前端自选下拉+数量回归。
    """
    from app.services.skill_node_plugins import _KpNode
    from app.services.skill_plan_runtime import ask_option_signal
    node = _KpNode()
    ask = {"question": "整体落定？", "options": [{"label": "全部按推荐落定", "pick_all": True}]}
    opts = node.extra_ask_options({"kp_parts": []}, ask, "")
    assert len(opts) == 1 and "自己" in opts[0]["label"]
    assert ask_option_signal("", opts[0], "brain_ask") == {}
    # 非整体卡（无 pick_all 选项）不注入
    plain = node.extra_ask_options({"kp_parts": []}, {"options": [{"label": "其他"}]}, "")
    assert plain == []
