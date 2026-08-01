"""LLM client — Qwen (DashScope) via OpenAI-compatible mode.

Streams chat completions token-by-token. Swap base_url/model to switch
providers later without touching callers.

Config priority: system_config (llm_config) > .env > defaults
"""
import json
from typing import AsyncGenerator, List, Dict, Optional

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
        "base_url": config.get("base_url") or _settings.LLM_BASE_URL,
        "api_key": config.get("api_key") or _settings.LLM_API_KEY,
        "model": config.get("model") or _settings.LLM_MODEL,
        "system_prompt": config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT,
        "temperature": config.get("temperature", 0.7),
        "max_tokens": config.get("max_tokens", 8000),
    }


def _client(base_url: str, api_key: str) -> AsyncOpenAI:
    if not api_key:
        raise LLMError("LLM_API_KEY 未配置(见 .env 或 system_config.llm_config)")
    return AsyncOpenAI(
        base_url=base_url,
        api_key=api_key,
    )


async def stream_chat(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Yield token deltas from the model (OpenAI-compatible streaming).

    messages: [{role: 'system'|'user'|'assistant', content: '...'}, ...]
    """
    config = _get_llm_config()
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
