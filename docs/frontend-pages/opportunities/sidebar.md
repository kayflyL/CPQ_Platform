# 商机协作流 (OpportunitySidebar + OpportunityFeed + OpportunityFiles)

## 功能概述

商机详情页右侧抽屉，提供团队协作功能：消息评论 + 文件管理 + 在线状态。

### 核心功能

#### OpportunitySidebar.vue（抽屉容器）
- Teleported to body 的抽屉包装器
- 管理覆盖层可见性状态
- 传递给子组件 OpportunityFeed

#### OpportunityFeed.vue（实时协作流）
- 消息时间线展示
- 文件附件展示
- 在线状态指示器（谁在线）
- 打字指示器
- 消息编辑器/发送器
- WebSocket 实时推送

#### OpportunityFiles.vue（文件管理器）
- 拖拽上传文件
- 文件列表展示
- 文件操作：打开、重命名、删除、下载
- Modal 上传 UI
- 使用 multipart/form-data

## 组件位置

- `components/quote/OpportunitySidebar.vue` — 抽屉容器
- `components/quote/OpportunityFeed.vue` — 实时协作流
- `components/quote/OpportunityFiles.vue` — 文件管理器

嵌入在 `OpportunityDetail.vue` 中，通过 `v-model:show-sidebar` 控制显隐。

## API 端点

### 消息/评论
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/feed/{opportunity_id}/messages` | `feedApi.messages.list` | 获取消息列表 |
| POST | `/api/feed/{opportunity_id}/messages` | `feedApi.messages.create` | 发送消息（multipart，含附件） |
| DELETE | `/api/feed/messages/{message_id}` | `feedApi.messages.remove` | 软删除消息 |
| GET | `/api/comments/{opportunity_id}` | — | 获取评论列表 |
| POST | `/api/comments/{opportunity_id}` | — | 发表评论 |
| GET | `/api/comments/{opportunity_id}/count` | — | 获取评论数 |
| DELETE | `/api/comments/{comment_id}` | — | 删除评论 |

### 文件/附件
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/feed/{opportunity_id}/attachments` | `feedApi.attachments.list` | 获取附件列表 |
| POST | `/api/feed/{opportunity_id}/attachments` | `feedApi.attachments.upload` | 上传附件（multipart） |
| GET | `/api/feed/attachments/{id}/download` | `feedApi.attachments.downloadUrl` | 下载附件（URL） |
| GET | `/api/feed/attachments/{id}/versions` | `feedApi.attachments.versions` | 获取版本列表 |
| POST | `/api/feed/attachments/{id}/version` | `feedApi.attachments.addVersion` | 上传新版本（multipart） |
| DELETE | `/api/feed/attachments/{id}` | `feedApi.attachments.remove` | 软删除附件 |

### 用户/在线状态
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/feed/users` | `feedApi.users.list` | 获取用户列表 |
| POST | `/api/feed/users` | `feedApi.users.ensure` | 按名称获取或创建用户 |
| WebSocket | `/api/feed/ws/{opportunity_id}` | — | 实时推送（消息、在线状态） |

### 商机文件（OpportunityFiles 使用）
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/opportunities/{id}/files` | 获取文件列表 |
| POST | `/api/opportunities/{id}/files/upload` | 上传文件 |
| GET | `/api/opportunities/{id}/files/download` | 下载文件 |
| PUT | `/api/opportunities/{id}/files/rename` | 重命名文件 |
| DELETE | `/api/opportunities/{id}/files` | 删除文件 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `public` | `comments` | 商机评论/批注 |
| `opportunities` | `opportunity_attachments` | Feed 文件附件元数据（`FeedAttachment`） |
| (in-memory/Redis) | presence state | 在线状态 |

## 文件存储

物理文件由 `FeedAttachment` 表索引，落盘在 `backend/storage/opportunities/{opportunity_id}/{object_id}{ext}`（`storage_key` 为 UUID 派生，不依赖业务字段）。下载走 API 代理，非扫盘。
