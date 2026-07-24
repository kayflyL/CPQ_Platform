"""
迁移脚本 v3：字段管理功能增强
- business_fields 表新增字段：validation_rules, options, dependencies, created_at, updated_at, created_by, updated_by
- 新增 field_references 表（字段引用关系）
- 新增 field_audit_logs 表（审计日志）
- 新增 field_usage_stats 表（使用统计）
"""
import sqlite3
import os
from datetime import datetime

DB_PATH = 'D:\\Quotation_Automation\\Reference\\kp_data.db'


def migrate():
    print(f"数据库路径: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print(f"✗ 数据库不存在: {DB_PATH}")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ==================== 1. 更新 business_fields 表 ====================
    print("\n=== 更新 business_fields 表 ===")
    
    # 获取现有列
    cursor.execute("PRAGMA table_info(business_fields)")
    existing_cols = {row[1] for row in cursor.fetchall()}
    print(f"现有列: {existing_cols}")

    # 新增字段定义
    new_columns = [
        ('validation_rules', 'TEXT DEFAULT NULL'),
        ('options', 'TEXT DEFAULT NULL'),
        ('dependencies', 'TEXT DEFAULT NULL'),
        ('created_at', 'TEXT DEFAULT NULL'),
        ('updated_at', 'TEXT DEFAULT NULL'),
        ('created_by', 'TEXT DEFAULT "system"'),
        ('updated_by', 'TEXT DEFAULT "system"'),
    ]

    added = 0
    for col_name, col_def in new_columns:
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE business_fields ADD COLUMN {col_name} {col_def}")
            print(f"  ✓ 新增列: {col_name}")
            added += 1
        else:
            print(f"  - 列已存在: {col_name}")

    # 为现有记录设置 created_at
    if 'created_at' in [col[1] for col in new_columns]:
        cursor.execute("""
            UPDATE business_fields 
            SET created_at = datetime('now'), updated_at = datetime('now')
            WHERE created_at IS NULL
        """)
        print(f"  ✓ 更新现有记录的 created_at/updated_at")

    # ==================== 2. 创建 field_references 表 ====================
    print("\n=== 创建 field_references 表 ===")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS field_references (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_key TEXT NOT NULL,
            ref_type TEXT NOT NULL,
            ref_id INTEGER NOT NULL,
            ref_name TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (field_key) REFERENCES business_fields(key) ON DELETE CASCADE
        )
    """)
    print("  ✓ field_references 表创建成功")

    # ==================== 3. 创建 field_audit_logs 表 ====================
    print("\n=== 创建 field_audit_logs 表 ===")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS field_audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_key TEXT NOT NULL,
            action TEXT NOT NULL,
            changes TEXT,
            operator TEXT DEFAULT 'system',
            operated_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (field_key) REFERENCES business_fields(key) ON DELETE CASCADE
        )
    """)
    print("  ✓ field_audit_logs 表创建成功")

    # ==================== 4. 创建 field_usage_stats 表 ====================
    print("\n=== 创建 field_usage_stats 表 ===")
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS field_usage_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            field_key TEXT UNIQUE NOT NULL,
            usage_count INTEGER DEFAULT 0,
            last_used_at TEXT,
            FOREIGN KEY (field_key) REFERENCES business_fields(key) ON DELETE CASCADE
        )
    """)
    print("  ✓ field_usage_stats 表创建成功")

    # ==================== 5. 为现有字段创建使用统计记录 ====================
    print("\n=== 初始化使用统计 ===")
    
    cursor.execute("SELECT key FROM business_fields")
    keys = [row[0] for row in cursor.fetchall()]
    
    for key in keys:
        cursor.execute("""
            INSERT OR IGNORE INTO field_usage_stats (field_key, usage_count, last_used_at)
            VALUES (?, 0, NULL)
        """, (key,))
    
    print(f"  ✓ 为 {len(keys)} 个字段初始化使用统计")

    conn.commit()
    conn.close()

    print(f"\n✓ 迁移完成: 新增 {added} 列, 创建 3 个新表")
    return True


if __name__ == '__main__':
    migrate()
