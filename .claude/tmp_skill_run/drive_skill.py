# -*- coding: utf-8 -*-
"""驱动脚本：对 support_engineer 的 preview 线程发消息并收取 WS 事件落盘。

用法：
  python drive_skill.py new run1            # 新建 preview 线程并发送 REQUIREMENT
  python drive_skill.py say run2 "回复文本" thread_id   # 在既有线程追加一条消息
"""
import asyncio, io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import httpx
import websockets

BASE = "http://localhost:8000"
USER = {"username": "admin", "password": "fA5zXkyWv_RyrAqe"}
OUT_DIR = r"D:/CPQ_Platform_V1/.claude/tmp_skill_run"

REQUIREMENT = """CPU：2颗兆芯50000 处理器（2.2GHz/96C）
内存：768GB DDR5
硬盘：2块480G SSD+1块1.92T SSD+4块6T HDD
Raid：Raid卡（1GB缓存，支持超融合，RAID0/1/5/6和JBOD）
网卡：4个千兆，2个万兆
电源：双电源
服务：3年专业支持和关键任务 (7x24)"""


async def main():
    mode = sys.argv[1]
    tag = sys.argv[2]
    thread_id = ""
    text = ""
    selections = None
    if mode == "new":
        text = REQUIREMENT
    elif mode == "pick":
        # pick <tag> <value> <thread_id> <qty> <slot>  →  card_selections 提交（stepper 姿势）
        thread_id = sys.argv[4]
        qty = int(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] else 0
        slot = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else "brain_ask"
        selections = [{"slot": slot, "value": sys.argv[3], "qty": qty}]
        text = sys.argv[3]
    else:
        text = sys.argv[3]
        thread_id = sys.argv[4]
    os.makedirs(OUT_DIR, exist_ok=True)
    async with httpx.AsyncClient(timeout=30, trust_env=False) as http:
        tok = (await http.post(f"{BASE}/api/auth/login", json=USER)).json()["token"]
        hdr = {"Authorization": f"Bearer {tok}"}
        if mode == "new":
            r = await http.post(
                f"{BASE}/api/assistant/threads/resolve", headers=hdr,
                json={"role_key": "support_engineer", "entry_point": "skill_studio_preview"})
            thread_id = r.json()["thread"]["thread_id"]
        print("THREAD_ID", thread_id)
        out = os.path.join(OUT_DIR, f"events_{tag}.jsonl")
        f = open(out, "a", encoding="utf-8")
        async with websockets.connect(
                f"ws://localhost:8000/api/assistant/ws/{thread_id}?token={tok}",
                max_size=None) as ws:
            r = await http.post(f"{BASE}/api/assistant/threads/{thread_id}/messages",
                                headers=hdr,
                                json={"content": text,
                                      **({"card_selections": selections} if selections else {})})
            print("POST", r.status_code)
            n = 0
            terminal_seen = False
            quiet_after = 0
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=8)
                except asyncio.TimeoutError:
                    if terminal_seen:
                        break
                    if n == 0:
                        quiet_after += 1
                        if quiet_after >= 8:
                            print("NO_EVENT_TIMEOUT")
                            break
                    continue
                try:
                    evt = json.loads(raw)
                except Exception:
                    continue
                n += 1
                t = evt.get("type")
                f.write(json.dumps(evt, ensure_ascii=False) + "\n")
                f.flush()
                if t == "chunk":
                    print("chunk:", str(evt.get("delta") or evt)[:80].replace("\n", " "))
                elif t == "done":
                    print("EVT done", str(evt)[:120].replace("\n", " "))
                elif t in ("analysis_finished", "pipeline_paused", "error"):
                    print("EVT*", t, str(evt)[:220].replace("\n", " "))
                    terminal_seen = True
                else:
                    print("EVT", t, str(evt)[:170].replace("\n", " "))
        f.close()
        print("TOTAL_EVENTS", n, "THREAD", thread_id)


asyncio.run(main())
