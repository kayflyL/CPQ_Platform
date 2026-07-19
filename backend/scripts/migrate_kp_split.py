"""
KP 配件拆表迁移脚本
将 kp.kp_records 单表拆分为 6 张规范化表：
  kp.kp_categories      — 分类主表
  kp.kp_parts           — 配件主表
  kp.kp_part_specs      — 规格参数（键值对）
  kp.kp_price_history   — 价格历史
  kp.kp_part_compat     — 兼容机型关联
  kp.kp_part_related    — 关联配件推荐

旧表 kp.kp_records 保留不删除，作为备份。
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from sqlalchemy import text
from app.models.base import engine


def run_migration():
    """执行拆表迁移"""
    with engine.connect() as conn:
        # ============================================================
        # 1. 建表
        # ============================================================

        # 1.1 分类表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kp.kp_categories (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                parent_id INTEGER REFERENCES kp.kp_categories(id),
                icon VARCHAR(50),
                sort_order INTEGER DEFAULT 0,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 1.2 配件主表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kp.kp_parts (
                id SERIAL PRIMARY KEY,
                category_id INTEGER REFERENCES kp.kp_categories(id),
                oem_sku VARCHAR(200),
                alt_sku VARCHAR(200),
                brand VARCHAR(100),
                name VARCHAR(500) NOT NULL,
                short_desc TEXT,
                full_desc TEXT,
                condition VARCHAR(50) DEFAULT '全新',
                lead_time VARCHAR(100),
                image_url TEXT,
                datasheet_url TEXT,
                moq INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 1.3 规格参数键值表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kp.kp_part_specs (
                id SERIAL PRIMARY KEY,
                part_id INTEGER NOT NULL REFERENCES kp.kp_parts(id) ON DELETE CASCADE,
                spec_key VARCHAR(200) NOT NULL,
                spec_value TEXT,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(part_id, spec_key)
            )
        """))

        # 1.4 价格历史表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kp.kp_price_history (
                id SERIAL PRIMARY KEY,
                part_id INTEGER NOT NULL REFERENCES kp.kp_parts(id) ON DELETE CASCADE,
                price DOUBLE PRECISION,
                currency VARCHAR(10) DEFAULT 'RMB',
                price_date DATE,
                note TEXT,
                source VARCHAR(200),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))

        # 1.5 兼容机型关联表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kp.kp_part_compat (
                id SERIAL PRIMARY KEY,
                part_id INTEGER NOT NULL REFERENCES kp.kp_parts(id) ON DELETE CASCADE,
                server_model VARCHAR(200) NOT NULL,
                UNIQUE(part_id, server_model)
            )
        """))

        # 1.6 关联配件推荐表
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS kp.kp_part_related (
                id SERIAL PRIMARY KEY,
                source_part_id INTEGER NOT NULL REFERENCES kp.kp_parts(id) ON DELETE CASCADE,
                target_part_id INTEGER NOT NULL REFERENCES kp.kp_parts(id) ON DELETE CASCADE,
                sort_order INTEGER DEFAULT 0,
                UNIQUE(source_part_id, target_part_id)
            )
        """))

        conn.commit()
        print("✓ 6 张新表创建完成")

        # ============================================================
        # 2. 从旧表提取分类，写入 kp_categories
        # ============================================================
        # 先检查是否已有数据（幂等）
        existing_cats = conn.execute(text("SELECT COUNT(*) FROM kp.kp_categories")).scalar()
        if existing_cats > 0:
            print(f"⚠ kp_categories 已有 {existing_cats} 条，跳过分类迁移")
        else:
            # 从旧表提取所有 distinct category，统一命名后写入
            rows = conn.execute(text("""
                SELECT DISTINCT TRIM(category) as cat, COUNT(DISTINCT model) as cnt
                FROM kp.kp_records
                WHERE category IS NOT NULL AND TRIM(category) != ''
                GROUP BY TRIM(category)
                ORDER BY cnt DESC
            """)).fetchall()

            # 分类名统一映射（大小写、重复合并）— 从数据驱动，不硬编码
            # 规则：相同小写名合并，取出现次数最多的原始名作为标准名
            cat_map = {}  # normalized -> standard_name
            for row in rows:
                raw = row[0]
                normalized = raw.lower().replace(' ', '')
                if normalized not in cat_map:
                    cat_map[normalized] = raw
                else:
                    # 保留记录数更多的那个名称
                    existing_cnt = conn.execute(
                        text("SELECT COUNT(*) FROM kp.kp_records WHERE TRIM(category) = :c"),
                        {"c": cat_map[normalized]}
                    ).scalar()
                    if row[1] > existing_cnt:
                        cat_map[normalized] = raw

            # 写入分类表
            sort_idx = 0
            for normalized, standard_name in cat_map.items():
                conn.execute(text("""
                    INSERT INTO kp.kp_categories (name, sort_order)
                    VALUES (:name, :sort)
                """), {"name": standard_name, "sort": sort_idx})
                sort_idx += 1

            conn.commit()
            print(f"✓ 从旧数据提取 {len(cat_map)} 个分类写入 kp_categories")

        # ============================================================
        # 3. 从旧表提取 distinct model → kp_parts
        # ============================================================
        existing_parts = conn.execute(text("SELECT COUNT(*) FROM kp.kp_parts")).scalar()
        if existing_parts > 0:
            print(f"⚠ kp_parts 已有 {existing_parts} 条，跳过配件迁移")
        else:
            # 获取分类 id 映射（包含合并后的映射）
            cat_rows = conn.execute(text("SELECT id, name FROM kp.kp_categories")).fetchall()
            cat_id_map = {r[1]: r[0] for r in cat_rows}

            # 构建旧分类名 → 新分类 id 的映射（处理合并）
            all_old_cats = conn.execute(text("""
                SELECT DISTINCT TRIM(category) FROM kp.kp_records
                WHERE category IS NOT NULL AND TRIM(category) != ''
            """)).fetchall()

            old_to_new_cat_id = {}
            for (old_cat,) in all_old_cats:
                normalized = old_cat.lower().replace(' ', '')
                for std_name, cat_id in cat_id_map.items():
                    if std_name.lower().replace(' ', '') == normalized:
                        old_to_new_cat_id[old_cat] = cat_id
                        break

            # 提取 distinct model，取最新一条的 category
            models = conn.execute(text("""
                SELECT DISTINCT ON (TRIM(model))
                    TRIM(model) as model,
                    category,
                    note
                FROM kp.kp_records
                WHERE model IS NOT NULL AND TRIM(model) != ''
                ORDER BY TRIM(model), date DESC
            """)).fetchall()

            inserted = 0
            for row in models:
                model_name = row[0]
                old_category = row[1]
                cat_id = old_to_new_cat_id.get(old_category)

                conn.execute(text("""
                    INSERT INTO kp.kp_parts (category_id, name, short_desc)
                    VALUES (:cat_id, :name, :desc)
                """), {
                    "cat_id": cat_id,
                    "name": model_name,
                    "desc": row[2] or None
                })
                inserted += 1

            conn.commit()
            print(f"✓ 从旧数据提取 {inserted} 个配件型号写入 kp_parts")

        # ============================================================
        # 4. 迁移价格历史 kp_records → kp_price_history
        # ============================================================
        existing_history = conn.execute(text("SELECT COUNT(*) FROM kp.kp_price_history")).scalar()
        if existing_history > 0:
            print(f"⚠ kp_price_history 已有 {existing_history} 条，跳过价格迁移")
        else:
            # 构建 model_name → part_id 映射
            parts = conn.execute(text("SELECT id, name FROM kp.kp_parts")).fetchall()
            name_to_part_id = {r[1]: r[0] for r in parts}

            # 迁移所有旧记录
            old_records = conn.execute(text("""
                SELECT TRIM(model), price, currency, date, note
                FROM kp.kp_records
                WHERE model IS NOT NULL AND TRIM(model) != ''
                ORDER BY date
            """)).fetchall()

            migrated = 0
            for rec in old_records:
                model_name = rec[0]
                part_id = name_to_part_id.get(model_name)
                if part_id is None:
                    continue

                # 解析日期
                price_date = None
                if rec[3]:
                    try:
                        price_date = rec[3]  # 已经是 YYYY-MM-DD 字符串
                    except Exception:
                        pass

                conn.execute(text("""
                    INSERT INTO kp.kp_price_history (part_id, price, currency, price_date, note)
                    VALUES (:part_id, :price, :currency, :date, :note)
                """), {
                    "part_id": part_id,
                    "price": rec[1],
                    "currency": rec[2] or 'RMB',
                    "date": price_date,
                    "note": rec[4]
                })
                migrated += 1

            conn.commit()
            print(f"✓ 迁移 {migrated} 条价格记录到 kp_price_history")

        # ============================================================
        # 5. 创建索引
        # ============================================================
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kp_parts_category ON kp.kp_parts(category_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kp_parts_name ON kp.kp_parts(name)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kp_parts_oem_sku ON kp.kp_parts(oem_sku)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kp_part_specs_part ON kp.kp_part_specs(part_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kp_price_history_part ON kp.kp_price_history(part_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kp_price_history_date ON kp.kp_price_history(price_date)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kp_part_compat_part ON kp.kp_part_compat(part_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_kp_part_related_source ON kp.kp_part_related(source_part_id)"))
        conn.commit()
        print("✓ 索引创建完成")

        # ============================================================
        # 6. 验证
        # ============================================================
        counts = {}
        for tbl in ['kp_categories', 'kp_parts', 'kp_part_specs', 'kp_price_history', 'kp_part_compat', 'kp_part_related']:
            c = conn.execute(text(f"SELECT COUNT(*) FROM kp.{tbl}")).scalar()
            counts[tbl] = c

        old_count = conn.execute(text("SELECT COUNT(*) FROM kp.kp_records")).scalar()

        print(f"\n========== 迁移完成 ==========")
        print(f"旧表 kp_records: {old_count} 条（保留备份）")
        for tbl, cnt in counts.items():
            print(f"  kp.{tbl}: {cnt} 条")


def rollback():
    """回滚：删除新表"""
    with engine.connect() as conn:
        for tbl in ['kp_part_related', 'kp_part_compat', 'kp_price_history', 'kp_part_specs', 'kp_parts', 'kp_categories']:
            conn.execute(text(f"DROP TABLE IF EXISTS kp.{tbl} CASCADE"))
        conn.commit()
    print("✓ 已回滚，新表已删除，旧表 kp_records 未受影响")


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'rollback':
        rollback()
    else:
        run_migration()
