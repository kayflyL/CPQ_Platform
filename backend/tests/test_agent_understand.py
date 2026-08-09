# -*- coding: utf-8 -*-
"""agent_understand 单测（纯 LLM 填表 + resolver + 完整度/反问判定）。

跑法（backend 目录）：python -X utf8 -m pytest tests/test_agent_understand.py -q
"""
import asyncio
from unittest.mock import AsyncMock, patch

from app.services import agent_understand, llm_client


def _catalog():
    return {"server_types": ["AI / 加速计算服务器", "通用计算服务器", "存储服务器"],
            "series": ["Orion", "Polaris", "Intel"], "forms": ["1U", "2U", "4U"]}


def test_llm_primary_extracts_to_ext():
    """纯 LLM 填表 → resolver 合并 → ext；够支撑选配（server_type+品类）。"""
    slots = {"cpu": {"model": "AMD EPYC 9124", "qty": 1},
             "memory": {"per_stick_gb": 32, "qty": 16, "type": "DDR5"},
             "server_type": "AI / 加速计算服务器", "form": "4U"}
    with patch("app.services.llm_client.chat_json", AsyncMock(return_value=slots)), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        res = asyncio.run(agent_understand.run_agent_understand("需求", {}, catalog=_catalog()))
    assert res["ok"] and res["source"] == "llm"
    assert res["ext"]["server_type_name"] == "AI / 加速计算服务器"   # catalog 锚定
    assert res["ext"]["cpu_signal"]["model"] == "AMD EPYC 9124"
    assert "9124" in res["ext"]["keywords"]
    assert res["sufficient"] is True                                  # 有类型 + 有品类


def test_llm_insufficient_flags_missing_for_clarify():
    """抽不全（缺 server_type）→ sufficient=False + missing_critical → dispatch 触发反问。"""
    slots = {"memory": {"per_stick_gb": 32, "qty": 16}}  # 无 server_type
    with patch("app.services.llm_client.chat_json", AsyncMock(return_value=slots)), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        res = asyncio.run(agent_understand.run_agent_understand("内存32G", {}, catalog=_catalog()))
    assert res["source"] == "llm"
    assert res["sufficient"] is False
    assert "服务器类型/用途" in res["missing_critical"]


def test_llm_disabled_returns_not_ok():
    """闸：LLM 关 → ok=False（AI 失效），由编排器路由到 extract 规则理解兜底节点，不再内联兜底。"""
    with patch("app.services.llm_client.is_llm_enabled", return_value=False):
        res = asyncio.run(agent_understand.run_agent_understand("服务器", {}))
    assert res["ok"] is False
    assert res["error"] == "llm_disabled"
    assert res.get("ext") is None


def test_llm_error_returns_not_ok():
    """闸：LLM 失败 → ok=False（交规则理解兜底节点）。"""
    with patch("app.services.llm_client.chat_json",
               AsyncMock(side_effect=llm_client.LLMError("boom"))), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        res = asyncio.run(agent_understand.run_agent_understand("服务器", {}))
    assert res["ok"] is False
    assert "llm_error" in res["error"]


def test_empty_slots_returns_not_ok():
    """分步模式：LLM 全子任务返回空 → ok=False（交规则理解兜底节点），错误含 all_substeps_failed。"""
    with patch("app.services.llm_client.chat_json", AsyncMock(return_value={})), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        res = asyncio.run(agent_understand.run_agent_understand("服务器", {}))
    assert res["ok"] is False
    assert "all_substeps_failed" in res["error"]


def test_legacy_empty_slots_returns_not_ok():
    """legacy 单次路径（split_steps=false）：LLM 返回空 → error=empty_slots（旧语义保留）。"""
    with patch("app.services.llm_client.chat_json", AsyncMock(return_value={})), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        res = asyncio.run(agent_understand.run_agent_understand("服务器", {"split_steps": False}))
    assert res["ok"] is False
    assert res["error"] == "empty_slots"


def test_empty_text_returns_not_ok():
    res = asyncio.run(agent_understand.run_agent_understand("", {}))
    assert res["ok"] is False
    assert res["error"] == "empty_text"


def test_build_messages_has_whitelist_and_text():
    msgs = agent_understand.build_agent_messages("EPYC 9124", _catalog())
    assert msgs[0]["role"] == "system"
    assert "AI / 加速计算服务器" in msgs[1]["content"]   # catalog 白名单
    assert "EPYC 9124" in msgs[1]["content"]             # 需求原文


def test_sub_step_retry_succeeds_after_failure():
    """分步子任务：单个子任务失败（空回）→ 按 sub_step_retries 便宜重试成功。"""
    slots = {"cpu": {"model": "Intel 6530", "qty": 2}, "memory": {"per_stick_gb": 64, "qty": 16}}
    calls = []
    async def fake_chat_json(messages, **kw):
        calls.append(messages)
        if len(calls) == 1:
            raise llm_client.LLMError("LLM 返回空内容")
        return slots
    with patch("app.services.llm_client.chat_json", side_effect=fake_chat_json), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        res = asyncio.run(agent_understand.run_agent_understand("要一台服务器", {}))
    # 首个并发子任务失败一次后重试成功，其余子任务直接成功 → 整体 ok
    assert res["ok"] is True and res["source"] == "llm"
    assert len(calls) >= 5  # 至少 4 个子任务 + 1 次重试


def test_split_steps_config_disable_and_override():
    """分步可配：split_steps=false → 走 legacy 单次；steps.type_form.enabled=false → 只剩 3 步。"""
    assert agent_understand._load_understand_steps({"split_steps": False}) == []
    steps = agent_understand._load_understand_steps({"steps": {"type_form": {"enabled": False}}})
    assert [s["key"] for s in steps] == ["cpu_mem", "drive_gpu", "net_psu_raid", "analysis"]
    steps2 = agent_understand._load_understand_steps({"steps": {"cpu_mem": {"system_prompt": "自定义"}}})
    by = {s["key"]: s for s in steps2}
    assert by["cpu_mem"]["system_prompt"] == "自定义"


def test_sub_step_messages_focus_no_noise():
    """子任务 prompt 聚焦：cpu_mem 步不带类型白名单（避免噪音触发过度思考）。"""
    from app.services.agent_understand import build_sub_step_messages, _load_understand_steps
    steps = {s["key"]: s for s in _load_understand_steps({})}
    msgs = build_sub_step_messages(steps["cpu_mem"], "要 64G*16 内存", _catalog())
    user = msgs[1]["content"]
    assert "CPU 和内存" in msgs[0]["content"]
    assert "在售服务器类型" not in user  # 非类型步骤不带白名单
    assert len(user) < 600  # 轻 prompt


def test_build_agent_messages_caps_long_text():
    """需求原文限长（3000 字），防超长输入拖慢 reasoning 模型。"""
    msgs = agent_understand.build_agent_messages("需" * 5000, _catalog())
    assert len(msgs[1]["content"]) < 3600
    assert "已截断" in msgs[1]["content"]


def test_few_shot_capped_to_two():
    """few-shot 限量 ≤2：案例再多也只取前 2，且单条需求截短。"""
    cases = [
        {"requirement": "A" * 300, "kp_parts": [{"category": f"C{i}", "qty": 1} for i in range(12)]}
        for _ in range(5)
    ]
    with patch("app.services.case_provider.get_case_provider") as mp:
        mp.return_value.retrieve.return_value = cases
        text = agent_understand._retrieve_few_shot({"case_source": "internal", "case_top_k": 5}, "query")
    assert len([l for l in text.splitlines() if l.strip().startswith("案例")]) == 2
    assert "A" * 300 not in text  # 单条需求已截短
