import io, re, os
p = r"app\services\capability_executor.py"
s = io.open(p, "r", encoding="utf-8", newline="").read()
orig = s

# 1) 替换 _route_resume_intent 整个函数为 _decide_plan_turn
start = s.index("async def _route_resume_intent(")
end = s.index("async def run_fixed_workflow(")
new_fn = '''async def _decide_plan_turn(ctx: dict, message: str, broadcast: Callable[..., Any], pause_target: str) -> bool:
    """角色层唯一的“感知+决策”入口：判断这句对话对当前计划是否有用。

    返回 True 表示已处理（自然回答/退出），本轮不再跑节点；False 表示继续执行计划。
    首轮与续跑都走这里，避免节点内各自再判一次意图（次次多调、互打架）。
    """
    text = str(message or "").strip()
    if not text:
        return False
    try:
        from app.services.workflow_intent import resolve_intent
        idata = await resolve_intent(text, _intent_context(ctx))
    except Exception:
        return False
    intent = str((idata or {}).get("intent") or "").strip().lower()

    if intent == "cancel":
        ctx["flow_exit"] = "cancelled"
        ctx["awaiting_input"] = False
        return True
    if intent == "self_config":
        ctx["flow_exit"] = "self_config"
        ctx["awaiting_input"] = False
        return True
    if intent in ("noise", "ask", "list_catalog", "explain"):
        ctx_lines = _intent_context(ctx)
        try:
            from app.services.workflow_intent import catalog_digest
            cat = await catalog_digest()
        except Exception:
            cat = ""
        if cat and intent == "list_catalog":
            ctx_lines += "\\n\\n【在售目录】\\n" + cat
        try:
            from app.services.workflow_intent import reply_with_context
            reply = await reply_with_context(text, ctx_lines)
        except Exception:
            reply = ""
        if not reply:
            reply = str((idata or {}).get("reply") or "").strip()
        if not reply and intent == "list_catalog" and cat:
            reply = str(cat or "")
        if not reply:
            return False
        ctx["awaiting_input"] = True
        ctx["plan_pause"] = True
        ctx["current_target"] = pause_target
        ctx["last_ask_question"] = reply
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": pause_target, "question": reply,
                                 "options": [], "why": "plan_reply"})
            except Exception:
                pass
        return True
    return False


'''
s = s[:start] + new_fn + s[end:]

# 2) 替换入口 gate + resume 逻辑
old_block = '''    if not str(ctx.get("current_target") or "").strip() and ctx.get("requirement_text"):
        try:
            from app.services.workflow_intent import resolve_intent
            _entry = await resolve_intent(str(ctx.get("requirement_text") or "").strip())
            _entry_intent = str((_entry or {}).get("intent") or "").strip().lower()
            # 关键词兜底：即使 LLM 分类漂移，明显的“列目录/解释”也按非选型处理
            try:
                from app.services.workflow_intent import resolve_intent_keywords
                _kw_intent = resolve_intent_keywords(str(ctx.get("requirement_text") or "").strip())
                if _kw_intent in ("list_catalog", "explain"):
                    _entry_intent = _kw_intent
            except Exception:
                pass
            if _entry_intent in ("noise", "ask", "list_catalog", "explain"):
                from app.services.workflow_intent import catalog_digest, reply_with_context
                _lines = _intent_context(ctx)
                try:
                    _cat = await catalog_digest()
                except Exception:
                    _cat = ""
                if _cat:
                    _lines += "\\n\\n【在售目录】\\n" + _cat
                _reply = await reply_with_context(str(ctx.get("requirement_text") or ""), _lines)
                if not _reply:
                    _reply = str((_entry or {}).get("reply") or "").strip()
                if not _reply and _entry_intent == "list_catalog" and _cat:
                    _reply = str(_cat or "")
                if _reply:
                    ctx["awaiting_input"] = True
                    ctx["current_target"] = "__entry_reply__"
                    ctx["last_ask_question"] = _reply
                    await broadcast({"type": "need_confirm", "step": "input", "question": _reply,
                                     "options": [], "why": "entry_intent_reply"})
                    return ctx
        except Exception:
            pass

    resume_from = str(ctx.get("current_target") or "").strip()
    if resume_from and resume_from in nodes and await _route_resume_intent(ctx, broadcast, resume_from):
        return ctx
    queue: list[str] = sorted([nid for nid, degree in indeg.items() if degree == 0])
    if resume_from and resume_from in nodes:
        # 多轮能力会话：用户回答后从暂停节点继续，避免重跑 input/agent_fill 后把
        # “选型号/换配件/取消”等用户回答误当成原始需求补问。
        queue = [resume_from]'''
new_block = '''    resume_from = str(ctx.get("current_target") or "").strip()
    # 角色层唯一意图感知：无论首轮还是续跑，先判断这句对计划是否有用。
    # 提问/闲聊/看目录/解释 → 自然回答并停在原地；取消/自配 → 退出计划。
    _pause_target = resume_from if (resume_from and resume_from in nodes) else "input"
    _msg = str(ctx.get("last_user_answer") or "").strip() or str(ctx.get("requirement_text") or "").strip()
    if _msg and await _decide_plan_turn(ctx, _msg, broadcast, _pause_target):
        return ctx
    # 从“入口/问答暂停”续跑：current_target 若不属于任何节点（如旧的 __entry_reply__ 或空串），
    # 说明尚未进入节点，继续时应重置为入口，让计划从起点开始。
    if resume_from and resume_from not in nodes:
        ctx["current_target"] = ""
        resume_from = ""
    queue: list[str] = sorted([nid for nid, degree in indeg.items() if degree == 0])
    if resume_from and resume_from in nodes:
        # 多轮能力会话：用户回答后从暂停节点继续，避免重跑 input/agent_fill 后把
        # “选型号/换配件/取消”等用户回答误当成原始需求补问。
        queue = [resume_from]'''
assert old_block in s, "old entry block not found"
s = s.replace(old_block, new_block)

assert s != orig
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("patched OK, len", len(orig), "->", len(s))
