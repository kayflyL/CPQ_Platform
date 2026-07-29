# 服务器管理 Tab (Admin Tabs)

> 最后更新：2026-07-27

## 功能概述

服务器管理后台（`/servers/admin`，宿主组件 `ServerAdminPage.vue`）下三个 Tab 的管理界面。入口与路由见 [server-admin.md](server-admin.md)。

## Tab 1: 料号库 (PartsLibrary)

### 功能
- 配件列表（卡片/表格视图切换）
- 分类筛选（两级：section + category）
- 新增/编辑/删除配件
- 编辑表单字段：料号 PN / 名称 / **规格**（自由文本规格串，如 `PCBA_3.5''_Triple-mode`）/ **说明**（人话用途介绍，给不熟悉的同事看）/ 部段 / 类别 / 单价 / 扩展属性
- 扩展属性（schema-driven：enum-single, enum-multi, free-tags, number, text）—— 结构化规格存 `specs` JSONB（wattage/tdp/io_slot/chassis…）
- 按 section/category/chassis/series 筛选
- 搜索（料号/名称/规格/说明）

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/parts` | `partsApi.list` | 配件列表（筛选+搜索） |
| GET | `/api/parts/sections` | `partsApi.sections` | 段列表 |
| GET | `/api/parts/categories` | `partsApi.categories` | 分类列表 |
| POST | `/api/parts` | `partsApi.create` | 创建配件 |
| PUT | `/api/parts/{pn}` | `partsApi.update` | 更新配件 |
| DELETE | `/api/parts/{pn}` | `partsApi.delete` | 删除配件 |

### 数据库表
| Schema | 表 |
|--------|-----|
| `l6` | `parts_master` |
| `l6` | `part_sections` |
| `kp` | `kp_categories` |
| `kp` | `kp_parts` |
| `kp` | `kp_part_specs` |

---

## Tab 2: 基准配置 (BaseConfigBuilder + BomTemplateManager)

### BaseConfigBuilder 功能
- 基准配置列表
- 快速创建基准配置
- 跳转编辑器（→ `/servers/base-config/:id`）
- 展示：名称、系列、机箱形态、盘位、料件数、总价

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/base-configs` | `baseConfigApi.list` | 基准配置列表 |
| DELETE | `/api/base-configs/{id}` | `baseConfigApi.delete` | 删除基准配置 |

### BomTemplateManager 功能
- BOM 模板列表
- 创建/编辑/删除 BOM 模板
- 模板内容管理（料件清单）
- 每行定义：type/label/slot/mode + 解析规则（desc/qty 计算逻辑）
- 规则支持 primary + fallback
- 模板关联到基准配置（bom_template_id）
- 拖拽排序行
- 查看模板使用情况（有多少 base_config 在用）

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/bom-templates` | `bomTemplateApi.list` | BOM 模板列表 |
| GET | `/api/bom-templates/{id}` | `bomTemplateApi.get` | 获取模板详情 |
| GET | `/api/bom-templates/for-base-config/{id}` | `bomTemplateApi.getForBaseConfig` | 获取基准配置关联的模板 |
| GET | `/api/bom-templates/{id}/usage` | — | 统计模板使用情况 |
| POST | `/api/bom-templates` | `bomTemplateApi.create` | 创建 BOM 模板 |
| PUT | `/api/bom-templates/{id}` | `bomTemplateApi.update` | 更新 BOM 模板 |
| DELETE | `/api/bom-templates/{id}` | `bomTemplateApi.delete` | 删除 BOM 模板 |

### 数据库表
| Schema | 表 |
|--------|-----|
| `l6` | `base_configs` |
| `l6` | `base_config_parts` |
| `l6` | `bom_templates` |
| `l6` | `bom_template_rows` (JSONB rules) |

---

## Tab 3: 机型管理 (ModelManager)

### 功能
- 服务器类型管理（CRUD）
- 机型管理：**列表卡片 + 删除**；新建/编辑跳独立编辑页 `ModelEditorPage`（→ `/servers/models/:id/edit`、`/new`），不再用 modal（详见 [model-editor.md](model-editor.md)）
- 类型-机型层级关系
- 机型关联基准配置
- 卡片网格展示：生命周期 chip、主图、形态/盘位/系列（继承自 base_config）、基准配置名
- 生命周期状态（new/active/eol/discontinued）
- 机型继承技术规格（form/bays/series）从关联的基准配置
- 图片上传支持（主图）
- 机型字段：name, type, lifecycle_status, image_url, **product_content**（产品化包装 JSONB：概述/应用场景/核心特性/产品规格）
- 已移除前端字段：use、description（DB 列保留）

### API 端点
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/types` | `catalogApi.listTypes` | 类型列表 |
| POST | `/api/server-catalog/types` | `catalogApi.createType` | 创建类型 |
| GET | `/api/server-catalog/models` | `catalogApi.listModels` | 机型列表 |
| POST | `/api/server-catalog/models` | `catalogApi.createModel` | 创建机型 |
| PUT | `/api/server-catalog/models/{id}` | `catalogApi.updateModel` | 更新机型 |
| DELETE | `/api/server-catalog/models/{id}` | `catalogApi.deleteModel` | 删除机型 |
| POST | `/api/server-catalog/models/image` | — | 上传机型图片（multipart） |
| GET | `/api/server-catalog/model-image/{filename}` | — | 读取机型图片 |
| GET | `/api/base-configs` | `baseConfigApi.list` | 基准配置列表（关联选择） |

### 数据库表
| Schema | 表 |
|--------|-----|
| `l6` | `server_types` |
| `l6` | `server_models` |
| `l6` | `base_configs` |
