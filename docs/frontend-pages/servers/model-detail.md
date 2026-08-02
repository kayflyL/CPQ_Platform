# 机型产品详情页 (ModelDetailPage)

> 最后更新：2026-08-02

## 功能概述

配置面的机型产品展示页。用户从机型目录点「查看详情」进入，浏览产品介绍/规格后点「配置这台服务器」进配置向导。**纯展示，无管理入口**（编辑只从管理面 ModelManager → ModelEditorPage 进）。

### 核心功能
1. **面包屑** — 返回机型目录（按机型的 server_type_id 回 `/servers/types/:typeId`）
2. **全宽日出场景 Hero** — 不局限卡片，铺满网页上半部分；天空/旭日地平线/大地三层场景构图。严格 z 序（后→前）：
   - 背景：天空→大地 垂直渐变（4 主题堆叠 opacity 过渡 0.7s：酒红/深蓝/纯黑/暗紫）
   - 水印：系列类别名（`seriesLabel`，后台 `server_series` 可改；白色 0.06 铺底）
   - 天空光晕：旭日映亮地平线上方（`radial-gradient` + `--sun-glow`）
   - 旭日辉光：扁椭圆贴地平线（`radial-gradient(ellipse)` `--sun-bright`→`--sun-color`），中心落于地平线、上半映亮天空下半被大地遮、`blur(12px)` 重模糊柔化——换图挡不住也只是地平线辉光，不再有突兀硬圆球
   - 大地遮罩：地平线下方 30%，盖太阳下半 + 加深大地（`--earth-overlay`）
   - 地面光晕：地平线下方旭日投射（`--sun-glow` 椭圆扩散），照亮倒影区域
   - 倒影：大地上的镜像，`scaleY(-1)` + opacity 0.6 + blur 2px + mask 58% 淡出
   - **旭日地平线光带**：切割服务器与倒影；横贯、中间最亮（`--sun-bright`）两端渐弱（`--sun-color`），多层 box-shadow 发光，如日出之光
   - 服务器：放大居中（540px / 64vw），底部立于地平线
   - 右上角生命周期徽标 + 左上角返回 + 底部 4 主题切换（机型名已并入下方信息卡）
   - 主题三色（`sun`/`sunBright`/`glow`）+ 大地遮罩集中在 `STAGE_THEMES` 常量；天际线光色随主题协同（酒红=橙红日出、深蓝=蓝光、纯黑=白光、暗紫=紫光）；水印文字来自后端可在后台更改
3. **机型信息卡 + CTA 行** — 展台下方独立玻璃浅卡：机型名（`model.name`）+ 形态/盘位/系列（继承自 base_config）+「配置这台服务器」CTA
4. **产品概述** — 一段话（overview）
5. **应用场景** — 标签云（scenarios 标签数组）
6. **核心特性** — 图标玻璃卡网格：外层透明容器避玻璃嵌套，每项独立 `glass-light` 卡（hover 蓝边 + 上浮），图标 `accent-gradient` 圆形底白字，无 icon 用品牌色圆点兜底
7. **产品规格** — 精致双列表：行 hover 高亮（`--cpq-overlay-a8`）、value 字重 500、分隔线细化；值保留换行 `white-space: pre-wrap`
8. **空内容兜底** — 机型未补充任何 product_content 时提示

### 数据流
- `getModel` 加载机型（含 base_config 主配置单对象 + `configs[]` 所有变体 + product_content）
- 配置变体卡片（产品概述下方）：每个配置一张卡片，点击展开看该配置的说明 + 规格差异（`config_content`）；机型级 product_content（概述/场景/特性/规格）在上方固定
- 点「配置这台服务器」→ `/servers/config/:modelId`（走主配置，本期不在向导内切变体）
- **无编辑入口**（配置面纯展示；配置变体归属与简介在管理面机型编辑页维护）

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/models/:modelId` | `views/server-config/ModelDetailPage.vue` |

## API 端点

| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/models/{id}` | `catalogApi.getModel` | 获取机型详情（base_config + product_content） |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_models` | 机型（含 product_content JSONB） |
| `l6` | `base_configs` | JOIN 提供 form/bays/series |

## 关键约定

- **信息架构**：机型目录（`ServerModelsPage`）→ **本详情页** → 配置向导（`ConfigWizardPage`）。机型目录卡片不再直进配置，先看详情。
- 展示字段读取 `product_content` 结构（`ModelProductContent` 类型），某块为空则对应区块不渲染；全空显兜底提示
- 产品规格值支持换行：编辑页 textarea 录入，本页 `white-space: pre-wrap` 渲染
