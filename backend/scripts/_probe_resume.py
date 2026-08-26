import sys, asyncio
sys.path.insert(0, ".")
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.capability_executor import run_fixed_workflow
evs=[]
async def bcast(p): evs.append(p)
async def run():
    repo=ReasoningFlowRepository()
    try:
        flow=repo.ensure_skill_flow("requirement_analysis", name="requirement_analysis")
    finally:
        repo.close()
    initial={
        "current_target":"agent_fill",
        "last_user_answer":"通用计算",
        "requirement_text":"我需要一台服务器",
        "ext":{"server_type_name":"通用计算服务器","server_type":"通用计算服务器","n":1,"purchase_qty":1},
        "requirement":{},
        "baselines":[], "kp_parts":[], "kp_by_model":{},
        "missing_fields":["server_type"],
        "history":[{"role":"user","content":"我需要一台服务器"},{"role":"assistant","content":"请问这台服务器的主要用途是什么？例如通用计算、AI加速还是存储？"}],
        "turn_count":1,
    }
    ctx=await run_fixed_workflow("t","我需要一台服务器",flow,bcast,initial_ctx=initial)
    print("awaiting=",ctx.get("awaiting_input"),"target=",ctx.get("current_target"),"clarity=",ctx.get("clarity"))
    print("missing=",ctx.get("missing_fields"))
    for e in evs:
        if e.get("type") in ("need_input","need_confirm"):
            print("EVT",e.get("type"),"step=",e.get("step"),"q=",str(e.get("question"))[:90])
    print("baselines=",[(b.get("name")) for b in (ctx.get("baselines") or [])])
asyncio.run(run())
