# -*- coding: utf-8 -*-
"""智能对话填表 Agent 冒烟回归：确保 run_agent_fill 不因模块常量缺失而 NameError。

历史 BUG：capabilities.py 引用了未定义的 _KNOWN_SLOT_KEYS / _AGENT_FILL_AGENT_PROMPT /
_AGENT_FILL_TOOL_IDS，导致 agent_fill 在调用 LLM 前直接崩溃、流水线中止。
此测试机型掉 LLM，专防这类“用了但没定义”回归。
"""
import asyncio
import os
import sys
from unittest.mock import patch

# 独立运行（python -X utf8 tests/test_agent_fill_smoke.py）时把 backend 根加进 sys.path；
# pytest 走 conftest.py，不依赖这行。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_capability_spec_validate_ok():
    from app.services import capability_spec
    assert capability_spec.validate_specs() == []


def test_agent_fill_runs_without_undefined_constant():
    """机型掉 LLM 后 run_agent_fill 必须能跑完并落槽，而非第 890 行 NameError。"""
    import app.services.agent_react as ar
    from app.services import capabilities

    async def fake_loop(**kwargs):
        return {
            "ok": True,
            "answer": {"fill": {"server_type_name": "AI训练", "server_model": "ESA25V3-P",
                                "purchase_qty": 1}, "ask": "", "done": True, "edit": False},
            "tool_calls_log": [],
        }

    ctx = {"requirement_text": "4U 训推一体机 ESA25V3-P，2颗C86，64G DDR5，2块480G SSD，1张K100",
           "ext": {}, "llm_enabled": True}
    with patch.object(ar, "run_react_loop", new=fake_loop):
        res = asyncio.run(capabilities.run_agent_fill(ctx, {}))
    assert res.get("ok") is True
    # 客户原话真实点名 ESA25V3-P → 需求表保留；LLM 编造/反推的其它字段不落。
    assert ctx["ext"].get("server_model") == "ESA25V3-P"
    assert ctx["ext"].get("purchase_qty") == 1


def test_agent_fill_drops_model_not_in_text():
    """客户未点名机型号时，需求表不得被 LLM/下游回填 server_model 及其反推字段。"""
    import app.services.agent_react as ar
    from app.services import capabilities

    async def fake_loop(**kwargs):
        return {
            "ok": True,
            "answer": {"fill": {"server_type_name": "AI训练", "server_model": "ESA25V3-P",
                                "platform_type": "Orion", "chassis_form": "4U",
                                "purchase_qty": 1}, "ask": "", "done": True, "edit": False},
            "tool_calls_log": [],
        }

    ctx = {"requirement_text": "4U 训推一体机，2颗C86，64G DDR5，2块480G SSD，1张K100",
           "ext": {}, "llm_enabled": True}
    with patch.object(ar, "run_react_loop", new=fake_loop):
        res = asyncio.run(capabilities.run_agent_fill(ctx, {}))
    assert res.get("ok") is True
    # 重构后：机型回填必须拦截（server_model 应为空）；客户原话的 4U 保留；
    # 语义推断出的类型（训推→AI 训练）与系列/形态应被信任并保留，不再被旧白名单删除。
    assert ctx["ext"].get("server_model") is None
    assert ctx["ext"].get("chassis_form") == "4U"
    assert ctx["ext"].get("server_type_name") is not None
    assert ctx["ext"].get("purchase_qty") == 1
