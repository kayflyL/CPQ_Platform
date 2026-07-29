# 导出模板管理 (ExportTemplateList)

## 功能概述

管理报价单导出模板，支持两种模板类型：
1. **Univer 模板** — 电子表格引擎，支持字段绑定
2. **规格书模板** — 规格文档模板，支持品牌定制

## 前端路由

| 路由 | 组件 |
|------|------|
| `/export-templates` | `views/ExportTemplateList.vue` |

## 子页面导航

| 操作 | 跳转 |
|------|------|
| 编辑 Univer 模板 | → `/export-templates/univer/:id` |
| 编辑规格书模板 | → `/export-templates/spec/:id` |

---

## Univer 模板 (UniverTemplateEditor)

### 功能
- 基于 Univer 引擎的电子表格模板编辑器
- 用户绑定数据字段到单元格：
  - 静态字段（固定值）
  - 动态字段（从数据源动态获取）
- 支持预览（使用真实商机/报价单数据）
- 字段分组：
  - opportunity（商机信息）
  - config（配置信息）
  - system（系统配置）
  - l6_details（L6 明细）
  - kp_details（KP 明细）
  - config_summary（配置汇总）
- 动态数据源支持列映射和部件选择

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/univer-templates` | `univerTemplateApi.list` | 模板列表 |
| GET | `/api/univer-templates/{id}` | `univerTemplateApi.getById` | 获取模板详情 |
| POST | `/api/univer-templates` | `univerTemplateApi.create` | 创建模板 |
| PUT | `/api/univer-templates/{id}` | `univerTemplateApi.update` | 更新模板 |
| DELETE | `/api/univer-templates/{id}` | `univerTemplateApi.delete` | 删除模板 |
| POST | `/api/univer-templates/{id}/set-default` | `univerTemplateApi.setDefault` | 设为默认模板 |
| POST | `/api/univer-templates/upload` | `univerTemplateApi.uploadExcel` | 上传 Excel 转 Univer snapshot |
| POST | `/api/univer-templates/{id}/preview` | `univerTemplateApi.preview` | 预览填充数据后的 snapshot |

### 字段与数据源
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/fields/scope/{scope}` | `getFieldsByScope` | 按业务域获取字段 |
| GET | `/api/fields/dynamic-sources` | `getDynamicSources` | 获取动态数据源子字段 |
| GET | `/api/opportunities/list` | `opportunityApi.list` | 商机列表（预览选择） |
| GET | `/api/quotations` | `quotationApi.getByOpportunity` | 报价单列表（预览选择） |

### 数据库表
| Schema | 表 | 用途 |
|--------|-----|------|
| `opportunities` | `univer_templates` | Univer 模板主表 |
| `opportunities` | `univer_template_bindings` | 模板字段绑定 |
| `rules` | `fields` | 字段定义 |
| `rules` | `dynamic_source_fields` | 动态数据源字段 |

---

## 规格书模板 (SpecTemplateEditor)

### 功能
- 规格文档模板编辑器
- 品牌定制：
  - Logo 上传
  - 公司名称
  - 主题颜色
- 显示选项：
  - 页眉/页脚配置
  - 章节显示/隐藏
  - 标签自定义（config_subtotal, grand_total）
- 打印预览覆盖层
- 遗留迁移逻辑（config_subtotal 和 grand_total 标签）

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/spec-templates` | `specTemplateApi.list` | 模板列表 |
| GET | `/api/spec-templates/default` | `specTemplateApi.getDefault` | 获取默认模板 |
| GET | `/api/spec-templates/{id}` | `specTemplateApi.getById` | 获取模板详情 |
| POST | `/api/spec-templates` | `specTemplateApi.create` | 创建模板 |
| PUT | `/api/spec-templates/{id}` | `specTemplateApi.update` | 更新模板 |
| DELETE | `/api/spec-templates/{id}` | `specTemplateApi.delete` | 删除模板 |
| POST | `/api/spec-templates/{id}/set-default` | `specTemplateApi.setDefault` | 设为默认模板 |
| POST | `/api/spec-templates/{id}/copy` | `specTemplateApi.copy` | 复制模板 |
| POST | `/api/spec-templates/upload-logo` | `specTemplateApi.uploadLogo` | 上传 Logo 图片 |
| GET | `/api/spec-templates/preview-data` | `specTemplateApi.getPreviewData` | 获取真实预览数据 |

### 数据库表
| Schema | 表 | 用途 |
|--------|-----|------|
| `rules` | `spec_templates` | 规格书模板主表 |

---

## 关键组件

- `UniverTemplateEditor.vue` — Univer 模板编辑器（字段绑定 + 预览）
- `SpecTemplateEditor.vue` — 规格书模板编辑器（品牌 + 显示选项）
- `FieldBindingPanel.vue` — 字段绑定面板
- `PreviewOverlay.vue` — 预览覆盖层
