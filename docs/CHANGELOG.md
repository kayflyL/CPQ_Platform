# 更新日志

本文件记录 CPQ Platform 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [0.1.11] - 2026-07-11

### 修复

#### 导出模板编辑器：动态绑定字段映射编辑丢失

**问题**：在导出模板编辑器中，给 config_summary 等动态绑定新增或调整列对应关系（如"服务器型号→B"）后，若未先点"保存绑定"就重新选中单元格、点击"已绑定"列表/"绑定总览"行、或重选"引用解析区域"，未提交的编辑会被静默丢弃，导致改动不生效、刷新后消失。

**修复**：`frontend/src/views/TemplateEditor.vue`
- 新增对 `bindingForm` 的深度 watcher，动态绑定的每次改动（增删字段、改列、换区域、模板行号、描述模板）实时提交到 `data.bindings`，不再依赖"保存绑定"按钮
- 重构 `saveBinding` → `commitBindingToData(silent)`，"保存绑定"按钮保留，行为不变
- 自动保存**仅对动态绑定**生效，静态单元格（标题等）仍走"保存绑定"，避免点击即重写、误伤 `staticValue` 等字段

### 优化

- **动态绑定字段映射实时生效**：编辑后预览即时联动，重新选中单元格不再丢失未保存的改动
- 注意：自动保存仅写入内存；落库（刷新后不丢）仍需点右上角"保存"按钮

### 文档

- **新增根目录 `CLAUDE.md`**：作为新会话自动入口，含项目定位、启动命令、分层约束红线、文档索引、常见坑与已知问题
- **新增 `docs/Pricing_Engine.md`**：2198 行定价引擎的算法详解（五维匹配/主板降级/机箱模糊/质保/利润率，附阈值常量与方法索引）
- **新增 `docs/Excel_Parsing.md`**：后端 Excel 上传解析逻辑、区域锚点三趟匹配、field_mapping 配置、多配置拆分
- **新增 `docs/Engineering_Guide.md`**：环境搭建、首次初始化、配置项、测试、生产部署、排错
- **新增 `docs/业务流程.md`**：业务流程图 canvas 转 mermaid + 报价策略
- **重写 `docs/API 路由.md`**：补全 119 端点的请求/响应结构；纠正 projects→opportunities 改名后的脱节
- **更新 `数据库.md` / `System_Architecture.md` / `Component_Inventory.md` / `Frontend_Style_Guide.md` / `Design_Principles.md`**：对齐 opportunities 改名、business_field 模块、6 库结构、`--cpq-*` 变量体系
- 统一所有文档版本号至 v0.1.11；修复 Deployment.md 断链；修正启动命令（`uv sync` → `pip install -r requirements.txt`）；`main.py` 根路由版本号改为读 `settings.APP_VERSION`

---

## [0.1.10] - 2026-07-09

### 修复

#### 硬编码问题修复（设计原则④：硬编码零容忍）

**后端路径硬编码**
- `backend/app/models/base.py`: 移除硬编码路径 `D:\CPQ_Platform_V1\data\`，改为从环境变量 `DATA_PATH` 读取
- `backend/app/core/config.py`: 新增 `DATA_PATH` 配置项，默认值 `D:\Quotation_Automation`

**前端 CSS 颜色硬编码**
- 修复 14 个 Vue 组件中的硬编码颜色值（共 100+ 处）
- 新增 CSS 变量到 `frontend/src/styles/tokens.css`：
  - 背景层级：`--cpq-bg-card`, `--cpq-bg-elevated`, `--cpq-bg-input`, `--cpq-bg-selected`, `--cpq-bg-highlight`, `--cpq-bg-dark`
  - 边框层级：`--cpq-border-dark`
  - 功能色：`--cpq-color-success`, `--cpq-color-warning`, `--cpq-color-info`, `--cpq-color-purple`, `--cpq-color-purple-dark`, `--cpq-color-orange`, `--cpq-color-gold`
  - 文字色：`--cpq-text-light`, `--cpq-text-inverse`, `--cpq-text-tertiary`, `--cpq-text-quaternary`, `--cpq-text-quinary`
- 受影响组件：`ParseTemplateEditor.vue`, `UploadPreviewDrawer.vue`, `ExcelTable.vue`, `L6ChassisCard.vue`, `L6SpecFilter.vue`, `ExcelParser.vue`, `Workspace.vue`, `TemplateList.vue`, `ProjectDetail.vue`, `ProjectList.vue`, `RulesManagement.vue`, `TemplateEditor.vue`, `PreviewModal.vue`, `L6Pricing.vue`

**CORS 配置硬编码**
- `backend/app/core/config.py`: 新增 `CORS_ORIGINS` 配置项，支持环境变量覆盖
- `backend/app/main.py`: 移除硬编码的 CORS 源列表，改为从配置读取

### 文档

- 新增 `docs/README.md`：项目简介、快速启动、技术栈、项目结构
- 新增 `docs/Deployment.md`：生产环境部署指南（环境变量、依赖安装、启动命令、Nginx 配置）

---

## [0.1.9] - 2026-07-04

### 新增
- **项目文件拖拽上传**：支持拖拽文件到项目文件列表直接上传，支持多文件同时拖拽
- **新建空项目自动创建文件夹**：创建项目时自动生成标准文件夹结构（uploads/exports）

### 优化
- **返回按钮文字优化**：从项目详情页进入报价工作台时，返回按钮显示"← 返回项目详情"

### 修复
- 修复从项目详情页点击"编辑/查看"按钮后路由跳转崩溃
- 修复项目文件列表加载失败（字段名不匹配）

---

## [0.1.8] - 2026-07-04

### 新增
- **L6 三栏对比视图**：左栏 Excel 需求 / 中栏匹配结果（五维对比标记 ✅⚠️❌）/ 右栏定价
- **导出模板引擎**：支持完整 Excel 模板文件、变量替换（`${project_name}`）、循环块语法（`[${disk_model}*${disk_qty}; ]`）
- **导出模板管理**：卡片式模板列表，支持新建/编辑/删除/设为默认
- **模板编辑器**：左侧配置面板 + 右侧实时预览，支持上传自定义 Excel 模板

### 优化
- **配置页预览重构**：完全复刻原始 Excel 模板结构，支持合并单元格、8 列表头
- **L6 匹配引擎增强**：支持主板降级匹配、机箱模糊匹配（如 2U → 2.5U）

### 修复
- 修复 L6 匹配规则引擎崩溃（变量未赋值）
- 修复导出时合并单元格写入错误
- 修复 Excel 需求显示为横线（前端字段名遗漏）

---

## [0.1.7] - 2026-07-03

### 新增
- **项目文件自动归档**：保存项目时自动创建文件夹并移动上传文件到项目目录
- **文件列表实时扫描**：直接扫描项目文件夹，本地增删文件后刷新即可看到
- **项目文件管理**：支持重命名/删除/上传/用系统默认应用打开
- **项目评论系统**：支持为项目添加评论，显示用户名/时间/内容
- **报价工作台侧边栏**：抽屉式侧边栏，包含项目文件（40%）和评论（60%）

### 优化
- 文件下载改为按文件名下载，增加路径穿越防护

---

## [0.1.6] - 2026-07-03

### 新增
- **质保服务费独立计算**：L6 质保和 KP 质保独立计算，互不影响
- **质保信息自动识别**：从报价单自动提取质保年限（如"质保3年"→ 3年）

### 优化
- **质保卡片重构**：显示识别状态、年限下拉选择、费率手动调整、金额实时显示

---

## [0.1.5] - 2026-07-03

### 新增
- **CPU 价格为 0 警告**：顶部红色警告框提示"有 CPU 价格为 0，整机成本可能偏低"
- **质保项可编辑**：质保服务项卡片提供数量/单价输入框

### 优化
- **L6 匹配状态显示优化**：整机匹配成功后，子项统一显示"已包含在整机价格中"
- **质保项独立统计**：质保费用与 L6/KP 成本分离，KPI 看板单独展示
- **价格输入体验优化**：输入框改为失去焦点后才触发重算，避免输入过程中价格跳变
- **KPI 看板按配置切换**：切换 CFG tab 时自动重算整机总成本/含税总价/利润额/毛利率

### 修复
- 修复前端税率计算错误（RMB 项多乘 13% 税）
- 修复综合毛利率计算错误（成本估算逻辑修正）

---

## [0.1.4] - 2026-07-03

### 新增
- **报价单导出规则模块**：支持动态分类（CPU/GPU/Memory/Disk，可自定义）、循环语法、拖拽交互
- **报价工作台评论功能**

### 优化
- **导出描述引擎重构**：支持循环块语法解析、动态提取配件分类、智能展开

---

## [0.1.3] - 2026-07-02

### 新增
- **L6 价格库五维规格匹配筛选**：机箱/机型/盘位/PSU/主板下拉筛选，实时匹配提示

### 优化
- **L6 价格库卡片样式重构**：机箱规格绿色大字（28px）、主板橙色高亮、PSU 紫色高亮
- 提取公共组件 `L6SpecFilter.vue`，消除 50+ 行重复代码

---

## [0.1.2] - 2026-07-02

### 新增
- **L6 匹配规则可视化配置页面**：匹配维度拖拽排序、降级匹配规则开关、机箱模糊匹配规则配置、L6 价格清单表格+规格筛选器、降级匹配步骤可视化、多条匹配结果手动选择

### 优化
- **L6 匹配引擎增强**：主板支持降级匹配、机箱支持模糊匹配（如 4U → 4.5U）
- **KP 价格库命名调整**："基准价格" → "KP价格库"
- **规则管理页面重构**：一级模块选择器（大色块卡片）+ 二级 Tab 层级分明

---

## [0.1.1] - 2026-07-01

### 新增
- **独立数据库架构**：`kp.db`、`l6.db`、`rules.db`、`cpq_platform.db` 分离，互不干扰
- **规则在线化**：Excel 锚点、L6 匹配维度、KP 分类映射、主板映射全部抽离到数据库，支持在线配置
- **基准价格管理**：按型号聚合、价格趋势图、多维排序
- **规则管理**：4 类规则 CRUD，支持在线编辑/新增/删除/批量保存
- **回收站**：软删除 + 恢复 + 永久删除
- **项目管理看板**：状态追踪、导出功能

### 优化
- 卡片布局改进：引入 `auto-fill minmax` 自适应网格
- 新增 Chart.js 价格趋势可视化（暗色背景、绿色折线）

---

## [0.1.0] - 2026-06-29

### 版本概述
从旧系统 0.2.5（Streamlit 单体架构）迁移到 Vue3 + FastAPI 前后端分离架构。

### 新增
- **智能上传**：Excel 拖拽上传 → 自动解析 → 多配置拆分
- **报价工作台**：实时精算看板、L6/KP 独立调价、财务联动
- **项目管理**：项目看板、校对模式、导出功能
- **基准价格**：KP/L6 价格在线 CRUD、历史趋势查询
- **核心引擎**：五维 L6 智能匹配、KP 手动同步、质保服务费按需、WYSIWYG 导出

### 技术栈
- 前端：Vue3 + TypeScript + Vite + Ant Design Vue + Pinia
- 后端：FastAPI + SQLAlchemy
- 数据库：SQLite × 4 独立库
- 样式：GitHub Dark 暗色主题（CSS 变量系统）
