"""LLM client — Qwen (DashScope) via OpenAI-compatible mode.

Streams chat completions token-by-token. Swap base_url/model to switch
providers later without touching callers.

Config priority: system_config (llm_config) > .env > defaults
"""
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
        "max_tokens": config.get("max_tokens", 2000),
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
        async for chunk in stream:
            try:
                delta = chunk.choices[0].delta.content
            except (AttributeError, IndexError):
                delta = None
            if delta:
                yield delta
    except Exception as e:
        raise LLMError(f"LLM 调用失败: {e}") from e
