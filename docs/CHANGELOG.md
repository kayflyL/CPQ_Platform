# 更新日志

本文件记录 CPQ Platform 的所有重要变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---
## [未发布]

### 重构

#### 料号库编辑页按类别分区重构 + specs 冗余字段清理

**问题**：料号库编辑页所有类别共用一个「细分 + 通用 specs 键值对」表单，看不出电源该填功率、CPU 该填 TDP、线缆该填适用范围；且 `specs` 与顶层列存在系统性重复（迁移脚本副产物）。

**改造内容**：

- **数据清理**（`backend/scripts/clean_parts_specs.py`，一次性 + 幂等）：删除 `specs.kind`（≡`sub_type`）、`specs.description`（≡顶层 `description`）、`specs.note`（并入顶层描述）；删除前对顶层为空的字段做提升。本次清理 18 行。
- **编辑表单分区**（`frontend/src/components/server-admin/PartsLibrary.vue`）：
  - 按「基础信息 / 规格参数 / 扩展属性」三区分组
  - 规格参数区按类别动态渲染专用字段（电源「功率W」、CPU/GPU/散热器「TDP」、机箱/背板「盘位数」、线缆「分组大小 + 适用盘位/背板 tags」、Riser/OCP「IO槽位/选项类型」）
  - 扩展属性区作为兜底键值对，自动排除已进规格参数区的 key，杜绝同一字段两处编辑
  - 类别不在字段族配置内时降级为仅基础+扩展（等价旧行为）
- **死字段清理**：删除前端「供应商」表单项（`parts_master` 表无此列，一直被静默丢弃）

**配套修复**：`PartsMasterRepository` 补 `update()` 方法（原缺失导致编辑保存 500）；类别输入由 `a-input` 改 `a-auto-complete`（支持选已有 + 输入新类别）。

**不在范围**：顶层 `tdp`/`cables_per` 死列保留不动；`l6_chassis_repo` 流程维持止血（其读 `specs.drive_bays/backplane` 是正确的，库内无 `applicable` 列）；未执行的 `parts.parts_master` / `migrate_to_parts_master.py` dead code 留待后续。

---
## [0.1.15] - 2026-07-17

### 修复

#### 报价工作台预览数据不完整

**问题**：报价工作台预览时，配置项和绑定字段显示不全（如报价单有 3 个配置，预览只显示 1 个且内容不完整），而 Univer 编辑器预览正常。

**根因**：Workspace 预览调用 `univerTemplateApi.preview()` 时缺少 `quotationId` 参数，导致后端 `load_preview_data` 跳过报价单数据加载（`config_summary`、`l6_details`、`kp_details` 等全部为空）。

**修复**：
- `frontend/src/views/quote/Workspace.vue` (第507行)：提取 `quotationId` 并传入 preview API
- `frontend/src/store/quote.ts`：补充 `ProjectInfo` 接口的 `quotation_id` 和 `version` 字段声明

**影响范围**：报价工作台预览功能，确保与 Univer 编辑器预览行为一致。

### 清理

#### 移除冗余字段 `confirmed_price`

**问题**：`confirmed_price` 是历史遗留的冗余字段，实际业务只使用 `base_price`（成本价）和 `final_price`（成交价）。

**清理内容**：
- **数据库**：删除 `opportunities.opportunity_items.confirmed_price` 列（迁移脚本：`backend/migrations/cleanup_confirmed_price.sql`）
- **后端模型**：移除 `OpportunityItem.confirmed_price` 字段定义
- **后端仓库层**：移除 `quotation_repo.py` 中的字段映射和保存逻辑
- **后端服务层**：移除 `preview_data_loader.py` 中的字段加载和 fallback 逻辑
- **后端引擎**：移除 `pricing_engine.py` 中所有 `confirmed_price` 的赋值和引用（共 7 处）
- **前端类型**：移除 `opportunity.ts` 中的 `confirmed_price` 类型定义

**影响范围**：报价单数据模型简化，价格字段统一为 `base_price` + `final_price`。

#### 移除冗余字段 `model_name` 和 `server_model`

**问题**：`kp_details` 和 `l6_details` 中的每条 item 都包含 `server_model` 和 `model_name` 字段，但这些是 `config_summary.server_model` 的冗余复制，且 `model_name` 在数据库中根本不存在（始终为空）。

**清理内容**：
- **后端服务层**：移除 `preview_data_loader.py` 中 item 构建时的 `model_name` 和 `server_model` 字段赋值
- **后端服务层**：移除顶层 `model_name` 和 `model_name_with_qty` 占位字段

**保留字段**：
- `config_summary.server_model`：配置级服务器型号（用户手动填写，保留）
- 前端 `Workspace.vue` 中的 `model_name`：商机级整机型号（保留）

**影响范围**：预览数据结构简化，消除冗余字段。

---
## [0.1.14] - 2026-07-16
修复导出模板编辑器有一圈灰脏脏的问题。
不是 Univer 内部的问题——是 `DefaultLayout` 的 `.main-scroll::after` 那个**暗角装饰**。它是一层覆盖整个视口的径向渐变（中心透明、四边渐暗），`position: fixed; z-index: 0`。Univer 的顶部工具栏和底部 sheet 栏正好落在视口的**边缘暗区**里，被这层暗角罩出了一圈灰；而表格中间在暗角的透明区，所以是白的。这也完美解释了你之前说的"刷新加载前灰一大片、加载后中间变白但上下还灰"——加载前没有 Univer 白底遮挡，整片都是暗背景＋暗角；加载后中间被白色盖住，但上下边缘仍被暗角罩着。

所以前面几轮我在 Univer 容器内部使劲（移除 backdrop-filter、改 gray 底色）都没用——灰根本不是 Univer 发出来的，是外层暗角盖下来的。方向一直偏了，抱歉。

修法很简单：把编辑器根元素提到暗角层之上。给 `.univer-template-editor` 加 `position: relative; z-index: 1`，它就盖住 `z-index: 0` 的暗角，工具栏和 sheet 栏不再被罩。

关于那个暗角装饰——它是 `DefaultLayout` 里 `.main-scroll` 的两个伪元素：`::before` 是粒子点阵动画、`::after` 是 vignette 暗角（中心透明、四边渐暗），再配合 `.main-scroll` 背景里的几层光晕渐变。这一套是配合你 cyberpunk 暗色主题的氛围装饰，让背景有光晕+粒子+边缘暗角的层次感，应该是之前做暗色主题或视觉重构时加的（不是这次动的）。它对普通页面是背景氛围，但像编辑器这种铺满整个 `.main-scroll` 的全屏页面，内容会被这层装饰罩住边缘、发灰发雾——现在已经用 `z-index:1` 把编辑器提到装饰层之上规避了。

要不要把它整个删掉，你定：删了的话所有页面都会变成纯色背景、干净但平淡；留着的话普通页面有氛围、全屏页面已经规避了。我先把"全屏页面要 `position:relative; z-index:1` 挡装饰层"这个坑记进项目记忆。
## [0.1.13] - 2026-07-16
### 修复
#### 导出模板编辑器：L6/KP保修字段映射预览丢失
**问题：** 在导出模板编辑器中，绑定L6/KP保修字段，前端预览，CFG1和CFG2显示内容如下： Warranty {{L6维保描述}} {{KP维保描述}} ，只有CFG3显示的内容是正确的。
**修复**：数据和代码完全对上。**这跟 binding 有没有建、字段绑没绑都无关，是填充引擎 `fill_snapshot` 的一个行号错位 bug。**

##### 证据链

先看你贴的数据里最关键的一条：**报价单项（items）里只有 CFG1 和 CFG2，CFG3 一项都没有**（第 2 节 36 项全是 CFG1/CFG2）。而 config_descriptions / config_server_models / config_warranty_info 里 CFG1/CFG2/CFG3 三个都有。这个差异是破案关键。

再看模板的 bindings：配置页（sheet-2）上有两个**动态**绑定——`l6_details`(A6) 和 `kp_details`(A9)，以及若干**静态**绑定，其中 warranty 的三条是 `warranty_desc_l6`(B11)、`warranty_desc_kp`(B12、D12)。

##### 因果链

`fill_snapshot`（`template_filler.py:69-104`）的处理顺序是**先动态、后静态**：

1. 动态绑定 `l6_details`/`kp_details` 会按该配置的明细条数**插入行**（`_insert_rows`）。CFG1 有 9 条 L6 + 7 条 KP，分别在 A6 插 8 行、A9 插 6 行，合计把第 9 行以下全部往下推了 14 行。于是原来在 B11/B12 的 warranty 单元格，连同里面的 `{{L6维保描述}}` 文字，被挤到了第 24 行附近。
2. 然后才处理静态绑定。但静态绑定的 `cellAddress` 是**存在 binding 里的固定值 "B11"/"B12"**，填充引擎**完全不会根据刚才动态插入的行去调整静态绑定的行号**。所以它把 "1质保3年…" 写到了**当前的 B11**——而这个位置此刻已经是 L6/KP 的某一行数据了，根本不是 warranty。
3. 真正的 warranty 文字 `{{L6维保描述}}` 早被挤到下方（约 B24），没有任何 binding 去覆盖它，于是**原样保留**。这就是你在 CFG1/CFG2 看到的占位符。

##### 为什么只有 CFG3 正常

因为 **CFG3 在 items 表里一条报价项都没有**。走动态绑定时 `data_rows` 过滤后为空，`_fill_dynamic_binding`（`:306`）直接 return，**不插入任何行**。于是 CFG3 页的 B11/B12 位置纹丝不动，静态绑定按原行号填入 `warranty_desc_l6[CFG3]` = "3质保3年…"，完全正确——你的"3"测试标记也因此完美显示。

一句话总结：**配置项越多（动态插入行越多）的配置页，下面那些静态绑定的行号错位就越严重；CFG3 因为没数据、不插行，反而侥幸正确。**

##### 这是设计缺陷

`_insert_rows`（`:344-401`）很认真地下移了 `cellData`、`rowData`、`mergeData` 里的行，**唯独漏了 binding 的 `cellAddress`**——因为 binding 不在那个 sheet 数据结构里。动态绑定和静态绑定用的是两套行号坐标系：动态绑定插入行后"地形"变了，静态绑定还在用旧地图。

##### 怎么修
核心是让静态绑定的行号感知到同 sheet 上动态插入产生的偏移。具体做法：在 `fill_snapshot` 里给每个 sheet 维护一张"行偏移表"（在某行之后插了多少行），`_insert_rows` 每次插入后记一笔；处理静态绑定时，按 `cellAddress` 解析出的行号查这张表、累加偏移，得到真实目标行号再写入。注意动态绑定是从下往上处理的，多个动态绑定的偏移要叠加，这个累加逻辑也要对应上。

要的话我直接帮你改 `template_filler.py`，改完用你这个报价单（CFG1/CFG2 有数据、CFG3 无数据）正好能同时验证"有插入行"和"无插入行"两种情况。要我动手吗？

顺带两个数据层的小问题（不是本次 bug 主因，但建议留意）：`config_quantities` 里缺了 CFG3（只有 CFG1:50/CFG2:15）、`config_count` 是 0；另外 warranty_desc_kp 你建了两条（B12 和 D12），如果不是故意的可以删掉一条。
## [0.1.12] - 2026-07-16
切换数据库，SQLite迁移至PostgreSQL

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
