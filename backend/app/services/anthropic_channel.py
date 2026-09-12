# -*- coding: utf-8 -*-
"""anthropic_channel —— Anthropic Messages 上游通道（OpenAI 风格 tools/messages 双向转换）。

背景：经实测，cloudprime 这类供应商的 /v1/chat/completions 只认 web_search_* 工具类型，
不认 OpenAI 的 type:function；而 /v1/messages 是真正的 Anthropic Messages API。因此要在
原生 function calling 下跑通，需把平台内部的 OpenAI 风格 tools/messages 端到端转成
Anthropic Messages（等价于 CC Switch/LiteLLM 所做的格式转换）。

本模块只做转换与传输，不依赖 llm_client；llm_client 在 upstream_format="anthropic" 时
把「带 tools 的调用」路由到这里，文本/JSON 走原 OpenAI Chat Completions（实测正常）。
"""
import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

_ANTHROPIC_VERSION = "2023-06-01"
_CONNECT_TIMEOUT = 15.0


class AnthropicChannelError(RuntimeError):
    """Anthropic 通道异常（含上游 400/传输失败），由 llm_client 收口成 LLMError。"""


class AnthropicTimeoutError(AnthropicChannelError):
    """看门狗/墙钟超时（连接挂死，或单轮长时间持续输出却迟迟不收敛）。

    超时与「通道不支持原生 tools」是两码事：超时必须收口成 LLMError（可重试/可如实失败），
    不能误报成 unsupported 让上层白降级掉原生工具通道。
    """


def anthropic_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """OpenAI 风格 tools → Anthropic tools [{name,description,input_schema}]。"""
    out: List[Dict[str, Any]] = []
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        fn = t.get("function") if isinstance(t.get("function"), dict) else t
        name = str(fn.get("name") or t.get("name") or "").strip()
        if not name:
            continue
        desc = str(fn.get("description") or t.get("description") or "").strip()
        params = fn.get("parameters") or t.get("parameters") or t.get("input_schema")
        if not isinstance(params, dict):
            params = {"type": "object", "properties": {}}
        out.append({"name": name, "description": desc, "input_schema": params})
    return out


def to_anthropic_messages(messages: List[Dict[str, Any]]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """平台内部 messages → (system, anthropic messages)。

    规则：
      - system 提示词提到顶层 system（多条用 \\n\\n 拼接）。
      - assistant 的 tool_calls → content 里的 tool_use 块。
      - role=tool 的结果 → 紧随的 user 消息里的 tool_result 块；若后面紧跟新的 user 文本，
        合并进同一条 user 消息（避免连发两条 user 被 Anhthropic 拒绝）。
    """
    system: Optional[str] = None
    out: List[Dict[str, Any]] = []
    pending: Optional[Dict[str, Any]] = None  # 累积 tool_result 的 user 消息

    def _flush() -> None:
        nonlocal pending
        if pending is not None:
            out.append(pending)
            pending = None

    def _text_block(content: Any) -> Dict[str, Any]:
        return {"type": "text", "text": str(content or "")}

    for m in messages or []:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            text = str(content or "").strip()
            if text:
                system = (system + "\n\n" + text) if system else text
            continue
        if role == "tool":
            if pending is None:
                pending = {"role": "user", "content": []}
            pending["content"].append({
                "type": "tool_result",
                "tool_use_id": str(m.get("tool_call_id") or ""),
                "content": str(content or ""),
            })
            continue

        # 非 tool 消息：若正累积 tool_result，且是 user 文本，则并入；否则先落 pending
        if pending is not None:
            if role == "user":
                text = str(content or "")
                if text:
                    pending["content"].append(_text_block(text))
                continue
            _flush()

        if role == "assistant" and m.get("tool_calls"):
            blocks: List[Dict[str, Any]] = []
            if content:
                blocks.append(_text_block(content))
            for tc in m.get("tool_calls") or []:
                tc = tc if isinstance(tc, dict) else {}
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                args = fn.get("arguments") if isinstance(fn, dict) else tc.get("arguments")
                if args is None:
                    args = tc.get("arguments") or {}
                if not isinstance(args, dict):
                    try:
                        args = json.loads(args) if isinstance(args, str) else {}
                    except Exception:
                        args = {}
                blocks.append({
                    "type": "tool_use",
                    "id": str(tc.get("id") or f"call_{len(blocks)}"),
                    "name": str(fn.get("name") or tc.get("name") or ""),
                    "input": args if isinstance(args, dict) else {},
                })
            out.append({"role": "assistant", "content": blocks})
            continue

        text = str(content or "")
        if not text:
            continue
        out.append({"role": role, "content": [_text_block(text)]})

    _flush()
    return system, out


async def _raise_for_status(resp: httpx.Response, url: str) -> None:
    if resp.status_code == 200:
        return
    try:
        body = (await resp.aread()).decode("utf-8", "replace")
    except Exception:
        body = ""
    msg = f"Anthropic 上游 {resp.status_code} @ {url}"
    if body:
        msg += " :: " + body[:500]
    logger.error(msg)
    raise AnthropicChannelError(msg)


async def chat(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: Optional[float] = None,
    timeout: float = 180.0,
    reasoning_effort: Optional[str] = None,
) -> Dict[str, Any]:
    """非流式 Anthropic 调用，返回与 chat_with_tools 同契约的 dict。

    返回：{"message": raw_assistant_message, "tool_calls": [{id,name,arguments}]}
    """
    url = (base_url or "").rstrip("/") + "/messages"
    system, msgs = to_anthropic_messages(messages)
    payload: Dict[str, Any] = {"model": model, "messages": msgs, "max_tokens": int(max_tokens), "stream": False}
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = anthropic_tools(tools)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(_CONNECT_TIMEOUT, read=timeout, write=30, pool=30), trust_env=False) as client:
        resp = await client.post(url, headers=headers, json=payload)
        await _raise_for_status(resp, url)
        data = resp.json()
    return _parse_nonstream(data)


def _parse_nonstream(data: Dict[str, Any]) -> Dict[str, Any]:
    content = data.get("content") or []
    text_parts: List[str] = []
    tool_calls: List[Dict[str, Any]] = []
    raw_tool_calls: List[Dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        if btype == "text":
            text_parts.append(str(block.get("text") or ""))
        elif btype == "tool_use":
            tid = str(block.get("id") or f"call_{len(tool_calls)}")
            name = str(block.get("name") or "")
            args = block.get("input") if isinstance(block.get("input"), dict) else {}
            args_raw = json.dumps(args, ensure_ascii=False) if args else "{}"
            tool_calls.append({"id": tid, "name": name, "arguments": args, "arguments_raw": args_raw})
            raw_tool_calls.append({
                "id": tid, "type": "function",
                "function": {"name": name, "arguments": args_raw},
            })
    content_text = "".join(text_parts)
    raw_message = {
        "role": "assistant",
        "content": content_text or "",
        "tool_calls": raw_tool_calls,
    }
    return {"message": raw_message, "tool_calls": tool_calls}


async def stream(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    max_tokens: int = 4096,
    temperature: Optional[float] = None,
    timeout: float = 180.0,
    first_token_timeout: Optional[float] = None,
    reasoning_effort: Optional[str] = None,
    overall_timeout: Optional[float] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """流式 Anthropic 调用，yield 与 stream_agent_chat 一致的归一化事件：
      {type:reasoning,delta} / {type:content,delta} / {type:tool_calls,tool_calls:[...]}
    """
    url = (base_url or "").rstrip("/") + "/messages"
    system, msgs = to_anthropic_messages(messages)
    payload: Dict[str, Any] = {
        "model": model, "messages": msgs, "max_tokens": int(max_tokens), "stream": True,
    }
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = temperature
    if tools:
        payload["tools"] = anthropic_tools(tools)
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    guard = first_token_timeout or timeout
    # 单轮整体墙钟上限：间隔看门狗管不住「持续吐 thinking、迟迟不收敛」的慢速生成
    loop = asyncio.get_running_loop()
    overall_deadline = (loop.time() + float(overall_timeout)) if overall_timeout else None
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(_CONNECT_TIMEOUT, read=guard, write=30, pool=30), trust_env=False,
    ) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            if resp.status_code != 200:
                await _raise_for_status(resp, url)
                return  # 理论上不达
            aiter = resp.aiter_lines()
            blocks: Dict[int, Dict[str, Any]] = {}
            # 每个 content_block 的输入 JSON 累积
            pending_tool_inputs: Dict[int, str] = {}
            while True:
                try:
                    budget = guard
                    over = False    # 本次等待是否被「单轮墙钟上限」卡住 → 断连原因要如实
                    if overall_deadline is not None:
                        left = overall_deadline - loop.time()
                        if left <= 0:
                            raise AnthropicTimeoutError(
                                f"Anthropic 单轮生成整体超时：超过 {float(overall_timeout):.0f}s 仍未收敛，已断开")
                        if left < budget:
                            budget = left
                            over = True
                    line = await asyncio.wait_for(aiter.__anext__(), timeout=budget)
                except StopAsyncIteration:
                    break
                except asyncio.TimeoutError:
                    if over:
                        raise AnthropicTimeoutError(
                            f"Anthropic 单轮生成整体超时：超过 {float(overall_timeout):.0f}s 仍未收敛，已断开")
                    raise AnthropicTimeoutError(f"Anthropic 流式间隔超时：{guard:.0f}s 无数据，已断开")
                line = (line or "").strip()
                if not line or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    event = json.loads(data)
                except Exception:
                    continue
                etype = event.get("type")
                if etype == "ping":
                    continue
                if etype == "error":
                    err = event.get("error") or {}
                    raise AnthropicChannelError(f"Anthropic 上游错误: {str(err)[:300]}")
                if etype == "content_block_start":
                    cb = event.get("content_block") or {}
                    idx = int(event.get("index") or 0)
                    blocks[idx] = {
                        "type": cb.get("type"),
                        "id": cb.get("id") or "",
                        "name": cb.get("name") or "",
                        "text": [],
                        "thinking": [],
                    }
                    if cb.get("type") == "tool_use":
                        pending_tool_inputs[idx] = ""
                    continue
                if etype == "content_block_delta":
                    idx = int(event.get("index") or 0)
                    delta = event.get("delta") or {}
                    dtype = delta.get("type")
                    if dtype == "text_delta":
                        txt = str(delta.get("text") or "")
                        if txt:
                            yield {"type": "content", "delta": txt}
                    elif dtype == "thinking_delta":
                        th = str(delta.get("thinking") or "")
                        if th:
                            yield {"type": "reasoning", "delta": th}
                    elif dtype == "input_json_delta":
                        pending_tool_inputs[idx] = str(pending_tool_inputs.get(idx) or "") + str(delta.get("partial_json") or "")
                    continue
                if etype in ("content_block_stop", "message_delta", "message_stop"):
                    continue
            # 流结束：把累积的 tool_use 块转成 tool_calls 事件
            tool_calls: List[Dict[str, Any]] = []
            for idx in sorted(blocks):
                b = blocks[idx]
                if b.get("type") != "tool_use":
                    continue
                raw = pending_tool_inputs.get(idx) or ""
                try:
                    args = json.loads(raw) if raw.strip() else {}
                except Exception:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                tool_calls.append({
                    "id": b.get("id") or f"call_{idx}",
                    "name": b.get("name") or "",
                    "arguments": args,
                    "arguments_raw": raw,
                })
            if tool_calls:
                yield {"type": "tool_calls", "tool_calls": tool_calls}
