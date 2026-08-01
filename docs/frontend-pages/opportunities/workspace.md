# 报价工作台 (Workspace)

> 最后更新：2026-08-01

## 功能概述

报价配置的核心工作区，三栏布局，支持多配置 Tab 切换。

### 核心功能
1. **配置 Tab 栏** — 多配置管理：
   - 添加/删除/重命名配置
   - 右键菜单操作
   - Tab 切换
2. **左栏：BOM 表格** — 纯展示（固化快照）：
   - 展示当前配置的 BOM 清单
   - 分两个区域：L6 配置（机箱部件，无成本）+ KP 配置（关键部件，有成本）
   - 从 Excel 上传时为固化快照，新建模式跟随中栏
   - 读取 `cfg.bom_template`, `cfg.bom_context`, `cfg.items`, `cfg.bom_excel_rows`
3. **中栏：服务器配置** — 核心编辑区：
   - 服务器型号选择（自动完成）
   - 数量设置
   - 配置描述
   - 各部件配置（CPU、内存、硬盘、GPU、网卡、电源、散热器等）
   - 推导引擎联动（功耗/PSU/GPU线缆/背板自动推导）
   - 手填兜底（推导不可用时手动填写）
4. **右栏：定价与利润** — 实时计算：
   - 成本合计
   - 售价计算
   - 利润率显示
   - **利润率告警**：综合毛利率低于门槛时弹一次性 Modal 提示线下特价审批。告警走**独立策略 `pricing.margin_alert`**（开关 `enabled` + 门槛 `threshold` + 标题 `title` + 正文 `content` 模板，正文支持 `${margin}`/`${threshold}` 占位符），经 `pricingRulesStore.getMarginAlert()` 读取；**阈值与文案都在策略中心「利润率告警」编辑器（`MarginAlertEditor.vue`，挂在定价画布）配，不再硬编码**。策略中心定价只作建议，告警**只警告不锁价、不自动改价**，与保底封顶（引擎 clamp）解耦。默认门槛 7%（`DEFAULT_MARGIN_ALERT`，seed 进 DB 可见可改）。（历史：曾借 `guardrail.floor` + 硬编码文案，2026-07-31 重构为独立 `margin_alert` 策略；`system_config.profit_margin_alert_threshold` 保留但不驱动此告警）
   - 价格参数调整

### 预览与导出模板

底部操作栏「预览」按钮的模板选择器合并了两套模板体系（`<a-select-opt-group>` 分组）：

- **Excel 模板**（`/api/univer-templates`）— Univer workbook 快照 + 单元格绑定。预览调 `univerTemplateApi.preview` 返回填充后的 `workbook_snapshot`，模态框内用 `UniverSheet` 渲染；确认按钮「下载 Excel」从 live Univer 实例读样式经 exceljs 写出 xlsx。
- **规格书模板**（`/api/spec-templates`）— 品牌 + 显示开关/标签。预览调 `specTemplateApi.getPreviewData` 拿 `configs`，模态框内用 `SpecSheet` 渲染（branding/display_options 取自选中模板）；确认按钮「打印为 PDF」走 `window.print` + Teleport overlay（复用 SpecSheet 的 `@media print` 规则）。

选择器 value 编码为 `excel:{id}` / `spec:{id}`（两套表 id 序列独立、可能重叠，前缀消歧），由 `selectedTemplate` computed 解析出 `{ type, id }` 驱动分流。默认选 Excel 默认模板；无 Excel 才回落规格书默认。


- 中栏 → 左栏单向联动
- Excel 模式：左栏 = 固化快照（不随中栏变化）
- 新建模式：左栏跟随中栏

## 前端路由

| 路由 | 组件 |
|------|------|
| `/quote/:opportunityId/:quotationId` | `views/quote/Workspace.vue` |

## API 端点

### 报价数据
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/quotations/{id}` | `quotationApi.getById` | 加载报价单数据 |
| GET | `/api/quotations/{id}/items` | — | 获取报价单配置项 |
| POST | `/api/quotations/{id}/items` | `quotationApi.saveItems` | 保存配置项 + 配置级字段 |
| POST | `/api/quotations/{id}/export` | `quotationApi.export` | 导出动作：冻结为已导出（盖 exported_at + 落 cost_snapshot） |
| POST | `/api/opportunities/save` | `projectApi.save` | 保存报价（含配置+文件） |

### 导出模板（预览用）
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/univer-templates` | `univerTemplateApi.list` | Excel 模板列表（选择器） |
| POST | `/api/univer-templates/{id}/preview` | `univerTemplateApi.preview` | Excel 预览：填数据返回 workbook_snapshot |
| GET | `/api/spec-templates` | `specTemplateApi.list` | 规格书模板列表（选择器） |
| GET | `/api/spec-templates/preview-data` | `specTemplateApi.getPreviewData` | 规格书预览：按商机/报价单返回 configs（喂 SpecSheet） |

### 配件查询
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/parts` | `partsApi.list` | 配件列表（选择部件） |
| GET | `/api/parts/sections` | `partsApi.sections` | 配件段列表 |
| GET | `/api/parts/categories` | `partsApi.categories` | 配件分类 |
| GET | `/api/parts/{pn}` | `partsApi.get` | 单个配件详情 |

### KP 配件同步/入库
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/quote/kp/history?model=` | `getKpHistory` | 按型号查 KP 价格历史；前端取首条作 db_price，决定按钮显隐与同步/入库分流 |
| POST | `/api/quote/kp/sync-price` | `syncKpPrice` | 同步价格 / 入库新配件（同一接口，后端按型号是否存在分流） |

### 推导引擎
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/derive` | `deriveApi.derive` | 传当前配置状态，返回推导结果 + 约束校验 |

### 系统配置
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/system-config/{key}/value` | `systemConfigApi.getValue` | 系统配置参数（税率/汇率等） |

### 规则
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/rules/export-categories` | `getExportCategories` | 导出分类规则 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `opportunities` | `quotations` | 报价单主表（template_json 存配置） |
| `opportunities` | `quotation_items` | 报价配置项 |
| `l6` | `parts_master` | 配件主数据（查价） |
| `l6` | `base_configs` | 基准配置 |
| `l6` | `config_schemes` | 配置方案 |
| `rules` | `system_config` | 税率/汇率/利润率等参数 |
| `rules` | `matching_rules` | 匹配规则 |
| `kp` | `kp_parts` | KP 配件主数据（报价工作台同步/入库目标） |
| `kp` | `kp_categories` | KP 配件分类（入库时按名查/建） |
| `kp` | `kp_price_history` | KP 配件价格历史（同步/入库都追加一条） |

## 关键组件

- `BomTable.vue` — 左栏 BOM 展示表格（L6 区 + KP 区）
- `UniverSheet.vue` — Excel 模板预览渲染（Univer 实例，非编辑模式）
- `SpecSheet.vue` — 规格书模板预览/打印渲染（白纸文档，多配置一页一配置；复用其 `@media print` 规则做 PDF 导出）
- Pinia store — 配置状态管理（store.configs）

## 注意事项

- `template_json` 是不透明 blob，前端加字段无需改后端
- 推导必须带手填兜底，缺失不阻塞不崩
- 所有业务参数（税率、汇率等）从 system_config 读取，代码不硬编码
- **导出即冻结**：点「下载 Excel」后，前端从 store（`getConfigTotals` + `l6_section_totals` + 汇率/税率）组装 cost_snapshot 并 POST `/quotations/{id}/export`，后端盖 `exported_at` + 落库。冻结后该报价单不再进工作台（在详情页点开只看成本快照 + Excel），编辑需「重新解析」生成新报价单。冻结比实时重算更准——反映导出当时的价格。
- **KP 配件同步/入库**：KP 卡片按钮文案由 db_price 决定——`refreshKpDbPrices` 对每行调 `getKpHistory(model)` 取首条历史为 db_price；型号有历史 →「同步价格」，完全不在库 →「入库新配件」。两者走同一接口 `syncKpPrice`，后端 `kp_repo.insert_price` 按型号查 `kp_parts`：已存在只追加一条价格历史（同步，连 `category` 都不读），不存在才按分类名查/建 `kp_categories` 并新建 part（入库）。**入库分类 = 该 KP 行的 `part_category`**（CPU/GPU/硬盘…，非系统推断，沿用配置里所属的配件分组），为空兜底 `'Key Parts'`。入库落裸记录（仅 name + category_id + 一条价格），品牌/OEM SKU/specs 为空，需事后去管理面补。
