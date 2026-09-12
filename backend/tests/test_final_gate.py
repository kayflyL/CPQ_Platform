# -*- coding: utf-8 -*-
"""交付终检（final_gate，2026-09-07 编排权移交后）回归测试。

旧版（编排引擎时代）由 kp_gate_gap 在 KP 阶段确定性弹确认卡拦截未落地行；
编排权移交后，该保障由组装前终检 final_gate 承担：登记的部件大类没有对应
落地行 → 拦截交付并给出如实原因，绝不静默出「全占位/缺行」方案
（2026-09-07 用户实测：方案表全占位的直接防线）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _ctx_with(reg_rows, landed_cats, model="ZS22V2-P"):
    from app.services.skill_plan_runtime import final_gate  # noqa: F401
    kp_parts = [{"category": c, "name": "真实料号", "qty": 1} for c in landed_cats]
    summary = {"kp_count": len(kp_parts),
               "unmatched_count": 0, "spec_mismatch_count": 0}
    return {
        "ext": {"kp_rows": reg_rows, "server_model": model},
        "_locked_baseline": {"name": model},
        "kp_parts": kp_parts,
        "kp_summary": summary,
    }


def test_final_gate_blocks_missing_category():
    """登记了 1.92T SSD 行但没有任何落地行 → 终检拦截，原因点名缺失大类。"""
    from app.services.skill_plan_runtime import final_gate
    ctx = _ctx_with(
        [{"part_category": "CPU", "description": "兆芯50000", "qty": 2},
         {"part_category": "HDD/SSD", "description": "1.92T SSD", "qty": 1}],
        landed_cats=["CPU"])
    gate = final_gate(ctx, composing=True)
    assert gate["ok"] is False
    assert "HDD/SSD" in gate["hint"]


def test_final_gate_blocks_without_model():
    """机型未锁定 → 不能交付。"""
    from app.services.skill_plan_runtime import final_gate
    ctx = _ctx_with([{"part_category": "CPU", "description": "x", "qty": 1}],
                    landed_cats=["CPU"], model="")
    ctx["_locked_baseline"] = {}
    ctx["ext"].pop("server_model")
    gate = final_gate(ctx, composing=True)
    assert gate["ok"] is False
    assert "机型" in gate["hint"]


def test_final_gate_passes_when_all_landed():
    """登记大类全部落地 → 放行。"""
    from app.services.skill_plan_runtime import final_gate
    ctx = _ctx_with(
        [{"part_category": "CPU", "description": "兆芯50000", "qty": 2},
         {"part_category": "Memory", "description": "768GB DDR5", "qty": 1}],
        landed_cats=["CPU", "Memory"])
    gate = final_gate(ctx, composing=True)
    assert gate["ok"] is True


def test_final_gate_honours_absent_categories():
    """客户明确放弃的大类（kp_reason.absent，如本机不配 GPU）不算缺失。"""
    from app.services.skill_plan_runtime import final_gate
    ctx = _ctx_with(
        [{"part_category": "CPU", "description": "x", "qty": 1},
         {"part_category": "GPU", "description": "GPU", "qty": 1}],
        landed_cats=["CPU"])
    ctx["node_state"] = {"kp_reason": {"absent": ["GPU"]}}
    gate = final_gate(ctx, composing=True)
    assert gate["ok"] is True
