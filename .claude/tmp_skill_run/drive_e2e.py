# -*- coding: utf-8 -*-
"""需求分析 skill 全流程实测驱动（原始事件落盘版，基于 scripts/e2e_skill.py 增强）。

用法（repo 根）：
  backend/.venv/Scripts/python.exe .claude/tmp_skill_run/drive_e2e.py --scenario <json> [--keep]

产物（同目录）：
  events_<name>.jsonl   原始 WS 事件逐条落盘（带 ts/相对秒）
  turns_<name>.json     每轮计时与统计
  messages_<name>.json  结束后线程消息快照（产物卡/文案核查用）
"""
import argparse
import json
import time
import asyncio
import threading
import urllib.request
import os

BASE = "http://127.0.0.1:8000"
OUT_DIR = os.path.dirname(os.path.abspath(__file__))


def http(method, path, payload=None, token=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


SC = {}
EVENTS_F = None
TURNS_F = None

_DECLINE_RE = None


def _is_decline(opt):
    import re
    global _DECLINE_RE
    if _DECLINE_RE is None:
        _DECLINE_RE = re.compile(r"不需要|无需|不配|不加装|不选|跳过")
    label = str((opt or {}).get("label") or "") + str((opt or {}).get("value") or "")
    sig = (opt or {}).get("signal") or {}
    return bool(_DECLINE_RE.search(label)) or bool(isinstance(sig, dict) and sig.get("kp_absent"))


def dump(ev, t0):
    if EVENTS_F is not None:
        EVENTS_F.write(json.dumps({"ts": round(time.time(), 3),
                                   "rel": round(time.time() - t0, 3),
                                   "event": ev}, ensure_ascii=False) + "\n")
        EVENTS_F.flush()


class Run:
    def __init__(self, token, thread_id):
        self.token = token
        self.tid = thread_id
        self.narration = []
        self.n_nodes = 0
        self.n_chunks = 0
        self.tool_events = []
        self.first_event_at = None

    async def turn(self, text=None, picks=None, option_slot=None, max_wait=420.0, silence=100.0):
        self.narration = []
        self.n_nodes = 0
        self.n_chunks = 0
        self.tool_events = []
        t0 = time.time()
        self.first_event_at = None
        body = {"content": text or "", "entry_point": "skill_studio_preview",
                "role_key": SC.get("role_key", "assistant"),
                "enable_clarity": SC.get("enable_clarity")}
        if option_slot:
            body["option_slot"] = option_slot  # 真实前端形状：value 作为 content + option_slot
        if picks is not None:
            body["card_selections"] = picks
        t = threading.Thread(target=lambda: http(
            "POST", f"/api/assistant/threads/{self.tid}/messages", body, self.token), daemon=True)
        t.start()
        import websockets
        url = f"ws://127.0.0.1:8000/api/assistant/ws/{self.tid}?token={self.token}"
        paused = None
        finished = False
        errors = []
        waiting = False
        async with websockets.connect(url, max_size=50_000_000) as ws:
            start = time.time()
            last = time.time()
            grace_until = None
            while True:
                try:
                    timeout = 5 if grace_until is None else max(0.1, grace_until - time.time())
                    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    now = time.time()
                    if grace_until is not None and now >= grace_until:
                        break
                    if now - last > silence or now - start > max_wait:
                        break
                    continue
                if self.first_event_at is None:
                    self.first_event_at = time.time() - t0
                last = time.time()
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                dump(ev, t0)
                typ = ev.get("type")
                if typ == "chunk":
                    self.narration.append(ev.get("delta") or "")
                    self.n_chunks += 1
                elif typ == "node_trace":
                    self.n_nodes += 1
                elif typ == "chat_progress" and ev.get("step") == "need_input":
                    # 重构后的缺口卡：chat_progress(need_input) + input_options 消息
                    msg = ev.get("message") or {}
                    try:
                        data = json.loads(msg.get("data") or "{}")
                    except Exception:
                        data = {}
                    paused = [{"slot": str(data.get("slot") or (data.get("missing_fields") or ["brain_ask"])[0]),
                               "question": data.get("question") or msg.get("content") or "",
                               "options": data.get("options") or [],
                               "row": data.get("row") or ""}]
                    waiting = True
                    grace_until = time.time() + 6.0  # 缓 6s 收尾事件再断
                elif typ == "pipeline_waiting":
                    waiting = True
                    if grace_until is None:
                        grace_until = time.time() + 6.0
                elif typ == "error":
                    errors.append(str(ev.get("message") or "")[:200])
                elif typ == "analysis_finished":
                    finished = True
                    break
        dur = time.time() - t0
        return {"paused": paused, "finished": finished, "duration": dur,
                "errors": errors, "narration": "".join(self.narration),
                "n_nodes": self.n_nodes, "n_chunks": self.n_chunks,
                "first_event_s": self.first_event_at}


def gap_answer(gaps, answers):
    texts, picks = [], []
    for g in (gaps or []):
        slot = str(g.get("slot") or "")
        row = str(g.get("row") or "")
        ans = answers.get(slot)
        if row and answers.get(row):
            ans = answers.get(row)
        elif row and "|" in row:
            cat = row.split("|", 1)[0].strip()
            if answers.get(cat):
                ans = answers.get(cat)
            elif SC.get("default_row_answer"):
                ans = SC.get("default_row_answer")
        if ans is None:
            continue
        ans = str(ans)
        opts = g.get("options") or []
        if ans.startswith("@recommend_or_decline"):
            # 无行卡（场景确认/是否加装门）：优先推荐标 → 「不需要」类逃生项 → 第一项
            hit = next((o for o in opts if o.get("recommended")), None)
            if hit is None:
                hit = next((o for o in opts if _is_decline(o)), None)
            if hit is None and opts:
                hit = opts[0]
            if hit is not None:
                picks.append({"slot": slot, "value": hit.get("value")})
        elif ans.startswith("@recommend"):
            hit = next((o for o in opts if o.get("recommended")), None) or (opts[0] if opts else None)
            if hit is not None:
                picks.append({"slot": slot, "value": hit.get("value")})
        elif ans.startswith("@absent"):
            hit = next((o for o in opts
                        if isinstance(o.get("signal"), dict)
                        and (o.get("signal") or {}).get("kp_absent")), None)
            if hit is not None:
                picks.append({"slot": slot, "value": hit.get("value")})
            else:
                texts.append("不需要")
        elif ans.startswith("@pick:"):
            key = ans.split(":", 1)[1]
            hit = next((o for o in opts
                        if key in (str(o.get("label") or "") + str(o.get("value") or "")
                                   + str(o.get("desc") or ""))), None)
            if hit is None and opts:
                hit = opts[0]
            if hit is not None:
                picks.append({"slot": slot, "value": hit.get("value")})
        else:
            texts.append(ans)
    if picks:
        return None, picks
    if texts:
        return "；".join(texts), None
    return None, None


def main():
    global SC, EVENTS_F, TURNS_F
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--thread", default=None, help="续跑已有线程（首轮用 resume_picks/resume_text）")
    args = ap.parse_args()
    SC = json.load(open(args.scenario, encoding="utf-8"))
    tag = SC.get("name", "run").replace(" ", "_")
    EVENTS_F = open(os.path.join(OUT_DIR, f"events_{tag}.jsonl"), "w", encoding="utf-8")
    TURNS_F = open(os.path.join(OUT_DIR, f"turns_{tag}.json"), "w", encoding="utf-8")

    token = http("POST", "/api/auth/login",
                 {"username": "admin", "password": "fA5zXkyWv_RyrAqe"})["token"]
    role = SC.get("role_key", "assistant")
    if args.thread:
        tid = args.thread
        print(f"▶ 场景[{SC.get('name')}] 续跑 thread={tid}", flush=True)
    else:
        tid = http("POST", "/api/assistant/threads/resolve",
                   {"role_key": role,
                    "entry_point": SC.get("entry_point", "skill_studio_preview")}, token)["thread"]["thread_id"]
        print(f"▶ 场景[{SC.get('name')}] thread={tid} clarity={SC.get('enable_clarity')}", flush=True)

    runner = Run(token, tid)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    turns_log = []

    if args.thread:
        first_text = SC.get("resume_text")
        first_picks = SC.get("resume_picks")
        result = loop.run_until_complete(runner.turn(text=first_text, picks=first_picks, max_wait=420.0))
    else:
        result = loop.run_until_complete(runner.turn(text=SC.get("input"), max_wait=420.0))
    turns = 1
    turns_log.append({"turn": turns, "input": (SC.get("input") or "")[:80],
                      "dur": result["duration"], "finished": result["finished"],
                      "paused": bool(result["paused"]), "errors": result["errors"],
                      "n_nodes": result["n_nodes"], "n_chunks": result["n_chunks"],
                      "first_event_s": result["first_event_s"],
                      "narration_len": len(result["narration"])})
    print(f"  [T{turns}] {result['duration']:.1f}s finished={result['finished']} "
          f"nodes={result['n_nodes']} err={result['errors']}", flush=True)
    answers = SC.get("answers") or {}
    while not result["finished"] and turns < int(SC.get("max_turns", 8)):
        gaps = result.get("paused")
        if gaps is None:
            print("  （无缺口且未完成——停止）", flush=True)
            break
        text, picks = gap_answer(gaps, answers)
        if text is None and picks is None:
            print("  （缺口无对应应答策略——停止）" + json.dumps(gaps, ensure_ascii=False)[:500], flush=True)
            break
        turns += 1
        print(f"  ▶ 应答[{turns}]: {(text or json.dumps(picks, ensure_ascii=False))[:160]}", flush=True)
        result = loop.run_until_complete(runner.turn(text=text, picks=picks))
        turns_log.append({"turn": turns, "input": (text or json.dumps(picks, ensure_ascii=False))[:160],
                          "dur": result["duration"], "finished": result["finished"],
                          "paused": bool(result["paused"]), "errors": result["errors"],
                          "n_nodes": result["n_nodes"], "n_chunks": result["n_chunks"],
                          "first_event_s": result["first_event_s"],
                          "narration_len": len(result["narration"])})
        print(f"  [T{turns}] {result['duration']:.1f}s finished={result['finished']} "
              f"nodes={result['n_nodes']} err={result['errors']}", flush=True)
    loop.close()

    try:
        msgs = http("GET", f"/api/assistant/threads/{tid}/messages", token=token)
        with open(os.path.join(OUT_DIR, f"messages_{tag}.json"), "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False, indent=1)
        print("消息快照已落盘", flush=True)
    except Exception as e:
        print("消息快照失败:", e, flush=True)

    json.dump({"thread_id": tid, "turns": turns, "finished": result.get("finished"),
               "turns_log": turns_log}, TURNS_F, ensure_ascii=False, indent=1)
    TURNS_F.close()
    EVENTS_F.close()

    if not args.keep:
        try:
            http("DELETE", f"/api/assistant/threads/{tid}?hard=1", token=token)
            print("预览线程已清理", flush=True)
        except Exception as e:
            print("清理失败(可忽略):", e, flush=True)
    print(f"总轮数 {turns}，完成={result.get('finished')}", flush=True)


if __name__ == "__main__":
    main()
