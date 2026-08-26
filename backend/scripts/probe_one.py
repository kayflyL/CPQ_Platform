# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error, time, sys
BASE = "http://127.0.0.1:8001"
text = sys.argv[1] if len(sys.argv) > 1 else "2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万"
payload = {"requirement_text": text, "force_complete": True}
data = json.dumps(payload).encode()
req = urllib.request.Request(BASE + "/api/reasoning-flow/test-run", data=data, method="POST", headers={"Content-Type": "application/json"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read().decode())
    ext = d.get("ext") or {}
    sem = ext.get("semantic") or {}
    print("status=200")
    print("awaiting:", d.get("awaiting_input"))
    print("plans:", len(d.get("plans") or []))
    print("ext:", json.dumps({k: v for k, v in ext.items() if k not in ("semantic","flow_configs")}, ensure_ascii=False)[:700])
    print("semantic:", json.dumps(sem, ensure_ascii=False)[:400])
    for ev in d.get("events") or []:
        if ev.get("type") == "need_input":
            print("need_input:", str(ev.get("question"))[:160], ev.get("missing_fields"))
        if ev.get("type") == "step_done":
            p = ev.get("payload") or {}
            print("  step_done:", ev.get("step"), "ok=", p.get("ok"), "source=", p.get("source"), "count=", p.get("count"), "reason=", str(p.get("reason"))[:100])
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode()[:500])
print("elapsed_s=%.1f" % (time.time()-t0))
