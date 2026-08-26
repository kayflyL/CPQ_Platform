import asyncio, sys
sys.path.insert(0,".")
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.capability_executor import run_fixed_workflow
from app.services import workflow_intent as wi

# deterministic intents for the two utterances
def _mock_intent(msg, ctx=None):
    t=str(msg or "").strip().lower()
    if "有哪些服务器" in t: return {"intent":"list_catalog","reply":""}
    if "介绍" in t or "es22" in t: return {"intent":"ask","reply":""}
    if "需要" in t: return {"intent":"refine","reply":""}
    return {"intent":"grasp","reply":""}
async def _rl(m,c=None): return _mock_intent(m,c)
async def _rep(m,c): return "（自然回复）"+str(m)[:30]
wi.resolve_intent = _rl
wi.reply_with_context = _rep

repo=ReasoningFlowRepository()
try: flow=repo.ensure_skill_flow("requirement_analysis", name="requirement_analysis")
finally: repo.close()

events=[]
async def bcast(p): events.append(p)

async def run(initial, req_text):
    events.clear()
    ctx = await run_fixed_workflow("t", req_text, flow, bcast, initial_ctx=initial)
    return ctx

async def main():
    # Turn 1: entry "你有哪些服务器"
    ctx1 = await run({"current_target":"", "last_user_answer":"", "ext":{},"baselines":[],"kp_parts":[],"kp_by_model":{}, "missing_fields":[], "history":[]}, "你有哪些服务器")
    print("T1 awaiting=", ctx1.get("awaiting_input"), "target=", repr(ctx1.get("current_target")))
    cards1=[e for e in events if e.get("type")=="business_entity_ready" ]
    print("T1 cards=", len(cards1))
    # Turn 2: user asks to explain a model -> should stay, no cards
    ctx2 = await run({"current_target":ctx1.get("current_target") or "input", "last_user_answer":"你能介绍下ES22V3服务器吗", "ext":ctx1.get("ext") or {}, "baselines":ctx1.get("baselines") or [], "kp_parts":ctx1.get("kp_parts") or [], "kp_by_model":ctx1.get("kp_by_model") or {}, "missing_fields":ctx1.get("missing_fields") or [], "history":[]}, "你有哪些服务器")
    print("T2 awaiting=", ctx2.get("awaiting_input"), "target=", repr(ctx2.get("current_target")), "exit=", ctx2.get("flow_exit"))
    cards2=[e for e in events if e.get("type")=="business_entity_ready"]
    need=[e for e in events if e.get("type")=="need_confirm"]
    print("T2 cards=", len(cards2), "need_confirm=", len(need))
    print("T2 reply_head=", (ctx2.get("last_ask_question") or "").replace("\n","|")[:60])

asyncio.run(main())
