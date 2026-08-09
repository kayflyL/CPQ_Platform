# -*- coding: utf-8 -*-
"""方案助手·需求分析 —— 模拟多轮对话端到端实测脚本（真实 LLM，本地 DB）。

用法（backend 目录，项目 venv）：
    python -X utf8 scripts/simulate_agent_rounds.py

逻辑：
  每个场景 = 一个全新 assistant 会话（thread）
    round0: run_assistant_pipeline(thread, 原始提问)
    若 need_input → 用场景脚本里的"用户回答"作为 supplement 再跑一轮
    直到 pipeline_done / candidates_ready / error 或达最大轮数
  输出：每一步事件 + 反问（问题/选项/why）+ 最终方案 + 推荐语 + BOM 摘要。
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.services.requirement_intel_service import run_assistant_pipeline
from app.repository.assistant_repo import AssistantRepository

MAX_ROUNDS = 8


def new_thread() -> str:
    repo = AssistantRepository()
    try:
        t = repo.create_thread(created_by="sim-agent", title="模拟对话实测")
        return t["thread_id"]
    finally:
        repo.close()


def summarize_event(ev: dict) -> str:
    t = ev.get("type")
    if t == "pipeline_start":
        steps = ", ".join(s.get("label") or s.get("key") for s in (ev.get("steps") or []))
        return f"🟦 pipeline_start：{steps}"
    if t == "step_start":
        return f"  ▶ step_start：{ev.get('label') or ev.get('step')}"
    if t == "step_done":
        p = ev.get("payload") or {}
        return f"  ✔ step_done：{ev.get('step')} → {json.dumps(p, ensure_ascii=False)[:160]}"
    if t == "need_input":
        opts = ev.get("options") or []
        return (f"❓ 反问（source={ev.get('source')}，round={ev.get('round')}）：\n"
                f"   Q：{ev.get('question')}\n"
                f"   选项：{opts if opts else '（无）'}\n"
                + (f"   💡 why：{ev.get('why')}\n" if ev.get("why") else ""))
    if t == "need_confirm":
        items = ev.get("items") or []
        return (f"❔ 需确认（default={ev.get('default')}）：\n   {ev.get('question')}\n"
                + "\n".join(f"   - {i}" for i in items[:8]))
    if t == "candidates_ready":
        plans = ev.get("plans") or []
        lines = [f"📦 方案 {i + 1}：{p.get('name')}（{p.get('series')} {p.get('form')}，"
                 f"{(p.get('summary') or {}).get('parts_count', '?')} 件 + KP "
                 f"{(p.get('summary') or {}).get('kp_count', '?')} 件，"
                 f"总价 {(p.get('summary') or {}).get('total_cost', '?')}）"
                 for i, p in enumerate(plans)]
        return "📦 candidates_ready：\n" + "\n".join(lines)
    if t == "pipeline_done":
        return "🏁 pipeline_done"
    if t == "pipeline_paused":
        return f"⏸ pipeline_paused（reply_id={ev.get('reply_id')}）"
    if t == "error":
        return f"⚠️ error：{ev.get('message')}"
    if t == "step_progress":
        sub = ev.get("sub") or {}
        return f"   ↳ {sub.get('kind')}：{sub.get('text')}"
    s = json.dumps(ev, ensure_ascii=False, default=str)
    return s[:200]


def render_events(events: list) -> list:
    out = []
    for ev in events:
        line = summarize_event(ev)
        if line:
            out.append(line)
    return out


async def run_scenario(name: str, first: str, replies: list) -> None:
    print("\n" + "=" * 78)
    print(f"场景：{name}")
    print(f"用户第一句：{first}")
    print("=" * 78)
    tid = new_thread()
    text = first
    reply_idx = 0
    all_events = []
    plans = []
    bom_output = None
    recommendation = None
    for rnd in range(MAX_ROUNDS + 1):
        supplement = None
        if rnd > 0:
            if reply_idx >= len(replies):
                # 没有预设回答，但系统还在问 → 强制出方案（用户点跳过）
                print(f"\n[第{rnd}轮] 无更多预设回答 → force_complete")
                events = await run_assistant_pipeline(tid, text, supplement=None, force_complete=True)
            else:
                answer = replies[reply_idx]
                reply_idx += 1
                print(f"\n[第{rnd}轮] 用户回答：{answer}")
                events = await run_assistant_pipeline(tid, text, supplement={"text": answer})
        else:
            print(f"\n[第{rnd}轮] 首轮")
            events = await run_assistant_pipeline(tid, text, supplement=None)
        all_events.extend(events)
        for ev in events:
            line = summarize_event(ev)
            if line:
                print(line)
            if ev.get("type") == "candidates_ready":
                plans = ev.get("plans") or []
                bom_output = ev.get("bom_output")
                recommendation = ev.get("recommendation")
            if ev.get("type") == "error":
                return
        if any(e.get("type") == "pipeline_done" for e in events) and plans:
            break
        if any(e.get("type") == "pipeline_done" for e in events):
            # done 但没方案（可能方案为空）
            break
        if not any(e.get("type") in ("need_input", "need_confirm") for e in events):
            # 没有反问也没 done → 可能出错或已收敛
            break
    # 终态：推荐语 + BOM 文本（与方案助手收尾同源）
    if plans:
        try:
            from app.api.assistant import _build_recommendation, _build_bom_text, _audit_warning
            rec = await _build_recommendation(plans, text, recommendation)
            bom = _build_bom_text(plans, bom_output)
            warn = _audit_warning(plans)
            print("\n── 助手最终输出 ──")
            if rec:
                print(rec)
                if bom:
                    print("\n—— BOM 明细 ——\n" + bom[:1200])
            else:
                print("（推荐语未生成，回退方案清单）")
                print(bom[:1200])
            if warn:
                print("\n" + warn)
        except Exception as e:
            print(f"\n（终态推荐/BOM 生成失败：{e}）")
    else:
        print("\n（未产出方案）")
    # 保存完整事件供复盘
    dump = Path("tmp") / f"sim_{uuid.uuid4().hex[:8]}.json"
    dump.parent.mkdir(exist_ok=True)
    dump.write_text(json.dumps({"scenario": name, "first": first, "events": all_events},
                               ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n（事件已存 {dump}）")


async def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", type=int, default=None, help="只跑第 N 个场景（1 起）")
    args = ap.parse_args()
    scenarios = [
        ("详细需求（AI 训练/推理）",
         "我要一台2U机架式服务器，双路AMD EPYC 9654，内存 32G*16条，2块960G SSD做系统盘，4块8T SATA数据盘，2块RTX 4090做AI推理，预算20万，放数据中心，跑AI训练推理",
         []),
        ("中等需求（数据库，给预算）",
         "帮我配一台服务器，主要跑数据库，预算10万左右",
         ["中型", "数据库", "标准", "2块960G SSD"]),
        ("模糊需求（你看着配）",
         "我要买台服务器，你看着配吧",
         []),
        ("闲聊开场（你好）",
         "你好",
         ["AI / 机器学习"]),
        ("意图切换（改主意）",
         "我要一台AI服务器跑大模型，需要4张H100",
         ["算了，我改主意了，给我配台普通Web服务器跑网站", "中型"]),
        ("存储服务器（委托推荐）",
         "我要一台存储服务器，具体配置你推荐",
         ["不确定/你推荐"]),
        ("裸规格（无场景/用途）",
         "2*EPYC 9654, 32G*16, 2*960G SSD, 预算30万",
         ["AI / 机器学习"]),
    ]
    if args.scenario is not None:
        scenarios = scenarios[args.scenario - 1:args.scenario]
    for name, first, replies in scenarios:
        try:
            await run_scenario(name, first, replies)
        except Exception as e:
            import traceback
            print(f"\n⚠️ 场景「{name}」执行异常：{e}")
            traceback.print_exc()
    print("\n" + "=" * 78)
    print("全部场景结束")


if __name__ == "__main__":
    asyncio.run(main())
