# -*- coding: utf-8 -*-
"""agent 子系统单测：ToolRegistry / build_tool_registry / search_cases handler / run_react_loop。

全 mock（不碰 DB / LLM），可 pytest 跑，也可 `python -X utf8 tests/test_agent_tools.py` 自跑。
"""
import asyncio
import json
import os
import sys
from unittest.mock import patch, AsyncMock, MagicMock

# 独立运行（python -X utf8 tests/test_agent_tools.py）时把 backend 根加进 sys.path；
# pytest 走 conftest.py，不依赖这行。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── ToolRegistry ──────────────────────────────────────────────────────

def test_tool_registry_register_schemas_execute():
    from app.services.agent_tools import ToolRegistry
    reg = ToolRegistry()
    async def h(args): return {"got": args}
    reg.register("foo", "foo tool", {"type": "object", "properties": {"x": {"type": "string"}}}, h)
    schemas = reg.schemas()
    assert len(schemas) == 1 and schemas[0]["function"]["name"] == "foo"
    assert schemas[0]["type"] == "function"
    out = asyncio.run(reg.execute("foo", {"x": "1"}))
    assert out == {"got": {"x": "1"}}
    # 未知工具 → error dict，不抛
    assert "error" in asyncio.run(reg.execute("nope", {}))


def test_build_tool_registry_filtering():
    from app.services.agent_tools import build_tool_registry
    full = build_tool_registry({})
    all_names = set(full.names())
    # 默认启用全集（含 select_models / pick_kp_parts / build_plan / search_cases）
    assert "select_models" in all_names and "search_cases" in all_names
    # enabled_tools 过滤：只留选中的
    only_sel = build_tool_registry({"enabled_tools": ["select_models"]})
    assert only_sel.names() == ["select_models"]


def test_search_cases_handler_off_returns_empty():
    """case_source=off → get_caseProvider 返回空 CaseProvider → retrieve [] 。"""
    from app.services.agent_tools import _search_cases_handler
    h = _search_cases_handler({"case_source": "off", "case_top_k": 2, "case_match": "tags_keyword"})
    out = asyncio.run(h({"query": "AI 服务器"}))
    assert out["count"] == 0 and out["cases"] == []


def test_search_cases_handler_uses_provider(monkeypatch=None):
    """case_source=internal → 调 InternalBomCaseProvider.retrieve（这里 mock 掉 DB）。"""
    from app.services import agent_tools
    fake_provider = MagicMock()
    fake_provider.retrieve.return_value = [{"requirement": "r", "scenario_tags": ["AI"], "l6_config": []}]
    with patch("app.services.case_provider.get_case_provider", return_value=fake_provider):
        h = agent_tools._search_cases_handler({"case_source": "internal", "case_top_k": 3, "case_match": "tags_keyword"})
        out = asyncio.run(h({"query": "8卡GPU", "tags": ["AI", "4U"]}))
    assert out["count"] == 1
    # retrieve 收到 query / tags / top_k
    args, kwargs = fake_provider.retrieve.call_args
    assert args[0] == "8卡GPU"  # query 是位置参数
    assert kwargs.get("tags") == ["AI", "4U"]
    assert kwargs.get("top_k") == 3


# ── run_react_loop ────────────────────────────────────────────────────

def _patch_llm(seq_or_raise):
    """把 llm_client.chat_json 换成按 seq 依次返回（或抛）的 async mock。"""
    if isinstance(seq_or_raise, BaseException):
        async def _h(messages, schema=None): raise seq_or_raise
        return _h
    seq = list(seq_or_raise)
    async def _h(messages, schema=None): return seq.pop(0)
    return _h


def test_react_final_no_tools():
    """无工具时，LLM 直接给 final → 返回 answer。"""
    from app.services import agent_react
    with patch("app.services.llm_client.chat_json", _patch_llm([{"action": "final", "answer": "ok"}])), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": []}, max_iterations=3))
    assert out["ok"] is True and out["answer"] == "ok" and out["iterations"] == 1


def test_react_calls_tool_then_final():
    """LLM 先 call_tool → 执行（mock registry 的 fake 工具）→ 喂回 → 再 final。"""
    from app.services import agent_react, agent_tools
    reg = agent_tools.ToolRegistry()
    seen = []
    async def fake_h(args):
        seen.append(args); return {"count": 1, "candidates": [{"name": "X"}]}
    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h)
    seq = [{"action": "call_tool", "tool": "fake_tool", "args": {"k": 1}, "thought": "go"},
           {"action": "final", "answer": "done"}]
    with patch("app.services.agent_react.build_tool_registry", return_value=reg), \
         patch("app.services.llm_client.chat_json", _patch_llm(seq)), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": ["fake_tool"]}, max_iterations=3))
    assert out["ok"] is True and out["answer"] == "done"
    assert seen == [{"k": 1}]
    assert len(out["tool_calls_log"]) == 1 and out["tool_calls_log"][0]["name"] == "fake_tool"


def test_react_llm_error_degrades():
    """LLM 抛 LLMError → ok=False（上层降级），不抛。"""
    from app.services import agent_react, llm_client
    with patch("app.services.llm_client.chat_json", _patch_llm(llm_client.LLMError("boom"))), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": []}, max_iterations=3))
    assert out["ok"] is False and out["answer"] == ""


def test_react_max_iterations_cap():
    """LLM 一直发非法 action → 超 max_iterations → ok=False（truncated）。"""
    from app.services import agent_react
    async def _always_bad(messages, schema=None): return {"action": "garbage"}
    with patch("app.services.llm_client.chat_json", _always_bad), \
         patch("app.services.llm_client.is_llm_enabled", return_value=True):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": []}, max_iterations=2))
    assert out["ok"] is False and out["iterations"] == 2


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        try:
            fn(); print(f"  ✅ {fn.__name__}"); passed += 1
        except Exception:
            print(f"  ❌ {fn.__name__}"); traceback.print_exc()
    print(f"\n{passed}/{len(fns)} passed")
