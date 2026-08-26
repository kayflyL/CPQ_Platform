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
    """多轮回复时，先用 LLM 判“这句到底在干嘛”；对确定节点会答错的意图
    （看目录/听不懂/闲聊/普通提问）直接给自然回复并停在原地，其余放行回节点。
    回复一律由 LLM 生成（人设/边界在数据文件），代码不写死任何话术；LLM 不可用则不拦截。"""
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

    ctx_lines = _intent_context(ctx)
    try:
        from app.services.workflow_intent import catalog_digest
        cat = await catalog_digest()
    except Exception:
        cat = ""
    if cat:
        ctx_lines += "\\n\\n【在售目录】\\n" + cat

    try:
        from app.services.workflow_intent import reply_with_context
        reply = await reply_with_context(answer, ctx_lines)
    except Exception:
        reply = ""
    if not reply:
        return False

    ctx["awaiting_input"] = True
    ctx["current_target"] = node_id
    ctx["last_ask_question"] = reply
    if broadcast:
        try:
            await broadcast({"type": "need_confirm", "step": node_id, "question": reply,
                             "options": [], "why": "intent_reply"})
        except Exception:
            pass
    return True


'''
s = s[:i] + new_fn + s[j:]
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("ok")
