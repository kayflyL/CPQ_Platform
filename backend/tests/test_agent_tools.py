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


def test_tool_registry_schemas_uses_summary():
    """OpenAI 契约：schemas() 的 function.description 应取简短 summary，而非冗长 description。"""
    from app.services.agent_tool_registry import ToolRegistry
    reg = ToolRegistry()
    async def h(args): return {}
    reg.register("foo", "这是一段非常长的完整描述……供前端/人查看，不应喂给模型", {"type": "object", "properties": {}}, h,
                 summary="简短的工具用途与时机")
    schema = reg.schemas()[0]["function"]
    assert schema["name"] == "foo"
    assert schema["description"] == "简短的工具用途与时机"
    assert "完整描述" not in schema["description"]


def test_tool_catalog_exposes_summary():
    """tool_catalog() 每个条目应带 summary；缺省回退 description，老数据不炸。"""
    from app.services.agent_tool_specs import _TOOL_SPECS, tool_catalog
    cat = {t["name"]: t for t in tool_catalog()}
    assert "summary" in cat["fill_requirement"]
    assert cat["fill_requirement"]["summary"] == _TOOL_SPECS["fill_requirement"]["summary"]
    # 没有 summary 的老条目不报错
    assert "summary" in cat["query_data"]


def test_build_tool_registry_filtering():
    from app.services.agent_tool_specs import build_tool_registry
    full = build_tool_registry({})
    all_names = set(full.names())
    # 默认启用全集（含 choose_model / search_cases）
    assert "choose_model" in all_names and "search_cases" in all_names
    # enabled_tools 过滤：只留选中的
    only_sel = build_tool_registry({"enabled_tools": ["choose_model"]})
    assert only_sel.names() == ["choose_model"]


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


# ── run_react_loop ────────────────────────────────────────────────────


def _native_tool_call(name, args, call_id="call_1"):
    """构造 chat_with_tools 返回的原生 tool_call 响应。"""
    return {
        "message": {"role": "assistant", "content": None},
        "tool_calls": [{"id": call_id, "name": name, "arguments": args,
                        "arguments_raw": json.dumps(args, ensure_ascii=False)}],
    }


def _native_final(answer):
    """构造 chat_with_tools 返回的最终文本响应。"""
    return {"message": {"role": "assistant", "content": answer}, "tool_calls": []}


def test_react_final_no_tools():
    """原生 function calling：无工具调用，LLM 直接给文本 → 返回 answer。"""
    from app.services import agent_react
    with patch("app.services.llm_client.chat_with_tools", AsyncMock(return_value=_native_final("ok"))):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": []}, max_iterations=3))
    assert out["ok"] is True and out["answer"] == "ok" and out["iterations"] == 1


def test_react_calls_tool_then_final():
    """LLM 先 native tool_call → 执行（fake 工具）→ 喂回 → 再最终文本。"""
    from app.services import agent_react
    from app.services.agent_tool_registry import ToolRegistry
    reg = ToolRegistry()
    seen = []
    async def fake_h(args):
        seen.append(args)
        return {"count": 1, "candidates": [{"name": "X"}]}
    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h)
    responses = [_native_tool_call("fake_tool", {"k": 1}), _native_final("done")]
    with patch("app.services.agent_react.build_tool_registry", return_value=reg), \
            patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=responses)):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": ["fake_tool"]}, max_iterations=3))
    assert out["ok"] is True and out["answer"] == "done"
    assert seen == [{"k": 1}]
    assert len(out["tool_calls_log"]) == 1 and out["tool_calls_log"][0]["name"] == "fake_tool"


def test_react_llm_error_degrades():
    """LLM 抛 LLMError → ok=False（上层降级），不抛。"""
    from app.services import agent_react, llm_client
    with patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=llm_client.LLMError("boom"))):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": []}, max_iterations=3))
    assert out["ok"] is False and out["answer"] == ""


def test_react_max_iterations_cap():
    """LLM 一直发 tool_call → 超 max_iterations → ok=False（截断）。"""
    from app.services import agent_react
    from app.services.agent_tool_registry import ToolRegistry
    reg = ToolRegistry()
    async def fake_h(args):
        return {"ok": True}
    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h)
    responses = [_native_tool_call("fake_tool", {"k": i}, call_id=f"call_{i}") for i in range(1, 6)]
    with patch("app.services.agent_react.build_tool_registry", return_value=reg), \
            patch("app.services.llm_client.chat_with_tools", AsyncMock(side_effect=responses)):
        out = asyncio.run(agent_react.run_react_loop("req", {"enabled_tools": ["fake_tool"]}, max_iterations=2))
    assert out["ok"] is False and out["iterations"] == 2


def test_stream_agent_chat_parses_tool_calls():
    """stream_agent_chat 应把流式 tool_calls 增量按 index 累积成 {type:tool_calls} 事件。"""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch
    from app.services import llm_client

    def _chunk(finish=None, content=None, tc=None):
        delta = SimpleNamespace(reasoning_content=None, content=content, tool_calls=tc)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, delta=delta)])

    async def _stream():
        yield _chunk(tc=[SimpleNamespace(index=0, id="call_1", function=SimpleNamespace(name="query_parts", arguments='{"category"'))])
        yield _chunk(tc=[SimpleNamespace(index=0, id=None, function=SimpleNamespace(name=None, arguments=': "CPU"}'))])
        yield _chunk(finish="tool_calls")

    fake_client = SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=AsyncMock(return_value=_stream()))))
    cfg = {"enabled": True, "base_url": "http://x", "api_key": "k", "model": "qwen-plus",
           "temperature": 0.7, "max_tokens": 1000}
    tools = [{"type": "function", "function": {"name": "query_parts", "parameters": {"type": "object", "properties": {}}}}]
    with patch.object(llm_client, "_get_llm_config", return_value=cfg), \
            patch.object(llm_client, "_client", return_value=fake_client):
        async def collect():
            out = []
            async for item in llm_client.stream_agent_chat([{"role": "user", "content": "hi"}], tools=tools, model="qwen-plus"):
                out.append(item)
            return out
        out = asyncio.run(collect())

    calls = [i for i in out if i.get("type") == "tool_calls"]
    assert calls, "缺少 tool_calls 事件"
    tc = calls[-1]["tool_calls"][0]
    assert tc["id"] == "call_1"
    assert tc["name"] == "query_parts"
    assert tc["arguments"] == {"category": "CPU"}


def test_run_stream_chat_loop_prefers_native_then_final():
    """原生流式 function calling：tool_calls 执行后喂回，再给 final 文本。"""
    import asyncio
    from unittest.mock import patch
    from app.services import agent_react
    from app.services.agent_tool_registry import ToolRegistry

    reg = ToolRegistry()
    seen = []
    async def fake_h(args):
        seen.append(args)
        return {"ok": True}
    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h, summary="fake")

    rounds = [
        [{"type": "tool_calls", "tool_calls": [{"id": "call_1", "name": "fake_tool", "arguments": {"k": 1}, "arguments_raw": "{\"k\": 1}"}]}],
        [{"type": "content", "delta": "done"}],
    ]
    idx = [0]
    async def _ag(messages, model=None, **kw):
        r = rounds[idx[0]] if idx[0] < len(rounds) else rounds[-1]
        idx[0] += 1
        for item in r:
            yield item

    with patch("app.services.agent_react.build_tool_registry", return_value=reg), \
            patch("app.services.llm_client.stream_agent_chat", _ag):
        out = asyncio.run(agent_react.run_stream_chat_loop(
            "req", {"enabled_tools": ["fake_tool"]}, system_prompt="sp", max_iterations=3))

    assert out["ok"] is True and out["answer"] == "done"
    assert seen == [{"k": 1}]
    assert len(out["tool_calls_log"]) == 1
    assert out["iterations"] == 2


def test_strictify_tools_only_when_required_complete():
    """_strictify_tools 仅在所有 object 字段都必填时加 additionalProperties:false + strict:true；
    存在可选字段则原样返回，避免我们的可选参数 schema 反打挂原生通道。"""
    from app.services.llm_client import _strictify_tools

    compat_tool = {"type": "function", "function": {
        "name": "foo",
        "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
    }}
    stricted = _strictify_tools([compat_tool])
    fn = stricted[0]["function"]
    assert fn["strict"] is True
    assert fn["parameters"]["additionalProperties"] is False

    optional_tool = {"type": "function", "function": {
        "name": "bar",
        "parameters": {"type": "object", "properties": {"x": {"type": "string", "description": "optional"}}},
    }}
    untouched = _strictify_tools([optional_tool])
    assert "strict" not in untouched[0]["function"]
    assert "additionalProperties" not in untouched[0]["function"]["parameters"]

    default_tool = {"type": "function", "function": {
        "name": "baz",
        "parameters": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
    }}
    assert _strictify_tools([default_tool])[0]["function"]["strict"] is True
    forbidden_tool = {"type": "function", "function": {
        "name": "qux",
        "parameters": {"type": "object", "properties": {"x": {"type": "string", "default": "a"}}, "required": ["x"]},
    }}
    assert "strict" not in _strictify_tools([forbidden_tool])[0]["function"]


def test_model_supports_strict_tools_probed():
    """实测（probe_capabilities）能把 supports_strict_tools 抬为 True（否则保持保守默认 False）。"""
    from app.services import llm_client
    caps = llm_client.get_model_capabilities("qwen-plus", {
        "model": "qwen-plus",
        "probe_capabilities": {"supports_strict_tools": True},
    })
    assert caps["supports_strict_tools"] is True
    default_caps = llm_client.get_model_capabilities("qwen-plus", {"model": "qwen-plus"})
    assert default_caps["supports_strict_tools"] is False


def test_tool_registry_execute_timeout():
    """工具执行超时按失败返回模型可见错误（对标 OpenAI error_as_result），不抛异常。"""
    from app.services.agent_tool_registry import ToolRegistry, _TOOL_CALL_TIMEOUT
    from unittest.mock import patch
    reg = ToolRegistry()
    async def slow_handle(args):
        import asyncio
        await asyncio.sleep(0.2)
        return {"ok": True}
    reg.register("slow", "slow", {"type": "object", "properties": {}}, slow_handle)
    with patch("app.services.agent_tool_registry._TOOL_CALL_TIMEOUT", 0.01):
        out = asyncio.run(reg.execute("slow", {}))
    assert "error" in out and "超时" in out["error"]


def test_cap_tool_context_terminates_and_shrinks():
    """工具上下文压缩必须收敛：压缩后长度(≈312)低于 victim 门槛(400)，
    否则同一条消息被反复压缩到同样长度 → 死循环卡死事件循环（2026-09-12 py-spy 实测）。"""
    from app.services.agent_react import _cap_tool_context, _TOOL_CONTEXT_CAP_CHARS
    msgs = [{"role": "tool", "content": "x" * 450} for _ in range(60)]  # 27000 字 > 20000 上限
    _cap_tool_context(msgs)  # 旧实现（COMPRESS_TO=400=门槛）在此永久死循环
    total = sum(len(m["content"]) for m in msgs)
    assert total <= _TOOL_CONTEXT_CAP_CHARS
    assert "已压缩" in msgs[0]["content"]      # 最老的被压缩
    assert msgs[-1]["content"] == "x" * 450    # 最近的保持完整
    assert all(len(m["content"]) <= 400 for m in msgs if "已压缩" in m["content"])  # 压缩过的不再可被选中


def _stream_rounds(rounds):
    """把若干轮事件列表包成 stream_agent_chat 假件（逐轮出队）。"""
    idx = [0]

    async def _ag(messages, model=None, **kw):
        if idx[0] < len(rounds):
            r = rounds[idx[0]]
            idx[0] += 1
        else:
            r = rounds[-1]
        if isinstance(r, Exception):
            raise r
        for item in r:
            yield item

    return _ag


def test_stream_loop_intermediate_prose_superseded():
    """覆盖语义（2026-09-16）：带工具调用轮次的正文=过程旁白，被收口轮覆盖而非拼接——
    曾把「核对通过：…」旁白粘进最终报告。"""
    import asyncio
    from unittest.mock import patch
    from app.services import agent_react
    from app.services.agent_tool_registry import ToolRegistry

    reg = ToolRegistry()
    async def fake_h(args):
        return {"ok": True}
    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h)

    rounds = [
        [{"type": "content", "delta": "核对通过：本月商机 18。继续取数。"},
         {"type": "tool_calls", "tool_calls": [{"id": "c1", "name": "fake_tool",
                                                "arguments": {}, "arguments_raw": "{}"}]}],
        [{"type": "content", "delta": "数据范围：2026.01.01 ~ 2026.09.16\n\n## 一、周数据"}],
    ]
    with patch("app.services.agent_react.build_tool_registry", return_value=reg), \
            patch("app.services.llm_client.stream_agent_chat", _stream_rounds(rounds)):
        out = asyncio.run(agent_react.run_stream_chat_loop(
            "req", {"enabled_tools": ["fake_tool"]}, system_prompt="sp", max_iterations=3))

    assert out["ok"] is True
    assert out["answer"] == "数据范围：2026.01.01 ~ 2026.09.16\n\n## 一、周数据"
    assert "核对通过" not in out["answer"]


def test_stream_loop_llm_error_salvages_latest_prose():
    """LLM 断流兜底取最近一轮非空正文（旁白），不是历史旁白的拼接。"""
    import asyncio
    from unittest.mock import patch
    from app.services import agent_react, llm_client
    from app.services.agent_tool_registry import ToolRegistry

    reg = ToolRegistry()
    async def fake_h(args):
        return {"ok": True}
    reg.register("fake_tool", "fake", {"type": "object", "properties": {}}, fake_h)

    rounds = [
        [{"type": "content", "delta": "旁白一"},
         {"type": "tool_calls", "tool_calls": [{"id": "c1", "name": "fake_tool",
                                                "arguments": {}, "arguments_raw": "{}"}]}],
        [{"type": "content", "delta": "旁白二"},
         {"type": "tool_calls", "tool_calls": [{"id": "c2", "name": "fake_tool",
                                                "arguments": {}, "arguments_raw": "{}"}]}],
        llm_client.LLMError("conn reset"),
    ]
    with patch("app.services.agent_react.build_tool_registry", return_value=reg), \
            patch("app.services.llm_client.stream_agent_chat", _stream_rounds(rounds)):
        out = asyncio.run(agent_react.run_stream_chat_loop(
            "req", {"enabled_tools": ["fake_tool"]}, system_prompt="sp", max_iterations=3))

    assert out["ok"] is True and out["answer"] == "旁白二"


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
