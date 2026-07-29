"""KP 配件库数据清洗脚本

执行清洗：
1. 删除价格历史重复记录（保留一条）
2. 修正价格异常配件的货币单位（RMB → USD）

用法：python scripts/clean_kp_data.py [--dry-run]
"""
import sys
import json
from pathlib import Path
from datetime import date
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from psycopg2.extras import DictCursor
from app.core.config import get_settings

s = get_settings()
conn = psycopg2.connect(
    host=s.POSTGRES_HOST, port=s.POSTGRES_PORT, dbname=s.POSTGRES_DB,
    user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD, client_encoding="UTF8"
)
cur = conn.cursor(cursor_factory=DictCursor)

# 检查参数
dry_run = "--dry-run" in sys.argv
if dry_run:
    print("=" * 60)
    print("【模拟运行】不会实际修改数据")
    print("=" * 60)

print("\n" + "=" * 60)
print("KP 配件库数据清洗")
print("=" * 60)

# ==================== 1. 删除价格历史重复记录 ====================
print("\n【1. 删除价格历史重复记录】")

# 查找重复组（同 part_id + 同 price + 同 currency + 同 price_date）
cur.execute("""
    SELECT part_id, price, currency, price_date, COUNT(*) AS dup_count,
           array_agg(id ORDER BY id) AS dup_ids
    FROM kp.kp_price_history
    WHERE price_date IS NOT NULL
    GROUP BY part_id, price, currency, price_date
    HAVING COUNT(*) > 1
""")
dup_groups = cur.fetchall()

deleted_count = 0
for r in dup_groups:
    ids = r["dup_ids"]
    # 保留第一条，删除其余
    keep_id = ids[0]
    delete_ids = ids[1:]
    print(f"  part_id={r['part_id']} | ¥{r['price']} | {r['price_date']} | 保留 id={keep_id}，删除 {len(delete_ids)} 条: {delete_ids}")
    if not dry_run:
        cur.execute("DELETE FROM kp.kp_price_history WHERE id = ANY(%s)", (delete_ids,))
        deleted_count += len(delete_ids)

if not dry_run:
    conn.commit()
    print(f"\n  ✓ 已删除 {deleted_count} 条重复记录")
else:
    print(f"\n  [模拟] 将删除 {sum(len(r['dup_ids'])-1 for r in dup_groups)} 条重复记录")

# ==================== 2. 修正货币单位（RMB → USD） ====================
print("\n【2. 修正货币单位（RMB → USD）】")

# 价格异常配件列表（来自分析脚本）
anomaly_parts = [
    {"part_id": None, "name": "AMD EPYC 9354", "min_price": 1350.0},
    {"part_id": None, "name": "AMD EPYC 9654", "min_price": 2300.0},
    {"part_id": None, "name": "AMD EPYC 9334", "min_price": 1040.0},
    {"part_id": None, "name": "KH50000 96C", "min_price": 3500.0},
    {"part_id": None, "name": "AMD EPYC 9124", "min_price": 600.0},
    {"part_id": None, "name": "7.68T NVME SSD", "min_price": 3700.0},
    {"part_id": None, "name": "AMD EPYC 9355", "min_price": 2200.0},
]

# 查找 part_id
for a in anomaly_parts:
    cur.execute("SELECT id FROM kp.kp_parts WHERE name = %s", (a["name"],))
    row = cur.fetchone()
    a["part_id"] = row["id"] if row else None

fixed_count = 0
for a in anomaly_parts:
    if not a["part_id"]:
        print(f"  ⚠ 配件 '{a['name']}' 不存在，跳过")
        continue

    # 找出该配件的低价记录（价格接近 min_price）
    cur.execute("""
        SELECT id, price, currency, price_date
        FROM kp.kp_price_history
        WHERE part_id = %s AND currency = 'RMB'
        ORDER BY price ASC
    """, (a["part_id"],))
    rows = cur.fetchall()

    # 找价格在 min_price 附近的记录（允许 10% 偏差）
    target_records = [r for r in rows if abs(r["price"] - a["min_price"]) / a["min_price"] < 0.1]

    for r in target_records:
        print(f"  part_id={a['part_id']} '{a['name']}' | ¥{r['price']} | {r['price_date']} | RMB → USD")
        if not dry_run:
            cur.execute("UPDATE kp.kp_price_history SET currency = 'USD' WHERE id = %s", (r["id"],))
            fixed_count += 1

if not dry_run:
    conn.commit()
    print(f"\n  ✓ 已修正 {fixed_count} 条记录的货币单位")
else:
    print(f"\n  [模拟] 将修正 {sum(1 for a in anomaly_parts if a['part_id'])} 条记录")

# ==================== 3. 验证清洗结果 ====================
print("\n【3. 验证清洗结果】")

# 重新统计重复
cur.execute("""
    SELECT COUNT(*) AS n FROM (
        SELECT part_id, price, currency, price_date
        FROM kp.kp_price_history
        WHERE price_date IS NOT NULL
        GROUP BY part_id, price, currency, price_date
        HAVING COUNT(*) > 1
    ) t
""")
dup_after = cur.fetchone()["n"]
print(f"  剩余重复组数: {dup_after}")

# 重新检查价格异常
cur.execute("""
    SELECT ph.part_id, p.name, ph.price, ph.currency
    FROM kp.kp_price_history ph
    JOIN kp.kp_parts p ON ph.part_id = p.id
    WHERE p.name IN ('AMD EPYC 9354', 'AMD EPYC 9654', 'AMD EPYC 9334', 'KH50000 96C',
                     'AMD EPYC 9124', '7.68T NVME SSD', 'AMD EPYC 9355')
    ORDER BY p.name, ph.price
""")
check_rows = cur.fetchall()
print(f"  异常配件价格历史（修正后）:")
for r in check_rows:
    print(f"    {r['name']} | ¥{r['price']} | {r['currency']}")

print("\n" + "=" * 60)
if dry_run:
    print("【模拟运行完成】请去掉 --dry-run 参数执行实际清洗")
else:
    print("【清洗完成】")
print("=" * 60)

cur.close()
conn.close()