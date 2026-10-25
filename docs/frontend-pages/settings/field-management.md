# 字段管理 (FieldManagement)

## 功能概述

统一的字段管理页面，管理系统中所有业务字段的定义、作用域、组件映射等。

### 核心功能
1. **字段列表** — 展示所有业务字段：
   - 字段名（field_key）
   - 显示标签（label）
   - 数据类型（text, number, date, enum, etc.）
   - 作用域（scope）
   - 页面（page）
   - 是否必填
   - 默认值
2. **字段编辑** — 创建/更新/删除字段定义
3. **作用域管理** — 定义字段在哪些业务域中使用：
   - opportunity（商机）
   - quotation（报价单）
   - config（配置）
   - export（导出）
4. **页面管理** — 定义字段在哪些页面显示：
   - opportunity-detail（商机详情）
   - workspace（工作台）
   - export-template（导出模板）
5. **组件映射** — 定义字段使用哪种 UI 组件渲染：
   - input（文本输入）
   - select（下拉选择）
   - autocomplete（自动完成）
   - date-picker（日期选择器）
   - number-input（数字输入）
6. **动态数据源** — 配置字段的动态数据源：
   - 数据源类型（API, static, formula）
   - 数据源配置
   - 子字段映射

## 前端路由

| 路由 | 组件 |
|------|------|
| `/settings/fields` | `views/settings/FieldManagement.vue` |

## API 端点

### 字段管理
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/admin/business-fields` | — | 列出所有业务字段 |
| POST | `/api/admin/business-fields` | — | 新增业务字段 |
| PUT | `/api/admin/business-fields/{field_key}` | — | 更新业务字段 |
| DELETE | `/api/admin/business-fields/{field_key}` | — | 删除业务字段 |
| GET | `/api/admin/business-fields-export` | — | 导出字段定义 |
| POST | `/api/admin/business-fields-import` | — | 导入字段定义 |

### 字段查询
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/fields/scope/{scope}` | `getFieldsByScope` | 按业务域获取字段 |
| GET | `/api/fields/page/{page}` | `getFieldsByPage` | 按页面获取字段 |
| GET | `/api/fields/dynamic-sources` | `getDynamicSources` | 获取动态数据源子字段 |
| GET | `/api/fields/type-keywords` | `getTypeKeywords` | 获取部件类型关键词映射 |
| GET | `/api/fields/component-mapping` | `getComponentMapping` | 获取组件映射 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `rules` | `business_fields` | 业务字段定义主表 |
| `rules` | `dynamic_source_fields` | 动态数据源字段 |
| `rules` | `field_references` | 字段引用关系 |
| `rules` | `field_audit_logs` | 字段审计日志 |
| `rules` | `field_usage_stats` | 字段使用统计 |

## 关键字段结构

```typescript
interface BusinessField {
  field_key: string;        // 唯一标识
  label: string;            // 显示标签
  data_type: string;        // 数据类型
  scope: string[];          // 作用域列表
  page: string[];           // 页面列表
  required: boolean;        // 是否必填
  default_value: any;       // 默认值
  options?: any[];          // 选项（enum 类型）
  validation?: any;         // 验证规则
  component?: string;       // UI 组件类型
  dynamic_source?: string;  // 动态数据源配置
}
```

## 注意事项

- 字段修改会影响整个系统（商机、报价单、导出模板等）
- 字段定义是全局的，作用域和页面控制显示范围
- 动态数据源支持从 API 或公式动态获取选项
- 字段审计日志记录所有修改历史
- 导入/导出支持批量管理字段定义
