# -*- coding: utf-8 -*-
"""配件确认卡（2026-09-07）：未匹配 must_ask 行必须由引擎确定性弹 brain_ask 表单卡。

    回归目标（用户实测根因）：旧版确认卡依赖模型自愿调 ask_user——模型偏好散文时只剩
    一句问话、无可点选项；或前置 kp_required 空选项卡阻塞/死循环。本测试用真实流程配置 +
    stub 大脑（不发起 LLM）验证：未匹配行 → 引擎弹 brain_ask parts_card，候选为库内真实
    件（含 KH50000 96C）；引擎不再硬编码"推荐"——那必须由 AI 产出。
"""
import os
import sys
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


def _flow_configs():
    from app.repository.reasoning_flow_repo import ReasoningFlowRepository
    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis", name="需求分析")
    finally:
        repo.close()
    if not flow:
        return None
    return dict(flow.get("node_configs") or {})


@pytest.mark.skipif(_flow_configs() is None, reason="需求分析流程未配置")
def test_kp_confirm_card_emitted_deterministically():
    """未匹配 must_ask 行 → 引擎弹 brain_ask 表单卡（真实候选推荐），非空卡/非 kp_required。"""
    from app.services.skill_plan_runtime import run_skill_plan_core
    flow_configs = _flow_configs()
    ext = {
        "server_type_name": "通用计算服务器", "platform_type": "Polaris",
        "server_model": "ZS22V2-P", "purchase_qty": 1, "warranty_years": "3年",
        "confirmed_slots": {"server_type": "通用计算服务器", "platform_type": "Polaris",
                            "server_model": "ZS22V2-P", "purchase_qty": 1,
                            "warranty_years": "3年"},
        "kp_rows": [
            {"part_category": "CPU", "description": "2颗兆芯50000 处理器（2.2GHz/96C）", "qty": 2},
            {"part_category": "Memory", "description": "768GB DDR5", "qty": 1},
        ],
    }
    async def broadcast(payload):
        return None
    async def brain(*args, **kwargs):
        return None
    ctx = {
        "requirement_text": "CPU：2颗兆芯50000 处理器\n内存：768GB DDR5",
        "ext": ext, "slots_provided": True, "skip_fill_round": True,
        "force_complete": False,
    }
    out = asyncio.run(run_skill_plan_core(ctx, flow_configs, broadcast, title="probe", brain=brain))
    gaps = out.get("engine_gaps") or []
    assert gaps, "应有引擎缺口（brain_ask 确认卡）"
    gap = gaps[0]
    assert gap.get("slot") == "brain_ask", f"应为 brain_ask 确认卡，实为 {gap.get('slot')}"
    assert gap.get("reason_code") == "brain_ask"
    assert gap.get("parts_card") is True
    assert gap.get("row") == "CPU|2颗兆芯50000 处理器（2.2GHz/96C）"
    labels = [o.get("label") for o in (gap.get("options") or [])]
    assert labels and "KH50000 96C" in labels, f"应含真实候选推荐，实为 {labels}"
    assert isinstance(gap.get("pick_meta"), dict) and gap["pick_meta"].get("row")
    # 回归：引擎不硬编码推荐（AI 建议必须来自大脑）；绝不再出现 kp_required 空选项卡 /
    # kp_unmatched 空信号卡。候选以「候选」组自选，不标推荐。
    assert not any(o.get("recommended") for o in (gap.get("options") or []))
