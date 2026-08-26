import sys, asyncio, json
sys.path.insert(0, ".")
from app.services.capabilities import run_agent_fill

async def noop(p=None): pass

async def main():
    ctx={
        "requirement_text":"通用计算",
        "ext":{},
        "history":[{"role":"user","content":"我需要一台服务器"},{"role":"assistant","content":"请问这台服务器的主要用途是什么？例如通用计算、AI加速还是存储？"}],
        "missing_fields":[],
        "last_user_answer":"通用计算",
    }
    r=await run_agent_fill(ctx,{},noop)
    print("ok=",r.get("ok"),"done=",r.get("done"),"sufficient=",r.get("sufficient"))
    print("missing=",ctx.get("missing_fields"))
    print("clarity=",ctx.get("clarity"))
    ext=ctx.get("ext") or {}
    print("ext_keys=",json.dumps({k:ext[k] for k in list(ext)[:20]},ensure_ascii=False)[:600])
    print("sem=",json.dumps((ext.get("semantic") or {}),ensure_ascii=False)[:300])

asyncio.run(main())
