"""
数据库迁移脚本：创建 project_files 表
"""
import sqlite3
from pathlib import Path


def migrate():
    """创建 project_files 表"""
    # 数据库文件在项目根目录的 data 文件夹
    db_path = Path("../data/cpq_platform.db")
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return False
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查表是否已存在
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name='project_files'
    """)
    
    if cursor.fetchone():
        print("✅ project_files 表已存在，无需迁移")
        conn.close()
        return True
    
    # 创建 project_files 表
    cursor.execute("""
        CREATE TABLE project_files (
            file_id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            file_type TEXT NOT NULL,
            original_name TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            created_by TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(project_id)
        )
    """)
    
    # 创建索引
    cursor.execute("""
        CREATE INDEX idx_project_files_project_id 
        ON project_files(project_id)
    """)
    
    cursor.execute("""
        CREATE INDEX idx_project_files_file_type 
        ON project_files(file_type)
    """)
    
    conn.commit()
    conn.close()
    
    print("✅ 成功创建 project_files 表")
    return True


if __name__ == "__main__":
    migrate()
