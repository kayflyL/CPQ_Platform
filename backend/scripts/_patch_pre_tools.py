# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "reasoning_executor.py")
text = io.open(path, encoding="utf-8").read()

anchor = "def _apply_agent_effects(structured: dict, ctx: dict, config: dict) -> dict:"
helpers = r'''def _resolve_pre_args(args: Any, ctx: dict) -> Any:
    """解析 pre_tools 参数模板：ctx.<path> 取 ctx，req.<path> 取 requirement。"""
    if isinstance(args, str):
        if args.startswith("ctx."):
            return _dig_path(ctx, args[4:])
        if args.startswith("req."):
            return _dig_path(ctx.get("requirement") or {}, args[4:])
        return args
    if isinstance(args, dict):
        return {k: _resolve_pre_args(v, ctx) for k, v in args.items()}
    if isinstance(args, list):
        return [_resolve_pre_args(x, ctx) for x in args]
    return args


async def _run_pre_tools(config: dict, ctx: dict) -> list[str]:
    """执行节点配置的确定性前置工具，收集事实供 LLM 单次决策（AI 只编排，事实从工具来）。"""
    specs = config.get("pre_tools") or []
    if not specs:
        return []
    from app.services.agent_tools import build_tool_registry
    names = []
    for spec in specs:
        t = spec.get("tool") if isinstance(spec, dict) else spec
        if t:
            names.append(str(t))
    if not names:
        return []
    reg = build_tool_registry({"enabled_tools": names})
    out: list[str] = []
    for spec in specs:
        tool = spec.get("tool") if isinstance(spec, dict) else spec
        if not tool:
            continue
        args = spec.get("args") if isinstance(spec, dict) else {}
        args = _resolve_pre_args(args, ctx)
        try:
            res = await reg.execute(str(tool), args)
        except Exception as exc:
            logger.exception("pre_tool failed tool=%s", tool)
            res = {"error": str(exc)}
        try:
            txt = json.dumps(res, ensure_ascii=False, default=str)
        except Exception:
            txt = str(res)
        out.append(f"[工具 {tool} 结果]\n{txt[:3000]}")
    return out


'''
assert anchor in text
text = text.replace(anchor, helpers + anchor, 1)

old_block = '''    extra_context = "\\n\\n".join(extra)

    result = await run_react_loop(
        requirement_text=str(text),
        config=config,
        extra_context=extra_context,
        max_iterations=int(config.get("max_iterations") or 6),
        system_prompt=config.get("system_prompt") or None,
        history=ctx.get("history") or [],
    )'''
new_block = '''    pre = await _run_pre_tools(config, ctx)
    extra_context = "\\n\\n".join(pre + extra)

    result = await run_react_loop(
        requirement_text=str(text),
        config=config,
        extra_context=extra_context,
        max_iterations=int(config.get("max_iterations") or 6),
        system_prompt=config.get("system_prompt") or None,
        history=ctx.get("history") or [],
        final_only=bool(config.get("final_only")),
        final_only_contract=config.get("final_only_contract"),
    )'''
assert old_block in text, "run block anchor missing"
text = text.replace(old_block, new_block, 1)
io.open(path, "w", encoding="utf-8").write(text)
print("agent pre_tools/final_only patched OK")
