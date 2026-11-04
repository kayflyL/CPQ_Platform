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

from ai_office import skill_chat # noqa: E402


def _fake_self(card_emitted_sink):
    fake = SimpleNamespace(
        emit_input_card=card_emitted_sink,
        mem={"skill_chat:support_engineer": {}},
        role_key="support_engineer",
        thread_id="t_race",
        result_ctx={},
        ext={},
    )
    # _emit_gap_card 拆出的助手方法按 self. 查找：给 namespace 假身绑上真实现
    cls = skill_chat._ChatTurnRuntime
    fake._card_options_for_gap = cls._card_options_for_gap.__get__(fake)
    fake._persist_last_card = cls._persist_last_card.__get__(fake)
    return fake


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


# ── 合批多问卡（2026-11-04：可答缺口 ≥2 → 一张分页卡问完，不再一轮只发第一张）──────


def test_gap_card_batches_multiple_gaps_into_one_multi_card():
    """两个可答缺口 → 一张 multi_questions 卡：先落留底再广播，选项按 slot 合并留底。"""
    order = []
    payloads = []

    async def fake_emit(q, payload):
        order.append("broadcast")
        payloads.append(payload)
        return None

    gaps = [
        {"slot": "server_type", "reason_code": "field_confirm", "question": "部署在哪？",
         "options": [{"label": "机房上架", "value": "机房上架", "rule_match": True}]},
        {"slot": "kp_row:kp-gpu0001", "reason_code": "kp_pick", "question": "", "parts_card": True,
         "row": "kp-gpu0001", "qty": 2, "qty_max": 4,
         "pick_meta": {"row": "kp-gpu0001", "category": "GPU", "request_spec": "B200 两张"},
         "options": [{"label": "NVIDIA H100 80G", "value": "NVIDIA H100 80G", "qty": 2, "qty_max": 4,
                      "signal": {"kp_manual_pick": {"row": "kp-gpu0001", "part_id": "250"}}}]},
    ]
    questions = ["部署在哪？", "还需要确认配件：「GPU · B200 两张」怎么配？"]
    fake = _fake_self(fake_emit)
    with patch.object(skill_chat, "_save_mem",
                      lambda tid, rk, m: order.append("save") or saved.update({"mem": m})), \
            patch.object(skill_chat, "_merged_narration", lambda ctx: ""):
        saved = {}
        card_emitted, card_opts = asyncio.run(
            skill_chat._ChatTurnRuntime._emit_gap_card(fake, gaps, questions, "", None))

    assert card_emitted is True
    assert order == ["save", "broadcast"], f"必须先落留底再广播，实际顺序={order}"
    payload = payloads[0]
    mq = payload.get("multi_questions") or []
    assert len(mq) == 2, "≥2 个可答缺口必须合成一张分页卡"
    assert payload.get("slot_options") is None and payload.get("multi_questions"), "合批不走单卡形状"
    assert mq[1]["parts_card"] is True and mq[1]["qty"] == 2
    # 两题选项全部进 last_card（点击 (slot,value) 匹配覆盖合批卡每一题）
    lc = saved["mem"]["last_card"]
    assert [o["slot"] for o in lc["options"]] == ["server_type", "kp_row:kp-gpu0001"]
    assert lc["pick_meta"] == {"__multi__": True,
                               "slots": {"kp_row:kp-gpu0001": {"row": "kp-gpu0001", "category": "GPU",
                                                               "request_spec": "B200 两张"}}}
    # 返回的 card_opts 与留底一致（续跑路由用）
    assert [o["slot"] for o in card_opts] == ["server_type", "kp_row:kp-gpu0001"]
    assert card_opts[1]["signal"]["kp_manual_pick"]["part_id"] == "250"


def test_batch_drops_zero_option_brain_ask_and_stays_single_card():
    """合批里混入零选项 brain_ask（B4）→ 剔除后只剩 1 个可答缺口 → 走单卡形状。"""
    order = []
    payloads = []

    async def fake_emit(q, payload):
        order.append("broadcast")
        payloads.append(payload)
        return None

    gaps = [
        {"slot": "brain_ask", "reason_code": "brain_ask", "question": "机制提示", "options": []},
        {"slot": "server_type", "reason_code": "field_confirm", "question": "部署在哪？",
         "options": [{"label": "机房上架", "value": "机房上架"}]},
    ]
    questions = ["机制提示转述", "部署在哪？"]
    fake = _fake_self(fake_emit)
    with patch.object(skill_chat, "_save_mem",
                      lambda tid, rk, m: order.append("save")), \
            patch.object(skill_chat, "_merged_narration", lambda ctx: ""):
        card_emitted, card_opts = asyncio.run(
            skill_chat._ChatTurnRuntime._emit_gap_card(fake, gaps, questions, "", None))

    assert card_emitted is True
    assert len(payloads) == 1
    payload = payloads[0]
    assert payload.get("multi_questions") is None, "只剩一个可答缺口必须退回单卡形状"
    assert payload.get("question") == "部署在哪？"
    assert [o["slot"] for o in card_opts] == ["server_type"]
