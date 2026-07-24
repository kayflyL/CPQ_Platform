"""
数据库迁移脚本：projects.db → opportunities.db
重命名数据库文件和表名
"""
import sqlite3
import os
import shutil
from datetime import datetime

# 数据目录
DATA_DIR = r"D:\Quotation_Automation\Reference"

# 文件路径
OLD_DB = os.path.join(DATA_DIR, "projects.db")
NEW_DB = os.path.join(DATA_DIR, "opportunities.db")

def migrate_database():
    """执行数据库迁移"""
    print("=" * 60)
    print("数据库迁移：projects.db → opportunities.db")
    print("=" * 60)
    
    # 检查旧数据库是否存在
    if not os.path.exists(OLD_DB):
        print(f"❌ 错误：旧数据库不存在 {OLD_DB}")
        return False
    
    # 检查新数据库是否已存在
    if os.path.exists(NEW_DB):
        print(f"⚠️  警告：新数据库已存在 {NEW_DB}")
        print("   请先备份或删除旧数据库")
        return False
    
    # 备份旧数据库
    backup_file = f"{OLD_DB}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n1. 备份旧数据库: {backup_file}")
    shutil.copy2(OLD_DB, backup_file)
    print("   ✓ 备份完成")
    
    # 复制并重命名数据库文件
    print(f"\n2. 复制数据库文件")
    print(f"   源: {OLD_DB}")
    print(f"   目标: {NEW_DB}")
    shutil.copy2(OLD_DB, NEW_DB)
    print("   ✓ 复制完成")
    
    # 重命名表
    print(f"\n3. 重命名数据库表")
    conn = sqlite3.connect(NEW_DB)
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"   当前表: {[t[0] for t in tables]}")
    
    # 重命名表
    renames = [
        ("projects", "opportunities"),
        ("project_files", "opportunity_files"),
        ("project_items", "opportunity_items"),
    ]
    
    for old_table, new_table in renames:
        try:
            # 检查表是否存在
            cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{old_table}';")
            if cursor.fetchone():
                cursor.execute(f"ALTER TABLE {old_table} RENAME TO {new_table};")
                print(f"   ✓ {old_table} → {new_table}")
            else:
                print(f"   ⚠️  表 {old_table} 不存在，跳过")
        except Exception as e:
            print(f"   ❌ 重命名 {old_table} 失败: {e}")
            conn.rollback()
            conn.close()
            return False
    
    # 重命名列（如果有 project_id 列）
    print(f"\n4. 重命名列名")
    
    # opportunities 表
    try:
        cursor.execute("PRAGMA table_info(opportunities);")
        columns = [row[1] for row in cursor.fetchall()]
        if 'project_id' in columns:
            cursor.execute("ALTER TABLE opportunities RENAME COLUMN project_id TO opportunity_id;")
            print("   ✓ opportunities.project_id → opportunity_id")
        if 'project_name' in columns:
            cursor.execute("ALTER TABLE opportunities RENAME COLUMN project_name TO opportunity_name;")
            print("   ✓ opportunities.project_name → opportunity_name")
    except Exception as e:
        print(f"   ⚠️  重命名 opportunities 列失败: {e}")
    
    # quotations 表
    try:
        cursor.execute("PRAGMA table_info(quotations);")
        columns = [row[1] for row in cursor.fetchall()]
        if 'project_id' in columns:
            cursor.execute("ALTER TABLE quotations RENAME COLUMN project_id TO opportunity_id;")
            print("   ✓ quotations.project_id → opportunity_id")
    except Exception as e:
        print(f"   ⚠️  重命名 quotations 列失败: {e}")
    
    # opportunity_files 表
    try:
        cursor.execute("PRAGMA table_info(opportunity_files);")
        columns = [row[1] for row in cursor.fetchall()]
        if 'project_id' in columns:
            cursor.execute("ALTER TABLE opportunity_files RENAME COLUMN project_id TO opportunity_id;")
            print("   ✓ opportunity_files.project_id → opportunity_id")
    except Exception as e:
        print(f"   ⚠️  重命名 opportunity_files 列失败: {e}")
    
    # 重命名索引
    print(f"\n5. 重命名索引")
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE '%project%';")
        indexes = cursor.fetchall()
        for idx in indexes:
            old_name = idx[0]
            new_name = old_name.replace('project', 'opportunity')
            cursor.execute(f"ALTER INDEX {old_name} RENAME TO {new_name};")
            print(f"   ✓ {old_name} → {new_name}")
    except Exception as e:
        print(f"   ⚠️  重命名索引失败: {e}")
    
    conn.commit()
    conn.close()
    print("   ✓ 所有更改已提交")
    
    # 删除旧数据库
    print(f"\n6. 删除旧数据库文件")
    os.remove(OLD_DB)
    print(f"   ✓ 已删除 {OLD_DB}")
    
    print("\n" + "=" * 60)
    print("✓ 数据库迁移完成！")
    print("=" * 60)
    print(f"\n新数据库位置: {NEW_DB}")
    print(f"备份文件位置: {backup_file}")
    print("\n请验证应用程序是否正常工作。")
    
    return True

if __name__ == "__main__":
    success = migrate_database()
    exit(0 if success else 1)
