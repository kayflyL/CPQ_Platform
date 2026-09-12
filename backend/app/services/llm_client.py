"""LLM client — Qwen (DashScope) via OpenAI-compatible mode.

Streams chat completions token-by-token. Swap base_url/model to switch
providers later without touching callers.

Config priority: system_config (llm_config) > .env > defaults
"""
import asyncio
import copy
import json
from typing import Any, AsyncGenerator, List, Dict, Optional

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.repository.system_config_repo import SystemConfigRepository

_settings = get_settings()

# reasoning 类模型把 max_tokens 预算耗尽在思考阶段时的诊断文案（面向操作员的事实说明）。
TRUNCATED_NOTICE = (
    "⚠️ 模型未给出正文：reasoning（思考）阶段耗尽了 max_tokens 预算，"
    "正式回复被截断（finish_reason=length）。请到「AI 设置」把 max_tokens 调到 ≥ 8000 后重试。"
)


class LLMError(Exception):
    """Raised when the LLM provider call fails (network / auth / quota)."""
    pass


class LLMNativeToolsUnsupported(LLMError):
    """Native function calling is not supported by the current provider/proxy."""
    pass


# 单轮整体墙钟上限（秒）的通道级默认：调用方可收紧，不能放开——「管道永远有上限」
# 是通道自己的性质，不该靠每个调用方各记得传一次（漏一个就是一次静默长跑）。
DEFAULT_OVERALL_TIMEOUT_S = 240.0


def _overall_timeout_msg(overall_timeout: float) -> str:
    """单轮模型调用整体超时的统一文案（引擎事实，非提示词；只进 trace/错误出口）。"""
    return (f"LLM 单轮生成整体超时：超过 {float(overall_timeout):.0f}s 仍未收敛"
            f"（长时间持续输出思考、不产出结论），已主动断开")


def _get_llm_config() -> dict:
    """从 system_config 读取 LLM 配置，优先级高于 .env"""
    repo = SystemConfigRepository()
    try:
        config = repo.get_value("llm_config", {})
    finally:
        repo.close()

    return {
        "enabled": bool(config.get("enabled", True)),
        "base_url": config.get("base_url") or _settings.LLM_BASE_URL,
        "api_key": config.get("api_key") or _settings.LLM_API_KEY,
        "model": config.get("model") or _settings.LLM_MODEL,
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_tokens", 16000),
        "capabilities_override": config.get("capabilities_override")
        if isinstance(config.get("capabilities_override"), dict)
        else {},
        "upstream_format": str(config.get("upstream_format") or "openai").lower(),
    }


def is_llm_enabled() -> bool:
    """统一 AI 引擎开关（设置-系统设置-AI 设置 → 启用 AI）。所有 AI 能力共用。"""
    try:
        return bool(_get_llm_config().get("enabled", True))
    except Exception:
        return True  # 读配置异常不阻塞：保持现状行为（默认开）


# ── 模型能力档案 ────────────────────────────────────────────────
# 调用方不判断具体模型字符串；所有「是否支持 JSON mode / 原生 tools / reasoning」的分支
# 统一收敛到这里。未知模型走保守默认（文本 JSON 解析 + 文本 ReAct），保证先稳后快。
BUILTIN_MODEL_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    "deepseek-v4-flash": {
        "supports_json_mode": False,
        "supports_native_tools": False,
        "supports_strict_tools": False,
        "reasoning_model": True,
    },
    "deepseek-v4-pro": {
        "supports_json_mode": False,
        "supports_native_tools": False,
        "supports_strict_tools": False,
        "reasoning_model": True,
    },
    "deepseek": {
        "supports_json_mode": False,
        "supports_native_tools": False,
        "supports_strict_tools": False,
        "reasoning_model": True,
    },
    "qwen": {
        "supports_json_mode": True,
        "supports_native_tools": True,
        "supports_strict_tools": False,
        "reasoning_model": False,
    },
    "gpt": {
        "supports_json_mode": True,
        "supports_native_tools": True,
        "supports_strict_tools": False,
        "reasoning_model": False,
    },
}

DEFAULT_MODEL_CAPABILITIES: Dict[str, bool] = {
    "supports_json_mode": False,
    "supports_native_tools": False,
    "supports_strict_tools": False,
    "reasoning_model": False,
}


def _builtin_capabilities(model: str) -> Dict[str, bool]:
    key = (model or "").strip().lower()
    for family in ("deepseek-v4-flash", "deepseek-v4-pro", "deepseek", "qwen", "gpt"):
        if key.startswith(family):
            return dict(BUILTIN_MODEL_CAPABILITIES[family])
    return dict(DEFAULT_MODEL_CAPABILITIES)


def get_model_capabilities(model: Optional[str] = None, config: Optional[dict] = None) -> Dict[str, bool]:
    """返回当前/指定模型的有效能力档案：内置档案 + llm_config.capabilities_override 覆盖。"""
    config = config if config is not None else _get_llm_config()
    model = (model or config.get("model") or "").strip()
    caps = _builtin_capabilities(model)
    # 上游为 Anthropic Messages 时，原生 function calling 天然可用（/chat/completions 不认
    # type:function，但 /messages 认）。这里把 supports_native_tools 抬为 True，供 auto/native
    # 通道决策；仍允许 capabilities_override 显式关闭，作为 Operator 的最终开关。
    if str(config.get("upstream_format") or "openai").lower() == "anthropic":
        caps["supports_native_tools"] = True

    overrides = config.get("capabilities_override") or {}
    if isinstance(overrides, dict):
        def _apply(ov: dict) -> None:
            for field in caps:
                if field in ov:
                    caps[field] = bool(ov[field])

        ov = overrides.get(model) if model else None
        if ov is None and model:
            ov = overrides.get(model.lower())
        if isinstance(ov, dict):
            _apply(ov)
        else:
            ov = overrides.get("*") or overrides.get("default")
            if isinstance(ov, dict):
                _apply(ov)
    return caps


def model_supports_native_tools(model: Optional[str] = None) -> bool:
    return bool(get_model_capabilities(model).get("supports_native_tools"))


def model_supports_strict_tools(model: Optional[str] = None) -> bool:
    return bool(get_model_capabilities(model).get("supports_strict_tools"))


_STRICT_FORBIDDEN_KEYS = ("default", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
                          "minLength", "maxLength", "pattern", "minItems", "maxItems",
                          "multipleOf", "minProperties", "maxProperties", "uniqueItems", "format")


def _is_strict_compatible(schema: Any) -> bool:
    """OpenAI strict 兼容性：要求所有 object 字段必填，且不含 strict 拒绝的约束键。

    不满足即返回 False，由 _strictify_tools 原样保留 schema（不置 strict），避免 400。
    """
    if not isinstance(schema, dict):
        return True
    if any(key in schema for key in _STRICT_FORBIDDEN_KEYS):
        return False
    typ = schema.get("type")
    if typ == "object":
        props = schema.get("properties") or {}
        req = schema.get("required") or []
        for key in props:
            if key not in req:
                return False
        for value in props.values():
            if not _is_strict_compatible(value):
                return False
    elif typ == "array":
        return _is_strict_compatible(schema.get("items") or {})
    return True


def _strictify_tools(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把 tool schema 追加 additionalProperties:false 并给 function 置 strict:true。

    仅当所有 object 层级的每个 property 都必填时开启 strict（OpenAI 要求 required 齐全，
    否则请求被 400 拒绝）。不满足即原样返回，避免我们自己的可选参数 schema 反把原生通道打挂。
    """
    if not tools:
        return tools
    for tool in tools:
        if not isinstance(tool, dict):
            return tools
        fn = tool.get("function") or {}
        params = fn.get("parameters") if isinstance(fn, dict) else None
        if not _is_strict_compatible(params):
            return tools

    out: List[Dict[str, Any]] = []
    for tool in tools:
        fn = dict(tool.get("function") or {})
        params = copy.deepcopy(fn.get("parameters") or {})

        def _add(obj: Any) -> None:
            if not isinstance(obj, dict):
                return
            typ = obj.get("type")
            if typ == "object":
                obj.setdefault("additionalProperties", False)
                for value in (obj.get("properties") or {}).values():
                    _add(value)
            elif typ == "array":
                _add(obj.get("items") or {})

        _add(params)
        fn["parameters"] = params
        fn["strict"] = True
        out.append({**tool, "function": fn})
    return out


def _ensure_json_instruction(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Ensure the prompt contains the literal 'json' word required by json_object mode."""
    msgs = [dict(m) for m in messages]
    if not msgs:
        msgs = [{"role": "system", "content": "请只输出 JSON 对象。"}]
    if msgs[0].get("role") != "system":
        msgs.insert(0, {"role": "system", "content": ""})
    content = str(msgs[0].get("content") or "")
    if "json" not in content.lower():
        content += "\n输出格式契约：只回一个 JSON 对象（纯 JSON 文本，非 Markdown 代码块）。"
    msgs[0]["content"] = content
    return msgs


def _parse_json_content(content: str) -> Any:
    """Parse model text as JSON: strips code fences and extracts the first complete object."""
    text = (content or "").strip()
    if not text:
        raise ValueError("empty JSON content")
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    raise ValueError("no JSON object found")


def _is_native_tools_unsupported(error: Exception) -> bool:
    """Best-effort detection for providers/proxies that reject native tools."""
    msg = str(error).lower()
    markers = (
        "unknown variant",
        "unknown parameter",
        "invalid parameter",
        "tools",
        "tool_choice",
        "function",
        "not support",
        "unsupported",
        "web_search",
    )
    return any(marker in msg for marker in markers)


def _client(base_url: str, api_key: str, timeout: float = 180.0) -> AsyncOpenAI:
    if not api_key:
        raise LLMError("LLM_API_KEY 未配置(见 .env 或 system_config.llm_config)")
    import httpx
    # 直连（trust_env=False）：LLM 流量绕开系统代理——2026-09-06 实测本地代理
    # （127.0.0.1:10809）对流式连接间歇黑洞（有连接、无数据、不断开），是 kp 阶段
    # 卡死/慢轮的根因之一；relay 国内直连 0.07s 可达，无需代理。
    http_client = httpx.AsyncClient(trust_env=False)
    return AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        max_retries=0,
        http_client=http_client,
    )


async def stream_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """Yield token deltas from the model (OpenAI-compatible streaming).

    messages: [{role: 'system'|'user'|'assistant', content: '...'}, ...]
    """
    config = _get_llm_config()
    if not config.get("enabled", True):
        raise LLMError("AI 引擎未启用（设置 → AI 设置 → 启用 AI）")
    client = _client(config["base_url"], config["api_key"])

    try:
        stream = await client.chat.completions.create(
            model=model or config["model"],
            messages=messages,  # type: ignore[arg-type]
            stream=True,
            temperature=config["temperature"] if temperature is None else temperature,
            max_tokens=config["max_tokens"] if max_tokens is None else max_tokens,
        )
        has_content = False
        finish_reason: Optional[str] = None
        async for chunk in stream:
            try:
                choice = chunk.choices[0]
            except (AttributeError, IndexError):
                continue
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta.content
            if delta:
                has_content = True
                yield delta
        # 流正常结束却无正文：reasoning 类模型在复杂任务上会把
        # max_tokens 预算在思考阶段(reasoning_content)耗尽,正文 content 一个
        # token 都没产出即被 length 截断。这里给出可操作的诊断,而不是让上层
        # 显示无意义的"(空回复)"。
        if not has_content:
            if finish_reason == "length":
                yield TRUNCATED_NOTICE
            else:
                yield (
                    f"⚠️ 模型返回为空(content 为空,finish_reason={finish_reason or 'none'})。"
                    "可能原因:模型异常、输入超限或被安全过滤。"
                )
    except Exception as e:
        raise LLMError(f"LLM 调用失败: {e}") from e


async def chat_json(
    messages: List[Dict[str, str]],
    schema: Optional[dict] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    timeout: float = 90.0,
    max_attempts: int = 2,
    max_tokens: Optional[int] = None,
    thinking: Optional[dict] = None,
    reasoning_effort: Optional[str] = None,
) -> dict:
    """非流式 JSON 模式调用 —— 结构化抽槽专用（LLM 节点 extract_enhance / best_fit 用）。

    与 stream_chat 并存、各司其职：
      • stream_chat —— 流式，给 question_gen「边出字边显示」的体感；
      • chat_json   —— 非流式，收全文再解析 JSON，给结构化抽取（绝不能边流边抽 JSON）。

    护栏（第一期已落实，见 docs/training 调研结论）：
      • reasoning 模型思考阶段会耗光 max_tokens → 正文空回；必须给足 max_tokens(≥8000)；
      • 走 JSON mode(response_format={"type":"json_object"})，按 schema 校验：多余键丢弃、类型强制、
        未知枚举置空（上层回退规则值，绝不裸进 match_kp/compose）；
      • 失败重试一次 → 仍失败 raise LLMError，上层降级到规则抽取结果（绝不阻塞主流程）。

    未配置/不可用时：上层走诚实降级（目录手动选型 + 明确告知），系统脱离网络大模型也能正常运行。

    timeout/max_attempts：调用方可按场景收紧（如理解节点首调给短超时+不重试，失败后自行换更轻的
    prompt 再试——避免「同一超长 prompt 失败后盲目重试同样失败」的假重试）。
    """
    config = _get_llm_config()
    if not config.get("enabled", True):
        raise LLMError("AI 引擎未启用（设置 → AI 设置 → 启用 AI）")
    client = _client(config["base_url"], config["api_key"], timeout=timeout)
    messages = _ensure_json_instruction(messages)

    profile = get_model_capabilities(model or config["model"], config)
    last_err: Optional[Exception] = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        use_json_mode = bool(profile.get("supports_json_mode")) and attempt == 1
        try:
            request_kwargs = {
                "model": model or config["model"],
                "messages": messages,  # type: ignore[arg-type]
                "temperature": config["temperature"] if temperature is None else temperature,
                "max_tokens": max_tokens if max_tokens is not None else config["max_tokens"],
            }
            if use_json_mode:
                request_kwargs["response_format"] = {"type": "json_object"}
            _extra_body: dict = {}
            if thinking is not None:
                _extra_body["thinking"] = thinking
            if reasoning_effort is not None:
                _extra_body["reasoning_effort"] = reasoning_effort
            if _extra_body:
                request_kwargs["extra_body"] = _extra_body
            resp = await client.chat.completions.create(**request_kwargs)
            content = ""
            try:
                content = (resp.choices[0].message.content or "").strip()
            except (AttributeError, IndexError):
                raise LLMError("LLM 返回结构异常（无 choices/message）")
            if not content:
                raise LLMError("LLM 返回空内容")
            try:
                data = _parse_json_content(content)
            except ValueError as e:
                raise LLMError(f"LLM 返回非 JSON：{e}") from e
            if not isinstance(data, dict):
                raise LLMError("LLM 返回 JSON 非对象（结构化抽槽需要对象）")
            if schema:
                data, _ = clean_by_schema(data, schema)
                if not data:
                    raise LLMError("LLM 输出未通过 schema 校验（全部字段无效）")
            return data
        except Exception as e:
            last_err = e
            # First attempt uses json_object mode; second attempt falls back to plain text + parser.
            if not use_json_mode:
                break
    raise LLMError(f"LLM JSON 调用失败(已降级重试): {last_err}")


async def chat_with_tools(
    messages: List[Dict[str, Any]],
    tools: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 90.0,
) -> Dict[str, Any]:
    """Native function-calling channel (OpenAI-compatible).

    Returns:
      {
        "message": raw assistant message to append to the conversation,
        "tool_calls": [{"id", "name", "arguments"}]
      }
    Raises LLMNativeToolsUnsupported when the provider/proxy rejects tools,
    so callers can fall back to text-ReAct.
    """
    config = _get_llm_config()
    if not config.get("enabled", True):
        raise LLMError("AI 引擎未启用（设置 → AI 设置 → 启用 AI）")
    caps = get_model_capabilities(model or config["model"], config)
    if not caps.get("supports_native_tools"):
        raise LLMNativeToolsUnsupported(f"模型 {config.get('model')} 的能力档案禁用了原生工具调用")
    if str(config.get("upstream_format") or "openai").lower() == "anthropic":
        from app.services import anthropic_channel
        anthropic_messages = list(messages or [])
        try:
            return await anthropic_channel.chat(
                anthropic_messages,
                tools=tools,
                model=model or config["model"],
                base_url=config["base_url"],
                api_key=config["api_key"],
                max_tokens=config["max_tokens"] if max_tokens is None else max_tokens,
                temperature=config["temperature"] if temperature is None else temperature,
                timeout=timeout,
            )
        except anthropic_channel.AnthropicChannelError as e:
            raise LLMNativeToolsUnsupported(str(e)) from e
    client = _client(config["base_url"], config["api_key"], timeout=timeout)
    request_tools = _strictify_tools(tools) if caps.get("supports_strict_tools") else tools
    try:
        resp = await client.chat.completions.create(
            model=model or config["model"],
            messages=messages,
            tools=request_tools,
            tool_choice="auto",
            temperature=config["temperature"] if temperature is None else temperature,
            max_tokens=config["max_tokens"] if max_tokens is None else max_tokens,
        )
    except Exception as e:
        if _is_native_tools_unsupported(e):
            raise LLMNativeToolsUnsupported(_format_err(e)) from e
        raise LLMError(_format_err(e)) from e
    try:
        choice = resp.choices[0]
        message = choice.message
    except (AttributeError, IndexError):
        raise LLMError("LLM 返回结构异常（无 choices/message）")

    raw_tool_calls = list(getattr(message, "tool_calls", None) or [])
    parsed_tool_calls: List[Dict[str, Any]] = []
    for tc in raw_tool_calls:
        function = getattr(tc, "function", None)
        if not function:
            continue
        args_text = getattr(function, "arguments", None) or "{}"
        try:
            args = json.loads(args_text) if isinstance(args_text, str) else (args_text or {})
        except Exception:
            args = {}
        if not isinstance(args, dict):
            args = {}
        parsed_tool_calls.append({
            "id": getattr(tc, "id", None) or f"call_{len(parsed_tool_calls)}",
            "name": getattr(function, "name", None) or "",
            "arguments": args,
        })

    raw_message: Dict[str, Any] = {
        "role": getattr(message, "role", None) or "assistant",
        "content": getattr(message, "content", None) or "",
        "tool_calls": [
            {
                "id": getattr(tc, "id", None) or f"call_{index}",
                "type": "function",
                "function": {
                    "name": getattr(getattr(tc, "function", None), "name", None) or "",
                    "arguments": getattr(getattr(tc, "function", None), "arguments", None) or "{}",
                },
            }
            for index, tc in enumerate(raw_tool_calls)
            if getattr(tc, "function", None)
        ],
    }
    return {"message": raw_message, "tool_calls": parsed_tool_calls}

# ── schema 收口工具：LLM 结构化输出进业务前的最后一道确定性闸门 ─────────
# 铁律：LLM 输出绝不裸进 match_kp/compose（碰料号/价格/兼容必须 100% 确定性）。
# 这里只做「格式收口」：多余键丢弃、类型强制、枚举校验；语义正确性由上层 merge 兜底。


def _coerce_scalar(value: Any, type_spec) -> Any:
    """按 JSON-schema 子集的 type 收口单个标量；无法收口返回 None。

    type_spec 可为 str 或 list（如 ["integer","string"]）。bool 单独处理
    （int(True)=1 会误吞 "true"）；整型拒绝非整数值（"7.68" 不强制成 7）。
    """
    types = [type_spec] if isinstance(type_spec, str) else list(type_spec or ["string"])
    if value is None:
        return None
    if "boolean" in types:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            v = value.strip().lower()
            if v in ("true", "yes", "y", "1", "是"):
                return True
            if v in ("false", "no", "n", "0", "否"):
                return False
    if "integer" in types:
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if value.is_integer() else None
        if isinstance(value, str):
            s = value.strip().replace(",", "")
            if not s:
                return None
            try:
                f = float(s)
            except ValueError:
                return None
            return int(f) if f.is_integer() else None
    if "number" in types:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip().replace(",", ""))
            except ValueError:
                return None
    if "string" in types:
        if isinstance(value, str):
            return value.strip()[:200]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return None


def _enum_canonical(value: Any, enum: list) -> Any:
    """枚举收口：字符串大小写不敏感匹配 → 返回枚举规范值；否则 None（上层回退规则值）。"""
    for e in enum:
        if isinstance(e, str) and isinstance(value, str):
            if value.strip().lower() == e.lower():
                return e
        elif type(e) is type(value) and value == e:
            return e
    return None


def _clean_scalar(value: Any, prop: dict, path: str, dropped: list) -> Any:
    cv = _coerce_scalar(value, prop.get("type") if isinstance(prop, dict) else "string")
    if cv is None:
        dropped.append(path)
    return cv


def _clean_by_schema(value: Any, schema: dict, path: str, dropped: list) -> Any:
    """递归收口（支持 object/array/标量/enum），无效子值丢弃并记 dropped。"""
    if not isinstance(schema, dict):
        return None
    if not isinstance(value, dict):
        dropped.append(path or "$")
        return None
    props = schema.get("properties") or {}
    out: dict = {}
    for k, prop in (props or {}).items():
        if k not in value or value[k] is None:
            continue
        p = f"{path}.{k}" if path else f"$.{k}"
        enum = prop.get("enum") if isinstance(prop, dict) else None
        if enum:
            canon = _enum_canonical(value[k], enum)
            if canon is None:
                dropped.append(p)
            else:
                out[k] = canon
            continue
        v = value[k]
        t = prop.get("type") if isinstance(prop, dict) else "string"
        if isinstance(v, list):
            item = (prop.get("items") if isinstance(prop, dict) else None) or {}
            cleaned_items = []
            for it in v:
                if isinstance(it, dict):
                    ci = _clean_by_schema(it, item, p, dropped)
                else:
                    ci = _clean_scalar(it, item, p, dropped)
                if ci:
                    cleaned_items.append(ci)
                if len(cleaned_items) >= 50:  # 数组长度上限，防异常输出撑爆
                    break
            out[k] = cleaned_items
            continue
        if isinstance(v, dict):
            cv = _clean_by_schema(v, prop, p, dropped)
            if cv is not None:
                out[k] = cv
            continue
        cv = _clean_scalar(v, prop, p, dropped)
        if cv is not None:
            out[k] = cv
    return out


def clean_by_schema(data: Any, schema: dict) -> tuple:
    """按 schema 收口 LLM 输出：多余键丢弃、类型强制、枚举校验。

    返回 (cleaned_dict, dropped_paths)。cleaned 为空 dict → 全部字段无效。
    只做格式收口，不做业务判断；语义兜底在上层 merge（规则赢）。
    """
    dropped: list = []
    cleaned = _clean_by_schema(data, schema, "", dropped)
    return (cleaned if isinstance(cleaned, dict) else {}), dropped


# ── 配置排障工具：测试连接 + 拉取模型列表（AI 设置页用）───────────────
# 表单未保存值经 overrides 传入，缺省字段回落到 _get_llm_config()
# (system_config.llm_config > .env > 默认)。用同步 OpenAI 客户端。

def _resolve_config(overrides: Optional[dict] = None) -> dict:
    """把 overrides 合并进 DB 配置：仅当 overrides 给出非空值时覆盖。"""
    config = _get_llm_config()
    if overrides:
        for k in ("base_url", "api_key", "model"):
            v = overrides.get(k)
            if v:
                config[k] = v
    return config


def _format_err(e: Exception) -> str:
    """从 openai 异常体里提出 message 字段，截断，便于前端展示。"""
    msg = str(e)
    try:
        start = msg.index("{")
        data = json.loads(msg[start:])
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            return data["error"].get("message") or msg
    except (ValueError, TypeError):
        pass
    return msg[:300]


def describe_model_capabilities(model: Optional[str] = None) -> dict:
    """返回当前/指定模型的能力档案视图（内置 + 覆盖 + 生效），供模型能力档案页展示。"""
    config = _get_llm_config()
    model = (model or config.get("model") or "").strip()
    builtin = _builtin_capabilities(model)
    effective = get_model_capabilities(model, config)

    override = None
    overrides = config.get("capabilities_override") or {}
    if isinstance(overrides, dict):
        override = overrides.get(model) or (overrides.get(model.lower()) if model else None)
        if not isinstance(override, dict):
            override = overrides.get("*") or overrides.get("default")
    return {
        "model": model,
        "builtin": builtin,
        "effective": effective,
        "override": override if isinstance(override, dict) else None,
    }


def probe_model_capabilities(overrides: Optional[dict] = None) -> dict:
    """实测当前端点的 JSON mode / 原生 tools 支持情况，reasoning 用内置档案作提示。

    只做轻量探测（每项单次小请求），结果供前端「能力探测」按钮展示与回写。
    """
    config = _resolve_config(overrides)
    if not config.get("api_key"):
        return {"success": False, "model": config.get("model"), "message": "未配置 api_key"}
    if not config.get("model"):
        return {"success": False, "model": config.get("model"), "message": "未配置 model"}
    try:
        from openai import OpenAI
        client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=30, max_retries=0)
    except Exception as e:
        return {"success": False, "model": config.get("model"), "message": _format_err(e)}

    out: dict = {
        "success": True,
        "model": config["model"],
        "supports_json_mode": False,
        "supports_native_tools": False,
        "reasoning_model": _builtin_capabilities(config["model"]).get("reasoning_model", False),
        "notes": [],
    }

    try:
        resp = client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": "请只输出一个 JSON 对象：{\"ok\": true}"}],
            max_tokens=64,
            response_format={"type": "json_object"},
        )
        content = (resp.choices[0].message.content or "").strip()
        out["supports_json_mode"] = bool(content)
        if not content:
            out["notes"].append("JSON mode 返回空正文")
    except Exception as e:
        out["supports_json_mode"] = False
        out["notes"].append(f"JSON mode 失败: {_format_err(e)}")

    try:
        resp = client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": "请调用 get_time 工具获取当前时间"}],
            tools=[{
                "type": "function",
                "function": {
                    "name": "get_time",
                    "description": "获取当前时间",
                    "parameters": {"type": "object", "properties": {}},
                },
            }],
            tool_choice="auto",
            max_tokens=64,
        )
        tool_calls = list(getattr(resp.choices[0].message, "tool_calls", None) or [])
        out["supports_native_tools"] = bool(tool_calls)
    except Exception as e:
        out["supports_native_tools"] = False
        out["notes"].append(f"原生 tools 失败: {_format_err(e)}")

    return out


def test_connection(overrides: Optional[dict] = None) -> dict:
    """实测一次 chat completion（同步，max_tokens=8）。返回 {success, message}。

    成功 message 给人可读确认；失败 message 是真实错误（HTTP/鉴权/model 名等），
    供 AI 设置页「测试连接」按钮直接展示，不再被占位文案吞掉。
    """
    config = _resolve_config(overrides)
    if not config.get("api_key"):
        return {"success": False, "message": "未配置 api_key（填入或设置 .env 的 LLM_API_KEY）"}
    if not config.get("model"):
        return {"success": False, "message": "未配置 model（填入或设置 .env 的 LLM_MODEL）"}
    try:
        from openai import OpenAI
        client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=20, max_retries=0)
        resp = client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
        )
        reply = (resp.choices[0].message.content or "").strip()
        return {
            "success": True,
            "message": f"连接成功 · 模型 {config['model']} 已响应",
            "reply": reply,
        }
    except Exception as e:
        return {"success": False, "message": _format_err(e)}


def list_models(overrides: Optional[dict] = None) -> list:
    """拉取 provider 可用模型 id 列表（GET {base_url}/models），按 id 排序。

    raises LLMError: 网络/鉴权/端点不支持 /models 时。
    """
    config = _resolve_config(overrides)
    if not config.get("api_key"):
        raise LLMError("未配置 api_key（填入或设置 .env 的 LLM_API_KEY）")
    try:
        from openai import OpenAI
        client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=20, max_retries=0)
        data = client.models.list()
        return sorted(m.id for m in data.data)
    except Exception as e:
        raise LLMError(_format_err(e)) from e


async def stream_agent_chat(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    timeout: float = 180.0,
    reasoning_effort: Optional[str] = None,
    first_token_timeout: Optional[float] = None,
    overall_timeout: Optional[float] = DEFAULT_OVERALL_TIMEOUT_S,
) -> AsyncGenerator[Dict[str, str], None]:
    """流式 Agent 聊天：把模型的 reasoning 与正文逐段吐出来（ChatGPT 式白盒）。

    与 stream_chat 的区别：
      - stream_chat 只 yield content（用于 question_gen 简单流式）。
      - stream_agent_chat yield {type: reasoning|content, delta}，供 Agent 循环把「思考」实时
        推到前端，模型先想清楚再行动。

    行为：
      - 模型能力档案为 reasoning 时，优先读取 delta.reasoning_content（思考）与 delta.content（正文）。
      - 传入 tools 且模型支持原生工具时，走 native function-calling 流；
        通道不支持时抛 LLMNativeToolsUnsupported，由上层回退文本循环（不重复触发副作用）。
      - timeout 是字节间隔超时（慢而流动的生成不受影响，挂死连接按 gap 断）；
        first_token_timeout 是「到首个输出」的看门狗（建连 + 排队 + 首 token），
        超时即断开交上层重试——对无数据的流快速放弃，对流动的慢生成保持耐心。
        首 token 之后【每个 chunk 间隔】同样受 first_token_timeout 约束（间隔看门狗）：
        黑洞连接常被 keepalive 字节"养着"导致 httpx read 超时不触发（read 只测"任一
        字节到达"，keepalive 会让它永不超时），按内容 chunk 间隔主动断开（litellm #29767 同源）。
      - overall_timeout 是「单轮总时长」的墙钟上限：间隔看门狗管不住「一直在吐字但迟迟
        不收敛」的慢速生成，单轮总时长必须另有兜底，否则一轮可以静默跑几十分钟（实测 1605s）。
      - reasoning 耗尽 max_tokens 导致正文为空时，yield 一条带 truncated 标记的兜底文案：
        单发消费方（普通对话）照常展示提示，Agent 循环则据标记作废该轮并重试，
        不让警告文本混进旁白/落库正文。
      - 失败统一抛 LLMError，绝不静默返回空串。
    """
    config = _get_llm_config()
    if not config.get("enabled", True):
        raise LLMError("AI 引擎未启用（设置 → AI 设置 → 启用 AI）")
    client = _client(config["base_url"], config["api_key"], timeout=timeout)

    model_name = model or config["model"]
    caps = get_model_capabilities(model_name, config)
    use_tools = bool(tools) and bool(caps.get("supports_native_tools"))
    if use_tools and str(config.get("upstream_format") or "openai").lower() == "anthropic":
        from app.services import anthropic_channel
        try:
            async for item in anthropic_channel.stream(
                messages,
                tools=tools,
                model=model_name,
                base_url=config["base_url"],
                api_key=config["api_key"],
                max_tokens=max_tokens if max_tokens is not None else config["max_tokens"],
                temperature=config["temperature"] if temperature is None else temperature,
                timeout=timeout,
                first_token_timeout=first_token_timeout,
                overall_timeout=overall_timeout,
            ):
                yield item
            return
        except anthropic_channel.AnthropicTimeoutError as e:
            # 超时不是「通道不支持原生 tools」：误报会让上层白白降级掉工具通道，
            # 必须收口成 LLMError，让上层按「可重试 / 可如实失败」处理。
            raise LLMError(str(e)) from e
        except anthropic_channel.AnthropicChannelError as e:
            raise LLMNativeToolsUnsupported(str(e)) from e

    request_kwargs: Dict[str, Any] = {
        "model": model_name,
        "messages": messages,
        "stream": True,
        "temperature": config["temperature"] if temperature is None else temperature,
        "max_tokens": max_tokens if max_tokens is not None else config["max_tokens"],
    }
    if use_tools:
        request_kwargs["tools"] = _strictify_tools(tools) if caps.get("supports_strict_tools") else tools
    if reasoning_effort is not None:
        request_kwargs["extra_body"] = {"reasoning_effort": reasoning_effort}
    # 末块 usage（prefill/生成 token 数与缓存命中）：诊断「慢在哪」的数据源；个别代理不认
    # 该参数报 400 时降级去掉重试一次（不牺牲主流程）。
    request_kwargs["stream_options"] = {"include_usage": True}

    async def _create():
        try:
            return await client.chat.completions.create(**request_kwargs)
        except Exception as e:
            if "stream_options" in _format_err(e) and "stream_options" in request_kwargs:
                request_kwargs.pop("stream_options", None)
                return await client.chat.completions.create(**request_kwargs)
            raise

    try:
        if first_token_timeout:
            stream = await asyncio.wait_for(_create(), timeout=first_token_timeout)
        else:
            stream = await _create()
    except asyncio.TimeoutError:
        raise LLMError(
            f"LLM 首字节超时：{first_token_timeout:.0f}s 内无响应（连接挂死或排队过久），已主动断开")
    except Exception as e:
        if use_tools and _is_native_tools_unsupported(e):
            raise LLMNativeToolsUnsupported(_format_err(e)) from e
        raise LLMError(_format_err(e)) from e

    try:
        has_content = False
        finish_reason: Optional[str] = None
        last_usage: Dict[str, int] = {}
        aiter = stream.__aiter__()
        pending_first = bool(first_token_timeout)
        # 间隔看门狗（2026-09-06，参照 litellm #29767）：首 token 后每个 chunk 也要超时
        guard = first_token_timeout if first_token_timeout else None
        # 整体墙钟上限（2026-09-11）：间隔看门狗只约束「两次输出之间的空隙」，慢速持续吐
        # reasoning 的模型会把看门狗无限重置 → 单轮永不收敛（实测 1605s 静默空转）。
        # 单轮总时长按墙钟兜底：到点即断，交上层按失败处理，绝不让回合无限挂起。
        loop = asyncio.get_running_loop()
        overall_deadline = (loop.time() + float(overall_timeout)) if overall_timeout else None
        # 流式原生 function calling：按 index 累积 tool_calls 增量（id/name/arguments 可能分片）
        tool_calls_acc: Dict[int, dict] = {}
        has_tool_calls = False
        while True:
            try:
                # 首/间隔看门狗（建连、黑洞挂死）+ 整体墙钟上限（慢速长跑）三者取最小值，谁先到谁断
                budget = first_token_timeout if pending_first else guard
                over = False    # 本次等待是否由「整体墙钟上限」卡住 → 断连原因要如实，不能张冠李戴
                if overall_deadline is not None:
                    left = overall_deadline - loop.time()
                    if left <= 0:
                        raise LLMError(_overall_timeout_msg(overall_timeout))
                    if budget is None or left < budget:
                        budget = left
                        over = True
                if budget is None:
                    chunk = await aiter.__anext__()
                else:
                    chunk = await asyncio.wait_for(aiter.__anext__(), timeout=budget)
                pending_first = False
            except StopAsyncIteration:
                break
            except asyncio.TimeoutError:
                if over:
                    raise LLMError(_overall_timeout_msg(overall_timeout))
                if pending_first:
                    raise LLMError(
                        f"LLM 首字节超时：{float(first_token_timeout or 0):.0f}s 内无任何输出（连接挂死），已主动断开")
                raise LLMError(
                    f"LLM 流式间隔超时：{float(guard or 0):.0f}s 内未收到下一个数据块（连接挂死），已主动断开")
            usage_obj = getattr(chunk, "usage", None)
            if usage_obj is not None:
                # DeepSeek: prompt_cache_hit_tokens；OpenAI 系: prompt_tokens_details.cached_tokens
                _det = getattr(usage_obj, "prompt_tokens_details", None)
                last_usage.update({
                    "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
                    "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
                    "cache_hit_tokens": (getattr(usage_obj, "prompt_cache_hit_tokens", None)
                                         or getattr(_det, "cached_tokens", None) or 0),
                })
                _comp_det = getattr(usage_obj, "completion_tokens_details", None)
                if _comp_det is not None:
                    last_usage["reasoning_tokens"] = getattr(_comp_det, "reasoning_tokens", 0) or 0
            try:
                choice = chunk.choices[0]
            except (AttributeError, IndexError):
                continue
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta
            reasoning = getattr(delta, "reasoning_content", None)
            content = getattr(delta, "content", None)
            if reasoning:
                yield {"type": "reasoning", "delta": str(reasoning)}
            if content:
                has_content = True
                yield {"type": "content", "delta": str(content)}
            tool_call_deltas = getattr(delta, "tool_calls", None)
            if tool_call_deltas:
                has_tool_calls = True
                for tcd in tool_call_deltas:
                    tcd_index = int(getattr(tcd, "index", 0) or 0)
                    acc = tool_calls_acc.setdefault(tcd_index, {"id": None, "name": "", "arguments": ""})
                    tcd_id = getattr(tcd, "id", None)
                    if tcd_id:
                        acc["id"] = str(tcd_id)
                    fn = getattr(tcd, "function", None)
                    if fn is not None:
                        fn_name = getattr(fn, "name", None)
                        if fn_name:
                            acc["name"] = str(acc.get("name") or "") + str(fn_name)
                        fn_args = getattr(fn, "arguments", None)
                        if fn_args:
                            acc["arguments"] = str(acc.get("arguments") or "") + str(fn_args)
        # 流式结束却无正文：reasoning 阶段耗尽 max_tokens，正文被 length 截断。
        # truncated 标记交消费方分流：普通对话展示提示，Agent 循环作废该轮重试。
        if last_usage:
            yield {"type": "usage", "usage": dict(last_usage)}
        if has_tool_calls and tool_calls_acc:
            parsed_tool_calls = []
            for idx in sorted(tool_calls_acc):
                acc = tool_calls_acc[idx]
                args_raw = acc.get("arguments") or ""
                try:
                    args = json.loads(args_raw) if args_raw.strip() else {}
                except Exception:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                parsed_tool_calls.append({
                    "id": acc.get("id") or f"call_{idx}",
                    "name": acc.get("name") or "",
                    "arguments": args,
                    "arguments_raw": args_raw,
                })
            yield {"type": "tool_calls", "tool_calls": parsed_tool_calls}
        if not has_content and not tool_calls_acc and finish_reason == "length":
            yield {
                "type": "content",
                "delta": TRUNCATED_NOTICE,
                "truncated": True,
            }
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"LLM 流式调用失败: {e}") from e
