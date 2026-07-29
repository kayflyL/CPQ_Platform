# 服务器配置门户 (ServerConfig)

## 功能概述

服务器模块面向销售/客户的产品入口：选服务器类型 → 跳机型目录 → 看产品详情 → 进配置向导。
管理维护功能已拆到独立的管理后台（[ServerAdminPage](server-admin.md)，`/servers/admin`）。

### 核心功能
- 服务器类型卡片选择（ModelCatalog）→ 跳机型目录 `/servers/types/:typeId`

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers` | `views/ServerConfig.vue` |

## 子页面导航（配置流程）

| 步骤 | 路由 |
|------|------|
| ① 选服务器类型 | `/servers/types/:typeId`（机型目录） |
| ② 看机型产品详情 | `/servers/models/:modelId`（[ModelDetailPage](model-detail.md)） |
| ③ 配置这台服务器 | `/servers/config/:modelId`（配置向导） |

## 关键组件

| 组件 | 用途 |
|------|------|
| `ModelCatalog.vue` | 服务器类型卡片列表（配置门户主体） |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_types` | 服务器类型 |
