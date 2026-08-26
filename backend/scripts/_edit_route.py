import io
p = "backend/app/services/capability_executor.py"
s = io.open(p, encoding="utf-8").read()

start_marker = "async def _route_resume_intent(ctx: dict, broadcast: Callable[..., Any], node_id: str) -> bool:"
end_marker = "async def run_fixed_workflow("
i = s.find(start_marker)
j = s.find(end_marker)
if i < 0 or j < 0 or j <= i:
    raise SystemExit("anchor not found")

new_fn = '''async def _route_resume_intent(ctx: dict, broadcast: Callable[..., Any], node_id: str) -> bool:
    """多轮回复时，先用 LLM 判“这句到底在干嘛”；
    对于确定节点会答错的意图（看目录/听不懂/闲聊/普通提问）直接给自然回复并停在原地，
    其余意图放行回确定性节点（取消/自配/重选/确认/补需求仍由节点处理）。"""
    answer = str(ctx.get("last_user_answer") or "").strip()
    if not answer:
        return False
    try:
        from app.services.workflow_intent import resolve_intent
        intent_data = await resolve_intent(answer, _intent_context(ctx))
    except Exception:
        return False
    intent = str(intent_data.get("intent") or "").strip().lower()
    if intent not in ("list_catalog", "explain", "noise", "ask"):
        return False

    if intent == "list_catalog":
        try:
            from app.services.workflow_intent import catalog_digest
            lines = await catalog_digest()
        except Exception:
            lines = "（暂时读不到目录，请稍后再试）"
        reply = "当前在售服务器目录如下，你可以补充具体需求（场景/类型/系列/形态/预算）：\\n" + str(lines)
    else:
        reply = ""
        try:
            from app.services.workflow_intent import reply_with_context
            _ctx_lines = _intent_context(ctx)
            try:
                from app.services.workflow_intent import catalog_digest
                _ctx_lines += "\\n\\n【在售目录】\\n" + (await catalog_digest())
            except Exception:
                pass
            reply = await reply_with_context(answer, _ctx_lines)
        except Exception:
            reply = ""
        if not reply:
            reply = "收到。你可以继续补充需求，或告诉我去详情页自己配置。"

    ctx["awaiting_input"] = True
    ctx["current_target"] = node_id
    ctx["last_ask_question"] = reply
    if broadcast:
        try:
            await broadcast({"type": "need_confirm", "step": node_id, "question": reply,
                             "options": [], "why": "根据用户提问直接回应"})
        except Exception:
            pass
    return True


'''

s = s[:i] + new_fn + s[j:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("patched _route_resume_intent")
