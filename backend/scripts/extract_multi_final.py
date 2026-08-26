# -*- coding: utf-8 -*-
import json, urllib.request, io
BASE="http://127.0.0.1:8001"
CASES=[("vague","给我一个服务器，性能好一点就行"),
       ("chitchat","你好，在吗"),
       ("missing_model","我要联想 WA5480 G3"),
       ("named_model","给我 ES22V3-P")]
for label,text in CASES:
    req=urllib.request.Request(BASE+"/api/reasoning-flow/test-run", data=json.dumps({"requirement_text":text,"force_complete":True}).encode(), method="POST", headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        d=json.loads(r.read().decode())
    buf=[]
    for ev in d.get("events") or []:
        if ev.get("type")=="step_progress" and ev.get("step")=="agent_fill":
            sub=ev.get("sub") or {}
            if sub.get("kind")=="thinking":
                buf.append(sub.get("text") or "")
    s="".join(buf)
    cands=[]
    i=0
    while True:
        j=s.find("{", i)
        if j==-1: break
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
                if depth==0: end=k; break
        if end!=-1:
            try:
                obj=json.loads(s[j:end+1])
                if isinstance(obj,dict) and obj.get("action")=="final":
                    cands.append(obj)
            except Exception: pass
            i=end+1
        else: i=j+1
    ans=cands[-1].get("answer") or {} if cands else {}
    print("="*60)
    print("CASE", label, "| done=", ans.get("done"), "| ask=", str(ans.get("ask"))[:80])
    print(" fill:", json.dumps(ans.get("fill") or {}, ensure_ascii=False, indent=1)[:400])
    print(" semantic:", json.dumps(ans.get("semantic") or {}, ensure_ascii=False))
