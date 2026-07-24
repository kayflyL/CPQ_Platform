"""
迁移脚本：为 quotations 表添加 config_quantities 字段
"""
import sqlite3
import os

DB_PATH = r"D:\Quotation_Automation\Reference\projects.db"

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"❌ 数据库不存在: {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 检查字段是否已存在
    cursor.execute("PRAGMA table_info(quotations)")
    columns = [row[1] for row in cursor.fetchall()]
    
    if 'config_quantities' in columns:
        print("✓ config_quantities 字段已存在，无需迁移")
        conn.close()
        return True
    
    print("📋 步骤 1: 添加 config_quantities 字段到 quotations 表...")
    cursor.execute("""
        ALTER TABLE quotations 
        ADD COLUMN config_quantities TEXT
    """)
    
    conn.commit()
    print("  ✓ 字段添加成功")
    
    # 验证
    cursor.execute("PRAGMA table_info(quotations)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'config_quantities' in columns:
        print("✓ 迁移完成，字段已验证")
    else:
        print("❌ 迁移失败，字段未找到")
        conn.close()
        return False
    
    conn.close()
    return True

if __name__ == "__main__":
    print(f"🔧 开始迁移: {DB_PATH}")
    if migrate():
        print("✅ 迁移成功完成")
    else:
        print("❌ 迁移失败")
        exit(1)
