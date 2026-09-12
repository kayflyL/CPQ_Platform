# -*- coding: utf-8 -*-
"""agent_tool_registry —— LLM 工具注册表门面。只负责注册 schema、数据源权限校验、执行分发。"""
import asyncio
from typing import Any, Callable, Dict, List

_MAX_DIGEST_CHARS = 4000
_TOOL_CALL_TIMEOUT = 60.0

def _truncate(s: str, limit: int = _MAX_DIGEST_CHARS) -> str:
    s = s or ""
    return s if len(s) <= limit else s[:limit] + "\n…(截断)"

class ToolRegistry:
    def __init__(self, allowed_data_sources: list = None):
        self._tools: Dict[str, dict] = {}
        self._allowed_data_sources = set(allowed_data_sources or []) if allowed_data_sources is not None else None
    def register(self, name: str, description: str, parameters: dict, handler: Callable[[dict], Any], data_sources: list = None, summary: str = None):
        self._tools[name] = {"name": name, "description": description, "summary": summary or description, "parameters": parameters, "handler": handler, "data_sources": data_sources or []}
    def schemas(self) -> List[dict]:
        return [{"type": "function", "function": {"name": t["name"], "description": t["summary"], "parameters": t["parameters"]}} for t in self._tools.values()]
    def names(self) -> List[str]:
        return list(self._tools.keys())
    async def execute(self, name: str, args: dict) -> Any:
        spec = self._tools.get(name)
        if not spec:
            return {"error": f"未知工具: {name}"}
        required = spec.get("data_sources") or []
        if self._allowed_data_sources is not None and required:
            missing = [item for item in required if item not in self._allowed_data_sources]
            if missing:
                return {"error": f"工具 {name} 缺少数据域权限: {', '.join(sorted(missing))}"}
        try:
            return await asyncio.wait_for(spec["handler"](args or {}), timeout=_TOOL_CALL_TIMEOUT)
        except asyncio.TimeoutError:
            return {"error": f"工具 {name} 执行超时（>{int(_TOOL_CALL_TIMEOUT)}s），已按失败处理"}
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("工具 %s 执行失败", name)
            return {"error": f"工具 {name} 执行失败: {e}"}
