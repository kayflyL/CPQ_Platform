"""
数据迁移脚本：projects 表字段迁移到 quotations 表

迁移内容：
- model_name, platform_type, chassis_form, fae, sales_person, l6_spec
- 新增 total_price, profit_margin 字段（从 project_items 计算）

执行前请备份数据库！
"""

import sqlite3
import sys

DB_PATH = 'D:/Quotation_Automation/Reference/projects.db'


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("🔄 开始数据迁移...")
    print(f"数据库: {DB_PATH}\n")
    
    # 1. 给 quotations 表添加新字段
    print("📋 步骤 1: 给 quotations 表添加新字段...")
    
    new_columns = [
        ('model_name', 'TEXT'),
        ('platform_type', 'TEXT'),
        ('chassis_form', 'TEXT'),
        ('fae', 'TEXT'),
        ('sales_person', 'TEXT'),
        ('l6_spec', 'TEXT'),
        ('total_price', 'REAL DEFAULT 0'),
        ('profit_margin', 'REAL DEFAULT 0'),
    ]
    
    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE quotations ADD COLUMN {col_name} {col_type}")
            print(f"  ✓ 添加字段: {col_name}")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print(f"  ⚠ 字段已存在: {col_name}")
            else:
                raise
    
    conn.commit()
    print()
    
    # 2. 从 projects 复制字段到 quotations
    print("📋 步骤 2: 从 projects 复制字段到 quotations...")
    
    cursor.execute("""
        UPDATE quotations
        SET 
            model_name = (SELECT model_name FROM projects WHERE projects.project_id = quotations.project_id),
            platform_type = (SELECT platform_type FROM projects WHERE projects.project_id = quotations.project_id),
            chassis_form = (SELECT chassis_form FROM projects WHERE projects.project_id = quotations.project_id),
            fae = (SELECT fae FROM projects WHERE projects.project_id = quotations.project_id),
            sales_person = (SELECT sales_person FROM projects WHERE projects.project_id = quotations.project_id),
            l6_spec = (SELECT l6_spec FROM projects WHERE projects.project_id = quotations.project_id)
    """)
    
    updated_count = cursor.rowcount
    conn.commit()
    print(f"  ✓ 更新了 {updated_count} 条 quotations 记录\n")
    
    # 3. 计算 total_price 和 profit_margin
    print("📋 步骤 3: 计算 total_price 和 profit_margin...")
    
    # 检查 project_items 表是否存在
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_items'")
    if not cursor.fetchone():
        print("  ⚠ project_items 表不存在，跳过计算")
    else:
        # 计算每个 quotation 的 total_price 和 profit_margin
        cursor.execute("""
            UPDATE quotations
            SET 
                total_price = (
                    SELECT COALESCE(SUM(final_price * qty), 0)
                    FROM project_items
                    WHERE project_items.quotation_id = quotations.quotation_id
                ),
                profit_margin = (
                    SELECT CASE 
                        WHEN SUM(base_price * qty) > 0 
                        THEN ROUND((SUM(final_price * qty) - SUM(base_price * qty)) * 100.0 / SUM(base_price * qty), 2)
                        ELSE 0 
                    END
                    FROM project_items
                    WHERE project_items.quotation_id = quotations.quotation_id
                )
        """)
        
        calculated_count = cursor.rowcount
        conn.commit()
        print(f"  ✓ 计算了 {calculated_count} 条 quotations 的价格和利润率\n")
    
    # 4. 验证结果
    print("📋 步骤 4: 验证迁移结果...")
    
    cursor.execute("""
        SELECT q.quotation_id, q.model_name, q.platform_type, q.total_price, q.profit_margin
        FROM quotations q
        WHERE q.status = 'active'
        LIMIT 5
    """)
    
    results = cursor.fetchall()
    if results:
        print("  样本数据:")
        for row in results:
            print(f"    {row[0]}: model={row[1]}, platform={row[2]}, price={row[3]}, margin={row[4]}%")
    else:
        print("  ⚠ 没有 active 状态的 quotations")
    
    conn.close()
    print("\n✅ 数据迁移完成！")


if __name__ == '__main__':
    if '--dry-run' in sys.argv:
        print("🔍 Dry run 模式，只检查不执行\n")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 检查 projects 表数据
        cursor.execute("SELECT COUNT(*) FROM projects")
        print(f"projects 表记录数: {cursor.fetchone()[0]}")
        
        cursor.execute("SELECT COUNT(*) FROM quotations")
        print(f"quotations 表记录数: {cursor.fetchone()[0]}")
        
        cursor.execute("""
            SELECT p.project_id, p.model_name, p.platform_type, COUNT(q.quotation_id) as quo_count
            FROM projects p
            LEFT JOIN quotations q ON p.project_id = q.project_id
            GROUP BY p.project_id
            LIMIT 5
        """)
        print("\n项目与报价单对应关系:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: model={row[1]}, platform={row[2]}, quotations={row[3]}")
        
        conn.close()
    else:
        migrate()
