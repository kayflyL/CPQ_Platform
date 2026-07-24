"""阶段2迁移：回填 kp_parts.brand + 新增 applicable.series（数据驱动过滤）。

三步（均幂等，可重复跑）：
  1. ALTER TABLE kp.kp_parts ADD COLUMN IF NOT EXISTS applicable jsonb
  2. 回填 brand：按 name 前缀规范化（仅 CPU/GPU/Raid card/MB/HBA/Bridge 有品牌；
     HDD/SSD、Memory、NIC 是规格开头，无品牌→跳过保持 null）
  3. 回填 applicable.series（仅 CPU）：
       AMD → ["Orion"]，兆芯(KH) → ["Polaris"]，Intel → []（待确认归属）
     其他品类 applicable 留 null = 全系列通用

系列绑定规则由用户定调（数据源 config_schemes/底盘件均空）。

用法：
  python -X utf8 scripts/migrate_kp_brand_series.py            # dry-run，只看统计
  python -X utf8 scripts/migrate_kp_brand_series.py --commit   # 执行写库
"""
import sys, json, argparse
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from psycopg2.extras import DictCursor
from app.core.config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true", help="真正写库（默认 dry-run）")
args = parser.parse_args()

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor(cursor_factory=DictCursor)

# ---- brand 规范化规则（顺序敏感，具体前缀优先；基于 name 前缀启发式）----
BRAND_RULES = [
    (['兆芯KH', '兆芯', 'KH50000', 'KH'], '兆芯'),
    (['AMD'], 'AMD'),
    (['W7900'], 'AMD'),              # AMD Radeon Pro W7900（GPU）
    (['Intel'], 'Intel'),
    (['Nvidia', 'NVIDIA', 'Nvida', 'RTX'], 'NVIDIA'),
    (['天数智芯'], '天数智芯'),
    (['昇腾'], '华为昇腾'),
    (['壁仞'], '壁仞'),
    (['武桐树'], '武桐树'),
    (['沐曦'], '沐曦'),
    (['曦云'], '曦云'),
    (['智铠', '智凯'], '智铠'),       # 疑似笔误，统一
    (['LSI'], 'LSI'),
    (['华科微'], '华科微'),
    (['自研'], '自研'),
]

# ---- CPU 的 series 绑定（用户定调）----
SERIES_BY_BRAND = {
    'AMD': ['Orion'],
    '兆芯': ['Polaris'],
    'Intel': [],                    # 待用户确认归属，暂两系列都不显示
}


def norm_brand(name):
    if not name:
        return None
    for prefixes, brand in BRAND_RULES:
        if any(name.startswith(p) for p in prefixes):
            return brand
    return None


def series_for(brand, cat):
    """仅 CPU 按 brand 绑 series；其他品类返回 None（不动 applicable）"""
    if cat != 'CPU':
        return None
    if brand in SERIES_BY_BRAND:
        return SERIES_BY_BRAND[brand]
    return None  # CPU 但 brand 未匹配 → 暂不设 applicable


# ---- 加载数据 ----
cur.execute("""
    SELECT p.id, p.name, p.brand, c.name AS cat
    FROM kp.kp_parts p
    JOIN kp.kp_categories c ON p.category_id = c.id
    ORDER BY c.sort_order, p.name
""")
parts = [dict(r) for r in cur.fetchall()]

brand_changes = []   # (id, cat, name, old, new)
series_changes = []  # (id, cat, name, brand, series)
brand_skipped = defaultdict(list)   # cat -> [(name)]  无品牌匹配

for p in parts:
    nb = norm_brand(p['name'])
    if nb:
        if (p['brand'] or None) != nb:
            brand_changes.append((p['id'], p['cat'], p['name'], p['brand'], nb))
        ser = series_for(nb, p['cat'])
        if ser is not None:
            series_changes.append((p['id'], p['cat'], p['name'], nb, ser))
    else:
        brand_skipped[p['cat']].append(p['name'])

# ---- dry-run 报告 ----
print(f"=== KP 配件总数: {len(parts)} ===\n")

print("=== ① brand 回填（按 name 前缀规范化）===")
by_brand = defaultdict(list)
for _, cat, name, _, nb in brand_changes:
    by_brand[nb].append(f"[{cat}] {name}")
for b, items in sorted(by_brand.items()):
    print(f"  → {b}（{len(items)} 条）")
    for it in items[:4]:
        print(f"      {it}")
    if len(items) > 4:
        print(f"      …等 {len(items)} 条")
print(f"  合计待写 brand: {len(brand_changes)} 条")

print(f"\n=== ② applicable.series 回填（仅 CPU）===")
ser_count = defaultdict(int)
for _, cat, name, b, ser in series_changes:
    key = f"{b} → {ser}"
    ser_count[key] += 1
for k, n in ser_count.items():
    print(f"  {k}（{n} 条）")
print(f"  合计待写 series: {len(series_changes)} 条")
# 列 CPU 里未绑 series 的（brand 未匹配的 CPU）
cpu_unbound = [p for p in parts if p['cat'] == 'CPU' and not norm_brand(p['name'])]
if cpu_unbound:
    print(f"  ⚠ CPU 未匹配 brand（不设 series）: {len(cpu_unbound)} 条")
    for p in cpu_unbound:
        print(f"      {p['name']!r}")

print(f"\n=== 无品牌（保持 null）的类别 ===")
for cat, names in brand_skipped.items():
    if cat in ('HDD/SSD', 'Memory', 'NIC', 'Fibre Channel', 'HBA', 'Key Parts', 'Bridge'):
        print(f"  {cat}: {len(names)} 条（规格开头，无品牌，正确留空）")

# ---- 写库 ----
if not args.commit:
    print("\n[dry-run] 未写库。确认统计无误后加 --commit 执行。")
else:
    cur.execute("ALTER TABLE kp.kp_parts ADD COLUMN IF NOT EXISTS applicable jsonb")
    print("✓ ALTER TABLE kp.kp_parts ADD COLUMN applicable jsonb（幂等）")

    brand_written = 0
    for pid, cat, name, old, nb in brand_changes:
        cur.execute(
            "UPDATE kp.kp_parts SET brand=%s WHERE id=%s AND brand IS DISTINCT FROM %s",
            (nb, pid, nb),
        )
        brand_written += cur.rowcount
    print(f"✓ brand 写入 {brand_written} 条（IS DISTINCT FROM，重跑为 0）")

    series_written = 0
    for pid, cat, name, b, ser in series_changes:
        sj = json.dumps(ser)
        cur.execute(
            "UPDATE kp.kp_parts SET applicable=jsonb_build_object('series', %s::jsonb) "
            "WHERE id=%s AND applicable IS DISTINCT FROM jsonb_build_object('series', %s::jsonb)",
            (sj, pid, sj),
        )
        series_written += cur.rowcount
    print(f"✓ applicable.series 写入 {series_written} 条（IS DISTINCT FROM，重跑为 0）")

    conn.commit()
    print("\n迁移写入完成。")

cur.close()
conn.close()
