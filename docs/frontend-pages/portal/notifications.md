# 通知系统（Notifications）

> 最后更新：2026-09-19（通知中心手机版：行操作常显 + 侧栏下移）

## 功能概述

站内通知子系统（2026-09-15 新增，同日升级为「富 popover + 独立全量页」双层通知中心）：机会流转事件 → 落库 + WS 实时推 → 全站顶栏铃铛（富 popover）+ `/notifications` 全量页。**不做**邮件/企微等站外推送、通知偏好设置。

挂点覆盖四步流程关键事件：

| 事件 type | 触发点 | 收件人 |
|-----------|--------|--------|
| `task_assigned` | 节点推进/指派（initiate、方案/成本提交、assign/transfer） | 新节点处理人 |
| `stage_advanced` | 各阶段提交成功 | 商机 owner |
| `card_returned` | 流转卡退回 | 被退回阶段处理人（body=退回原因） |
| `withdraw_requested` / `withdraw_approved` / `withdraw_rejected` | 撤回申请/审批 | 卡持有者 / 申请人 |
| `quote_submitted` | 报价单发送定稿 | 商机 owner |
| `pricing_approval_requested` | 发送撞低毛利红线、自动建审批单 | 全体有 `action.flow.approve.pricing` 的用户 |
| `pricing_approval_decided` | 总监批准/驳回审批单 | 申请报价员（body=审批意见） |

## 类型色标（SSOT）

`components/notifications/notificationMeta.ts`：type → {分组、图标、语义色}，铃铛与全量页共用。**筛选分组三档**：待办(蓝：任务/退回)/审批(琥珀：撤回+毛利审批全周期)/动态(绿：阶段/报价)——条目仍保留逐类型图标+标签（任务、退回、撤回…）便于辨识，收敛的只是筛选 chips。

色值 SSOT = `styles/tokens.css` 的 `--cpq-notif-{blue|green|red|amber|violet|cyan}(-bg)?`（双主题：暗底前景提亮、tint 加浓）；大面积警示面用 `--cpq-warn-surface/-border`（QuoteWorkbench 审批裁决条）。通知组件**禁止硬编码色值**。

## 铃铛富 popover（全站）

`NotificationBell.vue` 挂 `DefaultLayout` 顶栏（全页面可见）：

- 铃铛 hover 摇铃动画；a-badge 未读数
- 372px 面板：头部「通知 + 未读/全部 tab + 全部已读」→ 滚动列表（max 336px）→ 底部「清空已读 | 查看全部」
- 条目：类型图标 + 标题 + 摘要两行截断 + 相对时间（`utils/relativeTime.ts`：刚刚/N分钟前/昨天 HH:mm）+ 未读圆点
- hover 浮出单条操作：未读「标已读」/ 已读「删除」；点击条目标已读 + 跳 `/opportunities/{opp_id}`

## 通知中心全量页（/notifications）

`views/notifications/NotificationCenter.vue`（铃铛「查看全部」落地页）：

- 页头：总数/未读数 + 批量「清空已读 / 全部标为已读」
- 筛选：全部/未读 toggle + 三个分组 chips（待办/审批/动态，带分组未读数，来自 unread-count 的 by_type 求和）
- 列表：按天分组（今天/昨天/N 年 N 月），行内 hover 操作（标已读/删除/进入商机），antd 分页（20/页）
- 列表/筛选/分页自持状态走 REST；未读数与 WS 实时态复用 `useNotifications` 单例

## 前端链路

- `useNotifications`（composable，模块级单例）：WS 为主（`/api/notifications/ws`，token 鉴权 + 心跳 + 指数退避重连，上限 15s），连上先收 `unread_count` 快照、此后收 `notification` 增量；维护 `unreadCount` + `unreadByType`；暴露 markRead/markAllRead/removeOne/clearRead。
- `api/notifications.ts`：list / unreadCount / unreadStats / markRead / markAllRead / remove / clearRead。

## API

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/notifications?page=&page_size=&unread_only=&types=a,b` | 通知列表（分页 + 未读过滤 + 类型过滤） |
| GET | `/api/notifications/unread-count` | `{count, by_type}`（未读总数 + 按类型未读数） |
| POST | `/api/notifications/{id}/read` | 单条已读 |
| POST | `/api/notifications/read-all` | 全部已读 |
| DELETE | `/api/notifications/{id}` | 单条删除（仅本人的通知） |
| POST | `/api/notifications/clear-read` | 清空已读（删除全部已读通知） |
| WS | `/api/notifications/ws` | 实时推送（`unread_count` / `notification` 两类事件） |

## 后端

- 表：`opportunities.notifications`（notification_id / user_id / type / title / body / opportunity_id(跳转) / payload JSON / read_at / created_at），repo = `NotificationRepository`。
- 推送 helper：`notify_users(user_ids, type, title, body=…, opportunity_id=…, payload=…, exclude_user_id=…)` —— 落库+WS 推送，收件人去重、排除操作者本人、**永不抛错**（通知失败不影响业务主流程）。
- 线程桥接：同步端点（threadpool）→ WS（事件循环）经 `run_coroutine_threadsafe` + 启动时 `bind_loop`。

### 通知中心手机版（≤768px，2026-09-19）

页面 padding 12px；头部折行后「清空已读 / 全部标为已读」两按钮占满整行；通知行改为可折行布局——时间与操作按钮移到正文下方整行（左侧与正文对齐）。**关键：`.nc-acts` 桌面端 hover 才显示，触屏无 hover，手机端强制常显。**
