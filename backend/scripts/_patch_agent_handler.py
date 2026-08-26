# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "reasoning_executor.py")
text = io.open(path, encoding="utf-8").read()

# 1) import json
if "import json\n" not in text:
    text = text.replace("import logging\nimport re\nimport time\n",
                        "import json\nimport logging\nimport re\nimport time\n", 1)
# 2) Optional in typing
text = text.replace("from typing import Any, Awaitable, Callable",
                    "from typing import Any, Awaitable, Callable, Optional", 1)

old_handler = '''async def _handle_generic_agent(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Generic agent node: LLM decides, calls tools from the global catalog."""
    from app.services.agent_react import run_react_loop
    text = ctx.get("requirement_text") or ctx.get("normalized_text") or ""
    if not str(text).strip():
        return {"ok": False, "answer": "", "reason": "empty_text"}
    result = await run_react_loop(
        requirement_text=str(text),
        config=config,
        max_iterations=int(config.get("max_iterations") or 6),
        system_prompt=config.get("system_prompt") or None,
        history=ctx.get("history") or [],
    )
    ctx["agent_result"] = result
    return {
        "ok": result.get("ok"),
        "answer": result.get("answer") or "",
        "iterations": result.get("iterations") or 0,
        "tool_calls_log": result.get("tool_calls_log") or [],
        "thought_log": result.get("thought_log") or [],
    }'''

new_handler = '''def _dig_path(obj: Any, dotted: str, default: Optional[Any] = None):
    """按点分路径从 dict 取值，缺失返回 default。"""
    if not dotted:
        return default
    cur = obj
    for part in str(dotted).split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return default
        if cur is None:
            return default
    return cur


async def _handle_generic_agent(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:
    """Generic agent node: LLM decides, calls tools from the global catalog.

    config 可配（节点抽屉）：
      - context_map: [{key,label}] 把上游 ctx 序列化进 extra_context；
      - result_key:  把最终结构化答案写回 ctx 的键（默认沿用 agent_result）；
      - result_mapping: {ctx_key: path} 把答案里的子字段再复制到 ctx 顶层。
    结构化答案取 final answer（JSON 对象），非 JSON 则仅保留 agent_result。
    """
    from app.services.agent_react import run_react_loop
    text = ctx.get("requirement_text") or ctx.get("normalized_text") or ""
    if not str(text).strip():
        return {"ok": False, "answer": "", "reason": "empty_text"}

    extra = []
    for item in config.get("context_map") or []:
        k = str((item or {}).get("key") or "")
        label = str((item or {}).get("label") or k)
        val = ctx.get(k)
        if val is None:
            val = _dig_path(ctx, k)
        if val not in (None, "", [], {}):
            try:
                extra.append(f"[{label}]\\n{json.dumps(val, ensure_ascii=False, default=str)[:2000]}")
            except Exception:
                extra.append(f"[{label}]\\n{str(val)[:2000]}")
    extra_context = "\\n\\n".join(extra)

    result = await run_react_loop(
        requirement_text=str(text),
        config=config,
        extra_context=extra_context,
        max_iterations=int(config.get("max_iterations") or 6),
        system_prompt=config.get("system_prompt") or None,
        history=ctx.get("history") or [],
    )
    ctx["agent_result"] = result

    answer = str(result.get("answer") or "").strip()
    structured: Optional[dict] = None
    if answer:
        try:
            parsed = json.loads(answer)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            structured = parsed

    result_key = str(config.get("result_key") or "agent_result")
    if structured is not None:
        ctx[result_key] = structured
        for ck, path in (config.get("result_mapping") or {}).items():
            val = _dig_path(structured, str(path))
            if val is not None:
                ctx[str(ck)] = val

    return {
        "ok": result.get("ok"),
        "answer": answer,
        "iterations": result.get("iterations") or 0,
        "tool_calls_log": result.get("tool_calls_log") or [],
        "thought_log": result.get("thought_log") or [],
        "structured": structured,
    }'''

assert old_handler in text, "old handler anchor missing"
text = text.replace(old_handler, new_handler, 1)
io.open(path, "w", encoding="utf-8").write(text)
print("reasoning_executor agent handler patched OK")
