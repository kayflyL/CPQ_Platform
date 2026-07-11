# CPQ Platform 系统架构

> 版本：v0.1.11 | 更新日期：2026-07-11

---

## 1 概述

CPQ Platform 的项目定位与核心流程见根目录 [CLAUDE.md](../CLAUDE.md)，完整业务链路与报价策略见 [业务流程.md](业务流程.md)。本文聚焦系统功能模块、技术架构与前端路由。

---

## 2 功能模块

### 2.1 报价核心流程

| 模块 | 功能 | 关键文件 |
|------|------|----------|
| **智能上传** | Excel 拖拽上传 → 自动解析提取配置项 → 多配置(CFG)拆分 | 前端：`components/UploadPreviewDrawer.vue`（在工作台 `views/quote/Workspace.vue` 内触发）<br>后端：`api/quote.py` → `services/quote_service.py` → `engine/pricing_engine.py` |
| **报价工作台** | L6 三栏对比视图（需求/匹配/定价）+ KP 零件卡片 + 质保模块 + KPI 看板 + 商机侧边栏（文件+批注） | 前端：`views/quote/Workspace.vue` + `store/quote.ts`(Pinia)<br>后端：`api/quote.py` + `api/opportunities.py` |
| **导出报价单** | 根据导出模板生成 Excel 报价文件，支持变量替换和循环块语法 | 前端：`views/template/TemplateList.vue` + `TemplateEditor.vue`<br>后端：`api/export_templates.py` + `api/opportunities.py`（`/{opportunity_id}/export` 端点） |

### 2.2 商机管理

| 模块 | 功能 | 关键文件 |
|------|------|----------|
| **商机列表** | 商机看板、分页、搜索、批量操作 | 前端：`views/opportunity/OpportunityList.vue`<br>后端：`api/opportunities.py` + `repository/opportunity_repo.py` |
| **商机详情** | 商机与报价单 1:N 结构、基本信息编辑、报价单列表 | 前端：`views/opportunity/OpportunityDetail.vue`<br>后端：`api/opportunities.py` + `api/quotations.py` |
| **回收站** | 软删除、恢复、永久删除、批量操作 | 前端：`views/opportunity/RecycleBin.vue`<br>后端：`api/opportunities.py`（`/{id}/trash` `/{id}/restore` 端点） |
| **商机文件** | 拖拽上传、下载、重命名、删除、用系统默认应用打开、实时扫描商机文件夹 | 前端：`components/quote/OpportunityFiles.vue`<br>后端：`api/opportunities.py`（`/{id}/files/*` 端点） |
| **批注系统** | 商机级批注，工作台侧边栏和商机管理列表可见 | 前端：`components/CommentPanel.vue`<br>后端：`api/comments.py` + `repository/comment_repo.py` |

### 2.3 基准价格管理

| 模块 | 功能 | 关键文件 |
|------|------|----------|
| **KP 零件价格库** | 按分类搜索、型号重命名、备注编辑、价格更新（插入新记录保留历史）、历史价格懒加载 | 前端：`views/admin/BasePricing.vue`<br>后端：`api/admin.py`（`/kp/*` 端点）+ `repository/kp_repo.py` |
| **L6 整机价格库** | 在线编辑/新增/删除、按机型聚合分组、拖拽排序、价格历史快照、五维规格筛选 | 前端：`views/admin/L6Pricing.vue`<br>后端：`api/admin.py`（`/l6/*` 端点）+ `repository/l6_repo.py` |

### 2.4 规则引擎

所有业务规则存储在 `rules.db`，通过 API 在线配置，无需改代码。

| 模块 | 功能 | 关键文件 |
|------|------|----------|
| **解析模板** | 配置 Excel 解析的锚点和字段映射（L6/KP 区域识别） | 前端：`views/ParseTemplateEditor.vue`<br>后端：`api/rules.py`（`/l6-region-config` `/kp-region-config` 端点） |
| **KP 分类映射** | 关键词 → 零件分类（如 `cpu` → `CPU`），支持优先级 | 前端：`views/admin/MatchingRulesConfig.vue`<br>后端：`api/rules.py`（`/kp-category-mappings` 端点） |
| **主板映射** | CPU 特征 → 主板型号（如 `KH50000` → `Polaris MB`） | 前端：`views/admin/MotherboardMapping.vue`<br>后端：`api/rules.py`（`/motherboard-mappings` 端点） |
| **L6 匹配规则** | 五维匹配维度优先级、降级策略、机箱模糊匹配、主板降级开关 | 前端：`views/admin/MatchingRulesConfig.vue`<br>后端：`api/rules.py`（`/matching-rules` 端点）<br>引擎：`engine/pricing_engine.py`（读取规则执行匹配） |
| **导出分类** | 自定义导出时额外的配件分类 | 后端：`api/rules.py`（`/export-categories` 端点）；前端原 `/rules` 页已废弃重定向至 `/parse-template` |

### 2.5 业务字段管理（Business Field）

业务字段是一套**动态字段管理模块**：通过配置而非改代码，即可在商机/报价单/整机/零件等数据源上挂载自定义字段，并在导出时由 `PricingEngine` 动态解析取值。字段定义、引用关系、变更审计、使用统计均落库管理。

| 模块 | 功能 | 关键文件 |
|------|------|----------|
| **字段配置** | 字段 CRUD（key/label/category/source/type）、启用禁用、排序、分组、权限（editable/readonly/hidden）、校验规则与枚举选项 | 前端：`views/admin/BusinessFieldManagement.vue`<br>后端：`api/admin.py`（`/api/admin/business-fields` 系列端点）+ `repository/business_field_repo.py` |
| **引用检查** | 字段被模板/导出/规则引用时记录引用关系，删除前校验，支持强制删除 | 后端：`api/admin.py`（`/references`、`/check-references`、`/force` 端点） |
| **变更审计** | 字段创建/更新/删除全量留痕，支持查历史 | 后端：`api/admin.py`（`/{field_key}/history` 端点） |
| **值校验** | 按字段 validation_rules/options 校验单值或批量校验 | 后端：`api/admin.py`（`/{field_key}/validate`、`/validate-batch` 端点） |
| **使用统计** | 记录字段被使用次数与最近使用时间 | 后端：`api/admin.py`（`/{field_key}/stats`、`/record-usage` 端点） |
| **导入导出** | 字段定义批量导出/导入（skip/overwrite 模式） | 后端：`api/admin.py`（`/business-fields-export`、`/business-fields-import` 端点） |
| **报价引擎集成** | 导出时按字段 `source`/`source_column` 动态解析字段值 | 引擎：`engine/pricing_engine.py`（`_get_business_field_repo` / `_resolve_field_dynamically`） |

> 数据存储在 `kp_data.db`（表 `business_fields` / `field_references` / `field_audit_logs` / `field_usage_stats`）。

### 2.6 首页看板

| 模块 | 功能 | 关键文件 |
|------|------|----------|
| **Dashboard** | 商机统计概览（总商机/总配置/本周新增）+ 趋势数据 | 前端：`views/Dashboard.vue`<br>后端：`api/dashboard.py` |

---

## 3 技术架构

### 3.1 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Vue 3 + TypeScript + Vite + Ant Design Vue 4.x + Pinia |
| **后端** | FastAPI + SQLAlchemy (Raw SQL) |
| **数据库** | SQLite 独立库（kp_data / l6_data / opportunities / rules / l6_history，另有 comments.db 以原生 sqlite3 管理） |
| **Excel** | openpyxl + pandas |
| **样式** | Cyberpunk Dark 暗色主题（CSS 变量） |

### 3.2 后端分层

```
API 路由 (8 个模块: quote/opportunities/admin/rules/comments/dashboard/quotations/export-templates)
    ↓
Service 层 (QuoteService — 业务编排)
    ↓
Engine 层 (PricingEngine — 纯算法，统一走 Repository 访问数据)
    ↓
Repository 层 (9 个 Repo — 各自独立 Session)
    ↓
SQLite 独立库（kp_data / l6_data / opportunities / rules / l6_history / comments，严禁混用）
```

**关键约束**：
- Engine 不直接碰数据库，统一走 Repository（`PricingEngine` 通过注入的 `business_field_repo` 等读取配置）
- 数据源采用"挂载"模式（可配置路径、实时扫描、不存在静默跳过）
- 所有文件路径基于 `Path(__file__).parent` 动态获取，不硬编码

### 3.3 数据库

6 个独立 SQLite 库（kp_data / l6_data / opportunities / rules / l6_history / comments），统一存放于 `{DATA_PATH}/Reference/`（其中 5 个由 `base.py` 定义 engine，`comments.db` 由 `comment_repo.py` 原生管理）。完整表结构与每库每表字段见 [数据库.md](数据库.md)。

---

## 4 前端路由与页面

所有页面使用 `DefaultLayout.vue`（左侧固定导航 + 右侧唯一滚动区）。

| 路由 | 页面 | 侧边栏 | 说明 |
|------|------|:--:|------|
| `/dashboard` | `views/Dashboard.vue` | ✅ | 首页看板（默认页） |
| `/workspace` | `views/quote/Workspace.vue` | ❌ | 报价工作台（仅由上传或商机校对跳入） |
| `/opportunities` | `views/opportunity/OpportunityList.vue` | ✅ | 商机线索列表 |
| `/opportunities/:opportunityId` | `views/opportunity/OpportunityDetail.vue` | ✅ | 商机详情页 |
| `/recycle-bin` | `views/opportunity/RecycleBin.vue` | ❌ | 回收站 |
| `/base-pricing` | `views/admin/BasePricing.vue` | ✅ | KP 零件价格库 |
| `/l6-pricing` | `views/admin/L6Pricing.vue` | ✅ | L6 整机价格库 |
| `/parse-template` | `views/ParseTemplateEditor.vue` | ✅ | 解析模板配置 |
| `/excel-parser` | `views/ExcelParser.vue` | ❌ | Excel 独立解析工具（离线，不进生产上传链路） |
| `/rules` | —（重定向） | — | 旧规则管理，已废弃重定向至 `/parse-template` |
| `/export-templates` | `views/template/TemplateList.vue` | ✅ | 导出模板列表 |
| `/export-templates/:id/edit` | `views/TemplateEditor.vue` | ❌ | 导出模板编辑器 |
| `/business-fields` | `views/admin/BusinessFieldManagement.vue` | ✅ | 业务字段管理 |
| `/system-settings` | `views/admin/SystemSettings.vue` | ✅ | 系统设置 |

---

## 5 相关文档

完整文档索引见根目录 [CLAUDE.md](../CLAUDE.md)。

---

## 6 未来演进

| 阶段 | 目标 |
|------|------|
| 平台化 | PostgreSQL 迁移、多用户、RBAC 权限 |
| 知识平台 | 硬件兼容知识库、可视化规则引擎 |
| AI 原生 | 向量检索、相似配置推荐、AI 问答 |

> 注：当前阶段仅为单人单机工具，上述功能按需推进
