# -*- coding: utf-8 -*-
import json

with open(r"D:\CPQ_Platform_V1\backend\_flat_e2e.json", encoding="utf-8") as f:
    data = json.load(f)

for c in data:
    print("=" * 70)
    print("CASE:", c.get("label"), "| awaiting:", c.get("awaiting_input"),
          "| plans:", len(c.get("plans") or []))
    if c.get("http"):
        print("  http error:", c.get("http"), c.get("body"))
        continue
    ext = c.get("ext") or {}
    sem = ext.get("semantic") or {}
    print("  ext:", json.dumps({k: v for k, v in ext.items()
                                if k not in ("semantic", "flow_configs")}, ensure_ascii=False)[:400])
    print("  semantic:", json.dumps(sem, ensure_ascii=False)[:300])
    for ev in c.get("events") or []:
        if ev.get("type") == "need_input":
            print("  need_input:", str(ev.get("question"))[:160])
        if ev.get("type") == "step_done" and ev.get("step") in ("agent_fill", "model_reason", "kp_reason", "match_kp"):
            print(f"  [{ev.get('step')}] source={ev.get('source')} ok={ev.get('ok')} "
                  f"count={ev.get('count')} reason={str(ev.get('reason'))[:90]}")
