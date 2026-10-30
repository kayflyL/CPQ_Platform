# -*- coding: utf-8 -*-
"""agent_tool_registry —— LLM 工具注册表门面。只负责注册 schema、数据源权限校验、执行分发。

P3 上安全带（2026-10-31）：execute 对写语义工具（contract.effects="write"）统一做两件事——
①**结构化审计落账**（agent_audit.audit_write：actor/会话/工具/参数摘要/结果，fire-and-forget
不挡业务）；②**写后回读**（contract.verify 指向"模块.函数"→ 惰性解析调用，回读不符 = 结果
降级为 error 事实——"写了但没写对"如实报错，案台不算成功）。
"""
import asyncio
import json
import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_DIGEST_CHARS = 4000
_TOOL_CALL_TIMEOUT = 60.0

def _truncate(s: str, limit: int = _MAX_DIGEST_CHARS) -> str:
    s = s or ""
    return s if len(s) <= limit else s[:limit] + "\n…(截断)"

def _resolve_verify(ref: str) -> Optional[Callable]:
    """契约 verify 引用（"模块.函数"）→ 惰性解析函数对象；解析失败返回 None（降级标注）。"""
    try:
        mod_name, fn_name = str(ref or "").rsplit(".", 1)
        import importlib
        mod = importlib.import_module(f"app.services.{mod_name}")
        return getattr(mod, fn_name)
    except Exception:
        logger.exception("决策回读函数解析失败 verify=%s（降级：跳过回读）", ref)
        return None

class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, dict] = {}
    def register(self, name: str, description: str, parameters: dict, handler: Callable[[dict], Any],
                 summary: str = None, contract: dict = None):
        self._tools[name] = {"name": name, "description": description, "summary": summary or description,
                             "parameters": parameters, "handler": handler, "contract": contract or {}}
    def schemas(self) -> List[dict]:
        return [{"type": "function", "function": {"name": t["name"], "description": t["summary"], "parameters": t["parameters"]}} for t in self._tools.values()]
    def names(self) -> List[str]:
        return list(self._tools.keys())
    def contract(self, name: str) -> dict:
        return (self._tools.get(name) or {}).get("contract") or {}

    async def execute(self, name: str, args: dict) -> Any:
        spec = self._tools.get(name)
        if not spec:
            return {"error": f"未知工具: {name}"}
        contract = spec.get("contract") or {}
        try:
            result = await asyncio.wait_for(spec["handler"](args or {}), timeout=_TOOL_CALL_TIMEOUT)
        except asyncio.TimeoutError:
            return {"error": f"工具 {name} 执行超时（>{int(_TOOL_CALL_TIMEOUT)}s），已按失败处理"}
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("工具 %s 执行失败", name)
            return {"error": f"工具 {name} 执行失败: {e}"}
        if contract.get("effects") != "write" or not isinstance(result, dict) or not result.get("ok"):
            return result
        from app.services.skill_tool_context import TOOL_CTX
        return write_finish(name, contract, args or {}, result, TOOL_CTX.get() or {})


def write_finish(name: str, contract: dict, args: dict, result: dict, ctx: dict) -> dict:
    """写语义工具的成功收尾：①写后回读（契约 verify，不符=error 事实降级）；
    ②结构化审计落账（fire-and-forget）。registry 写路径唯一出口，sync 便于测试。"""
    readback = None
    verify_ref = contract.get("verify")
    if verify_ref:
        fn = _resolve_verify(verify_ref)
        if fn is not None:
            ok, facts = fn(args, result)
            readback = json.dumps({"ok": ok, **(facts if isinstance(facts, dict) else {})},
                                  ensure_ascii=False, default=str)
            if not ok:
                return {**result, "ok": False, "error": "readback_mismatch",
                        "readback": facts, "message": f"写后回读不符：{facts}"}
    try:
        from app.services.agent_audit import audit_write
        audit_write(tool=name, thread_id=str(ctx.get("thread_id") or ""),
                    agent_role_key=str(ctx.get("role_key") or ""),
                    user_id=str(ctx.get("user_id") or ""),
                    args_digest=_truncate(json.dumps(args or {}, ensure_ascii=False, default=str), 400),
                    result_ok=bool(result.get("ok")),
                    target_entity=str(contract.get("target_entity") or ""),
                    entity_id=str(result.get("quotation_id") or result.get("opportunity_id")
                                  or result.get("sheet_id") or result.get("bom_scheme_id") or ""),
                    readback=readback or "")
    except Exception:
        logger.exception("写工具审计落账失败 tool=%s（不挡业务）", name)
    return result
