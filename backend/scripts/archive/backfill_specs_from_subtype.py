"""一次性回填：把 parts_master.sub_type 迁到 specs 对应键（sub_type 列即将 DROP）。

方向（与 clean_parts_specs.py 相反——历史曾把 specs.kind 合进 sub_type，现逆向恢复）：
  - category='前面板线缆' : sub_type → specs.kind（若 specs.kind 已有值则不覆盖）
  - category='背板'       : sub_type 本就空，按 name 推断 specs.bt（三模→tri / 直连→dc）
  - 其他有 sub_type 的行  : 无前端消费方，跳过（DROP 时自然丢弃）

安全：默认 dry-run（只打印），--commit 才写库。
用法：
  python -X utf8 scripts/backfill_specs_from_subtype.py            # dry-run
  python -X utf8 scripts/backfill_specs_from_subtype.py --commit   # 实际写
"""
import sys, json, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from psycopg2.extras import DictCursor
from app.core.config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true", help="真正写入数据库（默认 dry-run）")
args = parser.parse_args()

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor(cursor_factory=DictCursor)


def load_specs(raw):
    if not raw:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    try:
        return json.loads(raw)
    except Exception:
        return {}


stat = {"front_cable": 0, "backplane": 0, "skip": 0}

# 1) sub_type 非空 → 按 category 分发
cur.execute(
    "SELECT pn, name, category, sub_type, specs FROM l6.parts_master "
    "WHERE sub_type IS NOT NULL AND sub_type <> ''"
)
for r in cur.fetchall():
    pn, cat, st = r["pn"], r["category"], r["sub_type"]
    specs = load_specs(r["specs"])
    if cat == "前面板线缆":
        if specs.get("kind"):
            print(f"[跳过] 前面板线缆 {pn}: specs.kind 已有值 '{specs['kind']}'")
            stat["skip"] += 1
            continue
        specs["kind"] = st
        print(f"[前面板线缆] {pn} ({r['name']}): specs.kind = {st}")
        if args.commit:
            cur.execute(
                "UPDATE l6.parts_master SET specs = CAST(%s AS jsonb) WHERE pn = %s",
                (json.dumps(specs, ensure_ascii=False), pn),
            )
        stat["front_cable"] += 1
    else:
        print(f"[跳过] {pn} (category={cat}, sub_type={st}) — 无前端消费方")
        stat["skip"] += 1

# 2) 背板 sub_type 本就空，按 name 推断 specs.bt
cur.execute("SELECT pn, name, specs FROM l6.parts_master WHERE category = '背板'")
for r in cur.fetchall():
    pn, name = r["pn"], r["name"] or ""
    specs = load_specs(r["specs"])
    if specs.get("bt"):
        continue
    nl = name.lower()
    if "三模" in name or "tri" in nl:
        specs["bt"] = "tri"
    elif "直连" in name or nl.startswith("dc") or "direct" in nl:
        specs["bt"] = "dc"
    else:
        continue
    print(f"[背板] {pn} ({name}): specs.bt = {specs['bt']}")
    if args.commit:
        cur.execute(
            "UPDATE l6.parts_master SET specs = CAST(%s AS jsonb) WHERE pn = %s",
            (json.dumps(specs, ensure_ascii=False), pn),
        )
    stat["backplane"] += 1

if args.commit:
    conn.commit()
    print(f"\n已提交：{stat}")
else:
    print(f"\nDRY-RUN（未写入）: {stat}  确认无误后加 --commit")

conn.close()
