# -*- coding: utf-8 -*-
"""黄金对话冒烟 harness（步骤3 评测瘦版）。

用法（cwd=backend）:
  python -X utf8 scripts/golden_smoke.py --list
  python -X utf8 scripts/golden_smoke.py --only g01-fuzzy-requirement
  python -X utf8 scripts/golden_smoke.py --all --out _golden_report.md

行为：直调 colleague_turn_service.run_colleague_turn（产品路径，含转接/记忆/工具），
跑完读 assistant_messages 做行为级宽松断言（崩溃/静默/价格泄漏/职责错乱四大回归）。
每条对话创建独立 thread（golden- 前缀标题），报告列出 id 便于清理。
"""
import argparse
import asyncio
import io
import json
import os
import re
import sys
import time
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CASES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "golden_conversations.json")

PRICE_RE = re.compile(r"[¥￥]\s*\d|\d+(?:\.\d+)?\s*(?:元|万)\b|价格[^\n]{0,8}\d")


def load_cases():
    with io.open(CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["cases"]


def load_colleague(role_key):
    from app.repository.system_config_repo import SystemConfigRepository
    repo = SystemConfigRepository()
    try:
        cfg = repo.get_value("ai_colleagues")
        if isinstance(cfg, str):
            cfg = json.loads(cfg)
        for c in (cfg or {}).get("colleagues", []):
            if c.get("role_key") == role_key:
                return c
        raise SystemExit(f"colleague not found: {role_key}")
    finally:
        repo.close()


def check_assert(spec, messages):
    """返回 (ok: bool, detail: str)。messages 为该 thread 全量消息 dict 列表。"""
    kind = spec.get("type")
    assistant_texts = [m.get("content") or "" for m in messages if m.get("role") == "assistant"]
    all_text = "\n".join(assistant_texts)
    kinds = [m.get("kind") for m in messages if m.get("role") == "assistant"]

    if kind == "error_free":
        bad = [m for m in messages if m.get("kind") == "error"]
        return (not bad), ("" if not bad else "存在 error 消息: " + (bad[0].get("content") or "")[:80])
    if kind == "asks_question":
        ok = any(("？" in t or "? " in t or "吗" in t) for t in assistant_texts)
        return ok, "" if ok else "回复中没有出现问句（反问缺失）"
    if kind == "handoff_any":
        ok = any(k == "handoff" for k in kinds)
        return ok, "" if ok else "没有发生转接"
    if kind == "no_handoff":
        ok = not any(k == "handoff" for k in kinds)
        return ok, "" if ok else "发生了不应有的转接"
    if kind == "artifact":
        ok = any(k == "business_artifact" for k in kinds)
        return ok, "" if ok else "没有产出业务工件"
    if kind == "mentions_any":
        kws = spec.get("keywords") or []
        ok = any(k in all_text for k in kws)
        return ok, "" if ok else f"回复未提到 {kws}"
    if kind == "no_price_digits":
        hit = PRICE_RE.search(all_text)
        return (not hit), "" if not hit else f"疑似价格泄漏: {hit.group(0)!r}"
    if kind == "any_of":
        details = []
        for sub in spec.get("any_of") or []:
            ok, detail = check_assert(sub, messages)
            if ok:
                return True, ""
            if detail:
                details.append(detail)
        return False, "; ".join(details) or "任一断言均未满足"
    return False, f"未知断言类型 {kind}"


async def run_case(case):
    from app.repository.assistant_repo import AssistantRepository
    from app.services.colleague_turn_service import run_colleague_turn

    colleague = load_colleague(case["role_key"])
    repo = AssistantRepository()
    thread = repo.create_thread(
        created_by="golden-smoke",
        title=f"golden-{case['id']}",
        colleague_role_key=case["role_key"],
        entry_point="ai_office",
    )
    thread_id = thread["thread_id"]
    repo.close()

    t0 = time.time()
    final_err = None
    for text in case.get("turns") or []:
        repo = AssistantRepository()
        history = repo.list_messages(thread_id, limit=20)
        repo.close()
        try:
            await run_colleague_turn(
                thread_id, text, None, history, colleague,
                user={"user_id": "golden-smoke", "name": "评测"},
            )
        except Exception as e:  # noqa: BLE001
            final_err = f"{type(e).__name__}: {e}"
            break

    elapsed = round(time.time() - t0, 1)
    repo = AssistantRepository()
    messages = repo.list_messages(thread_id, limit=200)
    repo.close()

    results = []
    if final_err:
        results.append((False, f"回合异常 {final_err}"))
    for spec in case.get("asserts") or []:
        results.append(check_assert(spec, messages))

    ok_all = all(ok for ok, _ in results) and messages
    replies = [m.get("content") or "" for m in messages if m.get("role") == "assistant" and m.get("kind") == "text"]
    sample = (replies[-1] if replies else "(无文本回复)").replace("\n", " ")[:220]
    return {
        "id": case["id"], "ok": ok_all, "elapsed_s": elapsed,
        "n_messages": len(messages), "thread_id": thread_id,
        "fail_details": [d for ok, d in results if not ok and d],
        "sample": sample,
    }


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", help="逗号分隔 case id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="_golden_report.md")
    args = ap.parse_args()

    cases = load_cases()
    if args.list:
        for c in cases:
            print(f"{c['id']:32s} {c['desc']}")
        return
    selected = cases if args.all else [c for c in cases if c["id"] in (args.only or "").split(",")]
    if not selected:
        ap.error("用 --list 查看用例，--only 或 --all 选择")

    results = []
    for c in selected:
        print(f"▶ {c['id']} …", flush=True)
        r = await run_case(c)
        results.append(r)
        mark = "PASS" if r["ok"] else "FAIL"
        print(f"  {mark} {r['elapsed_s']}s msgs={r['n_messages']} thread={r['thread_id'][:12]}", flush=True)
        for d in r["fail_details"]:
            print(f"    ✗ {d}", flush=True)

    lines = [
        "# 黄金对话冒烟报告", "",
        f"- 时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 用例：{len(results)} 条，通过 {sum(1 for r in results if r['ok'])} 条", "",
        "| 用例 | 结果 | 耗时s | 消息数 | thread |", "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['id']} | {'✅' if r['ok'] else '❌'} | {r['elapsed_s']} | {r['n_messages']} | `{r['thread_id'][:12]}` |")
    lines += ["", "## 回复摘要（人工复核区）", ""]
    for r in results:
        lines += [f"### {r['id']} {'✅' if r['ok'] else '❌'}", f"- thread: `{r['thread_id']}`"]
        for d in r["fail_details"]:
            lines.append(f"- 失败: {d}")
        lines += [f"> {r['sample']}", ""]

    with io.open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n报告已写入 {args.out}")
    sys.exit(0 if all(r["ok"] for r in results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
