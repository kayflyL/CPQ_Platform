"""LLM client — Qwen (DashScope) via OpenAI-compatible mode.

Streams chat completions token-by-token. Swap base_url/model to switch
providers later without touching callers.

Config priority: system_config (llm_config) > .env > defaults
"""
import json
from typing import Any, AsyncGenerator, List, Dict, Optional

from openai import AsyncOpenAI

from app.core.config import get_settings
from app.repository.system_config_repo import SystemConfigRepository

_settings = get_settings()

# 默认 System Prompt（被 system_config 覆盖）
DEFAULT_SYSTEM_PROMPT = (
    "你是 CPQ 平台的「方案助手」,辅助销售/FAE 做服务器配置与报价。"
    "用户当前所在页面的业务上下文会以「当前上下文」形式提供给你,作答时优先基于它。"
    "要求:1) 用中文回复;2) 对料号价格、库存、具体型号编号等易变信息,不要编造——"
    "不确定时请用户在配置页确认或查料号库;3) 回答简洁、分点。"
)


class LLMError(Exception):
    """Raised when the LLM provider call fails (network / auth / quota)."""
    pass


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
        "system_prompt": config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_tokens", 8000),
    }


def is_llm_enabled() -> bool:
    """统一 AI 引擎开关（设置-系统设置-AI 设置 → 启用 AI）。所有 AI 能力共用。"""
    try:
        return bool(_get_llm_config().get("enabled", True))
    except Exception:
        return True  # 读配置异常不阻塞：保持现状行为（默认开）


def _client(base_url: str, api_key: str, timeout: float = 600.0) -> AsyncOpenAI:
    if not api_key:
        raise LLMError("LLM_API_KEY 未配置(见 .env 或 system_config.llm_config)")
    return AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
    )


async def stream_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Yield token deltas from the model (OpenAI-compatible streaming).

    messages: [{role: 'system'|'user'|'assistant', content: '...'}, ...]
    """
    config = _get_llm_config()
    if not config.get("enabled", True):
        raise LLMError("AI 引擎未启用（设置 → AI 设置 → 启用 AI）")
    client = _client(config["base_url"], config["api_key"])

    # 如果 messages 没有 system prompt，插入配置的 system prompt
    if messages and messages[0].get("role") != "system":
        messages = [{"role": "system", "content": config["system_prompt"]}] + messages

    try:
        stream = await client.chat.completions.create(
            model=model or config["model"],
            messages=messages,  # type: ignore[arg-type]
            stream=True,
            temperature=config["temperature"],
            max_tokens=config["max_tokens"],
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
        # 流正常结束却无正文：reasoning 类模型(如 step-3.x)在复杂任务上会把
        # max_tokens 预算在思考阶段(reasoning_content)耗尽,正文 content 一个
        # token 都没产出即被 length 截断。这里给出可操作的诊断,而不是让上层
        # 显示无意义的"(空回复)"。
        if not has_content:
            if finish_reason == "length":
                yield (
                    "⚠️ 模型未给出正文:reasoning(思考)阶段耗尽了 max_tokens 预算,"
                    "正式回复被截断(finish_reason=length)。这是 reasoning 类模型"
                    "(如 step-3.x)在复杂任务上的典型现象。请到「AI 设置」调大 "
                    "max_tokens(reasoning 模型建议 ≥ 8000)后重试。"
                )
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
) -> dict:
    """非流式 JSON 模式调用 —— 结构化抽槽专用（LLM 节点 extract_enhance / best_fit 用）。

    与 stream_chat 并存、各司其职：
      • stream_chat —— 流式，给 question_gen「边出字边显示」的体感；
      • chat_json   —— 非流式，收全文再解析 JSON，给结构化抽取（绝不能边流边抽 JSON）。

    护栏（第一期已落实，见 docs/training 调研结论）：
      • reasoning 模型(step-3.x 等)思考阶段会耗光 max_tokens → 正文空回；必须给足 max_tokens(≥8000)；
      • 走 JSON mode(response_format={"type":"json_object"})，按 schema 校验：多余键丢弃、类型强制、
        未知枚举置空（上层回退规则值，绝不裸进 match_kp/compose）；
      • 失败重试一次 → 仍失败 raise LLMError，上层降级到规则抽取结果（绝不阻塞主流程）。

    未配置/不可用时：llm 节点默认 enable_llm=False 走 passthrough，系统脱离网络大模型也能正常运行。
    """
    config = _get_llm_config()
    if not config.get("enabled", True):
        raise LLMError("AI 引擎未启用（设置 → AI 设置 → 启用 AI）")
    client = _client(config["base_url"], config["api_key"], timeout=90)
    if messages and messages[0].get("role") != "system":
        messages = [{"role": "system", "content": config["system_prompt"]}] + messages

    last_err: Optional[Exception] = None
    for attempt in (1, 2):
        try:
            resp = await client.chat.completions.create(
                model=model or config["model"],
                messages=messages,  # type: ignore[arg-type]
                response_format={"type": "json_object"},
                temperature=config["temperature"],
                max_tokens=config["max_tokens"],
            )
            content = ""
            try:
                content = (resp.choices[0].message.content or "").strip()
            except (AttributeError, IndexError):
                raise LLMError("LLM 返回结构异常（无 choices/message）")
            if not content:
                raise LLMError("LLM 返回空内容")
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
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
            # 重试一次：网络抖动/偶发截断可自愈；仍失败 raise LLMError 交上层降级
    raise LLMError(f"LLM JSON 调用失败(重试1次): {last_err}")


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
        client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=20)
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
        client = OpenAI(base_url=config["base_url"], api_key=config["api_key"], timeout=20)
        data = client.models.list()
        return sorted(m.id for m in data.data)
    except Exception as e:
        raise LLMError(_format_err(e)) from e
