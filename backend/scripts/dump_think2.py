import json, io
with open(r"D:\CPQ_Platform_V1\backend\_probe_full.json", encoding="utf-8") as f:
    d = json.load(f)
buf=[]
for ev in d.get("events") or []:
    if ev.get("type")=="step_progress" and ev.get("step")=="agent_fill":
        sub=ev.get("sub") or {}
        if sub.get("kind")=="thinking":
            buf.append(sub.get("text") or "")
with io.open(r"D:\CPQ_Platform_V1\backend\_think.txt","w",encoding="utf-8") as f:
    f.write("".join(buf))
print("written", len("".join(buf)))
