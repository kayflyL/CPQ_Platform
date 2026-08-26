# -*- coding: utf-8 -*-
import json, urllib.request, urllib.error, time, sys
BASE = "http://127.0.0.1:8001"

CASES = [
    ("clear_full", "2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万"),
    ("english", "2U rack server with dual CPU 32 cores, 256GB RAM, 4x2.4T SAS drives, dual 10G NIC, RAID card, redundant PSU, budget 100k RMB"),
    ("delegate", "我不懂，你帮我推荐"),
    ("vague_perf", "给我一个服务器，性能好一点"),
    ("named_exist", "给我 ES22V3-P"),
    ("named_missing", "我要联想 WA5480 G3"),
    ("greeting", "你好，在吗"),
    ("gpu_ai", "帮我配一台能跑大模型的服务器，4卡GPU，2U"),
    ("xinchuang", "需要信创国产服务器，2U，双路兆芯"),
    ("storage", "存储服务器，12盘位，SAS硬盘"),
    ("budget", "预算5万，2U，普通办公用"),
    ("overspec", "2U 双路 64核 512G 8块NVMe 双万兆 四电源"),
]

def run(text):
    payload = {"requirement_text": text, "force_complete": True}
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(BASE + "/api/reasoning-flow/test-run", data=data, method="POST", headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"err": "HTTP%d %s" % (e.code, e.read().decode()[:200]), "elapsed": time.time()-t0}
    except Exception as e:
        return {"err": str(e)[:200], "elapsed": time.time()-t0}
    ext = d.get("ext") or {}
    sem = ext.get("semantic") or {}
    events = d.get("events") or []
    need = [ev for ev in events if ev.get("type") == "need_input"]
    steps = []
    for ev in events:
        if ev.get("type") == "step_done":
            p = ev.get("payload") or {}
            steps.append((ev.get("step"), p.get("ok"), p.get("count"), str(p.get("reason"))[:60]))
    return {
        "elapsed": round(time.time()-t0,1),
        "awaiting": d.get("awaiting_input"),
        "plans": len(d.get("plans") or []),
        "bom": bool(d.get("bom_scheme")),
        "steps": steps,
        "need_q": str(need[0].get("question"))[:90] if need else "",
        "need_fields": (need[0].get("missing_fields") or [])[:8] if need else [],
        "cats": (ext.get("categories") or [])[:10],
        "model": ext.get("model") or ext.get("selected_model") or "",
        "form": ext.get("form") or sem.get("form") or "",
        "series": sem.get("series") or ext.get("series") or "",
    }

for name, text in CASES:
    r = run(text)
    print("=====", name, "=====")
    print(" q:", text)
    if "err" in r:
        print(" ERR:", r["err"], "elapsed", r["elapsed"]); continue
    print(" awaiting:", r["awaiting"], "| plans:", r["plans"], "| bom:", r["bom"], "| elapsed:", r["elapsed"])
    print(" model:", r["model"], "| form:", r["form"], "| series:", r["series"])
    print(" cats:", r["cats"])
    if r["need_q"]:
        print(" NEED_ASK:", r["need_q"], "| fields:", r["need_fields"])
    for st in r["steps"]:
        print("  step:", st[0], "ok=", st[1], "count=", st[2], "reason=", st[3])
