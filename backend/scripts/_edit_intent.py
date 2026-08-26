import io
p = "backend/app/services/workflow_intent.py"
s = io.open(p, encoding="utf-8").read()

old_intents = '''    "cancel", "confirm_choice", "reselect", "grasp", "noise",
}'''
new_intents = '''    "cancel", "confirm_choice", "reselect", "grasp", "noise", "ask",
}'''
if old_intents not in s:
    raise SystemExit("intents anchor not found")
s = s.replace(old_intents, new_intents, 1)

extra = '''

_REPLY_SCHEMA = {
    "type": "object",
    "properties": {"reply": {"type": "string"}},
    "required": ["reply"],
}


async def reply_with_context(message: str, context: str) -> str:
    """对“普通提问/解释/闲聊”给一句自然中文回复，答案只能基于给定真实上下文。"""
    if not llm_client.is_llm_enabled():
        return ""
    system = (
        "你是 CPQ 服务器需求分析对话助手。请用一到三句自然中文回应用户。\\n"
        "答案只能基于下面的真实上下文；没有明确数据（如价格/兼容/库存）就说“选型后我会帮你确认”，"
        "不要编造型号、参数、价格。\\n\\n上下文：\\n" + str(context or "")[:3000]
    )
    try:
        data = await llm_client.chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": str(message or "")}],
            schema=_REPLY_SCHEMA,
            temperature=0.3,
            timeout=60.0,
            max_attempts=1,
        )
    except Exception as exc:
        logger.debug("workflow intent reply LLM 失败: %s", exc)
        return ""
    return str((data or {}).get("reply") or "").strip()
'''
s += extra
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("patched workflow_intent.py")
