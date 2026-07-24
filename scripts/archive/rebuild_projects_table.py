"""
数据库结构改造：删除 projects 表的冗余字段

这些字段已迁移到 quotations 表：
- model_name, platform_type, chassis_form, fae, sales_person, l6_spec

执行前请备份数据库！
"""

import sqlite3
import shutil
import os
from datetime import datetime

DB_PATH = os.getenv('DATA_PATH', r'D:\Quotation_Automation') + r'\Reference\projects.db'


def backup_database():
    """备份数据库"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f"{DB_PATH}.backup_{timestamp}"
    shutil.copy2(DB_PATH, backup_path)
    print(f"✓ 数据库已备份到: {backup_path}\n")
    return backup_path


def rebuild_projects_table():
    """重建 projects 表，删除冗余字段（事务保护，失败自动回滚）"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("🔄 开始重建 projects 表...")

    try:
        # 1. 创建新表（只保留必要字段）
        print("\n📋 步骤 1: 创建新 projects 表...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects_new (
                project_id TEXT PRIMARY KEY,
                project_name TEXT,
                customer_name TEXT,
                status TEXT DEFAULT 'active',
                folder_name TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)
        print("  ✓ 新表结构已创建")

        # 2. 复制数据
        print("\n📋 步骤 2: 复制数据到新表...")
        cursor.execute("""
            INSERT INTO projects_new (project_id, project_name, customer_name, status, folder_name, created_at, updated_at)
            SELECT project_id, project_name, customer_name, status, folder_name, created_at, updated_at
            FROM projects
        """)
        copied_count = cursor.rowcount
        print(f"  ✓ 复制了 {copied_count} 条记录")

        # 3. 删除旧表 + 重命名（原子操作，在同一个事务中）
        print("\n📋 步骤 3: 切换旧表 → 新表...")
        cursor.execute("DROP TABLE projects")
        cursor.execute("ALTER TABLE projects_new RENAME TO projects")
        print("  ✓ 切换完成")

        conn.commit()
        print("\n✅ 事务已提交")

    except Exception as e:
        conn.rollback()
        # Clean up the temp table if it exists
        try:
            cursor.execute("DROP TABLE IF EXISTS projects_new")
            conn.commit()
        except Exception:
            pass
        print(f"\n❌ 重建失败，已回滚: {e}")
        raise
    
    # 5. 验证结果
    print("\n📋 步骤 5: 验证新表结构...")
    cursor.execute("PRAGMA table_info(projects)")
    columns = cursor.fetchall()
    print("  projects 表现有字段:")
    for col in columns:
        print(f"    - {col[1]} ({col[2]})")
    
    # 6. 验证数据
    print("\n📋 步骤 6: 验证数据完整性...")
    cursor.execute("SELECT COUNT(*) FROM projects")
    count = cursor.fetchone()[0]
    print(f"  ✓ projects 表记录数: {count}")
    
    cursor.execute("""
        SELECT project_id, project_name, customer_name, status
        FROM projects
        LIMIT 3
    """)
    print("\n  样本数据:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: name={row[1]}, customer={row[2]}, status={row[3]}")
    
    # 7. 验证 quotations 关联
    print("\n📋 步骤 7: 验证 quotations 关联...")
    cursor.execute("""
        SELECT p.project_id, p.project_name, COUNT(q.quotation_id) as quo_count
        FROM projects p
        LEFT JOIN quotations q ON p.project_id = q.project_id
        GROUP BY p.project_id
        LIMIT 5
    """)
    print("  项目与报价单关联:")
    for row in cursor.fetchall():
        print(f"    {row[0]}: {row[1]} -> {row[2]}个报价单")
    
    conn.close()
    print("\n✅ projects 表结构改造完成！")
    print("\n已删除的字段:")
    print("  - model_name (已迁移到 quotations)")
    print("  - platform_type (已迁移到 quotations)")
    print("  - chassis_form (已迁移到 quotations)")
    print("  - fae (已迁移到 quotations)")
    print("  - sales_person (已迁移到 quotations)")
    print("  - l6_spec (已迁移到 quotations)")


if __name__ == '__main__':
    print("=" * 60)
    print("数据库结构改造：删除 projects 表冗余字段")
    print("=" * 60)
    print()
    
    # 备份
    backup_path = backup_database()
    
    # 重建表
    rebuild_projects_table()
    
    print("\n" + "=" * 60)
    print("如需回滚，请恢复备份文件:")
    print(f"  {backup_path}")
    print("=" * 60)
