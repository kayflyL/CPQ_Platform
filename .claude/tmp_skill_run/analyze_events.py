# -*- coding: utf-8 -*-
"""解析 events_<tag>.jsonl → 每节点输出物/用时报告。用法：
backend/.venv/Scripts/python.exe -X utf8 .claude/tmp_skill_run/analyze_events.py <tag>"""
import json
import sys
import os

tag = sys.argv[1]
base = os.path.dirname(os.path.abspath(__file__))
turns = json.load(open(os.path.join(base, f"turns_{tag}.json"), encoding="utf-8"))
tid = turns.get("thread_id")

# 事件按落盘顺序；rel 是相对各自轮次 t0 的秒数，需按轮次累加还原全局时间线
events = []
offset = 0.0
last_rel = 0.0
with open(os.path.join(base, f"events_{tag}.jsonl"), encoding="utf-8") as f:
    for line in f:
        rec = json.loads(line)
        if rec["rel"] < last_rel - 1.0:  # 新一轮（rel 重置）
            offset += last_rel
        last_rel = rec["rel"]
        rec["t"] = offset + rec["rel"]
        events.append(rec)

print(f"=== 线程 {tid} · {len(events)} 个事件 · 总时长 {events[-1]['t']:.1f}s ===\n")

# ── 轮次概览 ──
print("## 轮次概览")
for t in turns["turns_log"]:
    print(f"  T{t['turn']}: {t['dur']:.1f}s  finished={t['finished']}  paused={t['paused']}  "
          f"nodes={t['n_nodes']} chunks={t['n_chunks']} 首事件={t['first_event_s'] or '-'}s "
          f"旁白{t['narration_len']}字 err={t['errors'] or '无'}")
print()

# ── 节点级时间线（node_trace done + pipeline 关键事件）──
print("## 节点时间线（含引擎输出物摘要）")
for rec in events:
    ev = rec["event"]
    typ = ev.get("type")
    if typ == "node_trace":
        tr = ev.get("trace") or ev
        step = tr.get("step")
        status = tr.get("status")
        dur = tr.get("duration_ms")
        summ = (tr.get("summary") or "")[:150]
        line = f"  [{rec['t']:7.1f}s] {step:12s} {status:8s}"
        if dur is not None:
            line += f" {dur/1000:6.1f}s"
        if summ:
            line += f"  | {summ}"
        print(line)
        out = tr.get("output")
        if isinstance(out, dict) and out:
            for k, v in list(out.items())[:8]:
                s = json.dumps(v, ensure_ascii=False)
                print(f"      · {k}: {s[:220]}")
        art = tr.get("artifact")
        if isinstance(art, dict):
            data = art.get("data") or {}
            rows = data.get("rows") or []
            extra = ""
            if rows:
                extra = f" rows={len(rows)} 首行={json.dumps(rows[0], ensure_ascii=False)[:200]}"
            print(f"      artifact: kind={art.get('kind')} title={art.get('title')}{extra}")
    elif typ == "pipeline_paused":
        gaps = ev.get("gaps") or []
        print(f"  [{rec['t']:7.1f}s] ⏸ 暂停，缺口 {len(gaps)} 个：")
        for g in gaps:
            opts = [o.get("label") if isinstance(o, dict) else str(o) for o in (g.get("options") or [])[:6]]
            print(f"      slot={g.get('slot')} reason={g.get('reason_code')} row={g.get('row') or '-'} "
                  f"问={str(g.get('question') or '')[:100]}")
            if opts:
                print(f"        选项=[{' | '.join(str(o)[:40] for o in opts)}]")
    elif typ == "chat_progress" and ev.get("step") == "need_input":
        msg = ev.get("message") or {}
        try:
            data = json.loads(msg.get("data") or "{}")
        except Exception:
            data = {}
        opts = [o.get("label") for o in (data.get("options") or [])[:6]]
        print(f"  [{rec['t']:7.1f}s] ⏸ 缺口卡[{data.get('slot') or '?'}] row={data.get('row') or '-'} "
              f"问={str(data.get('question') or msg.get('content') or '')[:100]}")
        if opts:
            print(f"        选项=[{' | '.join(str(o)[:40] for o in opts)}]")
    elif typ == "pipeline_waiting":
        pass
    elif typ == "error":
        print(f"  [{rec['t']:7.1f}s] ✖ error: {str(ev.get('message'))[:200]}")
    elif typ == "pipeline_start":
        steps = [(s.get("step"), s.get("label")) for s in ev.get("steps") or []]
        print(f"  [{rec['t']:7.1f}s] ▶ pipeline_start: {steps}")
    elif typ == "pipeline_finished":
        print(f"  [{rec['t']:7.1f}s] ✔ pipeline_finished keys={list(ev.keys())[:10]}")
print()

# ── 旁白全文（按轮拼接 chunk）──
print("## 各轮 AI 旁白/回复")
turn_no = 0
cur = []
prev_rel = 0.0
for rec in events:
    if rec["rel"] < prev_rel - 1.0:
        turn_no += 1
        txt = "".join(cur).strip()
        if txt:
            print(f"  --- T{turn_no} ---\n  {txt[:1200]}")
        cur = []
    prev_rel = rec["rel"]
    if rec["event"].get("type") == "chunk":
        cur.append(rec["event"].get("delta") or "")
txt = "".join(cur).strip()
turn_no += 1
if txt:
    print(f"  --- T{turn_no} ---\n  {txt[:1200]}")
