"""线上推理流验证：建商机 → WebSocket 收 candidates_ready → 打印方案 → 删除商机。

用法（backend 目录，项目 venv）：
  python -X utf8 scripts/online_verify.py "需求文本"
  或  python -X utf8 scripts/online_verify.py --case R5-YC-9124-ES22V3P
依赖：本地 uvicorn（127.0.0.1:8000）已启动；websockets 库已装。
"""
import json
import sys
import asyncio
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"
WS = "ws://127.0.0.1:8000/api/reasoning/ws"


def http(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]


def main():
    args = sys.argv[1:]
    text = None
    if args:
        text = args[0]   # 直接贴需求文本（golden --case 已随回归中心砍掉）
    if not text:
        print(__doc__); return 2

    st, opp = http("POST", "/api/opportunities/", {"customer_name": "在线验证", "sales_person": "codex"})
    opp_id = opp.get("id") or opp.get("opportunity_id")
    print("商机:", opp_id)

    async def run():
        import websockets
        async with websockets.connect(f"{WS}/{opp_id}", max_size=20_000_000) as ws:
            http("POST", f"/api/reasoning/{opp_id}/generate",
                 {"requirement_text": text, "force_complete": True})
            plans, kp_sum = None, None
            while True:
                try:
                    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=120))
                except asyncio.TimeoutError:
                    break
                t = msg.get("type")
                if t == "step_done" and msg.get("step") == "match_kp":
                    kp_sum = msg.get("payload")
                if t == "candidates_ready":
                    plans = msg.get("plans")
                if t == "pipeline_done":
                    break
                if t == "error":
                    print("ERR:", msg); break
            return plans, kp_sum

    plans, kp_sum = asyncio.run(run())
    print("match_kp:", json.dumps(kp_sum, ensure_ascii=False))
    if not plans:
        print("无方案"); http("DELETE", f"/api/opportunities/{opp_id}"); return 1
    for i, p in enumerate(plans, 1):
        print(f"--- 方案{i}: {p.get('name')} | form={p.get('form')} ---")
        print("   signals:", json.dumps(p.get("chassis_signals"), ensure_ascii=False))
        for u in p.get("unmatched") or []:
            print(f"   ⚠ unmatched {u.get('category')}: {u.get('reason')}")
        for r in (p.get("cfg") or {}).get("bom_excel_rows") or []:
            if r.get("category") == "Key Parts":
                print(f"   KP {r.get('catalogue')} ×{r.get('qty')} ¥{r.get('base_price')}")
    http("DELETE", f"/api/opportunities/{opp_id}")
    print("商机已删除")
    return 0


if __name__ == "__main__":
    sys.exit(main())
