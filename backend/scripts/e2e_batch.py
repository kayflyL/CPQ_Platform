# -*- coding: utf-8 -*-
"""端到端批量冒烟：多种用户输入 → 走完整推理流水线，落盘行为数据。"""
import json
import time
import urllib.request
import urllib.error
import asyncio

BASE = "http://127.0.0.1:8001"
WS = "ws://127.0.0.1:8001/api/reasoning/ws"
OUT = r"D:\CPQ_Platform_V1\backend\_e2e_results.json"

CASES = [
    ("clear", "2U机架式服务器，2颗CPU，32核，256GB内存，4块2.4T SAS硬盘，双口万兆网卡，需要RAID卡，双电源，预算10万"),
    ("vague", "给我一个服务器，性能好一点就行"),
    ("chitchat", "你好，在吗"),
    ("english", "2U rack server, dual CPU 32 cores, 256GB RAM, 4x 2.4TB SAS, 10G dual-port NIC, RAID, redundant PSU"),
    ("missing_model", "我要联想 WA5480 G3"),
    ("delegate", "我不懂服务器，你帮我推荐一套合适的"),
    ("named_model", "给我 ES22V3-P"),
]


def http(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


def summarize(payload):
    """把 step_done payload 压缩成便于分析的行为摘要。"""
    if not isinstance(payload, dict):
        return payload
    out = {}
    for k in ("source", "ok", "reason", "error", "count", "sufficient", "clarity",
              "question", "missing_critical", "kp_count", "kparts"):
        if k in payload and payload[k] is not None:
            out[k] = payload[k]
    for k in ("matches", "candidates", "kp_parts", "baselines"):
        v = payload.get(k)
        if isinstance(v, list):
            out[k] = [{
                "name": x.get("name"), "id": x.get("id") or x.get("config_id"),
                "series": x.get("series"), "form": x.get("form"),
            } for x in v[:6] if isinstance(x, dict)]
    for k in ("by_category", "model_selection", "baseline"):
        if isinstance(payload.get(k), dict):
            out[k] = payload[k]
    return out


async def run_case(label, text, results):
    st, opp = http("POST", "/api/opportunities/", {"customer_name": "e2e_" + label, "sales_person": "codex"})
    if isinstance(opp, dict):
        opp_id = opp.get("id") or opp.get("opportunity_id")
    else:
        print(f"[{label}] 建商机失败 {st} {opp}")
        return
    if not opp_id:
        print(f"[{label}] 无 opp_id: {opp}")
        return
    case = {"label": label, "text": text, "opp_id": opp_id, "steps": {}, "plans": None, "error": None}
    try:
        import websockets
        async with websockets.connect(f"{WS}/{opp_id}", max_size=20_000_000) as ws:
            http("POST", f"/api/reasoning/{opp_id}/generate",
                 {"requirement_text": text, "force_complete": True})
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
                except asyncio.TimeoutError:
                    case["error"] = case["error"] or "ws_timeout"
                    break
                t = msg.get("type")
                if t == "step_done":
                    case["steps"][msg.get("step")] = summarize(msg.get("payload"))
                if t == "candidates_ready":
                    case["plans"] = msg.get("plans")
                if t == "pipeline_done":
                    break
                if t == "error":
                    case["error"] = str(msg.get("message") or msg)[:300]
                    break
    except Exception as e:
        case["error"] = (case["error"] or "") + "| exc:" + str(e)[:200]
    finally:
        http("DELETE", f"/api/opportunities/{opp_id}")
    results.append(case)
    print(f"[{label}] steps={list(case['steps'])} err={case['error']}")


def main():
    results = []
    for label, text in CASES:
        asyncio.run(run_case(label, text, results))
        time.sleep(12)  # 控制上游请求速率，避免雪崩
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("已写入", OUT)


if __name__ == "__main__":
    main()
