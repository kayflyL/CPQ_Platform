"""一次性清理 l6.parts_master.specs 的冗余 key（迁移脚本 migrate_to_parts_master.py 副产物）。

清理项：
  - specs.kind        → 若 sub_type 为空，提升到 sub_type；然后删除
  - specs.description → 若顶层 description 为空，提升到顶层；然后删除
  - specs.note        → 若顶层 description 仍为空，并入顶层；然后删除

保留所有有消费点的 specs key（wattage/tdp/bays/form/bt/group_size/drive_bays/backplane/io_slot/option_type/quantity）。

幂等：重复运行只清理残留，已无目标 key 的行不受影响。

用法：
  python scripts/clean_parts_specs.py            # dry-run，只打印统计
  python scripts/clean_parts_specs.py --commit   # 真正写入
"""
import argparse
import psycopg2
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true", help="真正写入数据库（默认 dry-run）")
args = parser.parse_args()

from app.core.config import get_settings

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor()

TARGETS = ["kind", "description", "note"]

# 统计：哪些行会被清理，分别属于哪种情况
cur.execute(
    "SELECT pn, category, sub_type, description, specs "
    "FROM l6.parts_master WHERE specs ?| %s",
    (TARGETS,),
)
rows = cur.fetchall()
stat = {
    "total": len(rows),
    "promote_kind": 0,       # sub_type 为空且 specs.kind 有值 → 提升
    "promote_desc": 0,       # 顶层 description 为空且 specs.description/note 有值 → 提升
    "pure_delete": 0,        # 顶层已有，纯删 specs key
}
for pn, cat, sub_type, desc, specs in rows:
    sp = specs if isinstance(specs, dict) else {}
    kind_val = sp.get("kind")
    desc_val = sp.get("description")
    note_val = sp.get("note")
    promoted_kind = (not sub_type) and bool(kind_val)
    promoted_desc = (not desc) and bool(desc_val or note_val)
    if promoted_kind:
        stat["promote_kind"] += 1
    if promoted_desc:
        stat["promote_desc"] += 1
    if not promoted_kind and not promoted_desc:
        stat["pure_delete"] += 1

print(f"[统计] 待清理 {stat['total']} 条")
print(f"  kind → sub_type 提升: {stat['promote_kind']}")
print(f"  description/note → 顶层 description 提升: {stat['promote_desc']}")
print(f"  纯删除 specs 冗余 key: {stat['pure_delete']}")

if not args.commit:
    print("\n[dry-run] 未写库。确认无误后加 --commit 执行。")
else:
    # 一条 SQL 完成全部：提升 + 删除（NULLIF 把空串当 NULL，COALESCE 只在目标为空时填）
    cur.execute(
        """
        UPDATE l6.parts_master SET
            sub_type    = COALESCE(NULLIF(sub_type, ''), NULLIF(specs->>'kind', '')),
            description = COALESCE(NULLIF(description, ''),
                                   NULLIF(specs->>'description', ''),
                                   NULLIF(specs->>'note', '')),
            specs       = specs - 'kind' - 'description' - 'note'
        WHERE specs ?| %s
        """,
        (TARGETS,),
    )
    affected = cur.rowcount
    conn.commit()
    print(f"\n✓ 已写入，影响 {affected} 行。")

cur.close()
conn.close()
