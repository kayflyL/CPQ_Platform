"""LLM client — Qwen (DashScope) via OpenAI-compatible mode.

Streams chat completions token-by-token. Swap base_url/model to switch
providers later without touching callers.

Config priority: system_config (llm_config) > .env > defaults
"""
import asyncio
import copy
import json
import logging
import re
from typing import Any, AsyncGenerator, List, Dict, Optional
from urllib.parse import urlparse

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.repository.system_config_repo import SystemConfigRepository

_settings = get_settings()
logger = logging.getLogger(__name__)

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


# ── 内联 <think> 推理块过滤（2026-09-13）───────────────────────────────────
# 部分中转（reasoning 模型经 OpenAI 兼容代理）不回 delta.reasoning_content，而是把
# 思考以 <think>…</think> 标签混进 content——原样透传会把推理文本连同标签一起
# 漏进用户气泡（用户实测）。所有流式出口统一走这个状态机改道；非流式出口用
# _strip_think_blocks 兜底。标签可能跨 chunk 分片，未判明的尾巴先扣留不发。
_THINK_OPEN, _THINK_CLOSE = "<think>", "</think>"
_THINK_HOLD = max(len(_THINK_OPEN), len(_THINK_CLOSE)) - 1


class _ThinkStreamFilter:
    """流式 content → (content|reasoning) 分拣：标签内=思考，标签外=正文。"""

    def __init__(self) -> None:
        self._in_think = False
        self._buf = ""
        self._skip_lead = False  # think 闭合后跳过紧随的空行（气泡里不留前导空行）

    def _emit_ready(self, text: str) -> str:
        if self._skip_lead:
            text = text.lstrip("\r\n")
            if not text:
                return ""
            self._skip_lead = False
        return text

    def feed(self, delta: str) -> List[tuple]:
        out: List[tuple] = []
        self._buf += str(delta or "")
        while self._buf:
            if self._in_think:
                idx = self._buf.find(_THINK_CLOSE)
                if idx >= 0:
                    if idx:
                        out.append(("reasoning", self._buf[:idx]))
                    self._buf = self._buf[idx + len(_THINK_CLOSE):]
                    self._in_think = False
                    self._skip_lead = True
                    continue
                if len(self._buf) > _THINK_HOLD:
                    out.append(("reasoning", self._buf[:-_THINK_HOLD]))
                    self._buf = self._buf[-_THINK_HOLD:]
                break
            idx = self._buf.find(_THINK_OPEN)
            if idx >= 0:
                piece = self._emit_ready(self._buf[:idx])
                if piece:
                    out.append(("content", piece))
                self._buf = self._buf[idx + len(_THINK_OPEN):]
                self._in_think = True
                continue
            if len(self._buf) > _THINK_HOLD:
                piece = self._emit_ready(self._buf[:-_THINK_HOLD])
                if piece:
                    out.append(("content", piece))
                self._buf = self._buf[-_THINK_HOLD:]
            break
        return out

    def flush(self) -> List[tuple]:
        """流结束：清掉扣留的尾巴（未闭合的 think 尾巴归思考，不进正文）。"""
        if not self._buf:
            return []
        if self._in_think:
            text, self._buf = self._buf, ""
            self._in_think = False
            return [("reasoning", text)]
        piece = self._emit_ready(self._buf)
        self._buf = ""
        return [("content", piece)] if piece else []


def _strip_think_blocks(text: str) -> str:
    """非流式出口兜底：剥掉内联 <think>…</think>（含未闭合的尾部思考块）。"""
    s = str(text or "")
    if _THINK_OPEN not in s:
        return s
    head, _, rest = s.partition(_THINK_OPEN)
    while True:
        _close, _tag, tail = rest.partition(_THINK_CLOSE)
        if _tag:
            _pre, _t2, rest = tail.partition(_THINK_OPEN)
            head += _pre
            if not _t2:
                return head
            continue
        # 无闭合标签：剩余部分整段按思考丢弃
        return head


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

    config = {
        "base_url": config.get("base_url") or _settings.LLM_BASE_URL,
        "api_key": config.get("api_key") or _settings.LLM_API_KEY,
        "model": config.get("model") or _settings.LLM_MODEL,
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_tokens", 16000),
        "upstream_format": str(config.get("upstream_format") or "openai").lower(),
        # thinking 透传（anthropic 上游）：GLM 系模型在 /api/anthropic 默认开思考，
        # 每个工具轮先吐数千字符思考流 → 单轮 40-130s。llm_config 配
        # {"thinking":{"type":"disabled"}} 显式关闭；不配 = 模型默认行为。
        "thinking": config.get("thinking")
        if isinstance(config.get("thinking"), dict) and config.get("thinking")
        else None,
    }
    # 能力档案事实源=探测：注入与当前 model@协议+端点 匹配的最近实测定论项
    config["probe_capabilities"] = _probe_capabilities_for(config)
    return config


def _is_anthropic_upstream(config: dict) -> bool:
    """协议分流唯一判据：llm_config.upstream_format == "anthropic"。

    Anthropic Messages 端点（如智谱 z.ai https://api.z.ai/api/anthropic）只认
    /v1/messages 家族路径——文本、JSON、流式、工具四条链路【全部】必须走
    anthropic_channel；只要有一条漏走 OpenAI SDK，换供应商就会拿到
    「HTTP 200 包 404 → 静默空回复」。别只给带 tools 的调用分流（历史教训）。
    """
    return str(config.get("upstream_format") or "openai").lower() == "anthropic"


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
    "glm": {
        "supports_json_mode": True,
        "supports_native_tools": True,
        "supports_strict_tools": False,
        "reasoning_model": True,
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
    for family in ("deepseek-v4-flash", "deepseek-v4-pro", "deepseek", "qwen", "glm", "gpt"):
        if key.startswith(family):
            return dict(BUILTIN_MODEL_CAPABILITIES[family])
    return dict(DEFAULT_MODEL_CAPABILITIES)


def get_model_capabilities(model: Optional[str] = None, config: Optional[dict] = None) -> Dict[str, bool]:
    """返回当前/指定模型的有效能力档案：内置家族默认 + 协议修正 + 实测（probe_capabilities）。

    档案事实源=探测：没探测过走内置保守默认；探测有定论的项（probe_capabilities）以实测
    为准。没有手工修正层——端点行为与档案不符时重新「能力探测」即可，结果落库自动生效。
    """
    config = config if config is not None else _get_llm_config()
    model = (model or config.get("model") or "").strip()
    caps = _builtin_capabilities(model)
    # 上游为 Anthropic Messages 时：tool_use 天然可用（/messages 认原生 function calling），
    # 抬为 True；response_format JSON mode 不存在，降为 False（chat_json 走提示词式，见
    # use_json_mode 的 (not use_anthropic) 短路）。两项都可被实测定论覆盖。
    if str(config.get("upstream_format") or "openai").lower() == "anthropic":
        caps["supports_native_tools"] = True
        caps["supports_json_mode"] = False

    probed = config.get("probe_capabilities")
    if isinstance(probed, dict):
        for field in caps:
            if field in probed:
                caps[field] = bool(probed[field])
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
    """Yield token deltas from the model (OpenAI 兼容 / Anthropic Messages 双协议).

    messages: [{role: 'system'|'user'|'assistant', content: '...'}, ...]
    """
    config = _get_llm_config()
    if _is_anthropic_upstream(config):
        from app.services import anthropic_channel
        has_content = False
        stop_reason: Optional[str] = None
        try:
            async for item in anthropic_channel.stream(
                messages,
                tools=None,
                model=model or config["model"],
                base_url=config["base_url"],
                api_key=config["api_key"],
                max_tokens=config["max_tokens"] if max_tokens is None else max_tokens,
                temperature=config["temperature"] if temperature is None else temperature,
                thinking=config.get("thinking"),
            ):
                item_type = item.get("type")
                if item_type == "content":
                    has_content = True
                    yield str(item.get("delta") or "")
                elif item_type == "meta":
                    stop_reason = item.get("stop_reason")
        except anthropic_channel.AnthropicChannelError as e:
            raise LLMError(str(e)) from e
        if not has_content:
            # 与 OpenAI 通道同款诊断：reasoning 模型把预算耗在思考上 → 正文被截
            if stop_reason == "max_tokens":
                yield TRUNCATED_NOTICE
            else:
                yield (
                    f"⚠️ 模型返回为空(content 为空,stop_reason={stop_reason or 'none'})。"
                    "可能原因:模型异常、输入超限或被安全过滤。"
                )
        return

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
        _think = _ThinkStreamFilter()
        async for chunk in stream:
            try:
                choice = chunk.choices[0]
            except (AttributeError, IndexError):
                continue
            if choice.finish_reason:
                finish_reason = choice.finish_reason
            delta = choice.delta.content
            if delta:
                # 内联 <think> 块不进正文（本通道无 reasoning 消费方，思考段直接丢弃）
                for kind, text in _think.feed(delta):
                    if kind == "content" and text:
                        has_content = True
                        yield text
        for kind, text in _think.flush():
            if kind == "content" and text:
                has_content = True
                yield text
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
    use_anthropic = _is_anthropic_upstream(config)
    client = None if use_anthropic else _client(config["base_url"], config["api_key"], timeout=timeout)
    messages = _ensure_json_instruction(messages)

    profile = get_model_capabilities(model or config["model"], config)
    last_err: Optional[Exception] = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        # Anthropic Messages 没有 response_format=json_object：靠 _ensure_json_instruction
        # 提示词约束 + 同一套解析/收口管线，重试语义与 JSON mode 失败降级一致。
        use_json_mode = (not use_anthropic) and bool(profile.get("supports_json_mode")) and attempt == 1
        try:
            if use_anthropic:
                from app.services import anthropic_channel
                result = await anthropic_channel.chat(
                    messages,
                    tools=None,
                    model=model or config["model"],
                    base_url=config["base_url"],
                    api_key=config["api_key"],
                    max_tokens=max_tokens if max_tokens is not None else config["max_tokens"],
                    temperature=config["temperature"] if temperature is None else temperature,
                    timeout=timeout,
                    thinking=thinking if isinstance(thinking, dict) else config.get("thinking"),
                )
                content = _strip_think_blocks(
                    str((result.get("message") or {}).get("content") or "")).strip()
            else:
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
                    content = _strip_think_blocks(
                        (resp.choices[0].message.content or "")).strip()
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
                thinking=config.get("thinking"),
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
    """返回当前/指定模型的能力档案视图（内置 + 生效 + 最近实测），供模型能力档案页展示。"""
    config = _get_llm_config()
    model = (model or config.get("model") or "").strip()
    builtin = _builtin_capabilities(model)
    effective = get_model_capabilities(model, config)

    fmt = str(config.get("upstream_format") or "openai").lower()
    probes = _load_probe_records()
    return {
        "model": model,
        "upstream_format": fmt,
        "builtin": builtin,
        "effective": effective,
        "last_probe": probes.get(_probe_key(model, fmt, str(config.get("base_url") or ""))),
    }


_PROBE_STORE_KEY = "llm_capability_probes"


def _probe_key(model: str, upstream_format: str, base_url: str = "") -> str:
    """留档键 model@协议@端点域名：同一模型在不同端点各自留档（官方直连/中转实测并存），
    重测只覆盖同端点同模型那一条，换端点不再冲掉历史。"""
    key = f"{(model or '').strip()}@{upstream_format or 'openai'}"
    host = (urlparse(base_url or "").netloc or "").lower()
    return f"{key}@{host}" if host else key


def _normalize_probe_records(records: dict) -> dict:
    """旧版两段键 model@协议 → 新版 model@协议@域名，并回填 model 字段；同键冲突留较新记录。"""
    out: dict = {}
    for key, rec in records.items():
        if not isinstance(rec, dict):
            continue
        rec = dict(rec)
        if key.count("@") == 1:
            model, _, fmt = key.rpartition("@")
            rec.setdefault("model", model.strip())
            rec.setdefault("upstream_format", (fmt or "openai").lower())
        new_key = _probe_key(str(rec.get("model") or ""), str(rec.get("upstream_format") or "openai"),
                             str(rec.get("base_url") or ""))
        old = out.get(new_key)
        if not isinstance(old, dict) or str(rec.get("tested_at") or "") >= str(old.get("tested_at") or ""):
            out[new_key] = rec
    return out


def _load_probe_records() -> dict:
    repo = SystemConfigRepository()
    try:
        records = repo.get_value(_PROBE_STORE_KEY, {})
    finally:
        repo.close()
    if not isinstance(records, dict):
        return {}
    return _normalize_probe_records(records)


def _probe_capabilities_for(config: dict) -> Dict[str, bool]:
    """抽取与当前 model@协议+端点 匹配的最近实测定论项。

    记录要生效必须：探测请求本身成功、base_url 与当前连接一致（换端点后旧记录作废）。
    只抽有定论的项（*_probed=True）；网络抖动导致的单项未定论不注入，保留内置默认。
    """
    model = (config.get("model") or "").strip()
    fmt = str(config.get("upstream_format") or "openai").lower()
    if not model:
        return {}
    try:
        rec = _load_probe_records().get(_probe_key(model, fmt, str(config.get("base_url") or "")))
    except Exception:
        return {}
    if not isinstance(rec, dict) or not rec.get("success"):
        return {}
    if rec.get("base_url") and config.get("base_url") and rec.get("base_url") != config.get("base_url"):
        return {}
    caps: Dict[str, bool] = {}
    for field, flag in (
        ("supports_json_mode", "json_mode_probed"),
        ("supports_native_tools", "native_tools_probed"),
    ):
        if rec.get(flag):
            caps[field] = bool(rec.get(field))
    return caps


def _save_probe_record(config: dict, result: dict) -> None:
    """探测结果落库（system_config.llm_capability_probes，键=model@协议@端点域名）。

    同端点同模型只留最近一次；不同端点各自留档，历史不被冲掉。展示层据此列出
    「实测模型清单」，_probe_capabilities_for 据此让实测直接驱动生效能力；
    落库失败不拖垮探测本身。
    """
    try:
        from datetime import datetime

        record = {
            k: result.get(k)
            for k in (
                "success", "supports_json_mode", "json_mode_probed",
                "supports_native_tools", "native_tools_probed",
                "reasoning_model", "default_thinking", "notes", "message",
            )
        }
        record["tested_at"] = datetime.now().isoformat(timespec="seconds")
        record["upstream_format"] = str(config.get("upstream_format") or "openai").lower()
        record["base_url"] = config.get("base_url")
        record["model"] = (result.get("model") or "").strip()
        records = _load_probe_records()
        records[_probe_key(record["model"], record["upstream_format"], str(record["base_url"] or ""))] = record
        repo = SystemConfigRepository()
        try:
            repo.set(_PROBE_STORE_KEY, records)
        finally:
            repo.close()
    except Exception as e:  # noqa: BLE001 —— 展示性落库，失败只记日志
        logger.warning("probe 记录落库失败: %s", e)


# 端点身份识别（路由元数据，非能力断言）：域名归谁是稳定事实，不像模型规格会过时。
# 不在表内的公网域名 = 第三方中转/自建代理（cloudprime 等 new-api 系代理都落这里）。
_OFFICIAL_ENDPOINT_HOSTS = {
    "api.z.ai": "智谱官方",
    "open.bigmodel.cn": "智谱官方",
    "api.openai.com": "OpenAI 官方",
    "api.anthropic.com": "Anthropic 官方",
    "api.deepseek.com": "DeepSeek 官方",
    "dashscope.aliyuncs.com": "阿里云百炼官方",
    "api.moonshot.cn": "月之暗面官方",
    "open.doubao.com": "火山方舟官方",
    "api.minimax.chat": "MiniMax 官方",
    "api.siliconflow.cn": "硅基流动官方",
}


def _endpoint_identity(base_url: str) -> tuple:
    """→ (身份文案, kind)：official 官方直连 / local 本地自建 / relay 第三方中转。

    用 hostname（去端口）判定身份；留档键 _probe_key 则保留端口（不同端口=不同端点）。
    """
    host = (urlparse(base_url or "").hostname or "").lower()
    if not host:
        return ("未知端点", "relay")
    if host in _OFFICIAL_ENDPOINT_HOSTS:
        return (_OFFICIAL_ENDPOINT_HOSTS[host], "official")
    local = (host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
             or host.endswith(".local")
             or host.startswith(("10.", "192.168."))
             or bool(re.match(r"^172\.(1[6-9]|2\d|3[01])\.", host)))
    if local:
        return ("本地/内网自建", "local")
    return ("第三方中转/自建", "relay")


def list_probe_history() -> dict:
    """实测模型清单：全部探测留档（含失败记录与历史端点），供「实测模型清单」tab 展示。

    只读事实——不掺「拉取模型列表」拉到但没测过的模型；标记与当前 llm_config
    （模型@协议@端点 三对上）匹配的那条为当前使用。
    """
    config = _get_llm_config()
    model = (config.get("model") or "").strip()
    fmt = str(config.get("upstream_format") or "openai").lower()
    current_key = _probe_key(model, fmt, str(config.get("base_url") or "")) if model else ""
    items = []
    for key, rec in _load_probe_records().items():
        if not isinstance(rec, dict):
            continue
        identity, identity_kind = _endpoint_identity(str(rec.get("base_url") or ""))
        items.append({
            "model": rec.get("model") or "",
            "base_url": rec.get("base_url") or "",
            "endpoint_identity": identity,
            "endpoint_identity_kind": identity_kind,
            "upstream_format": str(rec.get("upstream_format") or "openai"),
            "supports_json_mode": rec.get("supports_json_mode"),
            "json_mode_probed": rec.get("json_mode_probed"),
            "supports_native_tools": rec.get("supports_native_tools"),
            "native_tools_probed": rec.get("native_tools_probed"),
            "default_thinking": rec.get("default_thinking"),
            "reasoning_model": rec.get("reasoning_model"),
            "success": rec.get("success"),
            "message": rec.get("message"),
            "notes": rec.get("notes"),
            "tested_at": rec.get("tested_at"),
            "is_current": bool(current_key) and key == current_key,
        })
    items.sort(key=lambda r: str(r.get("tested_at") or ""), reverse=True)
    return {"records": items, "current_key": current_key}


def probe_model_capabilities(overrides: Optional[dict] = None) -> dict:
    """实测当前端点的 JSON mode / 原生 tools 支持情况，reasoning 用内置档案作提示。

    只做轻量探测（每项单次小请求），结果供前端「能力探测」按钮展示与回写。
    """
    config = _resolve_config(overrides)
    if not config.get("api_key"):
        return {"success": False, "model": config.get("model"), "message": "未配置 api_key"}
    if not config.get("model"):
        return {"success": False, "model": config.get("model"), "message": "未配置 model"}
    if _is_anthropic_upstream(config):
        result = _probe_anthropic(config)
        _save_probe_record(config, result)
        return result
    try:
        from openai import OpenAI
        client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=30, max_retries=0)
    except Exception as e:
        return {"success": False, "model": config.get("model"), "message": _format_err(e)}

    out: dict = {
        "success": True,
        "model": config["model"],
        "supports_json_mode": False,
        "json_mode_probed": False,
        "supports_native_tools": False,
        "native_tools_probed": False,
        "reasoning_model": _builtin_capabilities(config["model"]).get("reasoning_model", False),
        "default_thinking": False,
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
        # 请求成功即有定论（返回空 = 不支持，不是探测失败）
        out["supports_json_mode"] = bool(content)
        out["json_mode_probed"] = True
        if not content:
            out["notes"].append("JSON mode 返回空正文")
    except Exception as e:
        out["supports_json_mode"] = False
        out["notes"].append(f"JSON mode 探测失败: {_format_err(e)}")

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
        msg = resp.choices[0].message
        tool_calls = list(getattr(msg, "tool_calls", None) or [])
        out["supports_native_tools"] = bool(tool_calls)
        out["native_tools_probed"] = True
        reasoning = getattr(msg, "reasoning_content", None) or getattr(msg, "reasoning", None)
        if reasoning:
            out["default_thinking"] = True
    except Exception as e:
        out["supports_native_tools"] = False
        out["notes"].append(f"原生 tools 探测失败: {_format_err(e)}")

    _save_probe_record(config, out)
    return out


def _probe_anthropic(config: dict) -> dict:
    """Anthropic Messages 端点能力实测：原生 tools（真发一次 tool_use 请求）+ JSON 输出可靠性（提示词式）。

    「切换供应商后原生能力真实启用」的一键验证口——探测走的就是 anthropic_channel 同款
    协议路径（{base}/v1/messages + x-api-key），探测通过 = 四条链路的工具/JSON 通道可用。
    """
    import requests

    from app.services.anthropic_channel import _wrapped_error, messages_base

    url = messages_base(config.get("base_url")) + "/messages"
    headers = {
        "x-api-key": str(config["api_key"]),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    # glm 等 reasoning 模型思考吃预算：探测给 1024，避免「思考耗尽→正文/工具空」的假阴性
    out: dict = {
        "success": True,
        "model": config["model"],
        "supports_json_mode": False,
        "json_mode_probed": False,
        "supports_native_tools": False,
        "native_tools_probed": False,
        "reasoning_model": _builtin_capabilities(config["model"]).get("reasoning_model", False),
        "default_thinking": False,
        "notes": ["Anthropic 协议无原生 JSON mode，此处实测「提示词 JSON 输出」可靠性"],
    }

    def _post(payload: dict) -> dict:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        try:
            data = resp.json()
        except ValueError:
            raise RuntimeError(f"HTTP {resp.status_code} 非 JSON 响应: {resp.text[:200]}")
        wrapped = _wrapped_error(data)
        if wrapped:
            raise RuntimeError(wrapped)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {json.dumps(data, ensure_ascii=False)[:200]}")
        return data

    def _text_blocks(data: dict) -> str:
        return "".join(
            str(b.get("text") or "") for b in (data.get("content") or [])
            if isinstance(b, dict) and b.get("type") == "text")

    def _has_thinking(data: dict) -> bool:
        return any(
            isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking")
            for b in (data.get("content") or []))

    try:
        data = _post({
            "model": config["model"], "max_tokens": 1024,
            "messages": [{"role": "user", "content": "只输出一个 JSON 对象：{\"ok\": true}"}],
        })
        # 请求成功即有定论：解析出对象=支持；返回了正文但解析不出=不支持（思考耗尽算不支持，
        # 提示词式 JSON 的可靠性本来就要覆盖这种情况）
        if _has_thinking(data):
            out["default_thinking"] = True
        text = _strip_think_blocks(_text_blocks(data)).strip()
        try:
            parsed = _parse_json_content(text)
            out["supports_json_mode"] = isinstance(parsed, dict)
            out["json_mode_probed"] = True
            if not isinstance(parsed, dict):
                out["notes"].append("JSON 输出未解析出对象")
        except ValueError:
            out["supports_json_mode"] = False
            out["json_mode_probed"] = True
            out["notes"].append("JSON 输出解析失败（正文为空可能是思考耗尽预算）")
    except Exception as e:
        out["notes"].append(f"JSON 输出探测失败: {_format_err(e)}")

    try:
        data = _post({
            "model": config["model"], "max_tokens": 1024,
            "messages": [{"role": "user", "content": "请调用 get_time 工具获取当前时间"}],
            "tools": [{
                "name": "get_time",
                "description": "获取当前时间",
                "input_schema": {"type": "object", "properties": {}},
            }],
        })
        if _has_thinking(data):
            out["default_thinking"] = True
        tool_uses = [b for b in (data.get("content") or [])
                     if isinstance(b, dict) and b.get("type") == "tool_use"]
        out["supports_native_tools"] = bool(tool_uses)
        out["native_tools_probed"] = True
        if not tool_uses:
            out["notes"].append("本轮未触发 tool_use（模型选择直接回答，可重试一次探测）")
        if out["default_thinking"]:
            out["notes"].append("默认开思考：不带 thinking 参数也吐思考块——「模型与连接→思考模式」选「关闭」可提速")
    except Exception as e:
        out["supports_native_tools"] = False
        out["notes"].append(f"原生 tools 探测失败: {_format_err(e)}")

    return out


def test_connection(overrides: Optional[dict] = None) -> dict:
    """实测一次 chat completion（同步，max_tokens=8）。返回 {success, message}。

    成功 message 给人可读确认；失败 message 是真实错误（HTTP/鉴权/model 名等），
    供 AI 设置页「测试连接」按钮直接展示，不再被占位文案吞掉。
    upstream_format=anthropic 走 /v1/messages（OpenAI SDK 打不通该协议）。
    """
    config = _resolve_config(overrides)
    if not config.get("api_key"):
        return {"success": False, "message": "未配置 api_key（填入或设置 .env 的 LLM_API_KEY）"}
    if not config.get("model"):
        return {"success": False, "message": "未配置 model（填入或设置 .env 的 LLM_MODEL）"}
    if str(config.get("upstream_format") or "openai").lower() == "anthropic":
        return _test_connection_anthropic(config)
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


def _test_connection_anthropic(config: dict) -> dict:
    """Anthropic Messages 协议的连接实测：POST {base}/v1/messages（同步小请求）。"""
    import requests

    from app.services.anthropic_channel import _wrapped_error, messages_base

    url = messages_base(config.get("base_url")) + "/messages"
    headers = {
        "x-api-key": str(config["api_key"]),
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {"model": config["model"], "max_tokens": 8,
               "messages": [{"role": "user", "content": "ping"}]}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
    except Exception as e:
        return {"success": False, "message": _format_err(e)}
    try:
        data = resp.json()
    except ValueError:
        return {"success": False, "message": f"HTTP {resp.status_code} @ {url}: {resp.text[:200]}"}
    wrapped = _wrapped_error(data)
    if wrapped:
        return {"success": False, "message": f"Anthropic 上游错误 @ {url}: {wrapped}"}
    if resp.status_code != 200:
        return {"success": False, "message": f"HTTP {resp.status_code} @ {url}: "
                                             f"{json.dumps(data, ensure_ascii=False)[:200]}"}
    text = "".join(
        str(b.get("text") or "") for b in (data.get("content") or [])
        if isinstance(b, dict) and b.get("type") == "text").strip()
    return {"success": True, "message": f"连接成功 · 模型 {config['model']} 已响应", "reply": text}


def _list_models_raw(url: str, headers: dict) -> tuple:
    """裸 HTTP 拉模型列表：兼容 data/models/result 清单字段与 id/model/name 三种 id 键。

    返回 (ids, http_status, 错误摘要)；HTTP 200 包错误体时 ids 为空、摘要带真实响应。
    """
    import requests
    try:
        resp = requests.get(url, headers=headers, timeout=20)
    except Exception as e:
        return [], 0, _format_err(e)
    try:
        payload = resp.json()
    except ValueError:
        return [], resp.status_code, resp.text[:200]
    items = None
    if isinstance(payload, dict):
        items = payload.get("data")
        if items is None:
            items = payload.get("models") or payload.get("result")
    if not isinstance(items, list):
        items = []
    ids = sorted({str(it.get("id") or it.get("model") or it.get("name"))
                  for it in items
                  if isinstance(it, dict) and (it.get("id") or it.get("model") or it.get("name"))})
    snippet = "" if ids else json.dumps(payload, ensure_ascii=False)[:200]
    return ids, resp.status_code, snippet


def _list_models_anthropic(config: dict) -> list:
    """Anthropic Messages 协议的模型列表：GET {base}/v1/models（x-api-key 头）。"""
    from app.services.anthropic_channel import messages_base

    url = messages_base(config.get("base_url")) + "/models"
    ids, status, snippet = _list_models_raw(url, {
        "x-api-key": str(config["api_key"]),
        "anthropic-version": "2023-06-01",
    })
    if ids:
        return ids
    if status == 0:
        raise LLMError(f"拉取模型列表失败 @ {url}: {snippet}")
    raise LLMError(f"未拿到模型列表（HTTP {status}）{('：' + snippet) if snippet else ''} @ {url}。"
                   "该端点可能不支持 /models，请手动填写模型名")


def list_models(overrides: Optional[dict] = None) -> list:
    """拉取 provider 可用模型 id 列表，按 id 排序。

    upstream_format=anthropic → GET {base}/v1/models（x-api-key）；
    openai → OpenAI SDK，页对象 data 为空/报错时回落裸 HTTP 解析（部分兼容端点把错误
    包在 HTTP 200 里，如 z.ai 的 {"code":500,"msg":"404 NOT_FOUND"}，SDK 解析成 data=None，
    曾报 'NoneType' object is not iterable）。
    raises LLMError: 网络/鉴权/端点不支持 /models 时（消息带 provider 真实响应）。
    """
    config = _resolve_config(overrides)
    if not config.get("api_key"):
        raise LLMError("未配置 api_key（填入或设置 .env 的 LLM_API_KEY）")
    if str(config.get("upstream_format") or "openai").lower() == "anthropic":
        return _list_models_anthropic(config)
    base = (config.get("base_url") or "").rstrip("/")
    api_key = str(config["api_key"])
    sdk_err: Optional[str] = None
    try:
        from openai import OpenAI
        client = OpenAI(base_url=base, api_key=api_key, timeout=20, max_retries=0)
        page = client.models.list()
        ids = sorted({str(m.id) for m in (getattr(page, "data", None) or [])
                      if getattr(m, "id", None)})
        if ids:
            return ids
    except Exception as e:
        sdk_err = _format_err(e)
    ids, status, snippet = _list_models_raw(f"{base}/models",
                                            {"Authorization": f"Bearer {api_key}"})
    if ids:
        return ids
    detail = f"未拿到模型列表（HTTP {status}）{('：' + snippet) if snippet else ''}"
    if sdk_err:
        detail += f"；SDK：{sdk_err}"
    raise LLMError(detail + "。该端点可能不支持 /models，请手动填写模型名")


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
    model_name = model or config["model"]
    caps = get_model_capabilities(model_name, config)
    use_tools = bool(tools) and bool(caps.get("supports_native_tools"))
    if _is_anthropic_upstream(config):
        # Anthropic Messages 端点：带不带 tools 都必须走 anthropic_channel——纯文本
        # 若走 OpenAI SDK 会打 {base}/chat/completions，z.ai 这类端点回 200 包 404
        # → SDK 静默吐空流 → 上层「(空回复)」（2026-09-14 实测根因）。
        from app.services import anthropic_channel
        saw_content = saw_tools = False
        stop_reason: Optional[str] = None
        try:
            async for item in anthropic_channel.stream(
                messages,
                tools=tools if use_tools else None,
                model=model_name,
                base_url=config["base_url"],
                api_key=config["api_key"],
                max_tokens=max_tokens if max_tokens is not None else config["max_tokens"],
                temperature=config["temperature"] if temperature is None else temperature,
                timeout=timeout,
                first_token_timeout=first_token_timeout,
                overall_timeout=overall_timeout,
                thinking=config.get("thinking"),
            ):
                item_type = item.get("type")
                if item_type == "content":
                    saw_content = True
                elif item_type == "tool_calls":
                    saw_tools = True
                elif item_type == "meta":
                    stop_reason = item.get("stop_reason")
                yield item
            if not saw_content and not saw_tools and stop_reason == "max_tokens":
                # 思考耗尽预算、正文零产出：与 OpenAI 通道同款兜底，绝不让上层拿到空气
                yield {"type": "content", "delta": TRUNCATED_NOTICE, "truncated": True}
            return
        except anthropic_channel.AnthropicTimeoutError as e:
            # 超时不是「通道不支持原生 tools」：误报会让上层白白降级掉工具通道，
            # 必须收口成 LLMError，让上层按「可重试 / 可如实失败」处理。
            raise LLMError(str(e)) from e
        except anthropic_channel.AnthropicChannelError as e:
            # 带 tools 的失败可能只是「上游不认 tools」→ 收口成 Unsupported 让上层
            # 降级文本循环；纯文本调用没有降级余地，必须如实报错。
            if use_tools:
                raise LLMNativeToolsUnsupported(str(e)) from e
            raise LLMError(str(e)) from e

    client = _client(config["base_url"], config["api_key"], timeout=timeout)
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
        _think = _ThinkStreamFilter()
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
                # 内联 <think> 块改道为 reasoning 事件：思考照样进「思考过程」折叠 UI，
                # 正文与落库文本保持干净（不变量：chunk 拼接 == 落库 answer）
                for kind, text in _think.feed(content):
                    if not text:
                        continue
                    if kind == "content":
                        has_content = True
                        yield {"type": "content", "delta": text}
                    else:
                        yield {"type": "reasoning", "delta": text}
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
        # 流结束：清掉 <think> 过滤器扣留的尾巴（可能横跨最后几个 chunk）
        for kind, text in _think.flush():
            if not text:
                continue
            if kind == "content":
                has_content = True
                yield {"type": "content", "delta": text}
            else:
                yield {"type": "reasoning", "delta": text}
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
