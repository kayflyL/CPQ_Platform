"""KP 配件库数据清洗分析脚本

分析目标：
1. 价格历史重复条（同 part + 同价格 + 同币种 + 同日期）
2. 相似配件（oem_sku/alt_sku 精确匹配 + name 相似度）
3. 价格异常低的配件（同一配件历史价格差异巨大，可能是货币单位标错）
4. 其他数据质量问题

输出：数据问题报告（JSON + 控制台摘要）
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

print("=" * 60)
print("KP 配件库数据清洗分析")
print("=" * 60)

# ==================== 1. 基础统计 ====================
print("\n【1. 基础统计】")
cur.execute("SELECT COUNT(*) AS n FROM kp.kp_parts")
total_parts = cur.fetchone()["n"]
cur.execute("SELECT COUNT(*) AS n FROM kp.kp_price_history")
total_prices = cur.fetchone()["n"]
cur.execute("SELECT COUNT(DISTINCT category_id) AS n FROM kp.kp_parts WHERE category_id IS NOT NULL")
total_categories = cur.fetchone()["n"]
print(f"  配件总数: {total_parts}")
print(f"  价格历史总数: {total_prices}")
print(f"  分类数: {total_categories}")

# ==================== 2. 价格历史重复 ====================
print("\n【2. 价格历史重复分析】")
# 重复定义：同 part_id + 同 price + 同 currency + 同 price_date
cur.execute("""
    SELECT part_id, price, currency, price_date, COUNT(*) AS dup_count
    FROM kp.kp_price_history
    WHERE price_date IS NOT NULL
    GROUP BY part_id, price, currency, price_date
    HAVING COUNT(*) > 1
    ORDER BY dup_count DESC, part_id
    LIMIT 50
""")
dup_groups = cur.fetchall()
dup_total = sum(r["dup_count"] for r in dup_groups) - len(dup_groups)  # 超出1条的才是重复
print(f"  重复组数: {len(dup_groups)}")
print(f"  重复记录总数: {dup_total}")
if dup_groups:
    print("  TOP 10 重复组（part_id | 价格 | 币种 | 日期 | 重复数）:")
    for i, r in enumerate(dup_groups[:10], 1):
        print(f"    {i:2d}. part_id={r['part_id']} | {r['price']} {r['currency']} | {r['price_date']} | ×{r['dup_count']}")

# ==================== 3. 相似配件检测 ====================
print("\n【3. 相似配件检测】")
# 3.1 oem_sku / alt_sku 精确匹配
cur.execute("""
    SELECT p1.id AS id1, p1.name AS name1, p1.oem_sku AS oem1, p1.alt_sku AS alt1,
           p2.id AS id2, p2.name AS name2, p2.oem_sku AS oem2, p2.alt_sku AS alt2
    FROM kp.kp_parts p1
    JOIN kp.kp_parts p2 ON p1.id < p2.id
    WHERE (p1.oem_sku IS NOT NULL AND p1.oem_sku = p2.oem_sku)
       OR (p1.oem_sku IS NOT NULL AND p1.oem_sku = p2.alt_sku)
       OR (p1.alt_sku IS NOT NULL AND p1.alt_sku = p2.oem_sku)
       OR (p1.alt_sku IS NOT NULL AND p1.alt_sku = p2.alt_sku)
    LIMIT 50
""")
sku_dup = cur.fetchall()
print(f"  SKU 精确匹配组: {len(sku_dup)}")
if sku_dup:
    print("  前 5 组:")
    for i, r in enumerate(sku_dup[:5], 1):
        print(f"    {i}. ID {r['id1']} '{r['name1']}' (oem={r['oem1']}, alt={r['alt1']})")
        print(f"       ID {r['id2']} '{r['name2']}' (oem={r['oem2']}, alt={r['alt2']})")

# 3.2 同分类下名称相似（简单采样，不做全量 difflib）
cur.execute("""
    SELECT c.name AS cat, p1.id AS id1, p1.name AS name1,
           p2.id AS id2, p2.name AS name2
    FROM kp.kp_parts p1
    JOIN kp.kp_parts p2 ON p1.id < p2.id AND p1.category_id = p2.category_id
    JOIN kp.kp_categories c ON p1.category_id = c.id
    WHERE p1.name IS NOT NULL AND p2.name IS NOT NULL
      AND (p1.name = p2.name OR p1.name ILIKE p2.name || '%' OR p2.name ILIKE p1.name || '%')
    LIMIT 50
""")
name_sim = cur.fetchall()
print(f"  同分类名称前缀匹配组: {len(name_sim)}")
if name_sim:
    print("  前 5 组:")
    for i, r in enumerate(name_sim[:5], 1):
        print(f"    {i}. [{r['cat']}] ID {r['id1']} '{r['name1']}' vs ID {r['id2']} '{r['name2']}'")

# ==================== 4. 价格异常分析 ====================
print("\n【4. 价格异常分析（疑似货币单位错误）】")
# 对每个配件，取历史价格集合，检测是否有数量级差异（如 RMB 标成 USD，约 7 倍；或元标成分，100 倍）
cur.execute("""
    SELECT ph.part_id, p.name AS part_name, c.name AS category,
           MIN(ph.price) AS min_price, MAX(ph.price) AS max_price,
           COUNT(*) AS history_count,
           array_agg(ph.price ORDER BY ph.price) AS prices,
           array_agg(ph.currency ORDER BY ph.price) AS currencies
    FROM kp.kp_price_history ph
    JOIN kp.kp_parts p ON ph.part_id = p.id
    LEFT JOIN kp.kp_categories c ON p.category_id = c.id
    GROUP BY ph.part_id, p.name, c.name
    HAVING COUNT(*) >= 2 AND MIN(ph.price) > 0
""")
price_spread = cur.fetchall()

anomalies = []
for r in price_spread:
    min_p, max_p = r["min_price"], r["max_price"]
    ratio = max_p / min_p if min_p > 0 else 0
    # 异常阈值：价格差异超过 10 倍，或者在同一配件中出现 RMB 和 USD 混用
    currencies = set(r["currencies"])
    multi_currency = "RMB" in currencies and "USD" in currencies
    if ratio > 10 or multi_currency:
        anomalies.append({
            "part_id": r["part_id"],
            "name": r["part_name"],
            "category": r["category"],
            "min_price": min_p,
            "max_price": max_p,
            "ratio": round(ratio, 2),
            "history_count": r["history_count"],
            "multi_currency": multi_currency,
        })

print(f"  价格异常配件数: {len(anomalies)}")
if anomalies:
    # 按差异倍数排序
    anomalies.sort(key=lambda x: x["ratio"], reverse=True)
    print("  TOP 10 异常配件（差异倍数）:")
    for i, a in enumerate(anomalies[:10], 1):
        mc_flag = " [多币种]" if a["multi_currency"] else ""
        print(f"    {i:2d}. [{a['category']}] {a['name']} | ¥{a['min_price']:.2f} ~ ¥{a['max_price']:.2f} | {a['ratio']:.1f}倍{mc_flag}")

# ==================== 5. 其他数据质量问题 ====================
print("\n【5. 其他数据质量问题】")
# 5.1 无分类配件
cur.execute("SELECT COUNT(*) AS n FROM kp.kp_parts WHERE category_id IS NULL")
no_cat = cur.fetchone()["n"]
print(f"  无分类配件: {no_cat}")

# 5.2 无价格历史的配件
cur.execute("""
    SELECT COUNT(*) AS n FROM kp.kp_parts p
    WHERE NOT EXISTS (SELECT 1 FROM kp.kp_price_history ph WHERE ph.part_id = p.id)
""")
no_price = cur.fetchone()["n"]
print(f"  无价格历史的配件: {no_price}")

# 5.3 价格为 0 或 NULL 的历史记录
cur.execute("SELECT COUNT(*) AS n FROM kp.kp_price_history WHERE price IS NULL OR price = 0")
zero_price = cur.fetchone()["n"]
print(f"  价格为空或 0 的历史记录: {zero_price}")

# 5.4 无日期的价格记录
cur.execute("SELECT COUNT(*) AS n FROM kp.kp_price_history WHERE price_date IS NULL")
no_date = cur.fetchone()["n"]
print(f"  无日期的价格记录: {no_date}")

# ==================== 6. 汇总报告 ====================
print("\n" + "=" * 60)
print("【汇总报告】")
print("=" * 60)
print(f"价格历史重复: {dup_total} 条（{len(dup_groups)} 组）")
print(f"SKU 精确匹配疑似重复: {len(sku_dup)} 组")
print(f"同分类名称相似: {len(name_sim)} 组")
print(f"价格异常配件: {len(anomalies)} 个")
print(f"无分类配件: {no_cat}")
print(f"无价格历史配件: {no_price}")
print(f"价格为空/0 历史记录: {zero_price}")
print(f"无日期历史记录: {no_date}")

# 保存详细报告
report = {
    "generated_at": date.today().isoformat(),
    "summary": {
        "total_parts": total_parts,
        "total_prices": total_prices,
        "total_categories": total_categories,
        "price_duplicates": {"groups": len(dup_groups), "records": dup_total},
        "sku_duplicates": len(sku_dup),
        "name_similar": len(name_sim),
        "price_anomalies": len(anomalies),
        "no_category": no_cat,
        "no_price_history": no_price,
        "zero_price_records": zero_price,
        "no_date_records": no_date,
    },
    "price_duplicates_sample": [dict(r) for r in dup_groups[:20]],
    "sku_duplicates_sample": [dict(r) for r in sku_dup[:20]],
    "name_similar_sample": [dict(r) for r in name_sim[:20]],
    "price_anomalies": anomalies[:50],
}

report_path = Path(__file__).parent / "kp_data_cleaning_report.json"
with open(report_path, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"\n详细报告已保存至: {report_path}")

cur.close()
conn.close()