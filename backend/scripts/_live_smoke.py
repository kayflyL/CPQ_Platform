import json, urllib.request, urllib.error, time
BASE="http://127.0.0.1:8000"
payload={"requirement_text":"2U机架式服务器，2颗CPU，64核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，RAID卡，双电源，预算10万","force_complete":True}
req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run",data=json.dumps(payload).encode(),method="POST",headers={"Content-Type":"application/json"})
t0=time.time()
try:
    with urllib.request.urlopen(req,timeout=90) as r:
        d=json.loads(r.read().decode())
    print("status=200 awaiting=",d.get("awaiting_input"),"plans=",len(d.get("plans") or []))
    print("err=",d.get("error"))
except urllib.error.HTTPError as e:
    print("HTTP",e.code,e.read().decode()[:300])
print("elapsed=%.1f"%(time.time()-t0))
