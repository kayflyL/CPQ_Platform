-- 删除旧评论系统 public.comments 表。
-- 评论真身自 feed 上线起即 feed_messages(kind=comment)；本表前端/后端零引用
-- （2026-10-15 评论流@提及改造时删除了 /api/comments 路由与 comment_repo，
--  main.py 路由注册与 startup ensure_comments_table 同步移除）。
-- 手工执行一次即可，幂等。
DROP TABLE IF EXISTS public.comments;
