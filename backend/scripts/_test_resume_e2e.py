import sys, asyncio
sys.path.insert(0, ".")
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services import capability_executor as cap
from app.services.capability_executor import run_fixed_workflow
from app.services import workflow_intent as wi

evs = []
async def bcast(p):
    evs.append(p)

async def main():
    # deterministic intent classifier (browse + explain), real catalog_digest
    async def _rl(m, c=None):
        return {"intent": "list_catalog", "reply": ""}
    wi.resolve_intent = _rl
    async def _reply_llm(m, c):
        return "这是对当前选型问题的说明，请补充具体需求。"
    wi.reply_with_context = _reply_llm

    repo = ReasoningFlowRepository()
    try:
        flow = repo.ensure_skill_flow("requirement_analysis", name="requirement_analysis")
    finally:
        repo.close()
    print("flow_nodes=", list((flow.get("graph") or {}).get("nodes") and [n.get("id") for n in (flow.get("graph") or {}).get("nodes")]))

    initial = {
        "current_target": "model_reason",
        "last_user_answer": "都有哪些服务器",
        "requirement_text": "我需要一台服务器",
        "ext": {}, "baselines": [], "kp_parts": [], "kp_by_model": {},
        "missing_fields": [], "history": [],
    }
    ctx = await run_fixed_workflow("test-run", "我需要一台服务器", flow, bcast, initial_ctx=initial)
    print("awaiting_input=", ctx.get("awaiting_input"), "target=", ctx.get("current_target"))
    print("fatal=", ctx.get("fatal_error"))
    # assert no canned empty-candidate card
    canned = [e for e in evs if e.get("type") in ("need_confirm","need_input") and "未找到" in str(e.get("question") or "")]
    print("canned_event_count=", len(canned))
    need = [e for e in evs if e.get("type") == "need_confirm"]
    if need:
        print("reply_head=", (need[-1].get("question") or "").replace("\n","|")[:70])
    step_done = [e for e in evs if e.get("type") == "step_done" and e.get("step") == "model_reason"]
    print("model_reason_step_done_count=", len(step_done))

asyncio.run(main())
