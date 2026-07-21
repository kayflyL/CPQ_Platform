"""
评论数据访问层
PostgreSQL: public schema, comments table
"""
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy import text
from app.models.base import public_engine


class CommentRepo:
    """评论 Repository - PostgreSQL public schema"""

    def add_comment(self, opportunity_id: str, content: str, user_name: str = "匿名") -> int:
        """添加评论，返回评论 ID"""
        q = """
            INSERT INTO public.comments (opportunity_id, user_name, content, created_at)
            VALUES (:opp_id, :user, :content, :created)
            RETURNING id
        """
        with public_engine.begin() as conn:
            result = conn.execute(text(q), {
                "opp_id": opportunity_id,
                "user": user_name,
                "content": content,
                "created": datetime.now().isoformat()
            })
            return result.scalar()

    def get_comments(self, opportunity_id: str) -> List[Dict]:
        """获取商机的所有评论"""
        q = """
            SELECT id, opportunity_id, user_name, content, created_at
            FROM public.comments
            WHERE opportunity_id = :opp_id
            ORDER BY created_at ASC
        """
        with public_engine.connect() as conn:
            rows = conn.execute(text(q), {"opp_id": opportunity_id}).mappings().all()
        return [dict(row) for row in rows]

    def get_comment_count(self, opportunity_id: str) -> int:
        """获取商机评论数"""
        q = """
            SELECT COUNT(*) as count
            FROM public.comments
            WHERE opportunity_id = :opp_id
        """
        with public_engine.connect() as conn:
            result = conn.execute(text(q), {"opp_id": opportunity_id}).scalar()
        return result or 0

    def delete_comment(self, comment_id: int) -> bool:
        """删除评论"""
        q = "DELETE FROM public.comments WHERE id = :cid"
        with public_engine.begin() as conn:
            result = conn.execute(text(q), {"cid": comment_id})
        return result.rowcount > 0

    def delete_opportunity_comments(self, opportunity_id: str) -> int:
        """删除商机的所有评论（商机删除时调用）"""
        q = "DELETE FROM public.comments WHERE opportunity_id = :opp_id"
        with public_engine.begin() as conn:
            result = conn.execute(text(q), {"opp_id": opportunity_id})
        return result.rowcount


def ensure_comments_table():
    """幂等创建 public.comments 表（raw SQL 表，无 ORM 模型，startup 时调用）"""
    with public_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS public.comments (
                id SERIAL PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                user_name TEXT,
                content TEXT,
                created_at TEXT
            )
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_comments_opportunity_id
            ON public.comments(opportunity_id)
        """))


# 单例
comment_repo = CommentRepo()
