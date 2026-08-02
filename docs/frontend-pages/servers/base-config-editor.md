# 基准配置编辑器 (BaseConfigEditorPage)

> 最后更新：2026-08-02

## 功能概述

基准配置的全页编辑器，左编辑/右摘要双面板布局。

### 核心功能
1. **左侧编辑面板**：
   - 基础信息：名称、系列、机箱形态、盘位、关联 BOM 模板
   - 料件清单：可拖拽排序的料件列表
     - 分类选择（全部/特定分类）
     - 料号选择（PartPicker 组件）
     - 数量设置
     - 添加/删除料件行
2. **右侧摘要面板**：
   - 料件总数
   - 成本合计
   - 功耗合计（TDP）
3. **保存/取消** — 创建或更新基准配置

### 数据流
- 新建模式：空表单
- 编辑模式：加载现有基准配置（含料件列表）
- 料件从 parts_master 表读取
- 分类从 kp_categories 表读取
- BOM 模板从 bom_templates 表读取

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/base-config/:id?` | `views/server-admin/BaseConfigEditorPage.vue` |

参数：
- `id` 为空或 `new` → 新建模式
- `id` 为数字 → 编辑模式

## API 端点

### 基准配置
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/base-configs/{id}` | `baseConfigApi.get` | 获取基准配置详情（含料件） |
| POST | `/api/base-configs` | `baseConfigApi.create` | 创建基准配置 |
| PUT | `/api/base-configs/{id}` | `baseConfigApi.update` | 更新基准配置 |
| PUT | `/api/base-configs/{id}/parts` | `baseConfigApi.setParts` | 替换料件清单 |

### 配件查询
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/parts` | `partsApi.list` | 配件列表 |
| GET | `/api/parts/categories` | `partsApi.categories` | 配件分类 |

### BOM 模板
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/bom-templates` | `bomTemplateApi.list` | BOM 模板列表 |

### 系统配置
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/system-config/server_form_factor/value` | `systemConfigApi.getValue` | 机箱形态选项 |
| GET | `/api/system-config/server_series/value` | `systemConfigApi.getValue` | 服务器系列选项 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `base_configs` | 基准配置主表（name, series, form, bays, bom_template_id, model_id, config_content） |
| `l6` | `base_config_parts` | 基准配置料件（category, pn, quantity） |
| `l6` | `parts_master` | 配件主数据（查价、查功耗） |
| `kp` | `kp_categories` | 配件分类 |
| `l6` | `bom_templates` | BOM 模板 |
| `rules` | `system_config` | 机箱形态/系列枚举 |

## 关键组件

- `PartPicker.vue` — 料号选择器（分类筛选 + 搜索）
- `useSeries()` — 系列选项 composable
- `vuedraggable` — 拖拽排序
