import io
p = "backend/app/services/capability_executor.py"
s = io.open(p, encoding="utf-8").read()

helpers = '''

def _intent_context(ctx: dict) -> str:
    """把当前状态拼成意图判定的上下文（只含真实状态，不写死业务词）。"""
    parts: list[str] = []
    target = str(ctx.get("current_target") or "").strip() or "需求分析"
    parts.append("当前所在环节：" + target)
    last_ask = str(ctx.get("last_ask_question") or "").strip()
    if last_ask:
        parts.append("AI 上一条问的是：" + last_ask)
    req = str(ctx.get("requirement_text") or "").strip()
    if req:
        parts.append("客户已表达需求：" + req[:200])
    baselines = ctx.get("baselines") or []
    if isinstance(baselines, list) and baselines:
        names = [str((b or {}).get("name") or "") for b in baselines[:8] if isinstance(b, dict)]
        if names:
            parts.append("当前候选机型：" + "、".join(n for n in names if n))
    return "\\n".join(parts)


async def _route_resume_intent(ctx: dict, broadcast: Callable[..., Any], node_id: str) -> bool:
    """多轮回复时，先用 LLM 判“这句到底在干嘛”；
    对于确定节点会答错的意图（看目录/听不懂/闲聊）直接给自然回复并停在原地，
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
    if intent not in ("list_catalog", "explain", "noise"):
        return False

    if intent == "list_catalog":
        try:
            from app.services.workflow_intent import catalog_digest
            lines = await catalog_digest()
        except Exception:
            lines = "（暂时读不到目录，请稍后再试）"
        reply = "当前在售服务器目录如下，你可以补充具体需求（场景/类型/系列/形态/预算）：\\n" + str(lines)
    else:
        reply = str(intent_data.get("reply") or "").strip()
        if not reply:
            reply = "当前想确认你的具体需求（场景/类型/系列/形态/预算），你补充后我再给匹配方案；也可以告诉我去详情页自己配置。"

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
anchor = "async def run_fixed_workflow("
if helpers not in s:
    if anchor not in s:
        raise SystemExit("anchor run_fixed_workflow not found")
    s = s.replace(anchor, helpers + anchor, 1)

old = '    resume_from = str(ctx.get("current_target") or "").strip()\n    queue: list[str] = sorted([nid for nid, degree in indeg.items() if degree == 0])'
new = ('    resume_from = str(ctx.get("current_target") or "").strip()\n'
       '    if resume_from and resume_from in nodes and await _route_resume_intent(ctx, broadcast, resume_from):\n'
       '        return ctx\n'
       '    queue: list[str] = sorted([nid for nid, degree in indeg.items() if degree == 0])')
if old not in s:
    raise SystemExit("resume anchor not found")
s = s.replace(old, new, 1)

io.open(p, "w", encoding="utf-8", newline="").write(s)
print("patched capability_executor.py")
