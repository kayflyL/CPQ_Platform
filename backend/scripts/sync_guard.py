# -*- coding: utf-8 -*-
"""同步伴随守卫：业务数据同步（拉线索/配件/回填）前后各跑一次，防"其他数据被顺带破坏"。

before：对 配置三表（恒含）+ --tables 指定的业务表 做 ①行数快照 ②表数据备份落
        .scratch/sync_guard_<时间戳>/；
after ：与快照对比行数——任何表**变少** = 大字报警（有数据被删）；顺带跑流点名自检。

用法（同步前后各一次，--tables 用真实表名，schema 可带可不带）：
  python scripts/sync_guard.py before --tables opportunities,parts_master
  …… 执行同步 ……
  python scripts/sync_guard.py after  --tables opportunities,parts_master
配置三表恒在守卫范围：rules.reasoning_flow / rules.reasoning_node_config / rules.skill_catalog
——工作流定义是图纸，任何同步都不许让它变少。
"""
import argparse
import io
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402

PWD = ""
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".env"), encoding="utf-8") as f:
    for line in f:
        if line.startswith("POSTGRES_PASSWORD="):
            PWD = line.split("=", 1)[1].strip()
LIVE = dict(dbname="cpq_platform", user="postgres", password=PWD, host="localhost", port=5432)

GUARD_TABLES = ["rules.reasoning_flow", "rules.reasoning_node_config", "rules.skill_catalog"]


def resolve_table(cur, name: str):
    """表名 → (schema, table)；不存在返回 None。无 schema 前缀时按 search_path 找。"""
    if "." in name:
        schema, t = name.split(".", 1)
    else:
        schema, t = "public", name
    cur.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                (schema, t))
    return (schema, t) if cur.fetchone() else None


def main():
    ap = argparse.ArgumentParser(description="同步前后守卫：备份+行数对账+流点名")
    ap.add_argument("phase", choices=["before", "after"])
    ap.add_argument("--tables", default="", help="本次同步涉及的业务表，逗号分隔")
    args = ap.parse_args()

    conn = psycopg2.connect(**LIVE)
    cur = conn.cursor()
    names = GUARD_TABLES + [t.strip() for t in args.tables.split(",") if t.strip()]

    if args.phase == "before":
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        outdir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "..", "..", ".scratch", f"sync_guard_{ts}")
        os.makedirs(outdir, exist_ok=True)
        snapshot = {}
        for name in names:
            t = resolve_table(cur, name)
            if not t:
                print(f"? 跳过（库中无此表）：{name}")
                continue
            qualified = f"{t[0]}.{t[1]}"
            cur.execute(f"SELECT COUNT(*) FROM {qualified}")
            snapshot[qualified] = cur.fetchone()[0]
            buf = io.StringIO()
            cur.copy_expert(f"COPY {qualified} TO STDOUT", buf)
            with open(os.path.join(outdir, f"{t[1]}.txt"), "w", encoding="utf-8") as f:
                f.write(buf.getvalue())
        snapshot["_tables_hint"] = args.tables
        with open(os.path.join(outdir, "snapshot.json"), "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
        print(f"✅ before 完成：{len(snapshot) - 1} 张表已快照+备份 → {outdir}")
        for k, v in snapshot.items():
            if k != "_tables_hint":
                print(f"   {k}: {v} 行")
        return

    # after：找最近一份快照对比
    scratch = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".scratch")
    dirs = sorted((d for d in os.listdir(scratch) if d.startswith("sync_guard_")), reverse=True)
    if not dirs:
        print("✗ 找不到 before 快照（先跑 sync_guard.py before）")
        sys.exit(1)
    with open(os.path.join(scratch, dirs[0], "snapshot.json"), encoding="utf-8") as f:
        before = json.load(f)
    print(f"（对比快照：{dirs[0]}）")
    alarm = False
    for name in names:
        t = resolve_table(cur, name)
        if not t:
            continue
        qualified = f"{t[0]}.{t[1]}"
        cur.execute(f"SELECT COUNT(*) FROM {qualified}")
        now = cur.fetchone()[0]
        was = before.get(qualified)
        if was is None:
            continue
        mark = "✓" if now >= was else "⚠️"
        if now < was:
            alarm = True
        print(f"  {mark} {qualified}: {was} → {now}" + ("　【行数变少！数据被删了？】" if now < was else ""))
    if alarm:
        print("\n⚠️⚠️⚠️ 有表行数变少——先查 .scratch 里对应 before 备份再考虑回滚，别硬扛！")
        sys.exit(1)
    print("\n✅ after：无表变少。流点名自检：")
    from app.core.startup import check_registered_flows_present
    check_registered_flows_present()


if __name__ == "__main__":
    main()
