# -*- coding: utf-8 -*-
import json, urllib.request
BASE="http://127.0.0.1:8001"
CASES=[("vague","给我一个服务器，性能好一点就行"),
       ("chitchat","你好，在吗"),
       ("missing_model","我要联想 WA5480 G3"),
       ("named_model","给我 ES22V3-P")]
for label,text in CASES:
    req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run", data=json.dumps({"requirement_text":text,"force_complete":True}).encode(), method="POST", headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d=json.loads(r.read().decode())
    ext=d.get("ext") or {}
    plans=d.get("plans") or []
    sem=ext.get("semantic") or {}
    mr=""
    for ev in d.get("events") or []:
        if ev.get("type")=="step_done" and ev.get("step")=="model_reason":
            p=ev.get("payload") or {}
            mr=str(p.get("source"))+" count="+str(p.get("count"))
    print("="*60)
    print("CASE", label, "| awaiting=", d.get("awaiting_input"), "| plans=", len(plans), "| mr=", mr)
    print(" ext:", json.dumps({k:v for k,v in ext.items() if k not in ("semantic","flow_configs","llm_enhanced","categories","qty_map","cpu_signal","mem_signal","drive_groups","gpu_groups","multi_spec_filters","raid_groups","psu_signal","nic_groups")}, ensure_ascii=False)[:400])
    print(" semantic:", json.dumps(sem, ensure_ascii=False)[:200])
