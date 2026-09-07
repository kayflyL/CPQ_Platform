# -*- coding: utf-8 -*-
"""需求分析 skill E2E 测试工具（常驻）。

实时打印每轮：用户输入 → AI 旁白/回复 → 登记结果 → 引擎步骤 → 缺口卡 → 耗时，
并把整轮过程写成 Markdown 报告（_e2e_report.md）。

用法（backend 目录）：
  python -X utf8 scripts/e2e_skill.py --scenario <场景.json> [--keep]
场景 JSON：
{
  "name": "兆芯需求-反问开",
  "role_key": "support_engineer",
  "entry_point": "skill_studio_preview",
  "enable_clarity": true,
  "input": "CPU：2颗兆芯50000 ...",
  "answers": {                       # 缺口卡出现时按 slot 自动应答
    "platform_type": "Polaris",      # 普通文本 → 作为用户回复发送
    "server_model": "@pick:Polaris", # @pick:系列 → 从候选里点选第一个该系列机型（card_selections）
    "kp_required": "不需要GPU"       # 自由文本回复
  },
  "max_turns": 10
}
--keep：保留预览线程不清理（默认跑完 purge）。
--attach：不新建线程，挂载到你已打开的 Skill Studio 试运行面板正在使用的线程——
          场景消息会实时出现在试运行面板里（AI 旁白/缺口卡/引擎步骤原生渲染）。
          用法：先打开 Skill Studio 试运行窗口，再运行本工具。
"""
import argparse
import json
import time
import asyncio
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:8000"


def http(method, path, payload=None, token=None, timeout=30):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


class Run:
    def __init__(self, token, thread_id):
        self.token = token
        self.tid = thread_id
        self.narration = []
        self.events = []
        self.report = []
        self.last = time.time()

    async def listen(self, ws, max_wait=240.0):
        import websockets  # noqa: F811
        start = self.last = time.time()
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
            except asyncio.TimeoutError:
                if time.time() - self.last > 40 or time.time() - start > max_wait:
                    return
                continue
            self.last = time.time()
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            self.events.append(ev)
            t = ev.get("type")
            if t == "chunk":
                self.narration.append(ev.get("delta") or "")
            elif t == "pipeline_paused":
                print("    ⏸ 缺口卡: " + self._gap_text(ev.get("gaps") or []))
            elif t == "error":
                print("    ✖ " + str(ev.get("message") or "")[:120])

    def _gap_text(self, gaps):
        out = []
        for g in gaps:
            cats = ("（" + "、".join(g.get("cats") or []) + "）") if g.get("cats") else ""
            opts = [o.get("label") if isinstance(o, dict) else str(o) for o in (g.get("options") or [])[:4]]
            out.append(f"{g.get('slot')}{cats} 选项=[{'/'.join(opts)}]")
        return " | ".join(out) or "（无选项）"

    def summary(self):
        nodes = [(e.get("step"), str((e.get("trace") or e).get("summary") or "")[:40])
                 for e in self.events if e.get("type") == "node_trace"
                 and (e.get("trace") or e).get("status") == "done"]
        last_nodes = []
        for step, summ in nodes:
            if not last_nodes or last_nodes[-1][0] != step:
                last_nodes.append([step, summ])
            else:
                last_nodes[-1][1] = summ
        return last_nodes

    async def turn(self, text=None, picks=None, max_wait=240.0):
        self.narration = []
        self.events = []
        t0 = time.time()
        body = {"content": text or "", "entry_point": "skill_studio_preview",
                "role_key": SC.get("role_key", "assistant"),
                "enable_clarity": SC.get("enable_clarity")}
        if picks is not None:
            body["card_selections"] = picks
        t = threading.Thread(target=lambda: http(
            "POST", f"/api/assistant/threads/{self.tid}/messages", body, self.token), daemon=True)
        t.start()
        import websockets
        url = f"ws://127.0.0.1:8000/api/assistant/ws/{self.tid}?token={self.token}"
        paused = None
        finished = False
        async with websockets.connect(url, max_size=20_000_000) as ws:
            start = time.time()
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                except asyncio.TimeoutError:
                    if time.time() - self.last > 45 or time.time() - start > max_wait:
                        break
                    continue
                self.last = time.time()
                try:
                    ev = json.loads(raw)
                except Exception:
                    continue
                self.events.append(ev)
                typ = ev.get("type")
                if typ == "chunk":
                    self.narration.append(ev.get("delta") or "")
                    print(ev.get("delta") or "", end="", flush=True)
                elif typ == "node_trace":
                    tr = ev.get("trace") or ev
                    art = tr.get("artifact") or {}
                    if tr.get("step") == "model_reason" and art.get("kind") == "l6_chassis":
                        rows = (art.get("data") or {}).get("rows") or []
                        bad = [r.get("catalogue") for r in rows if any(
                            w in str(r.get("catalogue") or "").upper() for w in ("PCBA", "SCREW", "BMC"))]
                        head = json.dumps(rows[0], ensure_ascii=False) if rows else "（机箱表空）"
                        print("\n    [机箱表 %d 行 · 制造件混入: %s] 首行: %s" % (len(rows), bad or "无", head),
                              flush=True)
                elif typ == "pipeline_paused":
                    paused = ev.get("gaps") or []
                    print("\n    ⏸ 缺口卡: " + self._gap_text(paused), flush=True)
                elif typ == "error":
                    print("\n    ✖ " + str(ev.get("message") or "")[:160], flush=True)
                elif typ in ("analysis_finished",):
                    finished = True
                    break
                elif typ == "done":
                    pass
        dur = time.time() - t0
        print(f"\n    [本轮 {dur:.1f}s]")
        self.report.append({
            "input": (text or json.dumps(picks, ensure_ascii=False))[:200],
            "dur": dur, "narration": "".join(self.narration)[:400],
            "nodes": self.summary(), "paused": self._gap_text(paused) if paused else "",
            "finished": finished})
        return {"paused": paused, "finished": finished, "duration": dur}


import threading  # noqa: E402

SC = {}


def gap_answer(gaps, answers):
    """全部缺口 → (应答文本, card_selections)。S1 一次问全后一轮补齐：
    @recommend → 点选该卡带「推荐」标的选项（客户接受 AI 建议，逐类确认）；
    @absent → 点选「不配」逃生项（GPU 类）；
    @pick:关键字 → 点选候选（点击快速路，跳大脑确定性落槽）；
    普通文本 → 合并为一条用户回复（打字路，走大脑全量理解）。"""
    texts, picks = [], []
    for g in (gaps or []):
        slot = str(g.get("slot") or "")
        ans = answers.get(slot)
        # 行级/类目级答案优先于槽位兜底（brain_ask 逐类卡共用同一 slot，需按行区分）
        row = str(g.get("row") or "")
        if row and answers.get(row):
            ans = answers.get(row)
        elif row and "|" in row:
            cat = row.split("|", 1)[0].strip()
            if answers.get(cat):
                ans = answers.get(cat)
        if ans is None:
            continue
        ans = str(ans)
        if ans.startswith("@recommend"):
            opts = g.get("options") or []
            hit = next((o for o in opts if o.get("recommended")), None) or (opts[0] if opts else None)
            if hit is not None:
                picks.append({"slot": slot, "value": hit.get("value")})
        elif ans.startswith("@absent"):
            opts = g.get("options") or []
            hit = next((o for o in opts
                        if isinstance(o.get("signal"), dict)
                        and (o.get("signal") or {}).get("kp_absent")), None)
            if hit is not None:
                picks.append({"slot": slot, "value": hit.get("value")})
        elif ans.startswith("@pick:"):
            key = ans.split(":", 1)[1]
            opts = g.get("options") or []
            hit = next((o for o in opts
                        if key in (str(o.get("label") or "") + str(o.get("value") or "")
                                   + str(o.get("desc") or ""))), None)
            if hit is None and opts:
                hit = opts[0]
            if hit is not None:
                picks.append({"slot": slot, "value": hit.get("value")})
        else:
            texts.append(ans)
    # 点击轮只发 picks（点击快速路按 (slot,value) 直传，混发文本会走旁路语义）；
    # 未覆盖的缺口下轮引擎会重新弹出，收敛不循环
    if picks:
        return None, picks
    if texts:
        return "；".join(texts), None
    return None, None


def main():
    global SC
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--attach", action="store_true",
                    help="挂载到已打开的试运行面板线程，实时可见（不新建/不清理）")
    args = ap.parse_args()
    SC = json.load(open(args.scenario, encoding="utf-8"))

    token = http("POST", "/api/auth/login",
                 {"username": "admin", "password": "fA5zXkyWv_RyrAqe"})["token"]
    role = SC.get("role_key", "assistant")
    if args.attach:
        threads = http("GET",
                       f"/api/assistant/threads?include_preview=true&thread_kind=office_colleague&role_key={role}",
                       token=token).get("threads") or []
        preview = [t for t in threads if t.get("entry_point") == "skill_studio_preview"]
        if not preview:
            raise SystemExit("未找到已打开的试运行线程：请先打开 Skill Studio 试运行窗口再运行。")
        tid = preview[0]["thread_id"]
        print(f"▶ 场景[{SC.get('name')}] 挂载试运行线程 {tid}（面板实时可见）")
    else:
        tid = http("POST", "/api/assistant/threads/resolve",
                   {"role_key": role,
                    "entry_point": SC.get("entry_point", "skill_studio_preview")}, token)["thread"]["thread_id"]
        print(f"▶ 场景[{SC.get('name')}] thread={tid} clarity={SC.get('enable_clarity')}")

    runner = Run(token, tid)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 第一轮：主输入
    result = loop.run_until_complete(runner.turn(text=SC.get("input"), max_wait=240.0))
    turns = 1
    answers = SC.get("answers") or {}
    while not result["finished"] and turns < int(SC.get("max_turns", 8)):
        gaps = result.get("paused")
        if gaps is None:
            print("  （无缺口且未完成——停止）")
            break
        text, picks = gap_answer(gaps, answers)
        if text is None and picks is None:
            print("  （缺口无对应应答策略——停止）")
            break
        turns += 1
        print(f"  ▶ 应答[{turns}]: {text or picks}")
        result = loop.run_until_complete(runner.turn(text=text, picks=picks))
    loop.close()

    if not args.keep and not args.attach:
        try:
            http("DELETE", f"/api/assistant/threads/{tid}?hard=1", token=token)
            print("预览线程已清理")
        except Exception as e:
            print("清理失败(可忽略):", e)

    lines = [f"# E2E 报告 · {SC.get('name')}", "",
             f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 反问开关：{SC.get('enable_clarity')}  角色：{SC.get('role_key')}",
             f"- 结果：{'✅ 完成' if result.get('finished') else '⛔ 未完成'}，共 {turns} 轮", ""]
    for i, t in enumerate(runner.report, 1):
        lines += [f"## 轮次 {i}（{t['dur']:.1f}s）", f"- 输入：{t['input']}",
                  f"- 旁白：{t['narration'] or '（无）'}"]
        for step, summ in t["nodes"]:
            lines.append(f"- 引擎 {step}：{summ}")
        if t["paused"]:
            lines.append(f"- 缺口：{t['paused']}")
        lines.append("")
    with open("_e2e_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("报告已写入 _e2e_report.md")


if __name__ == "__main__":
    main()
