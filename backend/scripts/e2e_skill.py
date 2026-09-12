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
import os
import time
import asyncio
import urllib.request
import urllib.error

BASE = os.environ.get("E2E_BASE", "http://127.0.0.1:8000")

# 统一暂停载荷的合法 kind（真源 = pause_payload 的产出点：skill_turn_engine._emit_pause
# 的 brain_ask/delivery_gap/stuck/final_gate/failure + colleague_turn_service 的 approval）。
# 这里只做「收到的 kind 是否登记过」的事实核对，不复制任何话术。
PAUSE_KINDS = {"brain_ask", "delivery_gap", "final_gate", "stuck", "failure", "approval"}


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
        self.cards = []          # 缺口卡取证：{turn, slot, row, n_options, sig, repeat_card, repeat_row}
        self.pauses = []         # 中断点取证（P5-C1）：统一载荷的事实字段，一条广播一条
        self.artifacts = {}      # 末次产物：{step: {"kind","rows","cols"}}
        self.auto_answers = 0    # --auto-answer 兜底次数（脚本答案用尽后由脚本代答）
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
            elif t in ("pipeline_paused", "pipeline_waiting"):
                print("    ⏸ 缺口卡: " + self._gap_text(ev.get("gaps") or []))
            elif t == "error":
                print("    ✖ " + str(ev.get("message") or "")[:120])

    def _gap_text(self, gaps, recs=None):
        out = []
        for i, g in enumerate(gaps):
            cats = ("（" + "、".join(g.get("cats") or []) + "）") if g.get("cats") else ""
            opts = [o.get("label") if isinstance(o, dict) else str(o) for o in (g.get("options") or [])[:4]]
            row = ("·行 " + str(g.get("row"))) if g.get("row") else ""
            mark = ""
            r = (recs or [])[i] if recs and i < len(recs) else None
            if r:
                mark = (" ⚠重复卡" if r.get("repeat_card")
                        else " ⚠同行再问" if r.get("repeat_row")
                        else " ⚠同类目再问" if r.get("repeat_cat") else "")
            out.append(f"{g.get('slot')}{row}{cats} 选项=[{'/'.join(opts)}]{mark}")
        return " | ".join(out) or "（无选项）"

    def _collect_gaps(self, gaps):
        """缺口卡取证：算出每张卡的指纹，并标出「整张卡一模一样再来一次」与
        「同一行被反复追问」（P2 行清单增量化的目标指标）。指纹 = (slot, row, 选项值集合)。"""
        recs = []
        for g in (gaps or []):
            if not isinstance(g, dict):
                continue
            slot = str(g.get("slot") or "")
            row = str(g.get("row") or "")
            vals = tuple(sorted(str(o.get("value")) for o in (g.get("options") or [])
                                if isinstance(o, dict)))
            rec = {"turn": len(self.report) + 1, "slot": slot, "row": row,
                   "n_options": len(g.get("options") or []), "sig": (slot, row, vals)}
            rec["repeat_card"] = any(c["sig"] == rec["sig"] for c in self.cards)
            rec["repeat_row"] = bool(row) and any(
                (c["slot"], c["row"]) == (slot, row) for c in self.cards)
            # 同类目重复发卡：行键会漂（「内存（DDR5 RDIMM）」vs「内存 512G DDR5」），
            # 但客户看到的还是「内存怎么配」同一个决策——这才是 P2 行清单增量化的靶心。
            rec["cat"] = row.split("|", 1)[0].strip() if row else ""
            rec["repeat_cat"] = bool(rec["cat"]) and any(
                c.get("cat") == rec["cat"] for c in self.cards)
            self.cards.append(rec)
            recs.append(rec)
        return recs

    def _pause_fact(self, pf: dict) -> dict:
        """P5-C1：中断点只认统一载荷（pause_payload）——原样留档事实字段，不加工措辞。"""
        resume = pf.get("resume") if isinstance(pf.get("resume"), dict) else {}
        return {"turn": len(self.report) + 1,
                "kind": str(pf.get("kind") or ""),
                "step": str(pf.get("step") or ""),
                "label": str(pf.get("label") or ""),
                "reason_code": str(pf.get("reason_code") or ""),
                "resumable": bool(pf.get("resumable", True)),
                "pending": [str(p.get("slot") or p.get("tool") or p.get("governance_id") or "")
                            for p in (pf.get("pending") or []) if isinstance(p, dict)],
                "steps_done": list(resume.get("steps_done") or [])}

    def _print_artifacts(self):
        """逐节点打印产物（kind/行数/首行/耗时）——画布节点下方的输出物就是它。"""
        for ev in self.events:
            if ev.get("type") != "node_trace" or str(ev.get("status")) != "done":
                continue
            art = ev.get("artifact") or {}
            if not art:
                continue
            data = art.get("data") if isinstance(art.get("data"), dict) else {}
            rows = data.get("rows") or []
            cols = [c.get("key") for c in (data.get("columns") or [])]
            self.artifacts[str(ev.get("step") or "")] = {
                "kind": art.get("kind"), "rows": len(rows), "cols": cols}
            if rows:
                head = json.dumps(rows[0], ensure_ascii=False)[:160]
            else:
                head = "键=" + ",".join(list(data.keys())[:8])
            print("      · 产物 %s/%s 列=%s 行=%d %s 摘要=%s"
                  % (ev.get("step"), art.get("kind"), cols, len(rows),
                     ("首行=" + head) if rows else head,
                     str(ev.get("summary") or "")[:70]), flush=True)

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
                "role_key": SC.get("role_key", "assistant")}
        if picks is not None:
            body["card_selections"] = picks
        t = threading.Thread(target=lambda: http(
            "POST", f"/api/assistant/threads/{self.tid}/messages", body, self.token), daemon=True)
        t.start()
        import websockets
        url = BASE.replace("http://", "ws://") + f"/api/assistant/ws/{self.tid}?token={self.token}"
        paused = None
        pause_facts = []
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
                elif typ in ("pipeline_paused", "pipeline_waiting"):
                    paused = ev.get("gaps") or []
                    recs = self._collect_gaps(paused)
                    pf = ev.get("pause") if isinstance(ev.get("pause"), dict) else {}
                    if pf:
                        fact = self._pause_fact(pf)
                        self.pauses.append(fact)
                        pause_facts.append(fact)
                    print("\n    ⏸ 缺口卡: " + self._gap_text(paused, recs)
                          + ("  [pause=%s/%s resumable=%s]" % (pf.get("kind"),
                             pf.get("reason_code"), pf.get("resumable")) if pf else "  [⚠无统一载荷]"),
                          flush=True)
                elif typ == "error":
                    print("\n    ✖ " + str(ev.get("message") or "")[:160], flush=True)
                elif typ in ("analysis_finished", "pipeline_done"):
                    finished = True
                    if typ == "analysis_finished":
                        break
                elif typ == "turn_finished":
                    # 回合终态：收工本轮 WS 等待；finished 保留给「整个分析结束」语义
                    break
                elif typ == "done":
                    pass
        dur = time.time() - t0
        print(f"\n    [本轮 {dur:.1f}s]")
        self._print_artifacts()
        self.report.append({
            "input": (text or json.dumps(picks, ensure_ascii=False))[:200],
            "dur": dur, "narration": "".join(self.narration)[:400],
            "nodes": self.summary(), "paused": self._gap_text(paused) if paused else "",
            "pause": pause_facts, "finished": finished})
        return {"paused": paused, "finished": finished, "duration": dur}

    def metrics(self, turns, finished):
        """收敛指标（改前/改后同一口径）：轮数、墙体时间、缺口卡/重复卡、兜底次数、产物行数。"""
        dur = [t["dur"] for t in self.report]
        last_step = ""
        for t in self.report:
            if t["nodes"]:
                last_step = t["nodes"][-1][0]
        return {
            "scenario": SC.get("name"),
            "finished": bool(finished),
            "turns": turns,
            "wall_s": round(sum(dur), 1),
            "turn_s_min": round(min(dur), 1) if dur else None,
            "turn_s_max": round(max(dur), 1) if dur else None,
            "cards": len(self.cards),
            "repeat_cards": sum(1 for c in self.cards if c["repeat_card"]),
            "repeat_rows": sum(1 for c in self.cards if c["repeat_row"]),
            "repeat_cats": sum(1 for c in self.cards if c.get("repeat_cat")),
            "auto_answers": self.auto_answers,
            "kp_rows": (self.artifacts.get("kp_reason") or {}).get("rows"),
            "assembled_rows": (self.artifacts.get("compose") or {}).get("rows"),
            "last_step": last_step,
            "pause_events": len(self.pauses),
            "pause_kinds": sorted({p["kind"] for p in self.pauses}),
            "pause_reason_codes": sorted({p["reason_code"] for p in self.pauses}),
            "pause_facts_incomplete": sum(1 for p in self.pauses if not (p["kind"] and p["reason_code"])),
            "pause_kinds_unknown": sorted({p["kind"] for p in self.pauses} - PAUSE_KINDS),
        }


import threading  # noqa: E402

SC = {}


def _apply_answer(ans, g, slot, texts, picks):
    """把一条脚本答案落到 (picks/texts)；落不下就什么都不做（交给 _auto_answer 兜底）。"""
    ans = str(ans)
    opts = g.get("options") or []

    def _opt(pred):
        return next((o for o in opts if isinstance(o, dict) and pred(o)), None)

    if ans.startswith("@recommend"):
        hit = _opt(lambda o: o.get("recommended")) or (opts[0] if opts else None)
    elif ans.startswith("@absent"):
        hit = _opt(lambda o: isinstance(o.get("signal"), dict)
                   and (o.get("signal") or {}).get("kp_absent"))
    elif ans.startswith("@waived"):
        hit = _opt(lambda o: isinstance(o.get("signal"), dict)
                   and (o.get("signal") or {}).get("kp_waived"))
    elif ans.startswith("@pick:"):
        key = ans.split(":", 1)[1]
        hit = _opt(lambda o: key in (str(o.get("label") or "") + str(o.get("value") or "")
                                     + str(o.get("desc") or "")))
        if hit is None and opts:
            hit = opts[0]
    else:
        texts.append(ans)
        return
    if isinstance(hit, dict):
        picks.append({"slot": slot, "value": hit.get("value")})


def _auto_answer(g, answers):
    """脚本答案用尽时的兜底（--auto-answer，确定性策略，保证改前/改后同一口径）：
    有卡 → 优先点带「推荐」标的选项，否则第一个选项；无卡 → 走打字路（__text__ /
    场景 default_answer / 固定短语）。只求「客户照推荐走」，不引入新的业务判断。"""
    opts = g.get("options") or []
    if not opts:
        txt = (str(answers.get("__text__") or "").strip()
               or str(SC.get("default_answer") or "").strip() or "按你推荐的来")
        return "text", txt
    hit = next((o for o in opts if isinstance(o, dict) and o.get("recommended")), None)
    hit = hit or (opts[0] if isinstance(opts[0], dict) else None)
    if hit is None:
        return "text", "按你推荐的来"
    return "pick", hit.get("value")


def gap_answer(gaps, answers, auto=False):
    """全部缺口 → (应答文本, card_selections, 自动兜底的槽位)。S1 一次问全后一轮补齐：
    @recommend → 点选该卡带「推荐」标的选项（客户接受 AI 建议，逐类确认）；
    @absent → 点选「不配」逃生项（GPU 类）；
    @waived → 点选「保持原需求」（库内无料、客户已知悉）的豁免项；
    @pick:关键字 → 点选候选（点击快速路，跳大脑确定性落槽）；
    普通文本 → 合并为一条用户回复（打字路，走大脑全量理解）。
    auto=True：脚本没覆盖的卡由 _auto_answer 兜底，并在第三个返回值里记下兜了哪些
    （看清「脚本答案用尽」发生在第几张卡，而不是整轮直接停）。"""
    texts, picks, auto_slots = [], [], []
    for g in (gaps or []):
        slot = str(g.get("slot") or "")
        # 无选项的缺口（引擎只交回了提问、没组织选项卡：前端是大脑旁白 + 对话框，
        # 没有卡可点）→ 走「客户打字回答」这条路，答案取 __text__。
        if not (g.get("options") or []):
            ans = str(answers.get("__text__") or "").strip() or None
        else:
            ans = answers.get(slot)
            # 行级/类目级答案优先于槽位兜底（brain_ask 逐类卡共用同一 slot，需按行区分）
            row = str(g.get("row") or "")
            if row and answers.get(row):
                ans = answers.get(row)
            else:
                # 行引用是引擎铸造的 row_id（P3-3，文本里没有竖线）：类目只能由卡的
                # 身份元数据给出（pick_meta.category），旧式行键（类目|描述）才切竖线
                cat = str((g.get("pick_meta") or {}).get("category") or "").strip()
                if not cat and "|" in row:
                    cat = row.split("|", 1)[0].strip()
                if cat and answers.get(cat):
                    ans = answers.get(cat)
        before = (len(texts), len(picks))
        if ans is not None:
            _apply_answer(ans, g, slot, texts, picks)
        if auto and (len(texts), len(picks)) == before:
            kind, val = _auto_answer(g, answers)
            auto_slots.append(slot + ("·行 " + str(g.get("row")) if g.get("row") else ""))
            if kind == "pick":
                picks.append({"slot": slot, "value": val})
            else:
                texts.append(val)
    # 点击轮只发 picks（点击快速路按 (slot,value) 直传，混发文本会走旁路语义）；
    # 未覆盖的缺口下轮引擎会重新弹出，收敛不循环
    if picks:
        return None, picks, auto_slots
    if texts:
        return "；".join(texts), None, auto_slots
    return None, None, auto_slots

def main():
    global SC
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--auto-answer", action="store_true",
                    help="脚本答案用尽时按确定性策略代答（推荐项优先），跑到收敛为止；"
                         "用于量「轮数/重复发卡」这类收敛指标（改前改后同一口径）")
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
        print(f"▶ 场景[{SC.get('name')}] thread={tid}")

    runner = Run(token, tid)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def safe_turn(**kw):
        """跑一轮并吞掉 WS 异常：长跑时后端 --reload 重启会掐断连接，
        崩掉整轮等于白跑——改成停下来、照样落报告。"""
        try:
            return loop.run_until_complete(runner.turn(**kw)), ""
        except Exception as exc:
            return None, f"{exc.__class__.__name__}: {str(exc)[:90]}"

    # 第一轮：主输入
    result, err = safe_turn(text=SC.get("input"), max_wait=240.0)
    if err:
        print(f"  ✖ 首轮即中断：{err}", flush=True)
    turns = 1
    answers = SC.get("answers") or {}
    while result and not result["finished"] and turns < int(SC.get("max_turns", 8)):
        gaps = result.get("paused")
        if gaps is None:
            print("  （无缺口且未完成——停止）")
            break
        text, picks, auto_slots = gap_answer(gaps, answers, auto=args.auto_answer)
        if auto_slots:
            runner.auto_answers += len(auto_slots)
            print(f"  ⚙ 脚本答案未覆盖、自动兜底 {len(auto_slots)} 张卡：{'；'.join(auto_slots)}")
        if text is None and picks is None:
            print("  （缺口无对应应答策略——停止）")
            break
        turns += 1
        print(f"  ▶ 应答[{turns}]: {text or picks}")
        result, err = safe_turn(text=text, picks=picks)
        if err:
            print(f"  ✖ 回合中断（后端重启/断连？）：{err}——就此停止", flush=True)
            break
    finished = bool(result.get("finished")) if result else False
    loop.close()

    if not args.keep and not args.attach:
        try:
            http("DELETE", f"/api/assistant/threads/{tid}?hard=1", token=token)
            print("预览线程已清理")
        except Exception as e:
            print("清理失败(可忽略):", e)

    m = runner.metrics(turns, finished)
    m["interrupted"] = bool(err)
    lines = [f"# E2E 报告 · {SC.get('name')}", "",
             f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"- 角色：{SC.get('role_key')}",
             f"- 结果：{'✅ 完成' if finished else '⛔ 未完成'}，共 {turns} 轮", "",
             "## 指标", ""]
    lines += [f"- {k}：{v}" for k, v in m.items()]
    lines.append("")
    lines += ["## 暂停 / 断点", ""]
    if runner.pauses:
        lines += ["- 轮 %d：kind=%s reason=%s step=%s label=%s resumable=%s pending=%s steps_done=%s%s"
                  % (p["turn"], p["kind"], p["reason_code"], p["step"] or "—",
                     p["label"] or "—", p["resumable"], p["pending"] or "—",
                     p["steps_done"] or "—",
                     "  ⚠未登记的 kind" if p["kind"] not in PAUSE_KINDS else "")
                  for p in runner.pauses]
    else:
        lines.append("- （本次没有中断点：全程未触发 pause 广播）")
    lines.append("")
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
    with open("_e2e_metrics.json", "w", encoding="utf-8") as f:
        json.dump({"metrics": m, "cards": runner.cards, "turns": runner.report},
                  f, ensure_ascii=False, indent=1)
    print("报告已写入 _e2e_report.md / _e2e_metrics.json")
    print("指标：" + json.dumps(m, ensure_ascii=False))


if __name__ == "__main__":
    main()
