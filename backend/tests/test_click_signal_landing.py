# -*- coding: utf-8 -*-
"""点击通路回归：选项卡信号必须落进本节点私有状态。

历史事故（2026-09-10 实测定位）：点击通路里 `node_state(mem, KP_NODE)` 用了没导入的
`KP_NODE`，参数求值就 NameError，被 `except Exception` 吞掉 → 客户点了没反应、同一张卡
反复弹、线程永远走不到交付。单测全绿也照样漏，因为没有任何测试跑过这条通路。
"""
import asyncio
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROW = "GPU|NVIDIA B200 192G 显卡 2 张"
VAL = "保持原需求：NVIDIA B200 192G ×2"


def _seed():
    ext = {"server_type": "通用计算服务器", "platform_type": "Orion", "chassis_form": "2U",
           "purchase_qty": 1, "warranty_years": 3, "confirmed_slots": {"platform_type": "Orion"},
           "kp_rows": [{"part_category": "CPU", "description": "双路CPU（AMD平台）", "qty": 2},
                       {"part_category": "GPU", "description": "NVIDIA B200 192G 显卡 2 张", "qty": 2}]}
    return {
        "ext": ext,
        "steps_done": ["agent_fill", "model_reason"],
        "locked_baseline": {"name": "ES22V3-P", "series": "Orion", "form": "2U", "server_model_id": 6},
        "model_selection": {"name": "ES22V3-P", "series": "Orion", "form": "2U"},
        "node_state": {"kp_reason": {"row_answers": {}}},
        "last_card": {"options": [{"slot": "brain_ask", "value": VAL, "signal": {"kp_waived": [ROW]}}],
                      "pick_meta": {"row": ROW, "category": "GPU", "request_spec": "NVIDIA B200 192G 显卡 2 张",
                                    "series": "Orion", "pool": [], "pool_source": "brain_ask"}},
    }


def test_clicked_card_signal_lands_in_the_node_partition():
    """行卡点击 → 信号按 (slot,value) 命中留底卡 → 落进 kp_reason 私有状态（不再静默丢）。"""
    from app.services import skill_chat
    store = _seed()

    async def fake_loop(msg, **kwargs):
        return {"answer": "（打桩，不调模型）", "tool_calls_log": []}

    async def sink(_payload):
        return None

    async def card(_q, _d):
        return None

    async def scenario():
        with patch.object(skill_chat, "run_stream_chat_loop", fake_loop):
            return await skill_chat.handle_skill_chat_turn(
                thread_id="t_click", user_text="", colleague={"role_key": "support_engineer", "name": "技术支持"},
                chat_system_prompt="你是技术支持工程师", history=[], user={"user_id": "u"},
                opportunity_id="o_click", option_slot=None, event_sink=sink, emit_input_card=card,
                card_selections=[{"slot": "brain_ask", "value": VAL}], force_submit=True, skill_phase_hint="")

    with patch.object(skill_chat, "_load_mem", lambda _t, _r="assistant": dict(store)), \
         patch.object(skill_chat, "_save_mem", lambda _t, _r, mem: (store.clear(), store.update(mem))):
        asyncio.run(scenario())

    assert not store.get("click_errors"), f"点击不该失败：{store.get('click_errors')}"
    kp_st = (store.get("node_state") or {}).get("kp_reason") or {}
    assert kp_st.get("waived") == [ROW], f"点击信号必须落进本节点分区，实际：{kp_st}"
