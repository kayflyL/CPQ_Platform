# -*- coding: utf-8 -*-
import io, os
ROOT = r"D:\CPQ_Platform_V1"
path = os.path.join(ROOT, "backend", "app", "services", "reasoning_executor.py")
text = io.open(path, encoding="utf-8").read()

helpers = r'''def _apply_agent_effects(structured: dict, ctx: dict, config: dict) -> dict:
    """执行 Agent 结构化答案里的确定性副作用（编排胶水，非业务硬编码）。

    仅当 config.allowed_effects 声明时才触发对应动作：
      - build_bom:   用 baseline+parts 跑真实 build_plan，写 ctx.plans/bom_scheme；
      - self_config: 用户选择自配→冻结流程并退出主线（推送机型卡片由交互层处理）。
    """
    allowed = set(config.get("allowed_effects") or [])
    action = str(structured.get("action") or "").strip()
    if not action or action not in allowed:
        return {}
    effects: dict = {}
    if action == "self_config":
        ctx["flow_exit"] = "self_config"
        ctx["current_target"] = "model_choice"
        effects["self_config"] = True
    elif action == "build_bom":
        baseline = structured.get("baseline") or {}
        parts = structured.get("parts") or []
        if isinstance(baseline, dict) and isinstance(parts, list) and parts:
            try:
                from app.api.candidate_search import build_plan
                plan = build_plan(baseline, parts)
            except Exception as exc:
                logger.exception("build_bom effect failed")
                plan = {"error": str(exc)}
            if isinstance(plan, dict) and plan.get("error") is None:
                ctx["plans"] = [plan]
                ctx["bom_scheme"] = {"plans": [plan], "baseline": baseline, "parts": parts}
                effects["build_bom"] = True
            else:
                ctx["bom_error"] = plan.get("error") if isinstance(plan, dict) else "build_plan 失败"
                effects["build_bom"] = {"error": ctx.get("bom_error")}
        else:
            ctx["bom_error"] = "build_bom 缺 baseline 或 parts"
            effects["build_bom"] = {"error": ctx.get("bom_error")}
    return effects

'''

old_return = '''    result_key = str(config.get("result_key") or "agent_result")
    if structured is not None:
        ctx[result_key] = structured
        for ck, path in (config.get("result_mapping") or {}).items():
            val = _dig_path(structured, str(path))
            if val is not None:
                ctx[str(ck)] = val

    return {'''
new_return = '''    result_key = str(config.get("result_key") or "agent_result")
    effects: dict = {}
    if structured is not None:
        ctx[result_key] = structured
        for ck, path in (config.get("result_mapping") or {}).items():
            val = _dig_path(structured, str(path))
            if val is not None:
                ctx[str(ck)] = val
        effects = _apply_agent_effects(structured, ctx, config)

    return {'''

assert helpers not in text
assert old_return in text, "return anchor missing"
text = text.replace(old_return, new_return, 1)
# insert helper before def _handle_generic_agent
anchor = "async def _handle_generic_agent(ctx: dict, config: dict, broadcast: BroadcastFn) -> dict:"
assert anchor in text
text = text.replace(anchor, helpers + anchor, 1)
io.open(path, "w", encoding="utf-8").write(text)
print("agent effects patched OK")
