# 机型目录页 (ServerModelsPage)

> 最后更新：2026-09-21（内容不满一屏时 min-height:100vh 盖满防露主题底；返回钮 !important 压 antd token）

## 功能概述

展示某服务器类型下的所有机型，点击进机型产品详情页。**整页固定暗色**（深海蓝渐变 + 固定文字 token，不引用 `--cpq-*` 主题变量），与机型详情页一致、不受主题切换开关影响（顶栏经 `hero-dark` 机制切浅色文字）；3D 展示区 ModelShowcase 同步固定暗色（不再用主题 `.glass`）。**满高保障**：机型少页面不足一屏时 `min-height:100vh` 盖满（负 margin 已把页顶到 y=0），否则露出 `.main-scroll` 的浅色主题渐变；返回钮文字 `color … !important`（同详情页 `.scene-back`，压过 antd 按钮主题 token，浅色主题下不再是深字）。

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
| GET | `/api/server-catalog/models?type_id={id}&published_only=1` | `catalogApi.listModels` | 获取该类型下所有**上架**机型（`is_published=false` 的下架机型由管理面控制，货架不出现） |
| GET | `/api/server-catalog/models/{model_id}` | `catalogApi.getModel` | 获取机型详情 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_types` | 服务器类型信息 |
| `l6` | `server_models` | 机型列表（含 base_config 关联） |
| `l6` | `base_configs` | 基准配置（读取 form/bays 信息） |

## 关键组件

- `ModelShowcase.vue` — 3D 机型展示（根据类型匹配不同场景配置；固定暗色）
- `ServerModelCard.vue` — 机型卡公共组件（本页/门户货架传 `dark` 用固定暗色变体；管理面不传走主题玻璃）
- `showcase-config.ts` — 展示场景匹配配置

## 移动端（≤640px，2026-09-19）

- banner 类型胶囊 `.scene-capsule`：从「绝对居中 + wrap（375px 一行一枚竖叠三行）」改为单行等宽三枚（left/right 12px 定位、cap-btn flex 1 1 0 + 11px 字号 + 超长省略）。
- 机型货架 `.sc-models`：minmax(260px,1fr) 单列 → 两列 `repeat(2, minmax(0,1fr))` gap 10；页边 padding 24→12。
- 机型目录子页（ServerModelsPage.vue `.models-grid`）同款两列处理。
