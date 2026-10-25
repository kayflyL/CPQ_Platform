---
name: comment-mention-notify
description: 评论流@提及定调:feed发评论唯一入口后端解析、comment_mention通知全链路、旧/api/comments已删;碰评论流/提及/企微通知先看
metadata:
  node_type: memory
  type: project
  originSessionId: bd032897-de27-4e43-95a6-c6341c37ec0d
  modified: 2026-10-15T14:58:31.712Z
---

评论流 @提及（2026-10-15 实装）定调：

- **权威解析点唯一**：feed `post_message` → `_notify_mentions`（[feed.py]）对照全员名册精确匹配 `@名字`，最长名字优先（防"张三"吃"张三丰"）；解析器在 `backend/app/services/mention.py` 纯函数。前端 @ 浮层只是输入辅助，不做前端解析。
- 通知类型 `comment_mention` → 「待办」分组，站内铃铛/通知中心 + 企微外推（`_relay_wecom` 有专属分支：群播报 @被提人 + mentioned_list 真高亮）。
- **脱敏分支**：被提人无商机查看权 → 标题去客户名、无正文、不带 opportunity_id 跳转（两条 notify_users 调用分流）。
- 不结构化存提及——feed 正文存 `@名字` 纯文本即事实，渲染时按名册切段高亮（ApprovalFlowPanel `mentionSegments`），零迁移。
- 旧 `/api/comments` 路由、`comment_repo`、`public.comments` 表已删（迁移 `migrations/drop_public_comments.sql` 待手工执行）；评论真身= `opportunities.opportunity_messages`(kind=comment)。

**Why**: 曾评估过做内置用户IM被否（团队真实IM是企微，通知已外推），@提及是把"沟通指针"留在系统里的最小方案。

**How to apply**: 改评论/提及/通知先看 `_notify_mentions` 与 [[wecom-notify-channel]]（本地 wecom webhook 是启用状态）；E2E 测试教训见 [[e2e-browser-live-write-gotcha]]。测试用 `backend/tests/test_mention.py`（单测21）+ `test_feed_mention_e2e.py`（集成3，TestClient+stub企微+scratch数据物理清理）。
