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


def _probe_fake_resp(payload, status=200):
    class R:
        status_code = status
        text = ""
        def json(_self):
            return payload
    return R()


def test_probe_anthropic_detects_tools_and_json():
    from app.services import llm_client

    json_probe = {"content": [{"type": "text", "text": "{\"ok\": true}"}]}
    tools_probe = {"content": [{"type": "tool_use", "id": "c1", "name": "get_time", "input": {}}]}
    with patch("requests.post", side_effect=[_probe_fake_resp(json_probe), _probe_fake_resp(tools_probe)]) as m:
        out = llm_client._probe_anthropic({
            "base_url": "https://api.z.ai/api/anthropic",
            "api_key": "k", "model": "glm-5.3-flash",
        })
    assert out["success"] is True
    assert out["supports_json_mode"] is True and out["supports_native_tools"] is True
    # 协议路径：{base}/v1/messages，x-api-key 头
    url = m.call_args_list[0].args[0]
    assert url.endswith("/api/anthropic/v1/messages")
    assert m.call_args_list[0].kwargs["headers"]["x-api-key"] == "k"
    # 工具探测确实带了 tools
    assert "tools" in m.call_args_list[1].kwargs["json"]


def test_probe_anthropic_wrapped_error_not_silent():
    from app.services import llm_client

    wrapped = {"code": 500, "msg": "404 NOT_FOUND", "success": False}
    with patch("requests.post", side_effect=[_probe_fake_resp(wrapped), _probe_fake_resp(wrapped)]):
        out = llm_client._probe_anthropic({
            "base_url": "https://api.z.ai/api/anthropic", "api_key": "k", "model": "glm-5.3-flash",
        })
    assert out["supports_native_tools"] is False
    assert any("404" in n for n in out["notes"])  # 真实错误进了 notes，不是静默 False


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


def test_stream_agent_chat_without_tools_routes_to_anthropic():
    """upstream_format=anthropic 时【纯文本】也必须走 anthropic 通道——这是 2026-09-14
    空回复事故的根因：旧代码只在带 tools 时分流，纯文本走 OpenAI SDK 打错路径。"""
    from app.services import llm_client
    from app.services import anthropic_channel as ac

    calls = []
    async def fake_stream(*args, **kwargs):
        calls.append((args, kwargs))
        yield {"type": "content", "delta": "hi"}

    def _forbidden(*args, **kwargs):
        raise AssertionError("anthropic 上游不允许创建 OpenAI client")

    with patch.object(llm_client, "_get_llm_config", return_value=_anthropic_config()), \
         patch.object(ac, "stream", new=fake_stream), \
         patch.object(llm_client, "_client", side_effect=_forbidden):
        events = _collect(llm_client.stream_agent_chat([{"role": "user", "content": "hi"}]))
    assert [e["delta"] for e in events if e["type"] == "content"] == ["hi"]
    assert calls and calls[0][1].get("tools") is None


def test_stream_agent_chat_anthropic_budget_exhaustion_yields_truncated_notice():
    """思考耗尽预算（stop_reason=max_tokens）且零正文时，必须 yield truncated 兜底，
    绝不让上层拿到空气（『(空回复)』防线）。"""
    from app.services import llm_client
    from app.services import anthropic_channel as ac

    async def fake_stream(*args, **kwargs):
        yield {"type": "reasoning", "delta": "思考……"}
        yield {"type": "meta", "stop_reason": "max_tokens", "usage": {"output_tokens": 4096}}

    with patch.object(llm_client, "_get_llm_config", return_value=_anthropic_config()), \
         patch.object(ac, "stream", new=fake_stream):
        events = _collect(llm_client.stream_agent_chat([{"role": "user", "content": "hi"}]))
    fallback = [e for e in events if e.get("type") == "content"]
    assert len(fallback) == 1 and fallback[0].get("truncated") is True


def test_stream_chat_pure_text_routes_to_anthropic():
    """stream_chat（question_gen 简单流式）在 anthropic 上游也必须分流。"""
    from app.services import llm_client
    from app.services import anthropic_channel as ac

    calls = []
    async def fake_stream(*args, **kwargs):
        calls.append((args, kwargs))
        yield {"type": "content", "delta": "he"}
        yield {"type": "content", "delta": "llo"}
        yield {"type": "meta", "stop_reason": "end_turn", "usage": {}}

    def _forbidden(*args, **kwargs):
        raise AssertionError("anthropic 上游不允许创建 OpenAI client")

    with patch.object(llm_client, "_get_llm_config", return_value=_anthropic_config()), \
         patch.object(ac, "stream", new=fake_stream), \
         patch.object(llm_client, "_client", side_effect=_forbidden):
        chunks = _collect(llm_client.stream_chat([{"role": "user", "content": "hi"}]))
    assert chunks == ["he", "llo"]
    assert calls and calls[0][1].get("tools") is None


def test_stream_chat_anthropic_empty_reply_yields_diagnosis():
    """空流 + stop_reason=max_tokens → 诊断文案而非静默空。"""
    from app.services import llm_client
    from app.services import anthropic_channel as ac

    async def fake_stream(*args, **kwargs):
        yield {"type": "meta", "stop_reason": "max_tokens", "usage": {}}

    with patch.object(llm_client, "_get_llm_config", return_value=_anthropic_config()), \
         patch.object(ac, "stream", new=fake_stream):
        chunks = _collect(llm_client.stream_chat([{"role": "user", "content": "hi"}]))
    assert len(chunks) == 1 and "token" in chunks[0]


def test_chat_json_routes_to_anthropic():
    """chat_json（11 个调用方：skill 反问/大脑/记忆抽取）在 anthropic 上游走
    anthropic_channel.chat，无 response_format，同一套解析收口。"""
    from app.services import llm_client
    from app.services import anthropic_channel as ac

    async def fake_chat(*args, **kwargs):
        return {"message": {"role": "assistant", "content": '{"ok": 1}', "tool_calls": []},
                "tool_calls": []}

    def _forbidden(*args, **kwargs):
        raise AssertionError("anthropic 上游不允许创建 OpenAI client")

    with patch.object(llm_client, "_get_llm_config", return_value=_anthropic_config()), \
         patch.object(ac, "chat", new=AsyncMock(side_effect=fake_chat)) as m_chat, \
         patch.object(llm_client, "_client", side_effect=_forbidden):
        data = asyncio.run(llm_client.chat_json([{"role": "user", "content": "回 JSON"}]))
    assert data == {"ok": 1}
    assert m_chat.await_count == 1


def test_chat_json_anthropic_empty_content_raises_after_retry():
    """anthropic 分支正文为空（如思考耗尽预算）→ 按既有语义 raise LLMError（上层降级）。"""
    from app.services import llm_client
    from app.services import anthropic_channel as ac

    async def fake_chat(*args, **kwargs):
        return {"message": {"role": "assistant", "content": "", "tool_calls": []}, "tool_calls": []}

    with patch.object(llm_client, "_get_llm_config", return_value=_anthropic_config()), \
         patch.object(ac, "chat", new=AsyncMock(side_effect=fake_chat)):
        try:
            asyncio.run(llm_client.chat_json([{"role": "user", "content": "hi"}]))
            assert False, "应当抛出 LLMError"
        except llm_client.LLMError:
            pass


# ── 探测留档：键=model@协议@域名、旧键迁移、端点身份、实测清单 ──────────

def test_probe_store_host_keyed_and_legacy_migration():
    from app.services import llm_client
    """旧版 model@协议 键自动迁移到 model@协议@域名并回填 model；能力注入按当前端点找记录。"""
    legacy = {
        "glm-5.3-flash@anthropic": {
            "success": True, "supports_native_tools": True, "native_tools_probed": True,
            "tested_at": "2026-09-15T00:05:53", "upstream_format": "anthropic",
            "base_url": "https://api.z.ai/api/anthropic",
        },
    }
    out = llm_client._normalize_probe_records(legacy)
    assert "glm-5.3-flash@anthropic@api.z.ai" in out
    assert out["glm-5.3-flash@anthropic@api.z.ai"]["model"] == "glm-5.3-flash"

    cfg = {"model": "glm-5.3-flash", "upstream_format": "anthropic",
           "base_url": "https://api.z.ai/api/anthropic"}
    with patch.object(llm_client, "_load_probe_records", return_value=out):
        assert llm_client._probe_capabilities_for(cfg) == {"supports_native_tools": True}
    # 同模型同协议但换了端点 → 找不到记录，不误用旧结论
    cfg_other = dict(cfg, base_url="http://api.cloudprime.com.cn:5567/v1")
    with patch.object(llm_client, "_load_probe_records", return_value=out):
        assert llm_client._probe_capabilities_for(cfg_other) == {}


def test_endpoint_identity_buckets():
    from app.services import llm_client
    """端点身份：官方域名=official，localhost/内网（含带端口）=local，其余公网=relay。"""
    assert llm_client._endpoint_identity("https://api.z.ai/api/anthropic") == ("智谱官方", "official")
    assert llm_client._endpoint_identity("http://127.0.0.1:11434/v1")[1] == "local"
    assert llm_client._endpoint_identity("http://192.168.1.5:8000/v1")[1] == "local"
    assert llm_client._endpoint_identity("http://api.cloudprime.com.cn:5567/v1") == ("第三方中转/自建", "relay")


def test_list_probe_history_marks_current():
    from app.services import llm_client
    """清单含失败记录与历史端点、按时间倒序，与当前配置（模型@协议@端点 三对上）的记录打 is_current。"""
    store = llm_client._normalize_probe_records({
        "glm-5.3-flash@anthropic": {
            "success": True, "json_mode_probed": True, "supports_json_mode": True,
            "tested_at": "2026-09-15T00:05:53", "upstream_format": "anthropic",
            "base_url": "https://api.z.ai/api/anthropic",
        },
        "qwen3.7-plus@openai@api.cloudprime.com.cn:5567": {
            "success": False, "message": "model_not_found",
            "tested_at": "2026-09-10T10:00:00", "upstream_format": "openai",
            "base_url": "http://api.cloudprime.com.cn:5567/v1", "model": "qwen3.7-plus",
        },
    })
    cfg = {"model": "glm-5.3-flash", "upstream_format": "anthropic",
           "base_url": "https://api.z.ai/api/anthropic"}
    with patch.object(llm_client, "_load_probe_records", return_value=store), \
         patch.object(llm_client, "_get_llm_config", return_value=cfg):
        out = llm_client.list_probe_history()
    recs = out["records"]
    assert len(recs) == 2 and recs[0]["tested_at"] >= recs[1]["tested_at"]
    cur = [r for r in recs if r["is_current"]]
    assert len(cur) == 1 and cur[0]["model"] == "glm-5.3-flash"
    failed = [r for r in recs if r["success"] is False]
    assert len(failed) == 1 and failed[0]["endpoint_identity_kind"] == "relay"


if __name__ == "__main__":
    for fn in [v for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]:
        fn()
        print("[ok]", fn.__name__)
