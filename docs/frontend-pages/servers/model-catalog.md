# 机型目录页 (ServerModelsPage)

## 功能概述

展示某服务器类型下的所有机型，点击进入配置向导。

### 核心功能
1. **面包屑导航** — 返回服务器类型列表
2. **3D 机型总览** — ModelShowcase 组件（根据类型渲染不同 3D 场景）
3. **机型卡片网格** — 点击卡片进机型产品详情页（`/servers/models/:id`），卡片展示：
   - 机型名称、机箱形态（form factor tag）
   - 盘位数量
   - 「查看详情 →」按钮（整张卡片可点）

> 卡片不再直进配置向导，而是先进机型产品详情页（[ModelDetailPage](model-detail.md)）看介绍/规格，再由详情页「配置这台服务器」进配置向导。

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/types/:typeId` | `views/ServerModelsPage.vue` |

## API 端点

| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/types` | `catalogApi.listTypes` | 获取所有类型（找到当前类型） |
| GET | `/api/server-catalog/models?type_id={id}` | `catalogApi.listModels` | 获取该类型下所有机型 |
| GET | `/api/server-catalog/models/{model_id}` | `catalogApi.getModel` | 获取机型详情 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_types` | 服务器类型信息 |
| `l6` | `server_models` | 机型列表（含 base_config 关联） |
| `l6` | `base_configs` | 基准配置（读取 form/bays 信息） |

## 关键组件

- `ModelShowcase.vue` — 3D 机型展示（根据类型匹配不同场景配置）
- `showcase-config.ts` — 展示场景匹配配置
