import json, urllib.request, sys, os
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
BASE="http://127.0.0.1:8001"
text="2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万"
payload={"requirement_text": text, "force_complete": True}
req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run", data=json.dumps(payload).encode(), method="POST", headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req, timeout=300) as r:
    d=json.loads(r.read().decode())
ext=d.get("ext") or {}
print("ext keys:", sorted(ext.keys()))
from app.services.slot_contract import _missing_critical
miss=_missing_critical(ext)
print("missing_critical:", miss)
print("clarity:", d.get("ext",{}).get("clarity"))
# also look at model_reason payload reason
for ev in d.get("events") or []:
    if ev.get("type")=="step_done" and ev.get("step")=="model_reason":
        print("model_reason payload:", json.dumps(ev.get("payload") or {}, ensure_ascii=False)[:300])
