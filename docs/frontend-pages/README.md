# CPQ Platform 前端页面文档

> 最后更新：2026-08-01

> 本文档按功能模块组织，记录每个页面的路由、功能、API 端点和数据库表映射。  
> 用途：方案编写参考 + 新会话快速上下文加载。

## 目录结构

```
frontend-pages/
├── README.md              ← 本文件（总览）
├── opportunities/         ← 商机线索模块
│   ├── cockpit.md         ← 商机驾驶舱（列表+图表）
│   ├── detail.md          ← 商机详情页
│   ├── workspace.md       ← 报价工作台（三栏配置）
│   ├── recycle-bin.md     ← 回收站
│   └── sidebar.md         ← 商机协作流（消息+文件）
├── servers/               ← 服务器模块
│   ├── server-page.md     ← 服务器配置门户（产品入口）
│   ├── server-admin.md    ← 服务器管理后台（料号库/基准/机型）
│   ├── model-catalog.md   ← 机型目录
│   ├── model-detail.md    ← 机型产品详情页（展示+进配置）
│   ├── config-wizard.md   ← 配置向导（四步配置）
│   ├── base-config-editor.md ← 基准配置编辑器
│   ├── model-editor.md    ← 机型产品化包装编辑页（管理面）
│   └── admin-tabs.md      ← 管理Tab（料号库/基准配置/机型管理）
├── parts/                 ← 配件模块
│   └── parts-management.md ← 配件管理（CRUD+看板+数据洞察）
├── strategies/            ← 策略中心模块
│   └── strategies.md      ← 策略中心管理页（3域：定价加法引擎/选型CRE/推理流编排 + L3溯源 + 策略文档库）
└── settings/              ← 设置模块
    ├── ai-settings.md     ← AI 设置（方案助手/趋势分析/API 配置）
    ├── excel-parser.md    ← Excel 解析调试
    ├── export-templates.md ← 导出模板管理
    └── field-management.md ← 字段管理
```

## 技术栈

| 层 | 技术 |
|---|---|
| 前端框架 | Vue 3 + TypeScript + Composition API |
| UI 组件库 | Ant Design Vue 4.x |
| 图表 | ECharts (vue-echarts) |
| 状态管理 | Pinia |
| HTTP | Axios (baseURL: `/api`) |
| 后端 | FastAPI (Python) |
| 数据库 | PostgreSQL 18 (多 schema) |
| 文件存储 | 本地文件系统 (`D:\CPQ_Data\`) |

## 数据库 Schema 概览

| Schema | 用途 | 核心表 |
|--------|------|--------|
| `opportunities` | 商机/报价 | `opportunities`, `quotations`, `quotation_items`, `opportunity_files`, `univer_templates` |
| `kp` | 配件库 | `kp_categories`, `kp_parts`, `kp_part_specs`, `kp_price_history`, `kp_part_compat`, `kp_part_related` |
| `l6` | 整机/配置 | `l6_records`, `parts_master`, `base_configs`, `base_config_parts`, `bom_templates`, `config_schemes`, `server_types`, `server_models` |
| `rules` | 业务规则 | `parse_regions`, `parse_field_rules`, `business_fields`, `dynamic_source_fields`, `system_config`, `matching_rules` |
| `l6_history` | 价格历史 | `l6_price_history` |
| `public` | 通用 | `comments`（商机批注） |

## 前端路由总览

| 路由                                   | 页面          | 模块   |
| ------------------------------------ | ----------- | ---- |
| `/opportunities`                     | 商机驾驶舱       | 商机线索 |
| `/opportunities/:opportunityId`      | 商机详情        | 商机线索 |
| `/quote/:opportunityId/:quotationId` | 报价工作台       | 商机线索 |
| `/recycle-bin`                       | 回收站         | 商机线索 |
| `/servers`                           | 服务器配置门户     | 服务器  |
| `/servers/admin`                     | 服务器管理后台     | 服务器  |
| `/servers/types/:typeId`             | 机型目录        | 服务器  |
| `/servers/models/:modelId`           | 机型产品详情      | 服务器  |
| `/servers/models/:modelId/edit`      | 机型包装编辑      | 服务器  |
| `/servers/models/new`                | 机型包装编辑（新建）  | 服务器  |
| `/servers/config/:modelId`           | 配置向导        | 服务器  |
| `/servers/base-config/:id?`          | 基准配置编辑器     | 服务器  |
| `/parts`                             | 配件管理        | 配件   |
| `/strategies`                        | 策略中心        | 策略   |
| `/ai-settings`                       | AI 设置         | 设置   |
| `/excel-parser`                      | Excel 解析调试  | 设置   |
| `/export-templates`                  | 导出模板管理      | 设置   |
| `/export-templates/excel/:id`        | Excel 模板编辑器 | 设置   |
| `/export-templates/spec/:id`         | 规格书模板编辑器    | 设置   |
| `/export-templates/fields`           | 字段管理        | 设置   |

## 顶部导航菜单

| 菜单项 | 类型 | 跳转 | 说明 |
|--------|------|------|------|
| 商机线索 | 顶层 | `/opportunities` | |
| 服务器 | 顶层 | `/servers` | 产品配置门户（机型目录 → 详情 → 配置向导） |
| 配件 | 顶层 | `/parts` | |
| 策略中心 | 顶层 | `/strategies` | |
| 设置 ▸ AI 设置 | 子菜单 | `/ai-settings` | |
| 设置 ▸ 解析规则 | 子菜单 | `/excel-parser` | |
| 设置 ▸ 导出模板 | 子菜单 | `/export-templates` | |
| 设置 ▸ 服务器管理 | 子菜单 | `/servers/admin` | 机型 / 基准配置 / 料号库维护后台 |

> 导航高亮规则：服务器管理面路由（`/servers/admin`、`/servers/base-configs/*`、`/servers/models/new`、`/servers/models/*/edit`）高亮「设置 ▸ 服务器管理」并展开设置子菜单；其余 `/servers/*` 路由高亮顶层「服务器」。
>
> 变更：2026-08-01「服务器」由子菜单改为顶层项（直进产品配置），原「后台管理」迁入「设置」并更名为「服务器管理」。

## 后端 API 前缀总览

| 前缀 | 模块 |
|------|------|
| `/api/opportunities` | 商机 CRUD + 文件 + 字段历史 |
| `/api/quotations` | 报价 CRUD + 批量操作 |
| `/api/quote` | 报价上传解析 + 保存 |
| `/api/server-catalog` | 机型目录（类型/机型列表） |
| `/api/base-configs` | 基准配置 CRUD |
| `/api/parts` | 配件 CRUD + 分类 |
| `/api/dashboard` | 驾驶舱统计 |
| `/api/fields` | 动态字段管理 |
| `/api/system-config` | 系统配置 |
| `/api/kp-config` | 配件库配置 |
| `/api/bom-templates` | BOM 模板 |
| `/api/spec-templates` | 规格书模板 |
| `/api/univer-templates` | Univer 导出模板 |
| `/api/feed` | 商机动态流 |
| `/api/rules` | 解析规则 |
| `/api/derive` | 推导引擎 |
| `/api/config-schemes` | 配置方案 |
| `/api/l6-chassis` | L6 机箱 |
| `/api/rear-io` | 后面板 IO |
| `/api/admin` | 管理端 |
| `/api/admin/kp` | 配件库 CRUD + 看板 + 数据洞察（价格异动/比价矩阵/疑似重复） |
| `/api/strategies` | 策略中心 CRUD + 状态流转 + 引用埋点 |
| `/api/comments` | 评论/批注 |
