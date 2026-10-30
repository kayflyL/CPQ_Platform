# -*- coding: utf-8 -*-
"""流定义灌入（种子通道·入）：backend/seeds/flows/<flow_key>.json → 现库（幂等）。

默认语义 = 「空缺才灌，绝不覆盖用户改动」（与全站种子惯例一致：定价手册/权限目录同款）：
  - skill_catalog：按 key 找不到才插（找到了不动——线上可能已有人改描述）；
  - reasoning_flow：该 skill_key 无 active 流才插种子流 + 其节点配置；
  - 已存在 = 跳过并说明（--force 才覆盖：删旧 active 流行+节点配置后按种子重灌，慎用——
    会抹掉画布上的后续人工改动）。
插入后校准 reasoning_flow_id_seq。用法：
  python scripts/import_flow.py backend/seeds/flows/delivery_to_quotation.json [--force] [--dry]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2  # noqa: E402
from psycopg2.extras import Json  # noqa: E402


def _adapt(v):
    """dict/list → Json 包装（graph/launch_form/config 等结构化列）；其余原样。"""
    if isinstance(v, (dict, list)):
        return Json(v)
    return v

PWD = ""
with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       ".env"), encoding="utf-8") as f:
    for line in f:
        if line.startswith("POSTGRES_PASSWORD="):
            PWD = line.split("=", 1)[1].strip()
LIVE = dict(dbname="cpq_platform", user="postgres", password=PWD, host="localhost", port=5432)

FLOW_COLS = ["id", "name", "skill_key", "version", "status", "graph", "launch_form",
             "is_active", "description", "created_by", "updated_by"]


def main():
    ap = argparse.ArgumentParser(description="种子文件灌入现库（幂等：空缺才灌）")
    ap.add_argument("seed_path")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的同名流（慎用）")
    ap.add_argument("--dry", action="store_true", help="只报告将做什么，不写库")
    args = ap.parse_args()

    seed = json.load(open(args.seed_path, encoding="utf-8"))
    flow_key = seed["flow_key"]
    conn = psycopg2.connect(**LIVE)
    cur = conn.cursor()

    cur.execute("SELECT id FROM rules.reasoning_flow WHERE skill_key = %s AND is_active", (flow_key,))
    exists = cur.fetchone()

    actions = []
    if exists:
        if args.force:
            actions.append(f"FORCE：删除 flow_id={exists[0]} 的旧 active 流行及其节点配置，按种子重灌")
        else:
            actions.append(f"跳过：{flow_key} 已有 active 流（flow_id={exists[0]}）；--force 可覆盖")
    else:
        actions.append(f"插入流 {flow_key}（种子版本 v{seed['flow']['version']}）+ "
                       f"{len(seed['node_configs'])} 条节点配置")
    cur.execute("SELECT id FROM rules.skill_catalog WHERE key = %s", (seed["catalog"]["key"],)) \
        if seed.get("catalog") else None
    cat_exists = cur.fetchone() if seed.get("catalog") else None
    if seed.get("catalog"):
        actions.append(("跳过目录条目（已存在）" if cat_exists
                        else f"插入目录条目 key={seed['catalog']['key']}"))
    print("== 将执行 ==")
    for a in actions:
        print("  ·", a)
    if args.dry:
        print("== --dry：未写库 ==")
        return

    # 目录条目（按 key 补缺）
    if seed.get("catalog") and not cat_exists:
        c = seed["catalog"]
        cols = list(c.keys())
        cur.execute(f"INSERT INTO rules.skill_catalog ({', '.join(cols)}) "
                    f"VALUES ({', '.join(['%s'] * len(cols))})",
                    [_adapt(c[k]) for k in cols])
        print(f"✓ 目录条目已插：key={c['key']}")

    # 流 + 节点配置（空缺才灌；--force 先清旧）
    if exists and not args.force:
        conn.commit()
        print("== 完成（无改动）==")
        return
    if exists and args.force:
        cur.execute("DELETE FROM rules.reasoning_node_config WHERE flow_id = %s", (exists[0],))
        cur.execute("DELETE FROM rules.reasoning_flow WHERE id = %s", (exists[0],))
    f_row = seed["flow"]
    cur.execute("SELECT COALESCE(MAX(id),0)+1 FROM rules.reasoning_flow")
    f_row["id"] = cur.fetchone()[0]
    cur.execute(f"INSERT INTO rules.reasoning_flow ({', '.join(FLOW_COLS)}) "
                f"VALUES ({', '.join(['%s'] * len(FLOW_COLS))})",
                [_adapt(f_row[c]) for c in FLOW_COLS])
    new_fid = f_row["id"]
    for cfg in seed["node_configs"]:
        c = dict(cfg)
        c.pop("id", None)
        # 种子里的 config 可能是 JSON 字符串（DB 直出未解析）——统一转成对象再入库
        if isinstance(c.get("config"), str):
            try:
                c["config"] = json.loads(c["config"])
            except (ValueError, TypeError):
                pass
        c["flow_id"] = new_fid
        c.setdefault("version", 1)          # 非空列
        c.setdefault("updated_by", "import")  # 非空列
        cols = list(c.keys())
        marks = ", ".join(["%s"] * len(cols))
        cur.execute(f"INSERT INTO rules.reasoning_node_config ({', '.join(cols)}) "
                    f"VALUES ({', '.join(['%s'] * len(cols))})",
                    [_adapt(c[k]) for k in cols])
    cur.execute("SELECT setval('rules.reasoning_flow_id_seq', "
                "(SELECT COALESCE(MAX(id),1) FROM rules.reasoning_flow))")
    conn.commit()
    print(f"== 完成：{flow_key} 已灌入（flow_id={new_fid}，节点配置 {len(seed['node_configs'])} 条）==")


if __name__ == "__main__":
    main()
