import os, sys, asyncio, json, time, urllib.request
BE = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.abspath(BE))
from app.services.workflow_intent import resolve_intent, resolve_intent_keywords

async def main():
    msgs = [
        "你能介绍下ES22V3服务器吗",
        "介绍下ES22V3",
        "ES22V3这个型号怎么样",
        "讲讲ES22V3的参数",
        "我想要一台服务器",
    ]
    for m in msgs:
        r = await resolve_intent(m)
        k = resolve_intent_keywords(m)
        print(f"{m[:24]!r:26s} -> LLM={r.get('intent'):14s} kw={k}")

asyncio.run(main())

def http(text):
    body={"requirement_text":text,"force_complete":False}
    data=json.dumps(body).encode()
    req=urllib.request.Request("http://localhost:8000/api/reasoning-flow/test-run",data=data,headers={"Content-Type":"application/json"})
    t0=time.time()
    with urllib.request.urlopen(req,timeout=120) as r: resp=json.loads(r.read().decode())
    resp["total_s"]=round(time.time()-t0,1); return resp

print("=== /test-run ===")
r=http("你能介绍下ES22V3服务器吗")
evs=r.get("events") or []
seq=[e.get("step") for e in evs if e.get("type")=="step_start"]
ask=""
for e in evs:
    if e.get("type")=="need_input": ask=(e.get("question") or "")[:60]
ext=r.get("ext") or {}
print("total_s=",r.get("total_s"),"awaiting=",r.get("awaiting_input"),"seq=",",".join(seq),"plans=",len(r.get("plans") or []))
print("ext=",json.dumps({k:ext.get(k) for k in ("server_type_name","series","form","server_model","clarity","intent","customer_specified_model") if k in ext},ensure_ascii=False))
print("ask=",ask)
