# -*- coding: utf-8 -*-
"""BOM案例库 全量重放脚本 —— 改完规则后的安全网（无页面，训练用）。

用法（backend 目录，项目 venv，本地 DB 即可，无需起服务）：
    python -X utf8 scripts/replay_cases.py            # 全量重放
    python -X utf8 scripts/replay_cases.py --case BC-20260804-120556-149027   # 单案例

逻辑：
  每条 enabled 案例（requirement 非空）→ 用其原始需求跑 active 推理流
  → 系统产出 BOM（plan.cfg.bom_excel_rows）→ compare_boms 规格级对照案例 BOM
  → 绿（0 真差异）/ 红（差异明细，含类型建议）。

差异判定口径（2026-08-04 定）：
  真差异 = 品类数量 + 件级属性(part) + L6 结构 + 需求信号；措辞/格式(format)不算。
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app.repository.bom_case_repo import BomCaseRepository
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.bom_compare import compare_boms, plan_system_rows


def _real_diffs(s: dict) -> int:
    return int(s.get("category_diff") or 0) + int(s.get("part_diff") or 0) + \
        int(s.get("l6_diff") or 0) + int(s.get("requirement_diff") or 0)


async def _run_flow(requirement: str):
    repo = ReasoningFlowRepository()
    try:
        flow = repo.get_active_flow()
    finally:
        repo.close()
    if not flow:
        return None, "无 active 推理流（请先在策略中心-需求分析画布配置节点）"
    from app.services.reasoning_executor import run_graph_executor
    events: list = []
    async def _collect(payload: dict):
        events.append(payload)
    try:
        ctx = await run_graph_executor("replay", requirement, flow, _collect,
                                       initial_ctx={"budget": None, "force_complete": True})
    except Exception as e:
        return None, f"图执行失败: {e}"
    return ctx.get("plans") or [], None


def _fmt_rows(rows) -> list:
    out = []
    for r in rows or []:
        cat = r.get("part_category") or ""
        out.append(f"      {r.get('category')} | {cat} | {r.get('catalogue')} | {r.get('description')} | x{r.get('qty')}")
    return out


def _print_diff(d: dict, prefix="    "):
    t = d.get("type")
    tag = {"format": "format(不算)", "part": "part", "requirement": "requirement"}.get(t, t or "?")
    who = d.get("category") or d.get("item") or d.get("signal") or ""
    if "item" in d:  # L6 结构差异（qty 形态）
        print(f"{prefix}• [{tag}] {who}: 系统={d.get('system_qty')} vs 案例={d.get('case_qty')}"
              f"  (系统: {d.get('system_text') or '—'} / 案例: {d.get('case_text') or '—'})")
    else:
        print(f"{prefix}• [{tag}] {who} {d.get('field', '')}: 系统={d.get('system')} vs 案例={d.get('case')} {d.get('note', '')}")


async def replay_one(case: dict) -> dict:
    req = (case.get("requirement") or "").strip()
    if not req:
        return {"case": case["case_key"], "name": case["name"], "status": "skip",
                "reason": "requirement 为空（旧案例未补）"}
    plans, err = await _run_flow(req)
    if err:
        return {"case": case["case_key"], "name": case["name"], "status": "error", "reason": err}
    if not plans:
        return {"case": case["case_key"], "name": case["name"], "status": "error",
                "reason": "流程走完未产出方案"}
    # 多方案取差异最少者（系统可能出多个变体，取最接近案例的）
    best = None
    for p in plans:
        rep = compare_boms(
            plan_system_rows(p),
            case.get("bom_excel_rows") or [],
            requirement=req,
            system_unmatched=p.get("unmatched"),
            system_chassis_signals=p.get("chassis_signals"),
        )
        score = _real_diffs(rep["summary"])
        if best is None or score < best[0]:
            best = (score, p, rep)
    score, p, rep = best
    status = "ok" if score == 0 else "diff"
    return {
        "case": case["case_key"], "name": case["name"], "status": status,
        "plan": p.get("name") or "", "score": score, "report": rep,
        "plans_count": len(plans),
    }


async def main():
    ap = argparse.ArgumentParser(description="BOM案例库全量重放（改规则安全网）")
    ap.add_argument("--case", help="只重放指定 case_key")
    args = ap.parse_args()

    repo = BomCaseRepository()
    try:
        cases = repo.list_cases(with_parts=True)
    finally:
        repo.close()
    if args.case:
        cases = [c for c in cases if c["case_key"] == args.case]
        if not cases:
            print(f"未找到案例 {args.case}")
            return

    results = []
    for c in cases:
        results.append(await replay_one(c))

    ok_n = diff_n = skip_n = err_n = 0
    for r in results:
        if r["status"] == "ok":
            ok_n += 1
            print(f"\n✅ [{r['case']}] {r['name']}（方案: {r.get('plan')}）—— 0 差异")
        elif r["status"] == "diff":
            diff_n += 1
            print(f"\n❌ [{r['case']}] {r['name']}（方案: {r.get('plan')}，共 {r.get('plans_count')} 个）—— {r['score']} 个真差异")
            rep = r["report"]
            for c in rep["category_level"]:
                if c["status"] != "ok":
                    print(f"    • [qty] {c['category']}: 系统={c['system_qty']} vs 案例={c['case_qty']}")
            for cat in rep["part_level"]:
                for d in cat["diffs"]:
                    _print_diff(d)
            for d in rep["l6_level"]:
                _print_diff(d)
            for c in rep["requirement_checks"]:
                _print_diff(c)
        elif r["status"] == "skip":
            skip_n += 1
            print(f"\n⏭ [{r['case']}] {r['name']} —— {r.get('reason')}")
        else:
            err_n += 1
            print(f"\n⚠ [{r['case']}] {r['name']} —— {r.get('reason')}")

    print("\n" + "=" * 60)
    print(f"重放汇总: 共 {len(results)} | ✅ 0差异 {ok_n} | ❌ 有差异 {diff_n} | ⏭ 跳过 {skip_n} | ⚠ 出错 {err_n}")
    return 0 if diff_n == 0 and err_n == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
