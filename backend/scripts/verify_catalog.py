import sys, os, json, urllib.request
sys.path.insert(0, r"D:\CPQ_Platform_V1\backend")
# verify catalog
from app.services.catalog_guide import load_catalog
types, models = load_catalog()
print("types:", [str(t.get("name")) for t in (types or [])])
series=set(); forms=set()
for ms in (models or {}).values():
    for m in (ms or []):
        bc = m.get("base_config") or {}
        s = bc.get("series") or m.get("series")
        f = bc.get("form") or m.get("form")
        if s: series.add(str(s))
        if f: forms.add(str(f))
print("series:", sorted(series))
print("forms:", sorted(forms))
# also read actual server_type from a fresh run ext
BASE="http://127.0.0.1:8001"
text="2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万"
req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run", data=json.dumps({"requirement_text":text,"force_complete":True}).encode(), method="POST", headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req, timeout=300) as r:
    d=json.loads(r.read().decode())
ext=d.get("ext") or {}
print("ext.server_type_name:", repr(ext.get("server_type_name")))
print("ext.server_type:", repr(ext.get("server_type")))
