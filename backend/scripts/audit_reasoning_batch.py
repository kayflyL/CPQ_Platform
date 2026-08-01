"""批量验证推理流：拉库里真实 customer_requirement_text，逐条跑「真路径」run_graph_executor
（与 test-run 端点同源，force_complete=True 跳反问一步出方案），审计每条输出，最后汇 gap 清单。

用法：python -X utf8 backend/scripts/audit_reasoning_batch.py
只读（除推理流内部对 KP/baseline 的查询），不改库。
"""
import sys, json, asyncio
sys.path.insert(0, r'D:\CPQ_Platform_V1\backend')

from sqlalchemy import create_engine, text
from app.core.config import get_settings
from app.repository.reasoning_flow_repo import ReasoningFlowRepository
from app.services.reasoning_executor import run_graph_executor

url = get_settings().DATABASE_URL
engine = create_engine(url, connect_args={"client_encoding": "UTF8"})


def load_real_requirements() -> list[tuple[str, str, str]]:
    """(opportunity_id, customer_name, requirement_text) —— 仅取有真实需求文本的。"""
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT opportunity_id, customer_name, extra_fields "
            "FROM opportunities.opportunities "
            "WHERE status='active' AND extra_fields LIKE '%customer_requirement_text%' "
            "ORDER BY created_at DESC"
        )).fetchall()
    out = []
    for oid, cust, ef in rows:
        try:
            d = json.loads(ef) if isinstance(ef, str) else (ef or {})
        except Exception:
            continue
        t = (d or {}).get("customer_requirement_text")
        if isinstance(t, str) and len(t.strip()) >= 8:
            out.append((oid, cust or "-", t.strip()))
    return out


async def run_one(flow: dict, req_text: str, budget: float | None) -> dict:
    """跑一条需求，返回审计快照。"""
    events: list = []

    async def _collect(payload: dict):
        events.append(payload)

    try:
        ctx = await run_graph_executor(
            "audit", req_text, flow, _collect,
            initial_ctx={"budget": budget, "force_complete": True},
        )
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}", "events": events}

    ext = ctx.get("ext") or {}
    kp_by_model = ctx.get("kp_by_model") or {}
    plans = ctx.get("plans") or []

    # match_kp 审计：把每机型的 KP 件按 matched/unmatched 拆开
    kp_audit = []
    for model_key, kps in kp_by_model.items():
        matched = [k for k in kps if not k.get("unmatched")]
        unmatched = [k for k in kps if k.get("unmatched")]
        kp_audit.append({
            "model": model_key,
            "n": len(kps),
            "matched_cats": sorted({k.get("category") for k in matched if k.get("category")}),
            "unmatched_cats": sorted({k.get("category") for k in unmatched if k.get("category")}),
        })

    return {
        "ext": {
            "series": ext.get("series"), "form": ext.get("form"),
            "usage": ext.get("usage"), "server_type_name": ext.get("server_type_name"),
            "categories": ext.get("categories") or [],
            "keywords": ext.get("keywords") or [],
            "chassis_categories": ext.get("chassis_categories") or [],
            "budget": ext.get("budget"),
            "mem_signal": ext.get("mem_signal"),
            "cpu_signal": ext.get("cpu_signal"),
        },
        "baselines": [(p.get("name") or p.get("model")) for p in plans],
        "plans": [{
            "name": p.get("name") or p.get("model"),
            "parts_count": (p.get("summary") or {}).get("parts_count"),
            "kp_count": (p.get("summary") or {}).get("kp_count"),
            "total_cost": (p.get("summary") or {}).get("total_cost"),
            "currency": (p.get("summary") or {}).get("currency"),
            "over_budget": bool(p.get("over_budget")),
            "underspend": bool(p.get("underspend")),
        } for p in plans],
        "kp_audit": kp_audit,
        "clarity": ctx.get("clarity"),
        "events": events,
        "error": None,
    }


def fmt(v):
    if v is None:
        return "—"
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x) for x in v) if v else "∅"
    return str(v)


async def main():
    repo = ReasoningFlowRepository()
    try:
        flow = repo.get_active_flow()
    finally:
        repo.close()
    if not flow:
        print("❌ 无 active 推理流"); return

    reqs = load_real_requirements()
    print(f"=== 推理流批量验证（真实客户需求 {len(reqs)} 条）===\n")
    print(f"active flow: v{flow.get('version')} (graph nodes={len((flow.get('graph') or {}).get('nodes', []))})\n")

    results = []
    for i, (oid, cust, req) in enumerate(reqs, 1):
        # 从需求里抽预算（部分需求带预算字样），简单交给 executor 内 _extract_budget；这里不另传
        snap = await run_one(flow, req, budget=None)
        snap["oid"], snap["cust"], snap["req"] = oid, cust, req
        results.append(snap)

        print(f"━━━ #{i} {oid} | {cust} ━━━")
        print(f"需求: {req[:140]}{'…' if len(req)>140 else ''}")
        if snap.get("error"):
            print(f"  ❌ 执行失败: {snap['error'][:200]}")
            print()
            continue
        e = snap["ext"]
        print(f"  [extract] 系列={fmt(e['series'])} 形态={fmt(e['form'])} 用途={fmt(e['usage']) or fmt(e['server_type_name'])} "
              f"品类={fmt(e['categories'])} 底盘={fmt(e['chassis_categories'])} 预算={fmt(e['budget'])}")
        if e.get("mem_signal") or e.get("cpu_signal"):
            print(f"            内存信号={fmt(e.get('mem_signal'))} CPU信号={fmt(e.get('cpu_signal'))}")
        print(f"  [keywords] {fmt(e['keywords'])}")
        print(f"  [选型] 命中机型 {len(snap['baselines'])} 个: {fmt(snap['baselines'])}")
        if not snap["baselines"]:
            print(f"  ⚠ 无机型 → 流程空跑"); print(); continue
        for p in snap["plans"]:
            ob = " ⚠超预算" if p["over_budget"] else (" 💡低花销" if p["underspend"] else "")
            print(f"  [方案] {p['name']}: 底盘{p['parts_count']}件+KP{p['kp_count']}件 "
                  f"总价 {p['currency'] or 'RMB'} {p['total_cost']}{ob}")
        for k in snap["kp_audit"]:
            um = k["unmatched_cats"]
            tag = f"  ⚠ {len(um)} 品类未配到件: {fmt(um)}" if um else ""
            print(f"  [match_kp] {k['model']}: 配{k['n']}件 已配={fmt(k['matched_cats'])}{tag}")
        print()

    # ===== gap 汇总 =====
    print("\n" + "═" * 64)
    print("【gap 汇总】")
    ok = [r for r in results if not r.get("error")]
    n = len(results)
    sel_ok = sum(1 for r in ok if r["baselines"])
    print(f"  执行成功 {len(ok)}/{n} ｜ 选型命中≥1机型 {sel_ok}/{n}")

    # 系列/形态识别率
    series_hit = sum(1 for r in ok if r["ext"]["series"])
    form_hit = sum(1 for r in ok if r["ext"]["form"])
    print(f"  系列识别 {series_hit}/{len(ok)} ｜ 形态识别 {form_hit}/{len(ok)}")

    # 未配到件的品类频次（跨所有机型去重计数）
    from collections import Counter
    unmatched_counter = Counter()
    unmatched_cases = Counter()
    for r in ok:
        for k in r["kp_audit"]:
            for cat in k["unmatched_cats"]:
                unmatched_counter[cat] += 1
                unmatched_cases[cat] += 1
    if unmatched_counter:
        print(f"  未配到件品类（频次）:")
        for cat, c in unmatched_counter.most_common():
            print(f"    {c:3d}× {cat}")
    else:
        print("  未配到件品类: 无（match_kp 全命中）")

    # 总价范围
    costs = [p["total_cost"] for r in ok for p in r["plans"] if p["total_cost"] is not None]
    if costs:
        print(f"  方案总价范围: ¥{min(costs):.0f} ~ ¥{max(costs):.0f}（共 {len(costs)} 张方案）")

    over = sum(1 for r in ok for p in r["plans"] if p["over_budget"])
    under = sum(1 for r in ok for p in r["plans"] if p["underspend"])
    print(f"  超预算方案 {over} ｜ 低花销方案 {under}")


if __name__ == "__main__":
    asyncio.run(main())
