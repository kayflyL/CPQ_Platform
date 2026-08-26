# -*- coding: utf-8 -*-
"""端到端批量冒烟 v2：POST /api/reasoning-flow/test-run，同步拿全量行为数据。"""
import json
import time
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8001"
OUT = r"D:\CPQ_Platform_V1\backend\_flat_e2e.json"

CASES = [
    ("clear", "2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万"),
    ("vague", "给我一个服务器，性能好一点就行"),
    ("chitchat", "你好，在吗"),
    ("english", "2U rack server, dual CPU 32 cores, 256GB RAM, 4x 2.4TB SAS, 10G dual-port NIC, RAID, redundant PSU"),
    ("missing_model", "我要联想 WA5480 G3"),
    ("delegate", "我不懂服务器，你帮我推荐一套合适的"),
    ("named_model", "给我 ES22V3-P"),
]


def post_test_run(text, budget=None):
    payload = {"requirement_text": text, "force_complete": True}
    if budget is not None:
        payload["explicit_budget"] = budget
    data = json.dumps(payload).encode()
    req = urllib.request.Request(BASE + "/api/reasoning-flow/test-run", data=data,
                                 method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:600]


def trim_events(events):
    """压缩事件：只保留节点 step_done 的类型+关键字段与 need_input。"""
    keep = []
    for ev in events or []:
        t = ev.get("type")
        if t in ("step_start", "pipeline_start") and t == "step_start":
            keep.append({"type": t, "step": ev.get("step")})
        if t == "step_done":
            payload = ev.get("payload") or {}
            keep.append({
                "type": t, "step": ev.get("step"),
                "source": payload.get("source"), "ok": payload.get("ok"),
                "reason": payload.get("reason"), "error": payload.get("error"),
                "count": payload.get("count"), "question": payload.get("question"),
                "matches": [{"name": m.get("name"), "id": m.get("id") or m.get("config_id"),
                             "series": m.get("series"), "form": m.get("form")}
                            for m in (payload.get("matches") or [])][:6],
            })
        if t == "need_input":
            keep.append({"type": t, "question": ev.get("question"), "missing_fields": ev.get("missing_fields")})
    return keep


def main():
    results = []
    for label, text in CASES:
        st, data = post_test_run(text)
        if st != 200:
            results.append({"label": label, "text": text, "http": st, "body": data})
            print(f"[{label}] HTTP {st}: {data}")
        else:
            results.append({
                "label": label, "text": text,
                "events": trim_events(data.get("events")),
                "ext": data.get("ext") or {},
                "kp_by_model": data.get("kp_by_model") or {},
                "plans": [{"name": p.get("name"), "form": p.get("form"), "id": p.get("id"),
                           "unmatched": p.get("unmatched")} for p in (data.get("plans") or [])],
                "bom_scheme": data.get("bom_scheme") or {},
                "awaiting_input": data.get("awaiting_input"),
            })
            plans = data.get("plans") or []
            print(f"[{label}] steps={len(data.get('events') or [])} plans={len(plans)} "
                  f"awaiting={data.get('awaiting_input')}")
        time.sleep(12)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("已写入", OUT)


if __name__ == "__main__":
    main()
