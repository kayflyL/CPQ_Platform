# -*- coding: utf-8 -*-
"""agent_react —— 原生 function calling 智能体循环（OpenAI / Anthropic Messages 通道）。

工具编排只走原生 function calling（OpenAI / Anthropic Messages 通道），模型直接返回结构化
tool_calls，平台负责执行与回填；不再保留「文本式 ReAct」（```tool 围栏 / JSON action 协议）。
原生 tools 由 chat_with_tools / stream_agent_chat 按 upstream_format 路由到对应上游通道。
"""
import json
import logging
import time
from typing import Any, Awaitable, Callable, Optional

from app.services import llm_client
from app.services.agent_tool_specs import build_tool_registry

logger = logging.getLogger(__name__)

# 思考预算语义（2026-09-12 反转）：budget 只是软预算，思考放行到完成——relay 对带 tools
# 调用忽略 effort，思考是结构性的，09-06「掐断防跑飞」实测为净损失（撞顶轮掐断→重试
# 再撞顶→双倍付费零产出，kp_reason 整步被打掉重来 3 次）。硬上限=budget×3，只在病态
# 深思考时强制收口，且重试带硬指令。
_THINKING_HARD_CEILING_MULT = 3
# 步内工具结果总量上限：单条 1500 字截断早已存在，但总量无上限曾把单轮上下文堆到 38K 字
# （context rot → 思考爆炸）。超总量时压缩最老的工具消息到 _TOOL_CONTEXT_COMPRESS_TO 字。
# 不变量：压缩后长度(300+标记≈312) 必须低于 victim 门槛 400，否则同一条消息被反复"压缩"
# 到同样长度、总量永不下降 → while 死循环卡死事件循环（2026-09-12 py-spy 实测抓到）。
_TOOL_CONTEXT_CAP_CHARS = 20000
_TOOL_CONTEXT_COMPRESS_TO = 300
_TOOL_CONTEXT_VICTIM_MIN = 400


def _cap_tool_context(messages: list) -> None:
    """把步内已累积的工具消息总量压回上限内：从最老的开始压缩（最近的保持完整）。"""
    while True:
        total = sum(len(m.get("content") or "") for m in messages if m.get("role") == "tool")
        if total <= _TOOL_CONTEXT_CAP_CHARS:
            return
        victim = next((m for m in messages if m.get("role") == "tool"
                       and len(m.get("content") or "") > _TOOL_CONTEXT_VICTIM_MIN), None)
        if victim is None:
            return  # 全都已是压缩后长度仍超上限：不再无意义循环
        victim["content"] = (victim["content"] or "")[:_TOOL_CONTEXT_COMPRESS_TO] + "…（早期检索结果已压缩）"


async def _run_native_tool_loop(
    requirement_text: str,
    config: dict,
    extra_context: str,
    max_iterations: int,
    system_prompt: Optional[str],
    allowed_tool_ids: Optional[list],
    allowed_data_sources: Optional[list],
    model: Optional[str],
    event_sink: Optional[Any],
    history: Optional[list],
    tool_guard: Optional[Callable[[str, dict, Any], Awaitable[Any]]],
) -> dict:
    """Prefer native function calling; raise LLMError when the provider is unavailable."""
    base: dict = {
        "ok": False, "answer": "", "tool_calls_log": [],
        "thought_log": [], "iterations": 0,
    }
    cfg = config or {}
    try:
        if not llm_client.is_llm_enabled():
            base["answer"] = "AI 未启用"
            return base
    except Exception:
        pass

    registry = build_tool_registry(cfg, allowed_tool_ids=allowed_tool_ids, allowed_data_sources=allowed_data_sources)
    if not registry.names():
        base["answer"] = "未启用任何工具"
        return base

    sys_prompt = system_prompt or cfg.get("system_prompt") or ""
    messages: list = [{"role": "system", "content": sys_prompt}]
    if history:
        for m in history[-12:]:
            role = (m or {}).get("role") if isinstance(m, dict) else None
            content = (m or {}).get("content") if isinstance(m, dict) else None
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    user_content = f"需求：{requirement_text or ''}".strip()
    if extra_context:
        user_content += f"\n\n参考：{extra_context}"
    messages.append({"role": "user", "content": user_content})

    try:
        max_iter = max(1, int(max_iterations))
    except (TypeError, ValueError):
        max_iter = 5

    async def _emit(kind: str, text: str = "", tool: Optional[str] = None) -> None:
        if not event_sink:
            return
        try:
            await event_sink({
                "type": "step_progress",
                "step": "react",
                "sub": {"kind": kind, "text": text, "tool": tool},
            })
        except Exception:
            pass

    try:
        for i in range(max_iter):
            base["iterations"] = i + 1
            response = await llm_client.chat_with_tools(messages, tools=registry.schemas(), model=model)
            tool_calls = response.get("tool_calls") or []
            if tool_calls:
                base["tool_attempted"] = True
                messages.append(response["message"])
                for call in tool_calls:
                    name = str(call.get("name") or "").strip()
                    args = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                    await _emit("tool", f"正在调用工具 {name}", name)
                    result = await registry.execute(name, args)
                    if tool_guard is not None:
                        result = await tool_guard(name, args, result)
                    try:
                        result_str = result if isinstance(result, str) else \
                            json.dumps(result, ensure_ascii=False, default=str)
                    except Exception:
                        result_str = str(result)
                    await _emit("tool", f"工具 {name} 已完成", name)
                    base["tool_calls_log"].append({"name": name, "args": args, "result": result})
                    messages.append({
                        "role": "tool",
                        "tool_call_id": str(call.get("id") or ""),
                        "content": result_str,
                    })
                continue

            answer = str((response.get("message") or {}).get("content") or "").strip()
            base["ok"] = bool(answer)
            base["answer"] = answer
            return base
    except llm_client.LLMNativeToolsUnsupported as e:
        base["unsupported"] = True
        base["error"] = f"native_unsupported:{e}"[:300]
        return base
    except llm_client.LLMError as e:
        base["error"] = f"llm_error:{e}"[:300]
        return base
    except Exception as e:
        logger.exception("native tool loop unexpected error")
        base["error"] = f"exception:{e}"[:300]
        return base

    base["answer"] = ""
    return base


async def _run_native_stream_chat_loop(
    user_text, config, system_prompt, allowed_tool_ids, model, event_sink, history,
    tool_guard, max_iterations, llm_timeout, llm_first_token_timeout, llm_reasoning_effort,
    llm_temperature, llm_max_tokens, context_block, llm_thinking_budget,
    llm_overall_timeout,
) -> dict:
    """原生 function calling 流式聊天循环：模型直接返回流式 tool_calls，结果以 role:tool 回填。

    事件协议与 run_stream_chat_loop 一致（step_progress.step=react，sub.kind=thinking/chunk/tool）。
    返回契约同 run_stream_chat_loop。模型/代理不支持原生 tools 时抛 LLMNativeToolsUnsupported，
    由上层返回 unsupported，由调用方降级为普通对话。
    """
    base = {"ok": False, "answer": "", "tool_calls_log": [], "thinking": [], "iterations": 0}
    cfg = config or {}
    registry = build_tool_registry(cfg, allowed_tool_ids=allowed_tool_ids)
    if not registry.names():
        base["answer"] = "未启用任何工具"
        return base
    sys_prompt = system_prompt or cfg.get("system_prompt") or ""
    messages = [{"role": "system", "content": sys_prompt}]
    if history:
        for m in history[-12:]:
            role = (m or {}).get("role") if isinstance(m, dict) else None
            content = (m or {}).get("content") if isinstance(m, dict) else None
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": str(content)})
    user_tail = str(user_text or "").strip()
    if context_block and context_block.strip():
        user_tail = context_block.strip() + "\n\n" + user_tail
    messages.append({"role": "user", "content": user_tail})
    try:
        max_iter = max(1, int(max_iterations))
    except (TypeError, ValueError):
        max_iter = 6

    async def _emit(kind, **kv):
        if not event_sink:
            return
        try:
            await event_sink({"type": "step_progress", "step": "react", "sub": {"kind": kind, **kv}})
        except Exception:
            pass

    # 逐轮诊断留痕（D）：thinking 字数/整包字数/token 与缓存命中 —— 「慢在哪」靠这份数据说话
    round_usage: dict = {}
    round_thinking = 0

    def _record_round(round_idx: int, dur_ms: int, prose: str, tool_names: str,
                      status: str = "ok", error: str = "") -> None:
        try:
            from app.services.llm_trace import record_llm_trace
            prompt_chars = sum(len(str((m or {}).get("content") or "")) for m in messages)
            record_llm_trace(
                node_type="agent_round",
                model=str(model or ""),
                status=status or "ok", error=(error[:200] if error else None),
                duration_ms=int(dur_ms), prompt_chars=prompt_chars,
                response_chars=len(prose or ""), thinking_chars=int(round_thinking),
                prompt_tokens=int(round_usage.get("prompt_tokens") or 0),
                completion_tokens=int(round_usage.get("completion_tokens") or 0),
                cache_hit_tokens=int(round_usage.get("cache_hit_tokens") or 0),
                tool_name=(tool_names or "")[:80],
            )
        except Exception:
            pass

    async def _stream_round():
        nonlocal round_thinking
        prose = []
        thinking_chars = 0
        thinking_over = False
        truncated = False
        tool_calls = None
        try:
            _stream_kwargs = dict(
                model=model, tools=registry.schemas(), timeout=llm_timeout,
                first_token_timeout=llm_first_token_timeout, temperature=llm_temperature,
                reasoning_effort=llm_reasoning_effort, max_tokens=llm_max_tokens)
            # 通道自带单轮整体墙钟上限；本回合若另有更紧的预算就收紧它（只能更紧，不能放开）
            if llm_overall_timeout is not None:
                _stream_kwargs["overall_timeout"] = llm_overall_timeout
            stream = llm_client.stream_agent_chat(messages, **_stream_kwargs)
            async for item in stream:
                t = item.get("type")
                d = item.get("delta") or ""
                if t == "reasoning":
                    if d:
                        thinking_chars += len(str(d))
                        round_thinking += len(str(d))
                        await _emit("thinking", text=d)
                        # 硬上限（3×预算）才掐断；软预算不掐——见文件头注释
                        if (thinking_chars > llm_thinking_budget * _THINKING_HARD_CEILING_MULT
                                and not prose and tool_calls is None):
                            thinking_over = True
                            break
                elif t == "usage":
                    round_usage.update(item.get("usage") or {})
                elif t == "content":
                    if item.get("truncated"):
                        truncated = True
                        await _emit("tool", text="模型本轮 token 预算耗尽，正在重试…")
                        continue
                    prose.append(str(d))
                    await _emit("chunk", delta=str(d))
                elif t == "tool_calls":
                    tool_calls = item.get("tool_calls") or []
            await stream.aclose()
        except llm_client.LLMNativeToolsUnsupported:
            raise
        except llm_client.LLMError:
            if not prose and tool_calls is None:
                raise
            truncated = True
        if thinking_over:
            truncated = True
            await _emit("tool", text="思考超长（超3倍预算），强制收口重试…")
        return "".join(prose), tool_calls, truncated

    async def _stream_round_retry():
        try:
            return await _stream_round()
        except llm_client.LLMNativeToolsUnsupported:
            raise
        except llm_client.LLMError:
            await _emit("tool", text="模型连接中断，正在重试（1/2）…")
            return await _stream_round()

    all_prose = []
    trunc_streak = 0
    for i in range(max_iter):
        base["iterations"] = i + 1
        round_thinking = 0
        round_usage.clear()
        _rt0 = time.perf_counter()
        try:
            prose, tool_calls, truncated = await _stream_round_retry()
        except llm_client.LLMNativeToolsUnsupported as e:
            base["unsupported"] = True
            base["error"] = f"native_unsupported:{e}"[:300]
            return base
        except llm_client.LLMError as e:
            _record_round(i + 1, (time.perf_counter() - _rt0) * 1000, "", "",
                          status="llm_error", error=str(e))
            partial = "".join(all_prose)
            if partial.strip():
                base["ok"] = True
                base["answer"] = partial
            else:
                await _emit("error", text=f"流式对话失败：{e}")
            return base
        _names = ",".join(str(tc.get("name") or "") for tc in (tool_calls or []))
        _record_round(i + 1, (time.perf_counter() - _rt0) * 1000, prose, _names)
        all_prose.append(prose)
        if not truncated or prose.strip():
            trunc_streak = 0

        if tool_calls:
            messages.append({
                "role": "assistant", "content": prose.strip() or None,
                "tool_calls": [{"id": tc.get("id") or f"call_{j}", "type": "function",
                                "function": {"name": tc.get("name") or "",
                                             "arguments": tc.get("arguments_raw")
                                             or json.dumps(tc.get("arguments") or {}, ensure_ascii=False)}}
                               for j, tc in enumerate(tool_calls)],
            })
            for tc in tool_calls:
                name = str(tc.get("name") or "").strip()
                args = tc.get("arguments") if isinstance(tc.get("arguments"), dict) else {}
                await _emit("tool", text=f"正在调用 {name}…", tool=name)
                try:
                    result = await registry.execute(name, args)
                    if tool_guard is not None:
                        result = await tool_guard(name, args, result)
                except Exception as exc:
                    result = {"ok": False, "error": f"工具执行异常：{exc}"}
                try:
                    result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
                except Exception:
                    result_str = str(result)
                if len(result_str) > 1500:
                    result_str = result_str[:1500] + "…(截断)"
                await _emit("tool", text=f"{name} 完成", tool=name)
                base["tool_calls_log"].append({"name": name, "args": args, "result": result})
                messages.append({"role": "tool", "tool_call_id": tc.get("id") or "", "content": result_str})
            _cap_tool_context(messages)
            continue

        if truncated and not prose.strip():
            trunc_streak += 1
            if trunc_streak >= 2:
                partial = "".join(all_prose)
                if partial.strip():
                    base["ok"] = True
                    base["answer"] = partial
                return base
            messages.append({"role": "user", "content":
                             "上一轮思考超长被截断且无产出。立即基于已有信息"
                             "直接给出最终回答或下一步工具调用。"})
            continue

        if prose.strip():
            base["ok"] = True
            base["answer"] = "".join(all_prose)
            return base
        messages.append({"role": "user", "content": "上一轮输出为空。"})

    messages.append({"role": "user", "content": "工具调用已达上限。"})
    try:
        prose, _call, _trunc = await _stream_round()
        all_prose.append(prose)
    except llm_client.LLMNativeToolsUnsupported:
        pass
    except llm_client.LLMError:
        pass
    answer = "".join(all_prose)
    if answer.strip():
        base["ok"] = True
        base["answer"] = answer
    return base


async def run_stream_chat_loop(
    user_text: str,
    config: dict,
    system_prompt: str,
    allowed_tool_ids: Optional[list] = None,
    model: Optional[str] = None,
    event_sink: Optional[Any] = None,
    history: Optional[list] = None,
    tool_guard: Optional[Callable[[str, dict, Any], Awaitable[Any]]] = None,
    max_iterations: int = 6,
    llm_timeout: float = 60.0,
    llm_first_token_timeout: float = 30.0,
    llm_reasoning_effort: Optional[str] = None,
    llm_temperature: Optional[float] = None,
    llm_max_tokens: Optional[int] = None,
    context_block: Optional[str] = None,
    llm_thinking_budget: int = 6000,
    llm_overall_timeout: Optional[float] = None,
) -> dict:
    """聊天流式循环（仅原生 function calling；不再有文本式 ReAct 兜底）。

    事件词汇（step_progress.step=react）：sub.kind=thinking(text)/chunk(delta)/tool(text,tool)。
    返回契约与 run_react_loop 一致；answer=已推送给用户的全部正文（落库与流式严格一致）。
    """
    base: dict = {"ok": False, "answer": "", "tool_calls_log": [], "thinking": [], "iterations": 0}
    try:
        if not llm_client.is_llm_enabled():
            base["answer"] = "AI 未启用"
            return base
    except Exception:
        pass
    return await _run_native_stream_chat_loop(
        user_text=user_text, config=config, system_prompt=system_prompt,
        allowed_tool_ids=allowed_tool_ids, model=model, event_sink=event_sink,
        history=history, tool_guard=tool_guard, max_iterations=max_iterations,
        llm_timeout=llm_timeout, llm_first_token_timeout=llm_first_token_timeout,
        llm_reasoning_effort=llm_reasoning_effort, llm_temperature=llm_temperature,
        llm_max_tokens=llm_max_tokens, context_block=context_block,
        llm_thinking_budget=llm_thinking_budget, llm_overall_timeout=llm_overall_timeout)


async def run_react_loop(
    requirement_text: str,
    config: dict,
    extra_context: str = "",
    max_iterations: int = 5,
    system_prompt: Optional[str] = None,
    allowed_tool_ids: Optional[list] = None,
    allowed_data_sources: Optional[list] = None,
    model: Optional[str] = None,
    event_sink: Optional[Any] = None,
    history: Optional[list] = None,
    tool_guard: Optional[Callable[[str, dict, Any], Awaitable[Any]]] = None,
    llm_timeout: float = 90.0,
    llm_max_attempts: int = 2,
    llm_thinking: Optional[dict] = None,
    llm_reasoning_effort: Optional[str] = None,
    llm_temperature: Optional[float] = None,
    llm_max_tokens: Optional[int] = None,
) -> dict:
    """Agent loop：仅原生 function calling（OpenAI / Anthropic Messages），不再回退文本 ReAct。

    原生不支持时返回 unsupported/ok=False，由调用方降级为普通对话；绝不重跑副作用。
    保留 llm_temperature/llm_max_tokens 等签名兼容（原生通道由 config 决定，参数忽略）。
    """
    return await _run_native_tool_loop(
        requirement_text=requirement_text, config=config, extra_context=extra_context,
        max_iterations=max_iterations, system_prompt=system_prompt,
        allowed_tool_ids=allowed_tool_ids, allowed_data_sources=allowed_data_sources,
        model=model, event_sink=event_sink, history=history, tool_guard=tool_guard,
    )
