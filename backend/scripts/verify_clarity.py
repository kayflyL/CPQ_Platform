# -*- coding: utf-8 -*-
import json, urllib.request, time, sys
BASE="http://127.0.0.1:8001"
CASES=[
 ("clear_full", "2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万", True),
 ("clear_full_realmode", "2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万", False),
 ("english", "2U rack server with dual CPU 32 cores, 256GB RAM, 4x2.4T SAS drives, dual 10G NIC, RAID card, redundant PSU, budget 100k RMB", True),
 ("greeting", "你好，在吗", True),
]
def run(text,force):
    p={"requirement_text":text,"force_complete":force}
    data=json.dumps(p,ensure_ascii=False).encode()
    req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run",data=data,method="POST",headers={"Content-Type":"application/json"})
    t0=time.time()
    with urllib.request.urlopen(req,timeout=300) as r:
        d=json.loads(r.read().decode())
    mr=None
    for ev in d.get("events") or []:
        if ev.get("type")=="step_done" and ev.get("step")=="model_reason":
            mr=(ev.get("payload") or {}).get("source")
    return {"await":d.get("awaiting_input"),"plans":len(d.get("plans") or []),"bom":bool(d.get("bom_scheme")),"mr_source":mr,"el":round(time.time()-t0,1)}
for name,text,force in CASES:
    r=run(text,force)
    print(name, "| force=",force, "| await=",r["await"], "| plans=",r["plans"], "| bom=",r["bom"], "| mr=",r["mr_source"], "| el=",r["el"])
