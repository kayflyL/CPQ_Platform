# 配件管理 (Parts)

## 功能概述

独立的配件管理页面（kp 模块），覆盖配件完整 CRUD + 总览看板 + 数据洞察。

### 核心功能
1. **总览仪表盘**（选中「全部」且非清单模式时显示）
   - 统计卡：配件总数（含每周新增 sparkline）、本周新增、有效价格配件、**疑似重复**（可点击进 drawer）
   - 最近新入库 / 最近更新价格 两栏
2. **分类侧栏** — 扁平分类列表（含计数）+ 分类管理 modal（增删改）
3. **配件列表** — 卡片/表格视图切换、搜索（名称/SKU/品牌）、排序（名称/价格）、品牌多选、价格记录筛选（有报价/≥3条/暂无）、规格维度 chips 多选
4. **数据洞察工具**（工具栏按钮 + 抽屉，按需打开）：
   - **比价矩阵**：需先选分类，按某 spec_key 分组的价格分布（表格 + 箱线图切换）
   - **价格异动**：最新价 vs N 天前涨跌幅 TOP（涨幅/跌幅双栏，7/30 天切换，打开时 lazy 加载）
5. **配件详情抽屉** — 基础信息、规格参数、价格历史（含趋势折线图）、兼容机型
6. **CRUD** — 配件 / 价格记录 / 分类 的增删改
7. **批量导入导出** — Excel 导入预览（新增/更新/冲突）+ 模板下载 + 导出
8. **疑似重复检测** — drawer 展示重复组（不做自动合并，仅人工核实）

## 前端路由

| 路由       | 组件                      |
| -------- | ----------------------- |
| `/parts` | `views/admin/Parts.vue` |

## API 端点

所有接口挂在 `/api/admin/kp/*` 下（FastAPI 路由集中在 `backend/app/api/admin.py`，业务在 `backend/app/repository/kp_repo.py`）。

### 总览 / 数据洞察
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/admin/kp/stats` | 仪表盘统计（总数/本周新增/有效价格/每日新增序列/最近入库/最近调价） |
| GET | `/api/admin/kp/price-movers?days=&limit=` | 价格异动：最新价 vs N 天前涨跌幅 TOP（涨幅/跌幅各 N） |
| GET | `/api/admin/kp/price-matrix?category_id=&group_key=` | 比价矩阵：同分类按 spec_key 分组（min/Q1/median/Q3/max + 明细） |
| GET | `/api/admin/kp/parts/duplicates` | 疑似重复检测（oem_sku/alt_sku 精确 + 名称 difflib 相似度） |

### 分类 / 品牌 / 规格维度
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/admin/kp/categories` | 分类计数（旧接口，返回 {category, count}） |
| GET | `/api/admin/kp/categories/all` | 分类全量（含 id/name/parent_id/icon/sort_order） |
| POST / PUT / DELETE | `/api/admin/kp/categories[/{id}]` | 分类增删改 |
| GET | `/api/admin/kp/brands?category_id=` | 品牌聚合 + 计数 |
| GET | `/api/admin/kp/spec-facets?category_id=` | 规格维度聚合 {spec_key: [{value, count}]} |

### 配件 CRUD
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/admin/kp/parts` | 分页列表（筛选：category_id/search/brands/price_filter/specs；排序：name/price/updated_at） |
| GET | `/api/admin/kp/parts/{id}` | 配件详情（含规格/价格历史/兼容机型） |
| POST / PUT / DELETE | `/api/admin/kp/parts[/{id}]` | 配件增删改 |

### 价格历史
| 方法 | 路径 | 用途 |
|------|------|------|
| POST | `/api/admin/kp/parts/{id}/prices` | 为配件新增报价 |
| PUT / DELETE | `/api/admin/kp/prices/{id}` | 报价改/删 |

### 批量导入 / 导出
| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/admin/kp/parts/import-template` | 下载导入模板（含高频规格列） |
| GET | `/api/admin/kp/parts/export?category_id=` | 导出全部配件为 xlsx |
| POST | `/api/admin/kp/parts/import?dry_run=` | 批量导入（dry_run=true 返回预览，false 写入） |

## 数据库表（kp schema）

| 表 | 用途 |
|-----|------|
| `kp_categories` | 分类（支持 parent_id 层级，当前 UI 扁平） |
| `kp_parts` | 配件主表（oem_sku/alt_sku/brand/name/condition/lead_time/image_url/datasheet_url/moq/applicable） |
| `kp_part_specs` | 规格键值对（按分类差异化） |
| `kp_price_history` | 价格历史（price/currency/price_date/note/source） |
| `kp_part_compat` | 兼容机型关联 |
| `kp_part_related` | 关联配件推荐（表已建，前端尚未消费） |

> 最新价统一口径：`price_date DESC NULLS LAST, id DESC`（全项目 KP 取价一致语义）。

## 关键组件

- `views/admin/Parts.vue` — 配件管理主页面（列表+看板+洞察）
- `components/server-admin/PartsLibrary.vue` — 配件库管理组件（与服务器页共用）
- `components/common/PartPicker.vue` — 料号选择器
- 图表：`vue-echarts` + `useChartTheme`（LineChart 趋势、BoxPlotChart 比价矩阵、Sparkline 总览）

## 数据洞察实现要点

- **价格异动**：后端一次拉全量价格历史按 part_id 分组，Python 内找"最新价 + N 天前最近一条"算 delta%。极端值（历史跨度大）可能出现大幅涨跌，属数据特性。
- **比价矩阵**：后端按 spec_key 分组聚合，四分位数用 Python `statistics.quantiles(n=4, method='inclusive')`；前端箱线图数据格式 `[min, Q1, median, Q3, max]`。某分组仅 1 件时退化为一条线（echarts 原生支持）。
- **疑似重复**：Union-Find 合并命中对。强信号 = oem_sku/alt_sku 精确相等（跨字段也算）；弱信号 = 同分类下 `difflib.SequenceMatcher.ratio() >= 0.6`。桶 > 500 件时按 name 前缀再分小桶防 O(n²) 爆炸。阈值偏宽时噪声多，可调 `threshold`（当前硬编码 0.6）。

## 注意事项

- 配件数据量较大，列表分页加载；总览统计走独立聚合接口
- 图表色必须走 `useChartTheme`（canvas 读不到 CSS 变量）
- 配件与 l6 模块的 `parts_master` 是**两套独立数据**，本页面只管 kp 模块
- `kp_part_related` 表已建但前端未接，是后续"关联配件推荐"功能的预留位
