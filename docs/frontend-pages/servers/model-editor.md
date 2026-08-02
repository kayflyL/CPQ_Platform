# 机型产品化包装编辑页 (ModelEditorPage)

> 最后更新：2026-08-02

## 功能概述

机型的产品化包装编辑器，单栏流式布局。承载机型基本信息 + 面向客户的产品内容（介绍/规格），新建/编辑共用同一组件。

### 核心功能
1. **顶栏**：返回 / 标题（新建|编辑）/ 保存
2. **基本信息 + 关联基准配置（一对多·配置变体）**：机型名、类型、生命周期；配置变体卡片网格——每张卡片 设为主配置(radio)/编辑料件(跳基准配置编辑页)/取消关联/内联编辑配置简介（`config_content`：说明+规格差异两段）；「＋」卡片打开选择面板，列出未归属配置、点选即关联。**新建机型保存后留页**才能关联配置（关联需机型 id）
3. **产品主图**：本地上传（走 `/models/image`）或粘贴 URL，带缩略图预览
4. **产品内容**（结构化分块，存 `product_content` JSONB）：
   - **产品概述**：一段话（textarea）
   - **应用场景**：标签式输入（`a-select mode=tags`，输入回车添加），**跨机型联想**（从所有机型历史场景去重作 options）
   - **核心特性**：可增删行（图标 + 描述）
   - **产品规格**：可增删行（规格名 + 规格值，**规格值支持换行**，textarea autosize）

> 已移除字段：用途(use)、一句话简介(description)（前端不再编辑/展示，DB 列保留）

### 数据流
- 新建模式（`/new`）：空表单，类型默认取第一个
- 编辑模式（`/:id`）：`getModel` 加载机型；`listModels` 收集所有机型的应用场景作联想源
- 保存：`create`/`update`，成功后跳 `/servers?refresh=models`（`ServerConfig` 监听后落管理面·机型 tab）

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/models/new` | `views/server-admin/ModelEditorPage.vue` |
| `/servers/models/:modelId/edit` | `views/server-admin/ModelEditorPage.vue` |

`route.params.modelId` 为 `new` 或空 → 新建；为数字 → 编辑。

## API 端点

### 机型
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/models/{id}` | `catalogApi.getModel` | 获取机型（含 base_config + product_content） |
| GET | `/api/server-catalog/models` | `catalogApi.listModels` | 所有机型（收集应用场景联想源） |
| POST | `/api/server-catalog/models` | `catalogApi.createModel` | 新建机型 |
| PUT | `/api/server-catalog/models/{id}` | `catalogApi.updateModel` | 更新机型（含 product_content） |
| POST | `/api/server-catalog/models/image` | — | 上传机型主图（multipart） |

### 关联数据
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/types` | `catalogApi.listTypes` | 类型下拉 |
| GET | `/api/base-configs` | `baseConfigApi.list` | 基准配置下拉（继承参数 + 名称展示） |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_models` | 机型主表（name, server_type_id, base_config_id, lifecycle_status, image_url, **product_content JSONB**） |
| `l6` | `base_configs` | 关联基准配置（JOIN 提供 form/bays/series） |
| `l6` | `server_types` | 类型 |

## 关键约定

- `product_content` 为 JSONB，后端按不透明 blob 透传：`server_catalog_repo._MODEL_FIELDS` 白名单含 `product_content`，写入 `json.dumps` + `CAST AS jsonb`，`_attach_base_config` 读出归一化为 dict（参见 `add_server_model_product_content.sql`）
- `ModelProductContent` 类型见 `api/serverConfig.ts`：`{ overview?, features?: {icon?, text}[], specs?: {key, value}[], scenarios?: string[] }`
- `scenarios` 为 `string[]`，跨机型联想在前端从 `listModels` 结果扁平去重
- 骨架参照 `BaseConfigEditorPage`（顶栏 + `/new`&`:id` 路由复用），但**单栏流式**（非左右分栏）
