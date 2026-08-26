import io, re
p=r"app\services\reasoning_executor.py"
s=io.open(p,"r",encoding="utf-8",newline="").read()
orig=s
def rep(old,new,tag):
    global s
    assert old in s, "MISSING anchor: "+tag
    s=s.replace(old,new,1)

# F) remove _interrupt_reply function
st=s.index("async def _interrupt_reply(")
en=s.index("async def _handle_model_reason(")
s=s[:st]+s[en:]

# B) model_selection_intent default ""
old='''    text = str(answer or "").strip().lower()
    if not text:
        return "choose"
    try:
        from app.services import requirement_rule_catalog as _rc
        phrases = _rc.model_action_phrases()
    except Exception:
        phrases = {}
    for action in ("self_config", "auto_pick", "reselect", "cancel"):
        if any(k in text for k in phrases.get(action) or []):
            return action
    return "choose"'''
new='''    text = str(answer or "").strip().lower()
    if not text:
        return ""
    try:
        from app.services import requirement_rule_catalog as _rc
        phrases = _rc.model_action_phrases()
    except Exception:
        phrases = {}
    for action in ("self_config", "auto_pick", "reselect", "cancel"):
        if any(k in text for k in phrases.get(action) or []):
            return action
    return ""'''
rep(old,new,"model_selection_intent")

# A) resolve_selection_mode: use plan_intent, no second LLM
old='''    text = str(answer or "").strip()
    if text:
        try:
            from app.services.workflow_intent import resolve_intent
            ctx_lines = str(ctx.get("last_ask_question") or "").strip()
            if ctx_lines:
                ctx_lines = "当前环节：机型选型\\n" + ctx_lines
            data = await resolve_intent(text, ctx_lines)
            intent = str((data or {}).get("intent") or "").strip().lower()
            if intent == "auto_recommend":
                return "ai_config"
            if intent == "self_config":
                return "self_config"
            if intent in ("confirm_choice", "choose", "refine", "reselect"):
                return "recommend"
        except Exception:
            pass
    kw = _model_selection_intent(text)'''
new='''    # 意图由角色层统一判定；这里只做映射，不再二次调 LLM。
    pi = str(ctx.get("plan_intent") or "").strip().lower()
    if pi == "auto_recommend":
        return "ai_config"
    if pi == "self_config":
        return "self_config"
    if pi in ("confirm_choice", "choose", "refine", "reselect"):
        return "recommend"
    kw = _model_selection_intent(str(answer or "").strip())'''
rep(old,new,"resolve_selection_mode")

# C) handle_model_reason intent block
old='''    answer = str(ctx.get("last_user_answer") or "").strip()
    intent = ""
    if answer:
        try:
            from app.services.workflow_intent import resolve_intent
            _idata = await resolve_intent(answer, str(ctx.get("last_ask_question") or "")[:600])
            _it = str((_idata or {}).get("intent") or "").strip().lower()
            _interrupt = await _interrupt_reply(answer, _it, ctx, _idata, broadcast)
            if _interrupt is not None:
                return _interrupt
            if _it == "auto_recommend":
                intent = "auto_pick"
            elif _it == "self_config":
                intent = "self_config"
            elif _it == "confirm_choice":
                intent = "choose"
                ctx["_confirm_choice"] = True
            elif _it == "refine":
                intent = "refine"
            elif _it == "reselect":
                intent = "reselect"
            elif _it == "cancel":
                intent = "cancel"
        except Exception:
            intent = _model_selection_intent(answer)
        if not intent:
            intent = _model_selection_intent(answer)
    selection_mode = await _resolve_selection_mode(ctx, config, answer)'''
new='''    answer = str(ctx.get("last_user_answer") or "").strip()
    # 意图已由角色层 _decide_plan_turn 统一判定（存 ctx["plan_intent"]），节点不再重复分类。
    _pi = str(ctx.get("plan_intent") or "").strip().lower()
    intent = {
        "auto_recommend": "auto_pick",
        "self_config": "self_config",
        "confirm_choice": "choose",
        "choose": "choose",
        "refine": "refine",
        "reselect": "reselect",
        "cancel": "cancel",
    }.get(_pi, _model_selection_intent(answer) if answer else "")
    if intent == "choose" and _pi == "confirm_choice":
        ctx["_confirm_choice"] = True
    selection_mode = await _resolve_selection_mode(ctx, config, answer)'''
rep(old,new,"handle_model_reason_intent")

# D) resolve_kp_intent
old='''    """用 LLM 判断配件节点意图，关键词仅作兜底。返回 cancel / reselect_model / confirm / adjust。"""
    text = str(answer or "").strip()
    if not text:
        return "confirm"
    try:
        from app.services.workflow_intent import resolve_intent
        data = await resolve_intent(text, str(ctx.get("last_ask_question") or "")[:600])
        intent = str((data or {}).get("intent") or "").strip().lower()
        if intent == "cancel":
            return "cancel"
        if intent == "reselect":
            return "reselect_model"
        if intent == "confirm_choice":
            return "confirm"
        if intent == "refine":
            return "adjust"
        if intent in ("self_config", "auto_recommend", "choose"):
            return "confirm"
    except Exception:
        pass
    return _kp_reply_intent(text)'''
new='''    """配件节点意图映射：角色层已统一判定，这里只按 plan_intent 映射，关键词仅作兜底。"""
    text = str(answer or "").strip()
    pi = str(ctx.get("plan_intent") or "").strip().lower()
    if pi == "cancel":
        return "cancel"
    if pi == "reselect":
        return "reselect_model"
    if pi == "confirm_choice":
        return "confirm"
    if pi == "refine":
        return "adjust"
    if pi in ("self_config", "auto_recommend", "choose"):
        return "confirm"
    if not text:
        return "confirm"
    return _kp_reply_intent(text)'''
rep(old,new,"resolve_kp_intent")

# E) handle_kp_reason intent block
old='''    answer = str(ctx.get("last_user_answer") or "").strip()
    if answer:
        try:
            from app.services.workflow_intent import resolve_intent
            _idata = await resolve_intent(answer, str(ctx.get("last_ask_question") or "")[:600])
            _it = str((_idata or {}).get("intent") or "").strip().lower()
            _interrupt = await _interrupt_reply(answer, _it, ctx, _idata, broadcast)
            if _interrupt is not None:
                return _interrupt
        except Exception:
            pass
    intent = await _resolve_kp_intent(ctx, answer) if answer else "first"'''
new='''    answer = str(ctx.get("last_user_answer") or "").strip()
    intent = await _resolve_kp_intent(ctx, answer) if answer else "first"'''
rep(old,new,"handle_kp_reason_intent")

# collapse excess blank lines to <=2
s=re.sub(r"\n{4,}", "\n\n\n", s)
assert s!=orig
io.open(p,"w",encoding="utf-8",newline="").write(s)
print("patched reasoning_executor, len", len(orig), "->", len(s))
