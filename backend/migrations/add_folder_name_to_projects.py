"""
数据库迁移脚本：为 projects 表添加 folder_name 字段
"""
import sqlite3
import os

# 数据库路径 - projects 数据库
db_path = r"D:\Quotation_Automation\Reference\projects.db"

def migrate():
    """执行迁移"""
    print(f"数据库路径: {db_path}")
    
    if not os.path.exists(db_path):
        print(f"❌ 数据库文件不存在: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 检查字段是否已存在
        cursor.execute("PRAGMA table_info(projects)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "folder_name" in columns:
            print("✅ folder_name 字段已存在，无需迁移")
            return True
        
        # 添加 folder_name 字段
        cursor.execute("""
            ALTER TABLE projects 
            ADD COLUMN folder_name TEXT DEFAULT NULL
        """)
        
        conn.commit()
        print("✅ 成功添加 folder_name 字段")
        
        # 验证
        cursor.execute("PRAGMA table_info(projects)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"当前字段: {', '.join(columns)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 迁移失败: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = migrate()
    exit(0 if success else 1)
