# 服务器配置门户 (ServerConfig)

> 最后更新：2026-09-18（整页固定暗色，不随主题切换）

## 功能概述

服务器模块面向销售/客户的产品入口：**旭日舞台 banner（标题 + 类型胶囊快捷入口）→ 全部机型货架 → 机型详情 → 配置向导**。
banner 场景配方复用机型详情页 hero 骨架，**深蓝「银河 · 擎天」主题**（银河=斜跨天空的星带+星点+全天星野，擎=擎天光柱；不随胶囊换色）；**整页（banner+货架）固定暗色**（深海蓝渐变，自带 token 不引用 `--cpq-*` 主题变量），与机型详情页一致、**不受主题切换开关影响**（顶栏经 `hero-dark` 机制切浅色文字）。
banner 的**标题/轮播图可配**（管理后台「门户设置」tab，存 `system_config.server_portal_banner`）：**banner 只显示一行大标题（30px 玻璃渐变字）= 当前图的副标题**，没配副标题的图回落「主标题」文案（主标题留空再回落内置默认），随轮播切换淡入淡出；传了图则以**详情页产品图同款**立于地平线（min(540px,64vw) contain + 投影 + **镜像倒影**），左右箭头切换（如车驶入的节奏，~1.15s），银河场景始终可见，不传图只有银河场景。
管理维护功能已拆到独立的管理后台（[ServerAdminPage](server-admin.md)，`/servers/admin`）。

### 核心功能
- **banner（全幅，约 460px）**：
  - 场景图层（z 序）：深蓝天空渐变 → SERVERS 水印 → 银河星带（斜 -26°，蓝白为主+核心暖光，重模糊）→ 带内星点（顺带密集，闪烁）→ 全天星野（稀疏，慢闪）→ 擎天光柱×3（自地平线升起，中间主柱最亮）→ 天空光晕 → 旭日辉光（#5BB8FF）→ 大地遮罩 → 地面光晕 → **轮播倒影层**（镜像+渐隐 mask+blur，z 在大地之上、地平线之下）→ 地平线光带 → **轮播主图层**（详情页产品图同款立地平线+投影）→ 标题/胶囊 → 两侧箭头（骨架承 ModelDetailPage `.hero-scene`，去掉服务器本体/主题切换；闪烁/滑动动画尊重 prefers-reduced-motion）
  - **轮播传送带方向恒定**（纯按钮驱动，不随循环索引回弹）：点左箭头旧图向左驶离、新图从右 banner 边缘驶入（带左移）；点右箭头反之。轨道偏移 ±110vw 保证画面外起停；n=2 同样恒定。入场图先无动画瞬移到入场侧（no-anim + nextTick）再放开动画驶入
  - 标题「配置一台服务器」天空区居中；副标题=当前图自带文案（`sub-swap` 淡入淡出 ~0.3s，空不渲染）
  - **类型胶囊**（`scene-capsule`）：底部居中，玻璃胶囊按钮（配方同详情页 `scene-switch-btn`），文案=类型名+该类型上架机型数；**点击跳类型目录页**（纯导航，无激活态）
- **全部机型货架**（banner 下方，固定暗色）：`ServerModelCard`（`dark` 变体：主图 + 机型名 + 类型 + **tagline 一句话** + 形态/盘位/系列），点卡直达机型详情；标题右侧显示机型计数。**只展示上架机型**（`published_only`）；0 台上架时整段隐藏
- 货架卡 tagline 取 `product_content.tagline`，为空（机型内容未填）不占位
- 旧「类型大卡片」已删除（压成 banner 胶囊）

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers` | `views/ServerConfig.vue`（薄壳，banner 全幅由 ModelCatalog 自管） |

## 子页面导航（配置流程）

| 步骤 | 路由 |
|------|------|
| ① 按类型浏览 | `/servers/types/:typeId`（[机型目录页](model-catalog.md)，3D 展示在此） |
| ② 看机型产品详情 | `/servers/models/:modelId`（[ModelDetailPage](model-detail.md)） |
| ③ 配置这台服务器 | `/servers/config/:modelId`（配置向导） |

> 货架卡直达 ②，熟客可跳过 ①；胶囊直达 ①。②③ 左上角「返回」按钮：有站内来路（如本页货架直达）原路返回来源页；直接打开 URL 才回退到机型目录 ①。

## 关键组件

| 组件 | 用途 |
|------|------|
| `ModelCatalog.vue` | 门户主体：旭日舞台 banner + 类型胶囊 + 全部机型货架 |
| `ServerModelCard.vue` | 机型卡公共组件（门户货架 `show-tagline`；管理面/目录页无 tagline） |

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/server-catalog/types` | 类型胶囊 + 货架卡类型名 |
| GET | `/api/server-catalog/models?published_only=1` | 货架：只取上架机型（同时算各类型计数） |
| GET | `/api/server-catalog/portal-banner` | banner 标题/轮播图+每图副标题（system_config，未配置返回空对象） |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_types` | 服务器类型 |
| `l6` | `server_models` | 机型（含 `product_content` JSONB、`is_published` 上架开关） |
