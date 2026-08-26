# -*- coding: utf-8 -*-
import json, urllib.request, time
BASE = "http://127.0.0.1:8001"
text = "2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万"
payload = {"requirement_text": text, "force_complete": True}
data = json.dumps(payload).encode()
req = urllib.request.Request(BASE + "/api/reasoning-flow/test-run", data=data, method="POST", headers={"Content-Type": "application/json"})
t0=time.time()
with urllib.request.urlopen(req, timeout=300) as r:
    d = json.loads(r.read().decode())
with open(r"D:\CPQ_Platform_V1\backend\_probe_full.json","w",encoding="utf-8") as f:
    json.dump(d, f, ensure_ascii=False, indent=2)
print("elapsed_s=%.1f"%(time.time()-t0))
print("top keys:", list(d.keys()))
for ev in d.get("events") or []:
    t=ev.get("type")
    if t=="step_progress":
        print("  progress step=%s sub=%s" % (ev.get("step"), json.dumps(ev.get("sub") or {}, ensure_ascii=False)[:300]))
    elif t=="step_done":
        p=ev.get("payload") or {}
        print("  done step=%s ok=%s source=%s reason=%s" % (ev.get("step"), p.get("ok"), p.get("source"), str(p.get("reason"))[:80]))
    elif t=="need_input":
        print("  need_input:", str(ev.get("question"))[:120])
