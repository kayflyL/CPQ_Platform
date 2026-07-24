"""整理三表 → 两张表（KP 和 L6 严格分开，无第三张表）。

前提（用户定调）：整机只有两类件——KP 配件（kp_parts）和 L6 配件（l6.parts_master），
绝不合并、不要第三张表。本脚本把当前混乱的三表整理干净：

1. l6.parts_master 里混入的 KP 件（cpu/gpu/NVSwitch/NVLink）→ 移到 kp_parts
   - 9654/9554 在 kp_parts 已有 → 去重跳过
   - H100/A800/NVSwitch/NVLink → 新增（新建 NVSwitch/NVLink 类别，derive switch_extra 也认这俩名）
2. parts.parts_master（废弃的第三张表）的 L6 件 → 并入 l6.parts_master
   - pn 冲突（3 条电源）→ l6. 为准，跳过
   - 其余 33 条 → 并入，applicable 信息合并进 specs（l6 表无 applicable 列）
3. --commit 时：删 l6. 已移走的 6 条 KP 件
4. --drop 时：DROP parts.parts_master（第三张表）

用法：
  python -X utf8 scripts/migrate_consolidate_parts.py              # dry-run
  python -X utf8 scripts/migrate_consolidate_parts.py --commit      # 移数据 + 删 l6.KP件
  python -X utf8 scripts/migrate_consolidate_parts.py --commit --drop  # 再 DROP parts.表
"""
import sys, json, re, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from psycopg2.extras import DictCursor
from app.core.config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true", help="执行移数据 + 删 l6.KP 件（默认 dry-run）")
parser.add_argument("--drop", action="store_true", help="额外 DROP parts.parts_master（需 --commit）")
args = parser.parse_args()

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor(cursor_factory=DictCursor)


def fetch(q, p=None):
    cur.execute(q, p or {})
    return [dict(r) for r in cur.fetchall()]


# ============================================================
# A. 新建 kp_categories NVSwitch / NVLink（derive switch_extra 认这俩名）
# ============================================================
print("=== A. kp_categories（确保 NVSwitch/NVLink 类别存在）===")
cat_id = {r["name"]: r["id"] for r in fetch("SELECT id, name FROM kp.kp_categories")}
for cn in ("NVSwitch", "NVLink"):
    if cn not in cat_id:
        cur.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 FROM kp.kp_categories")
        next_sort = cur.fetchone()[0]
        print(f"  将新建类别: {cn!r} (sort_order={next_sort})")
        if args.commit:
            cur.execute(
                "INSERT INTO kp.kp_categories (name, sort_order) VALUES (%s, %s) RETURNING id",
                (cn, next_sort),
            )
            cat_id[cn] = cur.fetchone()[0]
        else:
            cat_id[cn] = None  # dry-run 占位
    else:
        print(f"  已存在: {cn!r} (id={cat_id[cn]})")

# ============================================================
# B. l6.parts_master 的 KP 件 → kp_parts
# ============================================================
print("\n=== B. l6.parts_master 的 KP 件 → kp_parts ===")
CAT_MAP = {"cpu": "CPU", "gpu": "GPU", "NVSwitch": "NVSwitch", "NVLink": "NVLink"}
# 品牌：H100/A800/NVSwitch/NVLink 都是 NVIDIA 系
def brand_of(name):
    n = (name or "").upper()
    if any(k in n for k in ("H100", "A800", "NVSWITCH", "NVLINK", "A100")):
        return "NVIDIA"
    return None

l6_kp = fetch("""
    SELECT pn, name, category, sub_type, tdp, cables_per, unit_price, specs
    FROM l6.parts_master WHERE category IN ('cpu', 'gpu', 'NVSwitch', 'NVLink')
""")

b_new, b_dup = [], []
for p in l6_kp:
    nm = p["name"] or ""
    # 去重：提取型号数字关键词查 kp_parts（无关键词则用全名）
    m = re.search(r"([0-9][0-9A-Z]{3,})", nm.upper())
    kw = m.group(1) if m else nm
    exists = fetch("SELECT id FROM kp.kp_parts WHERE name ILIKE %s", (f"%{kw}%",))
    if exists:
        b_dup.append((p["pn"], nm, kw, exists[0]["id"]))
        continue
    b_new.append(p)

print(f"  去重跳过（kp_parts 已有）: {len(b_dup)} 条")
for pn, nm, kw, kid in b_dup:
    print(f"    l6[{nm!r}] kw={kw!r} → kp_parts id={kid}")

print(f"  新增到 kp_parts: {len(b_new)} 条")
for p in b_new:
    print(f"    [{p['category']}] {p['pn']!r} {p['name']!r} tdp={p['tdp']} cables={p['cables_per']} ¥{p['unit_price']}")

if args.commit:
    for p in b_new:
        kp_cat = CAT_MAP[p["category"]]
        cid = cat_id.get(kp_cat)
        if cid is None:
            print(f"    !! 类别 {kp_cat!r} 无 id（dry-run 未建），跳过 {p['name']!r}")
            continue
        brand = brand_of(p["name"])
        # name 加品牌前缀（符合 kp_parts 习惯），oem_sku 用 l6 的正式 pn
        new_name = p["name"]
        if brand and not new_name.upper().startswith(brand.upper()):
            new_name = f"{brand} {new_name}"
        cur.execute(
            """INSERT INTO kp.kp_parts (category_id, oem_sku, brand, name, moq)
               VALUES (%s, %s, %s, %s, 1) RETURNING id""",
            (cid, p["pn"], brand, new_name),
        )
        new_id = cur.fetchone()[0]
        # specs：tdp / cables_per
        for key, val in (("tdp", p["tdp"]), ("cables_per", p["cables_per"])):
            if val is not None:
                cur.execute(
                    """INSERT INTO kp.kp_part_specs (part_id, spec_key, spec_value, sort_order)
                       VALUES (%s, %s, %s, 0) ON CONFLICT (part_id, spec_key) DO UPDATE SET spec_value=EXCLUDED.spec_value""",
                    (new_id, key, str(val)),
                )
        # 价格
        if p["unit_price"]:
            cur.execute(
                """INSERT INTO kp.kp_price_history (part_id, price, currency, price_date)
                   VALUES (%s, %s, 'RMB', CURRENT_DATE)""",
                (new_id, p["unit_price"]),
            )
    print(f"  ✓ kp_parts 新增 {len(b_new)} 条（含 specs/price）")

# ============================================================
# C. parts.parts_master 的 L6 件 → l6.parts_master
# ============================================================
print("\n=== C. parts.parts_master（废弃表）的 L6 件 → l6.parts_master ===")
parts_l6 = fetch("SELECT pn, name, category, sub_type, unit_price, specs, applicable FROM parts.parts_master")
l6_pns = {r["pn"] for r in fetch("SELECT pn FROM l6.parts_master")}
c_merge, c_skip = [], []
for p in parts_l6:
    (c_skip if p["pn"] in l6_pns else c_merge).append(p)

print(f"  冲突跳过（l6. 已有同 pn）: {len(c_skip)} 条")
for p in c_skip:
    print(f"    {p['pn']!r} [{p['category']}] {p['name']!r}")

print(f"  并入 l6.parts_master: {len(c_merge)} 条")

if args.commit:
    for p in c_merge:
        # specs 合并：parts.specs || parts.applicable（l6 表无 applicable 列，信息并进 specs 不丢）
        merged = {}
        if p["specs"]:
            merged.update(p["specs"] if isinstance(p["specs"], dict) else json.loads(p["specs"]))
        if p["applicable"]:
            ap = p["applicable"] if isinstance(p["applicable"], dict) else json.loads(p["applicable"])
            for k, v in ap.items():
                merged.setdefault(k, v)  # applicable 的 chassis/backplane 等并进 specs
        cur.execute(
            """INSERT INTO l6.parts_master (pn, name, category, sub_type, unit_price, specs)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb)
               ON CONFLICT (pn) DO UPDATE SET name=EXCLUDED.name, category=EXCLUDED.category,
                   sub_type=EXCLUDED.sub_type, unit_price=EXCLUDED.unit_price, specs=EXCLUDED.specs""",
            (p["pn"], p["name"], p["category"], p["sub_type"], p["unit_price"], json.dumps(merged, ensure_ascii=False)),
        )
    print(f"  ✓ l6.parts_master 并入 {len(c_merge)} 条")

# ============================================================
# D. 删 l6.parts_master 已移走的 KP 件（--commit）
# ============================================================
if args.commit:
    cur.execute("DELETE FROM l6.parts_master WHERE category IN ('cpu','gpu','NVSwitch','NVLink')")
    print(f"\n=== D. 删 l6.parts_master 的 KP 件: {cur.rowcount} 条（已移到 kp_parts）===")

conn.commit()

# ============================================================
# E. DROP parts.parts_master（--drop）
# ============================================================
if args.drop:
    if not args.commit:
        print("\n!! --drop 需配合 --commit")
    else:
        # 先把 3 个引用 parts.parts_master 的 FK 改指向 l6.parts_master（数据已全在 l6.）
        # base_config_parts.pn 21/21、base_configs.bp_tri/bp_dc 4/4 均已在 l6.（已核实）
        fk_swaps = [
            ("l6.base_configs", "base_configs_new_bp_tri_pn_fkey", "bp_tri_pn"),
            ("l6.base_configs", "base_configs_new_bp_dc_pn_fkey", "bp_dc_pn"),
            ("l6.base_config_parts", "base_config_parts_new_pn_fkey", "pn"),
        ]
        for tbl, con, col in fk_swaps:
            cur.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT {con}")
            cur.execute(f"ALTER TABLE {tbl} ADD CONSTRAINT {con} FOREIGN KEY ({col}) REFERENCES l6.parts_master(pn)")
            print(f"  FK {con}: parts.parts_master → l6.parts_master")
        cur.execute("DROP TABLE IF EXISTS parts.parts_master")
        conn.commit()
        print("\n=== E. 3 FK 改指向 l6.parts_master + DROP parts.parts_master（第三张表已删除）===")

if not args.commit:
    print(f"\n[dry-run] 未写库。统计：新建类别 {sum(1 for c in ('NVSwitch','NVLink') if c not in [r['name'] for r in fetch('SELECT name FROM kp.kp_categories')])} 个 | "
          f"kp_parts 新增 {len(b_new)} 去重 {len(b_dup)} | l6. 并入 {len(c_merge)} 冲突跳过 {len(c_skip)}")
    print("确认后加 --commit 执行；再加 --drop 删第三张表。")

cur.close()
conn.close()
