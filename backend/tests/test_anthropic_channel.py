# -*- coding: utf-8 -*-
"""anthropic_channel 单测：OpenAI↔Anthropic tools/messages 转换、非流式解析、流式累积。

全 mock 网络（httpx.MockTransport），不碰 DB / 真实 LLM。跑法：
  pytest tests/test_anthropic_channel.py -q
  python -X utf8 tests/test_anthropic_channel.py   # 自跑
"""
import asyncio
import json
import os
import sys
from unittest.mock import patch, AsyncMock

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 捕获真实 AsyncClient：后续 patch anthropic_channel.httpx.AsyncClient 时，
# factory 内部再调 httpx.AsyncClient 会拿到被 patch 的 MagicMock 导致自递归。
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def test_anthropic_tools_convert_openai_to_anthropic():
    from app.services.anthropic_channel import anthropic_tools

    tools = [{
        "type": "function",
        "function": {
            "name": "fill_requirement",
            "description": "填充线索登记表",
            "parameters": {"type": "object", "properties": {"cpu": {"type": "string"}}},
        },
    }]
    out = anthropic_tools(tools)
    assert len(out) == 1
    assert out[0] == {
        "name": "fill_requirement",
        "description": "填充线索登记表",
        "input_schema": {"type": "object", "properties": {"cpu": {"type": "string"}}},
    }


def test_anthropic_tools_skips_bad_and_defaults_schema():
    from app.services.anthropic_channel import anthropic_tools

    tools = [
        {"type": "function", "function": {"name": "ok", "description": "d"}},
        {"function": {"name": "  ", "description": "bad"}},
    ]
    out = anthropic_tools(tools)
    assert len(out) == 1
    assert out[0]["name"] == "ok"
    assert out[0]["input_schema"] == {"type": "object", "properties": {}}


def test_to_anthropic_messages_system_tool_use_and_tool_result_merge():
    from app.services.anthropic_channel import to_anthropic_messages

    messages = [
        {"role": "system", "content": "你是助手"},
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "foo", "arguments": '{"x": 1}'}},
        ]},
        {"role": "tool", "tool_call_id": "call_1", "content": "ok"},
        {"role": "user", "content": "继续"},
    ]
    system, out = to_anthropic_messages(messages)
    assert system == "你是助手"
    assert out[0] == {"role": "user", "content": [{"type": "text", "text": "你好"}]}
    assert out[1] == {"role": "assistant", "content": [
        {"type": "tool_use", "id": "call_1", "name": "foo", "input": {"x": 1}},
    ]}
    # tool_result 与后续 user 文本合并进同一条 user，避免连发两条 user 被 Anthropic 拒绝
    assert out[2]["role"] == "user"
    block_types = [b["type"] for b in out[2]["content"]]
    assert block_types == ["tool_result", "text"]
    assert out[2]["content"][0]["tool_use_id"] == "call_1"
    assert out[2]["content"][1]["text"] == "继续"


def test_to_anthropic_messages_system_multi_merge():
    from app.services.anthropic_channel import to_anthropic_messages

    messages = [
        {"role": "system", "content": "提示A"},
        {"role": "system", "content": "提示B"},
        {"role": "user", "content": "hi"},
    ]
    system, out = to_anthropic_messages(messages)
    assert system == "提示A\n\n提示B"
    assert len(out) == 1


def test_parse_nonstream_text_and_tool_use():
    from app.services.anthropic_channel import _parse_nonstream

    data = {
        "content": [
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "id": "call_1", "name": "fill_requirement", "input": {"cpu": "AMD"}},
        ],
    }
    res = _parse_nonstream(data)
    assert res["message"]["role"] == "assistant"
    assert res["message"]["content"] == "hello"
    assert res["tool_calls"][0]["id"] == "call_1"
    assert res["tool_calls"][0]["name"] == "fill_requirement"
    assert res["tool_calls"][0]["arguments"] == {"cpu": "AMD"}
    assert json.loads(res["tool_calls"][0]["arguments_raw"]) == {"cpu": "AMD"}
    raw_tc = res["message"]["tool_calls"][0]
    assert raw_tc["function"]["name"] == "fill_requirement"
    assert json.loads(raw_tc["function"]["arguments"]) == {"cpu": "AMD"}


def _collect(agen):
    """把异步生成器收集为 list（供 asyncio.run 使用）。"""
    async def go():
        return [item async for item in agen]
    return asyncio.run(go())


def test_stream_emits_content_and_tool_calls_events():
    from app.services import anthropic_channel

    sse = (
        'data: {"type":"message_start","message":{}}\n\n'
        'data: {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}\n\n'
        'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"hello"}}\n\n'
        'data: {"type":"content_block_stop","index":0}\n\n'
        'data: {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"call_1","name":"foo","input":{}}}\n\n'
        'data: {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\\"x\\": 1}"}}\n\n'
        'data: {"type":"content_block_stop","index":1}\n\n'
        'data: {"type":"message_delta","delta":{"stop_reason":"tool_use"}}\n\n'
        'data: {"type":"message_stop"}\n\n'
        'data: [DONE]\n\n'
    )

    def handler(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=sse.encode("utf-8"))

    def patched_client(*args, **kwargs):
        kwargs.pop("trust_env", None)
        kwargs.pop("timeout", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), timeout=30.0)

    with patch.object(anthropic_channel.httpx, "AsyncClient", side_effect=patched_client):
        events = _collect(anthropic_channel.stream(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "foo", "description": "d", "parameters": {"type": "object"}}}],
            model="m", base_url="http://x/v1", api_key="k", max_tokens=128,
        ))

    content_deltas = [e["delta"] for e in events if e["type"] == "content"]
    assert content_deltas == ["hello"]
    tool_events = [e for e in events if e["type"] == "tool_calls"]
    assert len(tool_events) == 1
    tcs = tool_events[0]["tool_calls"]
    assert tcs[0]["name"] == "foo"
    assert tcs[0]["arguments"] == {"x": 1}
    assert json.loads(tcs[0]["arguments_raw"]) == {"x": 1}


def test_chat_parses_nonstream_through_real_client():
    """非流式 chat 端到端：MockTransport 返回 Anthropic JSON，验证返回契约。"""
    from app.services import anthropic_channel

    body = json.dumps({
        "content": [
            {"type": "text", "text": "hi"},
            {"type": "tool_use", "id": "call_1", "name": "foo", "input": {"q": "1"}},
        ],
        "role": "assistant",
        "stop_reason": "tool_use",
    }).encode("utf-8")

    def handler(request):
        return httpx.Response(200, headers={"content-type": "application/json"}, content=body)

    def patched_client(*args, **kwargs):
        kwargs.pop("trust_env", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), timeout=30.0)

    with patch.object(anthropic_channel.httpx, "AsyncClient", side_effect=patched_client):
        res = asyncio.run(anthropic_channel.chat(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "foo", "description": "d", "parameters": {"type": "object"}}}],
            model="m", base_url="http://x/v1", api_key="k", max_tokens=128,
        ))

    assert res["message"]["content"] == "hi"
    assert res["tool_calls"][0]["name"] == "foo"
    assert res["tool_calls"][0]["arguments"] == {"q": "1"}


def test_chat_raises_anthropic_error_on_non_200():
    from app.services import anthropic_channel

    def handler(request):
        return httpx.Response(400, content=json.dumps({"error": {"message": "unknown tool"}}))

    def patched_client(*args, **kwargs):
        kwargs.pop("trust_env", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), timeout=30.0)

    with patch.object(anthropic_channel.httpx, "AsyncClient", side_effect=patched_client):
        try:
            asyncio.run(anthropic_channel.chat(
                [{"role": "user", "content": "hi"}],
                model="m", base_url="http://x/v1", api_key="k", max_tokens=128,
            ))
            assert False, "应当抛出 AnthropicChannelError"
        except anthropic_channel.AnthropicChannelError as e:
            assert "400" in str(e)


def _anthropic_config(**over):
    cfg = {
        "enabled": True,
        "base_url": "http://x/v1",
        "api_key": "k",
        "model": "deepseek-v4-flash",
        "temperature": 0.7,
        "max_tokens": 16000,
        "capabilities_override": {},
        "upstream_format": "anthropic",
    }
    cfg.update(over)
    return cfg


def test_chat_with_tools_routes_to_anthropic_and_keeps_caller_messages():
    """upstream_format=anthropic 时，chat_with_tools 应路由到 anthropic_channel.chat，
    并且**不**替调用方捏造 system 提示词（提示词只有配置层一个来源，client 无兜底）。"""
    from app.services import llm_client
    from app.services import anthropic_channel as ac

    async def fake_chat(*args, **kwargs):
        return {"message": {"role": "assistant", "content": "hi", "tool_calls": []}, "tool_calls": []}

    with patch.object(llm_client, "_get_llm_config", return_value=_anthropic_config()), \
         patch.object(ac, "chat", new=AsyncMock(side_effect=fake_chat)) as m_chat:
        res = asyncio.run(llm_client.chat_with_tools(
            [{"role": "user", "content": "配置一台服务器"}],
            tools=[{"type": "function", "function": {"name": "foo", "description": "d", "parameters": {"type": "object"}}}],
        ))
    assert res["message"]["content"] == "hi"
    m_chat.assert_called_once()
    assert m_chat.call_args.args[0] == [{"role": "user", "content": "配置一台服务器"}]


def test_stream_agent_chat_routes_to_anthropic_and_keeps_caller_messages():
    """upstream_format=anthropic 且带 tools 时，stream_agent_chat 应路由到 anthropic_channel.stream。"""
    from app.services import llm_client
    from app.services import anthropic_channel as ac

    calls = []
    async def fake_stream(*args, **kwargs):
        calls.append((args, kwargs))
        yield {"type": "content", "delta": "hello"}

    with patch.object(llm_client, "_get_llm_config", return_value=_anthropic_config()), \
         patch.object(ac, "stream", new=fake_stream):
        events = _collect(llm_client.stream_agent_chat(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "foo", "description": "d", "parameters": {"type": "object"}}}],
        ))
    assert [e["delta"] for e in events if e["type"] == "content"] == ["hello"]
    assert calls and calls[0][0][0] == [{"role": "user", "content": "hi"}]


if __name__ == "__main__":
    for fn in [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]:
        fn()
        print("[ok]", fn.__name__)
