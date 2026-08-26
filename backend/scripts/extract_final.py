import json, urllib.request, io
BASE="http://127.0.0.1:8001"
text="2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万"
req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run", data=json.dumps({"requirement_text":text,"force_complete":True}).encode(), method="POST", headers={"Content-Type":"application/json"})
with urllib.request.urlopen(req, timeout=300) as r:
    d=json.loads(r.read().decode())
# reconstruct agent_fill final answer from step_progress thinking chunks (concatenate and find last JSON)
buf=[]
for ev in d.get("events") or []:
    if ev.get("type")=="step_progress" and ev.get("step")=="agent_fill":
        sub=ev.get("sub") or {}
        if sub.get("kind")=="thinking":
            buf.append(sub.get("text") or "")
s="".join(buf)
# Find the last JSON object with action:final
import re
cands=[]
i=0
while True:
    j=s.find("{", i)
    if j==-1: break
    # attempt balanced parse
    depth=0; instr=False; esc=False; end=-1
    for k in range(j, len(s)):
        ch=s[k]
        if instr:
            if esc: esc=False
            elif ch=="\\": esc=True
            elif ch=='"': instr=False
            continue
        if ch=='"': instr=True
        elif ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:
                end=k; break
    if end!=-1:
        try:
            obj=json.loads(s[j:end+1])
            if isinstance(obj,dict) and obj.get("action")=="final":
                cands.append(obj)
        except Exception: pass
        i=end+1
    else:
        i=j+1
if cands:
    ans=cands[-1].get("answer") or {}
    print("FINAL answer JSON:")
    print(json.dumps(ans, ensure_ascii=False, indent=2)[:900])
else:
    print("no final json found; thinking tail:")
    print(s[-400:])
