# 服务器管理后台 (ServerAdminPage)

> 最后更新：2026-08-02

## 功能概述

服务器模块面向管理员的维护后台，四个 Tab 切换：机型管理 / 产品系列 / 基准配置 / 料号库。（配件适配 Tab 已于 2026-08-03 移除——specs.chassis 声明无装配消费，纯参考冗余）
从配置门户 `/servers` 拆出（**配置 = 面向客户展示，管理 = 内部维护**）。

> 菜单入口：2026-08-01 由「服务器」子菜单迁入「设置 ▸ 服务器管理」（路由 `/servers/admin` 不变）。顶层「服务器」菜单现直达产品配置门户。

### 核心功能
- 四 Tab（adminTab，默认机型管理）：机型管理 / 产品系列 / 基准配置 / 料号库
- 子页（机型/基准编辑器）保存后带 `?refresh=models` 或 `?refresh=base-config` 回来时，自动切到对应 Tab
- 各 Tab 的详细功能 / API / 数据库表见 [admin-tabs.md](admin-tabs.md)

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/admin` | `views/ServerAdminPage.vue` |

## 子页面导航（编辑器）

| 操作 | 跳转 |
|------|------|
| 机型管理：新建/编辑机型 | `/servers/models/new`、`/servers/models/:id/edit`（[ModelEditorPage](model-editor.md)） |
| 基准配置：新建/编辑 | `/servers/base-configs/new`、`/servers/base-configs/:id`（[BaseConfigEditorPage](base-config-editor.md)） |

## 关键组件

| 组件                                                 | 用途           |
| -------------------------------------------------- | ------------ |
| `ModelManager.vue`                                 | 机型管理 Tab（默认） |
| `SeriesManager.vue`                                | 产品系列 Tab     |
| `BaseConfigBuilder.vue` + `BomTemplateManager.vue` | 基准配置 Tab     |
| `PartsLibrary.vue`                                 | 料号库 Tab      |

> 各 Tab 的功能细节、API 端点、数据库表见 [admin-tabs.md](admin-tabs.md)。
