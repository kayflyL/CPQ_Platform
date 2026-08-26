# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "reasoning_executor.py")
text = io.open(path, encoding="utf-8").read()

helper = r'''async def _run_single_shot(text: str, config: dict, extra_context: str) -> dict:
    """final_only 节点的单发决策：走 chat_json（非流式，快），模型一次给契约 JSON。

    返回与 run_react_loop 兼容的 {ok, answer, iterations, tool_calls_log, thought_log}。
    """
    from app.services import llm_client
    from app.services.agent_react import REACT_SYSTEM_PROMPT, FINAL_ONLY_CONTRACT
    base: dict = {"ok": False, "answer": "", "iterations": 0, "tool_calls_log": [], "thought_log": []}
    if not llm_client.is_llm_enabled():
        base["answer"] = "AI 未启用"
        return base
    sys_prompt = (config.get("system_prompt") or REACT_SYSTEM_PROMPT) \
        + (config.get("final_only_contract") or FINAL_ONLY_CONTRACT) \
        + "\n\n一次输出，只输出一个 JSON 对象，不要 Markdown 代码块，不要复述需求。"
    messages = [{"role": "system", "content": sys_prompt}]
    user_content = f"需求：{text or ''}".strip()
    if extra_context:
        user_content += f"\n\n参考：{extra_context}"
    messages.append({"role": "user", "content": user_content})
    try:
        data = await llm_client.chat_json(llm_client._ensure_json_instruction(messages))
    except Exception as exc:
        logger.warning("single_shot chat_json failed: %s", exc)
        base["answer"] = ""
        return base
    if not isinstance(data, dict):
        base["answer"] = ""
        return base
    action = str(data.get("action") or "").strip()
    if action == "final" and isinstance(data.get("answer"), dict):
        base["answer"] = json.dumps(data.get("answer"), ensure_ascii=False)
        base["ok"] = True
    elif action == "final":
        base["answer"] = str(data.get("answer") or "").strip()
        base["ok"] = True
    else:
        base["answer"] = json.dumps(data, ensure_ascii=False) if data else ""
        base["ok"] = True
    base["iterations"] = 1
    return base


'''
anchor = "async def _handle_generic_agent(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:"
assert anchor in text
text = text.replace(anchor, helper + anchor, 1)

# 在调用 run_react_loop 处分流
old_call = '''    result = await run_react_loop(
        requirement_text=str(text),
        config=config,
        extra_context=extra_context,
        max_iterations=int(config.get("max_iterations") or 6),
        system_prompt=config.get("system_prompt") or None,
        history=ctx.get("history") or [],
        final_only=bool(config.get("final_only")),
        final_only_contract=config.get("final_only_contract"),
    )'''
new_call = '''    if config.get("final_only"):
        result = await _run_single_shot(text, config, extra_context)
    else:
        result = await run_react_loop(
            requirement_text=str(text),
            config=config,
            extra_context=extra_context,
            max_iterations=int(config.get("max_iterations") or 6),
            system_prompt=config.get("system_prompt") or None,
            history=ctx.get("history") or [],
            final_only=False,
        )'''
assert old_call in text, "call anchor missing"
text = text.replace(old_call, new_call, 1)
io.open(path, "w", encoding="utf-8").write(text)
print("single_shot branch patched OK")
