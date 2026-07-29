# 回收站 (RecycleBin)

## 功能概述

管理已删除的商机和报价单，支持恢复或永久删除。

### 核心功能
1. **商机回收** — 已删除商机列表：
   - 恢复商机（回到商机列表）
   - 永久删除（不可恢复）
   - 批量操作（选择复选框）
2. **报价单回收** — 已删除报价单列表：
   - 恢复报价单
   - 永久删除
   - 批量操作

## 前端路由

| 路由 | 组件 |
|------|------|
| `/recycle-bin` | `views/opportunity/RecycleBin.vue` |

## API 端点

### 商机回收
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/opportunities/list?include_deleted=true` | `projectApi.listDeleted` | 获取已删除商机 |
| POST | `/api/opportunities/{id}/restore` | `projectApi.restore` | 恢复商机 |
| POST | `/api/opportunities/batch-restore` | `projectApi.batchRestore` | 批量恢复商机 |
| POST | `/api/opportunities/batch-permanent-delete` | `projectApi.batchPermanentDelete` | 批量永久删除商机 |

### 报价单回收
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/quotations?status=deleted` | `quotationApi.list` | 获取已删除报价单 |
| POST | `/api/quotations/batch-restore` | `quotationApi.batchRestore` | 批量恢复报价单 |
| POST | `/api/quotations/batch-permanent-delete` | `quotationApi.batchPermanentDelete` | 批量永久删除报价单 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `opportunities` | `opportunities` | status='deleted' 的商机 |
| `opportunities` | `quotations` | status='deleted' 的报价单 |
