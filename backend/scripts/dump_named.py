import json, urllib.request, io
BASE="http://127.0.0.1:8001"
text="给我 ES22V3-P"
req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run", data=json.dumps({"requirement_text":text,"force_complete":True}).encode(), method="POST", headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req, timeout=300) as r:
    d=json.loads(r.read().decode())
with io.open(r"D:\CPQ_Platform_V1\backend\_probe_named.json","w",encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print("awaiting:", d.get("awaiting_input"), "plans:", len(d.get("plans") or []))
for ev in d.get("events") or []:
    t=ev.get("type")
    if t=="step_done":
        p=ev.get("payload") or {}
        print("  done", ev.get("step"), "source=", p.get("source"), "count=", p.get("count"), "ok=", p.get("ok"), "reason=", str(p.get("reason"))[:60])
    elif t=="need_input" or t=="need_confirm":
        print("  ", t, "step=", ev.get("step"), "question=", str(ev.get("question"))[:120])
