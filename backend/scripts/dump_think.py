import json
with open(r"D:\CPQ_Platform_V1\backend\_probe_full.json", encoding="utf-8") as f:
    d = json.load(f)
for ev in d.get("events") or []:
    if ev.get("type")=="step_progress" and ev.get("step")=="agent_fill":
        sub=ev.get("sub") or {}
        if sub.get("kind")=="thinking":
            print(sub.get("text"), end="")
print()
