"""
评论数据访问层
独立库：D:\Quotation_Automation\Reference\comments.db
"""
import sqlite3
from typing import List, Dict, Optional
from datetime import datetime
from app.core.config import get_settings
import os


class CommentRepo:
    """评论 Repository - 独立 SQLite 库"""
    
    def __init__(self):
        settings = get_settings()
        self.db_path = os.path.join(settings.DATA_PATH, "Reference", "comments.db")
        self._ensure_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _ensure_db(self):
        """确保数据库和表存在"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                opportunity_id TEXT NOT NULL,
                user_name TEXT DEFAULT '匿名',
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_opportunity_id 
            ON comments(opportunity_id)
        """)
        
        conn.commit()
        conn.close()
    
    def add_comment(self, opportunity_id: str, content: str, user_name: str = "匿名") -> int:
        """添加评论，返回评论 ID"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO comments (opportunity_id, user_name, content, created_at)
            VALUES (?, ?, ?, ?)
        """, (opportunity_id, user_name, content, datetime.now().isoformat()))
        
        comment_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return comment_id
    
    def get_comments(self, opportunity_id: str) -> List[Dict]:
        """获取商机的所有评论"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, opportunity_id, user_name, content, created_at
            FROM comments
            WHERE opportunity_id = ?
            ORDER BY created_at ASC
        """, (opportunity_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_comment_count(self, opportunity_id: str) -> int:
        """获取商机评论数"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM comments
            WHERE opportunity_id = ?
        """, (opportunity_id,))
        
        result = cursor.fetchone()
        conn.close()
        
        return result["count"] if result else 0
    
    def delete_comment(self, comment_id: int) -> bool:
        """删除评论"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM comments WHERE id = ?
        """, (comment_id,))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected > 0
    
    def delete_opportunity_comments(self, opportunity_id: str) -> int:
        """删除商机的所有评论（商机删除时调用）"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM comments WHERE opportunity_id = ?
        """, (opportunity_id,))
        
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return affected


# 单例
comment_repo = CommentRepo()
