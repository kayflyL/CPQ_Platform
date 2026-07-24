"""回填 CPU/GPU 的 tdp 到 kp.kp_part_specs（供 derive 功耗推导）。

只填高置信值（AMD 官方 9004 系列 datasheet + WebSearch 多源交叉确认）。
未匹配的 CPU/GPU 打印清单，待用户补 TDP_MAP 后重跑（幂等）。

tdp 是业务关键数据（影响电源数量推导），不确定的宁可留空也不猜。

用法：
  python -X utf8 scripts/migrate_kp_tdp.py            # dry-run，看清单
  python -X utf8 scripts/migrate_kp_tdp.py --commit   # 写库
"""
import sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import psycopg2
from psycopg2.extras import DictCursor
from app.core.config import get_settings

parser = argparse.ArgumentParser()
parser.add_argument("--commit", action="store_true", help="写库（默认 dry-run）")
args = parser.parse_args()

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8",
)
cur = conn.cursor(cursor_factory=DictCursor)

# 高置信 tdp（型号子串 -> 瓦数）。name 含该串即匹配。
# 来源：AMD 官方 EPYC 9004 系列 datasheet + TechPowerUp/cpu-monkey 多源确认
TDP_MAP = {
    '9554': 360,   # EPYC 9554 (64C) — 官方 360W，cTDP 320-400W
    '9654': 360,   # EPYC 9654 (96C) — 官方 360W
}
# 待确认/待补（见 dry-run 清单）：
#   AMD: 9115(125W存疑), 9354, 9334, 9347F, 9255, 7A23(疑非标准SKU)
#   国产 CPU: KH50000 全系、兆芯KH50000
#   Intel: 6430, Xeon 4416+/6530/8468（series=[] 隐藏，优先级低）
#   GPU: 全部（NVIDIA/天数智芯/壁仞/沐曦/昇腾/武桐树/曦云/智铠）

cur.execute("""
    SELECT p.id, p.name, c.name AS cat
    FROM kp.kp_parts p
    JOIN kp.kp_categories c ON p.category_id = c.id
    WHERE c.name IN ('CPU', 'GPU')
    ORDER BY c.name, p.name
""")
parts = [dict(r) for r in cur.fetchall()]

matched, unmatched = [], []
for p in parts:
    tdp = next((v for k, v in TDP_MAP.items() if k in p['name']), None)
    (matched if tdp else unmatched).append((p['id'], p['cat'], p['name'], tdp))

print("=== 已匹配（将回填 tdp）===")
for pid, cat, name, tdp in matched:
    print(f"  [{cat}] {name!r:32} → tdp={tdp}")

print(f"\n=== 未匹配（待补 tdp，清单交用户）===")
for pid, cat, name, _ in unmatched:
    print(f"  [{cat}] id={pid:<4} {name!r}")

if not args.commit:
    print(f"\n[dry-run] 未写库。确认后加 --commit 执行（{len(matched)} 条回填）。")
else:
    for pid, cat, name, tdp in matched:
        cur.execute("""
            INSERT INTO kp.kp_part_specs (part_id, spec_key, spec_value, sort_order)
            VALUES (%s, 'tdp', %s, 0)
            ON CONFLICT (part_id, spec_key) DO UPDATE SET spec_value = EXCLUDED.spec_value
        """, (pid, str(tdp)))
    conn.commit()
    print(f"\n✓ 回填 {len(matched)} 条 tdp（幂等，重跑无副作用）")

cur.close()
conn.close()
