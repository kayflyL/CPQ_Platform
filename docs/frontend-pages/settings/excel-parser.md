# Excel 解析器 (ExcelParser)

> 最后更新：2026-07-29

## 功能概述

Excel 报价单解析配置页面，管理解析规则和区域映射。

### 核心功能
1. **解析区域配置** — 定义 Excel 中不同区域的解析规则：
   - 区域名称（如"基本信息"、"配置清单"、"价格汇总"）
   - 起始单元格（如 A1）
   - 结束单元格（如 Z100）
   - 解析模式（header_row, data_rows, summary）
2. **字段解析规则** — 定义每个字段的提取逻辑：
   - 字段名（如 customer_name, platform_type）
   - 提取方式（cell_ref, column_search, formula）
   - 单元格引用或列搜索关键词
   - 数据类型转换
3. **预览解析** — 上传 Excel 测试解析效果
4. **业务字段映射** — 将 Excel 字段映射到系统字段

> 页面现已瘦身：解析逻辑抽到 `useExcelParser` composable（模块级单例），热力图与规则编辑抽为 `ParseHeatmapPreview` / `ParseRulesEditor` 子组件。**这套规则与组件被商机详情页的上传解析预览复用**（`QuotationParsePreviewModal`，见 `opportunities/detail.md`）——商机上传报价单时弹预览窗、在窗内调规则即改此处的全局规则。

## 前端路由

| 路由 | 组件 |
|------|------|
| `/excel-parser` | `views/ExcelParser.vue` |

## API 端点

### 解析区域
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/rules/parse-regions` | — | 获取所有解析区域配置 |
| POST | `/api/rules/parse-regions` | — | 批量保存解析区域 |
| PUT | `/api/rules/parse-regions/{region_id}` | — | 更新单个解析区域 |
| DELETE | `/api/rules/parse-regions/{region_id}` | — | 删除解析区域 |

### 字段规则
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/rules/parse-field-rules` | — | 获取所有字段解析规则 |
| POST | `/api/rules/parse-field-rules` | — | 批量保存字段规则 |
| PUT | `/api/rules/parse-field-rules/{rule_id}` | — | 更新单个字段规则 |
| DELETE | `/api/rules/parse-field-rules/{rule_id}` | — | 删除字段规则 |

### 预览与测试
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/rules/excel-parser-preview` | — | 使用新 ExcelParser 引擎预览解析 |
| POST | `/api/rules/parse-preview` | — | 解析 Excel 用于热力图预览 |

### 业务字段
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/admin/business-fields` | — | 列出所有业务字段 |
| POST | `/api/admin/business-fields` | — | 新增业务字段 |
| PUT | `/api/admin/business-fields/{field_key}` | — | 更新业务字段 |
| DELETE | `/api/admin/business-fields/{field_key}` | — | 删除业务字段 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `rules` | `parse_regions` | 解析区域定义 |
| `rules` | `parse_field_rules` | 字段解析规则 |
| `rules` | `business_fields` | 业务字段定义 |
| `rules` | `dynamic_source_fields` | 动态数据源字段 |
| `rules` | `field_references` | 字段引用关系 |
| `rules` | `field_audit_logs` | 字段审计日志 |
| `rules` | `field_usage_stats` | 字段使用统计 |

## 关键组件

- `useExcelParser.ts` — 解析逻辑单例 composable（规则加载 / 文件预览 / 区域·字段规则·KP 映射 CRUD）
- `ParseHeatmapPreview.vue` — 热力图预览（取值着色 + 来源 tooltip，纯展示）
- `ParseRulesEditor.vue` — 区域边界 + 字段取值列 + KP 分类映射编辑器（含编辑弹窗）

## 注意事项

- 解析规则修改后需要重新测试预览
- 业务字段定义影响整个系统（报价单、导出模板等）
- 解析引擎支持多种模式：cell_ref（单元格引用）、column_search（列搜索）、formula（公式）
