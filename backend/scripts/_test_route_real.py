import sys, asyncio, json
sys.path.insert(0, ".")
from app.services.capability_executor import _route_resume_intent
evs=[]
async def bcast(p): evs.append(p)
base={"requirement_text":"我需要一台服务器","current_target":"model_reason","last_ask_question":"需要一台服务器，请补充类型/系列/形态/预算"}
async def run():
    for msg in ["都有哪些服务器","玩游戏的有没有","我就想和你聊天，不想要服务器","我要一台通用计算服务器，2U"]:
        evs.clear()
        ctx=dict(base); ctx["last_user_answer"]=msg
        hit=await _route_resume_intent(ctx,bcast,"model_reason")
        print("MSG",msg,"hit=",hit)
        print("  reply=",(ctx.get("last_ask_question") or "").replace("\n","|")[:200])
asyncio.run(run())
