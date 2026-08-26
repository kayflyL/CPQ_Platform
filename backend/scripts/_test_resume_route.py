import sys, asyncio, json
sys.path.insert(0, ".")
from app.services import capability_executor as cap
from app.services import workflow_intent as wi

evs = []
async def bcast(p):
    evs.append(p)

async def main():
    # Stub LLM-dependent functions to avoid network; facts (catalog_digest) stay real.
    wi.resolve_intent = lambda msg, ctx=None: asyncio.coroutine(lambda: {"intent": "list_catalog", "reply": ""})() if False else _resolve(msg, ctx)
    async def _rl(m, c=None):
        return {"intent": "list_catalog", "reply": ""}
    wi.resolve_intent = _rl
    async def _reply_llm(m, c):
        return "你刚才问的是服务器选型相关的问题。系统正在等你补充具体需求（类型、系列、形态、预算），补充后我会给匹配方案。"
    wi.reply_with_context = _reply_llm

    base = {"requirement_text": "我需要一台服务器", "current_target": "model_reason", "last_user_answer": ""}
    # case 1: list_catalog
    evs.clear()
    ctx = dict(base); ctx["last_user_answer"] = "都有哪些服务器"
    hit = await cap._route_resume_intent(ctx, bcast, "model_reason")
    print("CASE list_catalog hit=", hit, "awaiting=", ctx.get("awaiting_input"), "target=", ctx.get("current_target"))
    q = ctx.get("last_ask_question") or ""
    print("  reply_head=", q[:60].replace("\n", "|"))
    print("  has_catalog_list=", ("服务器" in q and "-" in q))
    print("  events=", json.dumps(evs[-1], ensure_ascii=False)[:120])

    # case 2: explain
    evs.clear()
    ctx = dict(base); ctx["last_user_answer"] = "啥意思"
    wi.resolve_intent = lambda m, c=None: _rl2(m, c)
    async def _rl2(m, c):
        return {"intent": "explain", "reply": ""}
    hit = await cap._route_resume_intent(ctx, bcast, "model_reason")
    print("CASE explain hit=", hit, "reply=", (ctx.get("last_ask_question") or "")[:60])

    # case 3: grasp -> should NOT intercept
    evs.clear()
    ctx = dict(base); ctx["last_user_answer"] = "我要一台通用计算服务器，2U"
    wi.resolve_intent = lambda m, c=None: _rl3(m, c)
    async def _rl3(m, c):
        return {"intent": "grasp", "reply": ""}
    hit = await cap._route_resume_intent(ctx, bcast, "model_reason")
    print("CASE grasp hit=", hit, "(expect False)")

    # case 4: cancel -> NOT intercept
    evs.clear()
    ctx = dict(base); ctx["last_user_answer"] = "取消"
    wi.resolve_intent = lambda m, c=None: _rl4(m, c)
    async def _rl4(m, c):
        return {"intent": "cancel", "reply": ""}
    hit = await cap._route_resume_intent(ctx, bcast, "model_reason")
    print("CASE cancel hit=", hit, "(expect False)")

    # real catalog_digest
    d = await wi.catalog_digest()
    print("CATALOG nonempty=", bool(d.strip()), "len=", len(d), "head=", d[:80].replace("\n","|"))

asyncio.run(main())
