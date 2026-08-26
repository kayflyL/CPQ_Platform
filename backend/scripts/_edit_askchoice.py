import io
p = "backend/app/services/reasoning_executor.py"
s = io.open(p, encoding="utf-8").read()

old = '''    if not baselines:
        # 候选为空：绝不空转，给兜底“我自己配置/取消/先补充需求”。
        question = _fz_block + (fallback or "服务器目录暂未找到匹配机型。") + "\\n" + (
            "你可以：\\n"
            "· 回复“我自己配置”去服务器详情页自配；\\n"
            "· 补充场景/类型/系列/形态等需求，我再重新筛；\\n"
            "· 回复“取消”结束方案配置。")
        ctx["awaiting_input"] = True
        ctx["current_target"] = "model_reason"
        ctx["last_ask_question"] = question
        ctx["model_reason"] = {"source": "recommend", "baselines": [], "reason": "目录无匹配候选，等待用户选择"}
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "model_reason", "question": question,
                                 "options": ["我自己配置", "重新选机型", "取消"], "why": "候选为空",
                                 "candidates": []})
            except Exception:
                pass
        return {**rule_res, "source": "recommend", "matches": [], "question": question,
                "reason": "等待用户选择处理方式"}'''

new = '''    if not baselines:
        # 候选为空：先把在售目录里的真实机型作为可挑选候选，避免“未找到”→ 只能自配/取消的死板兜底。
        try:
            from app.services.catalog_guide import load_catalog
            _types, _by_type = load_catalog()
            _browse = []
            for _t in _types or []:
                for _m in (_by_type.get(str(_t.get("name") or "")) or []):
                    _bc = _m.get("base_config") or {}
                    _browse.append({"id": _m.get("id"), "name": _m.get("name") or "",
                                    "series": _bc.get("series") or _m.get("series") or "",
                                    "form": _bc.get("form") or _m.get("form") or ""})
        except Exception:
            _browse = []
        if _browse:
            baselines = _browse
            ctx["baselines"] = baselines
            rule_res = {**rule_res, "count": len(baselines)}
            return await _ask_model_choice(
                ctx, baselines, rule_res, broadcast,
                "按当前筛选条件暂未找到精确匹配机型，以下是在售目录里可参考的机型，你可选择其一，或继续补充需求：")
        # 目录也为空：简短中性提示，不再背“你可以/我自己配置/取消”的固定文案。
        question = _fz_block + "当前在售目录里没有可匹配的机型。请补充更具体的需求，或回复“取消”结束。"
        ctx["awaiting_input"] = True
        ctx["current_target"] = "model_reason"
        ctx["last_ask_question"] = question
        ctx["model_reason"] = {"source": "recommend", "baselines": [], "reason": "目录无匹配候选，等待用户选择"}
        if broadcast:
            try:
                await broadcast({"type": "need_confirm", "step": "model_reason", "question": question,
                                 "options": ["取消"], "why": "候选为空"})
            except Exception:
                pass
        return {**rule_res, "source": "recommend", "matches": [], "question": question,
                "reason": "等待用户选择处理方式"}'''

if old not in s:
    raise SystemExit("empty-candidate anchor not found")
s = s.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="").write(s)
print("patched reasoning_executor._ask_model_choice")
