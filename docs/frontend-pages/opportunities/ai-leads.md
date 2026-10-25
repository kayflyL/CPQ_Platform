# AI 线索 (AiLeads)

> 最后更新：2026-08-30（新页面：AI 办公室隐藏商机的管理入口 — 列表/查看对话/转正/清理）

## 功能概述

管理 AI 办公室对话中自动登记的隐藏商机（`status='ai_office'`，`opportunity_id='ai-{uuid}'`，`customer_name='{用户名} · {需求摘要}'`）。这类商机**有意**与业务列表隔离（业务列表过滤 `status != 'ai_office'`），本页提供「转正」通道把它们变成真实商机。

### 页面结构

1. **顶栏** — 标题「AI 线索」+ 副标（AI 办公室对话自动登记的商机 · 转正后进入商机列表）+ 搜索（摘要/所属人，防抖）+ 刷新 + 返回商机
2. **列表** `a-table` 服务端分页：
   - 列：☐ 多选 | 需求摘要（snippet + 所属人 + 「7天无动态」stale 标记）| 来源角色（AI 同事显示名，来自 `/api/ai-colleagues/` 名册）| 进度徽章 | 消息数 | 最近活动 | ⋯ 行菜单
   - 行菜单：查看对话 / 转正为商机… / 清理该线索
3. **进度徽章**（后端派生）：
   - `chatting` 对话中（蓝）— 无需求单无 BOM
   - `registered` 已登记需求（金）— 有 OpportunityRequirement
   - `plan` 已出方案（绿）— 有 OpportunityBomScheme
   - `stale` — 无需求单 && 最近活动 ≥7 天
4. **查看对话** — 只读 `a-drawer`（560px），读 `GET /api/assistant/threads/{thread_id}/messages`（limit 200），用户右侧/AI 左侧气泡，AI 名走名册显示名；管理员可跨用户查看（`_authorize_thread_access`）
5. **转正 modal** — 客户名称（必填）+ 业务归属（管理员从 `/api/opportunities/business-options` 选；普通用户固定归属自己，后端强制）。成功后：
   - 有需求单 → 直接进商机列表
   - 无需求单 → warning 提示「需在商机详情页补交后才出现在商机列表」（业务列表 `has_committed_requirement` 过滤）
6. **清理**（单条/批量）— `Modal.confirm` 二次确认后物理级联删除：会话消息 → 需求单 → BOM 方案 → 商机行，**不可恢复**；勾选行 → 底部悬浮批量条

## 前端路由

| 路由 | 组件 | perm |
|------|------|------|
| `/ai-leads` | `views/opportunity/AiLeads.vue` | `page.opportunities` |

入口：商机驾驶舱顶栏 🤖 图标按钮。

## API 端点（opportunities router）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/opportunities/ai-leads` | 列表（全量权限看所有；普通用户按 owner_user_id / sales_person 归属过滤）。返回字段含 thread_id/msg_count/colleague_role_key/has_requirement/has_bom_scheme/progress/stale |
| POST | `/api/opportunities/{opportunity_id}/promote` | 转正：status→active + 补客户名/业务归属；管理员选了业务则同步 owner_user_id |
| POST | `/api/opportunities/ai-leads/purge` | 批量清理（逐条校验 ai_office 身份 + 归属，返回 success/failed 明细） |
| GET | `/api/assistant/threads/{thread_id}/messages` | 只读消息（抽屉用） |
| GET | `/api/ai-colleagues/` | AI 同事名册（role_key → 显示名） |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `opportunities` | `opportunities` | status='ai_office' 的隐藏商机行 |
| `opportunities` | `assistant_threads` / `assistant_messages` | AI 办公室会话与消息（thread.opportunity_id 关联） |
| `opportunities` | `opportunity_requirements` / `opportunity_bom_schemes` | 进度标记数据源 |

## 注意事项

- 路由注册顺序：`/ai-leads` 必须在 `/{opportunity_id}` 通配 GET 之前（FastAPI 路径捕获）。
- 清理是物理删除；曾有一次人工 purge 的备份在 `backend/_purge_ai_opps_backup_20260829_230818.json`。
