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
    from app.services.agent_tool_registry import ToolRegistry
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
    from app.services.agent_tool_specs import build_tool_registry
    full = build_tool_registry({})
    all_names = set(full.names())
    # 默认启用全集（含 select_models / select_parts / build_plan / search_cases）
    assert "select_models" in all_names and "search_cases" in all_names
    # enabled_tools 过滤：只留选中的
    only_sel = build_tool_registry({"enabled_tools": ["select_models"]})
    assert only_sel.names() == ["select_models"]


def test_search_cases_handler_off_returns_empty():
    """case_source=off → get_caseProvider 返回空 CaseProvider → retrieve [] 。"""
    from app.services.agent_tool_handlers import _search_cases_handler
    h = _search_cases_handler({"case_source": "off", "case_top_k": 2, "case_match": "tags_keyword"})
    out = asyncio.run(h({"query": "AI 服务器"}))
    assert out["count"] == 0 and out["cases"] == []


def test_search_cases_handler_uses_provider(monkeypatch=None):
    """case_source=internal → 调 InternalBomCaseProvider.retrieve（这里 mock 掉 DB）。"""
    from app.services import agent_tool_handlers as agent_tools
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


def test_cost_breakdown_tool():
    from app.services.agent_tool_handlers import _tool_cost_breakdown
    out = asyncio.run(_tool_cost_breakdown({
        "plan": {
            "name": "4U AI 服务器",
            "model": "X100",
            "summary": {
                "l6_cost": 12000.0,
                "kp_cost": 88000.0,
                "total_cost": 100000.0,
                "currency": "RMB",
            },
        },
    }))
    assert out["cost"]["total_cost"] == 100000.0
    assert out["cost"]["l6_cost"] == 12000.0
    err = asyncio.run(_tool_cost_breakdown({}))
    assert "error" in err


def test_quote_draft_tool():
    from app.services.agent_tool_handlers import _tool_quote_draft
    out = asyncio.run(_tool_quote_draft({
        "plan": {
            "name": "4U AI 服务器",
            "model": "X100",
            "summary": {"total_cost": 100000.0, "currency": "RMB"},
        },
    }))
    assert out["draft"]["base_cost"] == 100000.0
    assert out["draft"]["status"] == "draft"
    assert "final_price" in out["draft"]
    err = asyncio.run(_tool_quote_draft({}))
    assert "error" in err


# ── run_react_loop ────────────────────────────────────────────────────


def _patch_stream(seq_or_raise):
    """把 llm_client.stream_agent_chat 换成按 seq 依次吐 JSON 片段的 async generator。

    每次调用 stream_agent_chat（Loop 的每一轮）取下一个 turn；数据耗尽重复最后一个，
    避免无限重试把测试拖死。异常分支仍是 async generator，保证 async for 能捕获。
    """
    if isinstance(seq_or_raise, BaseException):
        async def _ag(messages, model=None):
            raise seq_or_raise
            yield  # pragma: no cover 保持 async generator 语义
        return _ag
    seq = list(seq_or_raise)
    idx = 0
    async def _ag(messages, model=None):
        nonlocal idx
        it = seq[idx] if idx < len(seq) else (seq[-1] if seq else {"action": "final", "answer": ""})
        idx += 1
        yield {"type": "content", "delta": json.dumps(it, ensure_ascii=False)}
    return _ag


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
    from app.services import agent_react, llm_client
    with patch("app.services.llm_client.stream_agent_chat", _patch_stream([{"action": "final", "answer": "ok"}])),          patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=llm_client.LLMNativeToolsUnsupported("unsupported"))),          patch("app.services.llm_client.is_llm_enabled", return_value=True):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": []}, max_iterations=3))
    assert out["ok"] is True and out["answer"] == "ok" and out["iterations"] == 1


def test_react_calls_tool_then_final():
    """LLM 先 call_tool → 执行（mock registry 的 fake 工具）→ 喂回 → 再 final。"""
    from app.services import agent_react, llm_client
    from app.services.agent_tool_registry import ToolRegistry
    reg = ToolRegistry()
    seen = []
    async def fake_h(args):
        seen.append(args)
        return {"count": 1, "candidates": [{"name": "X"}]}
    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h)
    seq = [{"action": "call_tool", "tool": "fake_tool", "args": {"k": 1}, "thought": "go"},
           {"action": "final", "answer": "done"}]
    with patch("app.services.agent_react.build_tool_registry", return_value=reg),          patch("app.services.llm_client.stream_agent_chat", _patch_stream(seq)),          patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=llm_client.LLMNativeToolsUnsupported("unsupported"))),          patch("app.services.llm_client.is_llm_enabled", return_value=True):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": ["fake_tool"]}, max_iterations=3))
    assert out["ok"] is True and out["answer"] == "done"
    assert seen == [{"k": 1}]
    assert len(out["tool_calls_log"]) == 1 and out["tool_calls_log"][0]["name"] == "fake_tool"


def test_react_llm_error_degrades():
    """LLM 抛 LLMError → ok=False（上层降级），不抛。"""
    from app.services import agent_react, llm_client
    with patch("app.services.llm_client.stream_agent_chat", _patch_stream(llm_client.LLMError("boom"))),          patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=llm_client.LLMNativeToolsUnsupported("unsupported"))),          patch("app.services.llm_client.is_llm_enabled", return_value=True):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": []}, max_iterations=3))
    assert out["ok"] is False and out["answer"] == ""


def test_react_max_iterations_cap():
    """LLM 一直发非法 action → 超 max_iterations → ok=False（truncated）。"""
    from app.services import agent_react, llm_client
    async def _always_bad(messages, model=None):
        yield {"type": "content", "delta": json.dumps({"action": "garbage"})}
    with patch("app.services.llm_client.stream_agent_chat", _always_bad),          patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=llm_client.LLMNativeToolsUnsupported("unsupported"))),          patch("app.services.llm_client.is_llm_enabled", return_value=True):
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
