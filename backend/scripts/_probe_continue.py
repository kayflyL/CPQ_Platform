import asyncio, sys
sys.path.insert(0,".")
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.capability_executor import run_fixed_workflow
from app.services import workflow_intent as wi

def _mock_intent(msg, ctx=None):
    t=str(msg or "").strip().lower()
    if any(k in t for k in ["推荐","随便","都行"]): return {"intent":"auto_recommend","reply":""}
    if any(k in t for k in ["选","就这个"]): return {"intent":"confirm_choice","reply":""}
    if "取消" in t: return {"intent":"cancel","reply":""}
    if "自己配" in t or "自配" in t: return {"intent":"self_config","reply":""}
    if "介绍" in t: return {"intent":"ask","reply":""}
    return {"intent":"refine","reply":""}
async def _rl(m,c=None): return _mock_intent(m,c)
async def _rep(m,c): return "（自然回复）"+str(m)[:30]
wi.resolve_intent = _rl
wi.reply_with_context = _rep

repo=ReasoningFlowRepository()
try: flow=repo.ensure_skill_flow("requirement_analysis", name="requirement_analysis")
finally: repo.close()
events=[]
async def bcast(p): events.append(p)

async def main():
    base={"ext":{}, "baselines":[], "kp_parts":[], "kp_by_model":{}, "missing_fields":[], "history":[]}
    for msg in ["你推荐吧", "选第一个", "取消", "我自己配置", "介绍一下ZZZ"]:
        events.clear()
        ctx=await run_fixed_workflow("t","我要一台AI加速服务器",flow,bcast,initial_ctx={**base,"current_target":"model_reason","last_user_answer":msg})
        print(repr(msg), "-> exit=",ctx.get("flow_exit"), "awaiting=",ctx.get("awaiting_input"), "target=",repr(ctx.get("current_target")), "cards=", len([e for e in events if e.get("type")=="business_entity_ready"]), "step_done=", len([e for e in events if e.get("type")=="step_done"]))

asyncio.run(main())
