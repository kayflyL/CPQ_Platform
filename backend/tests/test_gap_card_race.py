# -*- coding: utf-8 -*-
"""发卡时序回归（2026-10-15）：选项卡必须「先落留底、再广播」。

背景事故：_emit_gap_card 旧序「先广播后落库」，用户秒点自选下拉/选项时 card-pick 端点
读到的还是旧 last_card（无 pick_meta）→ 409「当前选项卡不支持自选」→ 前端空下拉+一行
小字错误，看起来就是「下拉没内容」。
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import skill_chat  # noqa: E402


def _fake_self(card_emitted_sink):
    return SimpleNamespace(
        emit_input_card=card_emitted_sink,
        mem={"skill_chat:support_engineer": {}},
        role_key="support_engineer",
        thread_id="t_race",
        result_ctx={},
        ext={},
    )


def test_gap_card_persists_last_card_before_broadcast():
    """card-pick 的数据前提（last_card.pick_meta）必须在 WS 广播之前就位。"""
    order = []

    async def fake_emit(q, payload):
        order.append("broadcast")
        return None

    gaps = [{
        "slot": "brain_ask", "reason_code": "brain_ask",
        "question": "RAID 卡怎么选?", "parts_card": True, "row": "kp-abc",
        "qty": 2, "qty_max": 2,
        "pick_meta": {"row": "kp-abc", "category": "Raid card"},
        "options": [
            {"label": "LSI 9361-8i 2G", "value": "LSI 9361-8i 2G", "slot": "brain_ask", "group": "AI 推荐"},
            {"label": "保持原需求", "value": "保持原需求", "slot": "brain_ask", "group": "AI 推荐"},
        ],
    }]
    questions = ["RAID 卡怎么选?"]

    saved = {}
    fake = _fake_self(fake_emit)
    # 模拟真实调用链：_annotate_gaps 先把 pick_meta 从 gap 上摘下来再传参
    pick_meta = gaps[0].pop("pick_meta")
    with patch.object(skill_chat, "_save_mem",
                      lambda tid, rk, m: order.append("save") or saved.update({"mem": m})), \
            patch.object(skill_chat, "_merged_narration", lambda ctx: ""):
        card_emitted, card_opts = asyncio.run(
            skill_chat._ChatTurnRuntime._emit_gap_card(fake, gaps, questions, "", pick_meta))

    assert card_emitted is True
    assert order == ["save", "broadcast"], f"必须先落留底再广播，实际顺序={order}"
    lc = saved["mem"]["last_card"]
    assert lc["pick_meta"]["row"] == "kp-abc"
    assert len(lc["options"]) == 2


def test_gap_card_without_options_skips_persist_and_broadcast():
    """零选项 brain_ask 缺口走文字兜底：不落卡、不广播（B4 兜底语义不变）。"""
    order = []

    async def fake_emit(q, payload):
        order.append("broadcast")
        return None

    gaps = [{"slot": "brain_ask", "reason_code": "brain_ask", "question": "？", "options": []}]
    fake = _fake_self(fake_emit)
    with patch.object(skill_chat, "_save_mem",
                      lambda tid, rk, m: order.append("save")), \
            patch.object(skill_chat, "_merged_narration", lambda ctx: ""):
        card_emitted, card_opts = asyncio.run(
            skill_chat._ChatTurnRuntime._emit_gap_card(fake, gaps, ["？"], "", None))

    assert card_emitted is False
    assert order == [] and card_opts == []
