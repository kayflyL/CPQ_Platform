# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error, time
BASE="http://127.0.0.1:8001"
def run(text):
    p={"requirement_text":text,"force_complete":True}
    data=json.dumps(p,ensure_ascii=False).encode()
    req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run",data=data,method="POST",headers={"Content-Type":"application/json"})
    t0=time.time()
    with urllib.request.urlopen(req,timeout=300) as r:
        return json.loads(r.read().decode()), time.time()-t0
for text in ["2U rack server with dual CPU 32 cores, 256GB RAM, 4x2.4T SAS drives, dual 10G NIC, RAID card, redundant PSU, budget 100k RMB",
             "我要联想 WA5480 G3"]:
    d,el=run(text)
    print("#####", text[:40], "elapsed", round(el,1), "awaiting", d.get("awaiting_input"))
    print("TOPKEYS:", list(d.keys()))
    for ev in d.get("events") or []:
        t=ev.get("type")
        if t in ("assistant","message","text","step_done","need_input"):
            print("EV", t, "step=", ev.get("step"))
            pl=ev.get("payload") or {}
            for k in ("message","text","content","question","answer","reason","source","count","ok"):
                v=pl.get(k)
                if v:
                    s=str(v)
                    s=s[:220].replace("\n"," ")
                    print("   ",k,":",s)
            if ev.get("message"):
                print("   msg:", str(ev.get("message"))[:220])
    for f in ("ext","plans","bom_scheme","awaiting_input"):
        v=d.get(f)
        if f=="ext":
            print("EXT keys:", list((v or {}).keys()))
