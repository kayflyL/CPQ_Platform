# CPQ Platform 前端页面文档

> 最后更新：2026-10-21（设计文档迁 docs/前端设计/ 并按层更名）

> 本文档按功能模块组织，记录每个页面的路由、功能、API 端点和数据库表映射。  
> 用途：方案编写参考 + 新会话快速上下文加载。  
> 视觉规范：tokens.css=值 → [视觉风格指南.md](../前端设计/视觉风格指南.md)=材质层 → [布局与用法规范.md](../前端设计/布局与用法规范.md)=用法与理由 → prototypes/布局与用法规范.html=可视样张；改前端页面前先看。

## 目录结构

```
frontend-pages/
├── README.md              ← 本文件（总览）
├── portal/                ← 统一门户模块（协作报价流程）
│   ├── portal-home.md     ← 工作台三层架构（信号波纹banner+业务流程条纯展示+常用功能；右栏「我的工作台」入口卡=唯一主CTA；真实口径；2026-10-13）
│   ├── workstation.md     ← 门户工作台五子页（我的商机/技术/成本/报价/调度：复用商机线索表组件+状态权限门控）
│   ├── notifications.md   ← 通知系统（富 popover 铃铛 + /notifications 全量页 + WS 实时推，2026-09-15）
│   └── business-detail.md ← ⚠️ 已下线（并入 opportunities/detail.md 统一审批流详情页）
├── opportunities/         ← 商机线索模块
│   ├── cockpit.md         ← 商机驾驶舱（左右两栏：左图表栏单列纵滑+右宽表自适应+配件筛选按报价明细搜商机）
│   ├── ai-leads.md        ← AI 线索（AI 办公室隐藏商机：转正/清理/查看对话）
│   ├── detail.md          ← 商机详情页
│   ├── workspace.md       ← 报价工作台（三栏配置）
│   ├── recycle-bin.md     ← 回收站
│   └── sidebar.md         ← 商机协作流（消息+文件）
├── servers/               ← 服务器模块
│   ├── server-page.md     ← 服务器配置门户（产品入口）
│   ├── server-admin.md    ← 服务器管理后台（料号库/基准/机型）
│   ├── model-catalog.md   ← 机型目录
│   ├── model-detail.md    ← 机型产品详情页（暗色R5.3：铭牌/亮点/能力带/场景照片卡/折叠规格）
│   ├── config-wizard.md   ← 配置向导（四步配置）
│   ├── base-config-editor.md ← 基准配置编辑器
│   ├── model-editor.md    ← 机型产品化包装编辑页（管理面，与详情页顺序镜像+图标选择+场景配图上传）
│   └── admin-tabs.md      ← 管理Tab（料号库/基准配置/机型管理）
├── parts/                 ← 配件模块
│   └── parts-management.md ← 配件管理（CRUD+看板+数据洞察）
├── galaxy/                ← 星河首页（public/ 静态镜像页，非 vue-router 路由）
│   └── galaxy-home.md     ← 星河首页（BlueYard 镜像品牌化；访问必须 /galaxy/index.html 全路径；?debug-editor=1 字体调试编辑器）
├── office/                ← AI 办公室模块
│   └── ai-office.md       ← AI 办公室 3D 视图（现场/对话/任务看板 + 可交互物件：点显示器看任务 + 手机版 3D 全屏+头像行）
├── strategies/            ← 策略中心模块
│   └── strategies.md      ← 策略中心管理页（3域：定价加法引擎/选型CRE/推理流编排 + L3溯源 + 策略文档库）
└── settings/              ← 设置模块
    ├── ai-settings.md     ← AI 设置（方案助手/趋势分析/API 配置）
    ├── ai-office-team.md  ← AI 办公室团队/员工页（含 AI 角色访问权限与价格可见性）
    ├── skill-studio.md    ← 工作流编辑器（原 Skill Studio：左任务规则+大脑视角预览/中画布/右试运行）
    ├── artifact-templates.md ← 产出物模板中心（管理面「产出物」tab：PDF 模板三栏编辑器+图表资产同源引用+输出节点选模板）
    ├── excel-parser.md    ← Excel 解析调试
    ├── export-templates.md ← 导出模板管理
    ├── field-management.md ← 字段管理
    └── users-roles.md     ← 用户与权限（角色/用户管理 + 权限目录三层体系）
```

## 技术栈

| 层      | 技术                                   |
| ------ | ------------------------------------ |
| 前端框架   | Vue 3 + TypeScript + Composition API |
| UI 组件库 | Ant Design Vue 4.x                   |
| 图表     | ECharts (vue-echarts)                |
| 状态管理   | Pinia                                |
| HTTP   | Axios (baseURL: `/api`)              |
| 后端     | FastAPI (Python)                     |
| 数据库    | PostgreSQL 18 (多 schema)             |
| 文件存储   | 本地文件系统 (`D:\CPQ_Data\`)              |

## 数据库 Schema 概览

| Schema | 用途 | 核心表 |
|--------|------|--------|
| `opportunities` | 商机/报价 | `opportunities`, `quotations`, `quotation_items`, `opportunity_files`, `univer_templates`, `opportunity_flows`, `opportunity_flow_nodes`, `opportunity_requirements` |
| `kp` | 配件库 | `kp_categories`, `kp_parts`, `kp_part_specs`, `kp_price_history`, `kp_part_compat`, `kp_part_related` |
| `l6` | 整机/配置 | `l6_records`, `parts_master`, `base_configs`, `base_config_parts`, `bom_templates`, `server_types`, `server_models` |
| `rules` | 业务规则 | `parse_regions`, `parse_field_rules`, `business_fields`, `dynamic_source_fields`, `system_config`, `matching_rules` |
| `l6_history` | 价格历史 | `l6_price_history` |
| `public` | 通用 | `comments`（商机批注） |

## 前端路由总览

| 路由                                   | 页面          | 模块   |
| ------------------------------------ | ----------- | ---- |
| `/portal`                            | 工作台（磁贴墙） | 门户  |
| `/opportunities`                     | 商机驾驶舱       | 商机线索 |
| `/ai-leads`                          | AI 线索        | 商机线索 |
| `/opportunities/:opportunityId`      | 商机详情（统一审批流看板，按角色裁剪） | 商机线索 |
| `/quote/:opportunityId/:quotationId` | 报价工作台       | 商机线索 |
| `/recycle-bin`                       | 回收站         | 商机线索 |
| `/notifications`                     | 通知中心全量页  | 门户  |
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
| `/galaxy/index.html`                 | 星河首页（静态页，非路由） | 星河 |

## 顶部导航菜单

| 菜单项 | 类型 | 跳转 | 说明 |
|--------|------|------|------|
| 首页 | 顶层 | `/galaxy/index.html` | 星河品牌首页（静态页，window.location 整页跳转不走路由） |
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

## 移动端底部导航（≤768px，2026-09-19 新增）

DefaultLayout 级全局组件（`DefaultLayout.vue`），替代原左上角汉堡全屏菜单（已删除）：

- **底栏** `.mobile-tabbar`：固定底部、玻璃白底 + 药丸激活态；5 槽 = `topItems` RBAC 过滤后前 4（工作台 / AI 办公室 / 商机线索 / 服务器）+「更多」；栏高 58px + `env(safe-area-inset-bottom)`。
- **「更多」面板** `.more-sheet`：底部滑入 sheet，悬于底栏上方；收纳第 5+ 项（配件 / 解决方案）、次级页（AI 线索 / 回收站，`page.opportunities` 门控）、设置组、用户卡 + 退出登录。
- **让位机制**：`.scroll-clearance-bottom` 占位（高 = `--cpq-tabbar-inset`），对齐顶部 `scroll-clearance` 让位哲学；方案助手桌宠默认锚点与拖拽夹取同步上移（`useAssistantFab.MOBILE_TABBAR_INSET = 58`，与 CSS 常量两处同步）。

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
| `/api/l6-chassis` | L6 机箱 |
| `/api/rear-io` | 后面板 IO |
| `/api/admin` | 管理端 |
| `/api/admin/kp` | 配件库 CRUD + 看板 + 数据洞察（价格异动/比价矩阵/疑似重复） |
| `/api/strategies` | 策略中心 CRUD + 状态流转 + 引用埋点 |
| `/api/comments` | 评论/批注 |
