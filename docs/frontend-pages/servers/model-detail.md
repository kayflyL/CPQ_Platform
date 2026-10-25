# 机型产品详情页 (ModelDetailPage)

> 最后更新：2026-09-30（铭牌卡新增「下载资料」PDF 入口，读 product_content.docs）

## 功能概述

配置面的机型产品展示页（R5.3 暗色「数据/技术派」设计，原型 `docs/prototypes/服务器详情页-讲价值方案.html` 的落地）。用户从机型目录点「查看详情」进入，浏览产品介绍/规格后点「配置这台服务器」进配置向导。**纯展示，无管理入口**（编辑只从管理面 ModelManager → ModelEditorPage 进）。

### 核心功能
1. **返回** — 有站内来路（如从服务器门户货架直达）原路返回来源页；直接打开 URL 才按 server_type_id 回 `/servers/types/:typeId`
2. **全宽日出场景 Hero（用户设计，勿改）** — 天空/旭日地平线/大地三层场景构图，四主题（酒红/深蓝/纯黑/暗紫）切换。z 序：主题渐变层堆叠 opacity 过渡 → 系列名水印（`seriesLabel`）→ 天空光晕 → 旭日辉光 → 大地遮罩 → 地面光晕 → 倒影 → 旭日地平线光带 → 服务器立地平线；右上生命周期徽标、左上返回、底部主题切换
3. **铭牌信息卡**（叠 Hero 下缘 -34px，玻璃暗卡 + 顶部天幕光线）— mono 机型名 + 一句话定位（tagline，主题亮色）+ mono 形态/盘位/系列三格 +「配置这台服务器」工业蓝 CTA（#1677FF）+ **「下载资料」入口**（`product_content.docs`：1 份=幽灵按钮直下、多份=a-dropdown 逐份、0 份不渲染；走 `downloadOfficeFile` 带 Authorization 的 blob 下载——裸 `<a href>` 直链 AUTH_ENABLED 下 401）
4. **产品概述** — 章节头（mono kicker `Overview` + 大标题 + 右侧灰提示），一段话 overview
5. **为什么选它**（Highlights）— 发丝线 ruled list（非卡片矩阵）：每条 = 短标题（160-230px 栏）+ 一句话，行 hover 微亮
6. **产品能力**（Capabilities）— **全幅暗色带**（`band-dark`，`--band-bg` 主题联动 + 顶部天幕光线），组件 `components/server-config/CapabilityShowcase.vue`（2026-09-28 重构，原型 `docs/prototypes/机型详情-产品能力点选介绍-原型v4.html`）。n8n 式「左选右显」：**左栏** = 维度 logo（`capIcons` 发丝线图标 42px）+ 维度名 + mono 英文小字，激活态主题色竖条 + 微亮面板 + 底部进度条；**右侧** = 玻璃面板两栏 —— 内容列（mono kicker 英文 + 大标题 + 主题色短划线 + 介绍段 + metrics 大数字列 28px mono）+ 取景框舞台（点阵底 + 主题辉光 + 暗角 + 四角刻度 + 右下 mono 角标 `EN · 01/06`），舞台内为该维度 `icon` key 映射的**参数化硬件特写插画**（chip=CPU 晶格 / slots=插卡槽 / net=网口流线 / drive=25 盘位阵列 / term=管理终端 / fan=风扇墙+电源；未知键回落 chip，SMIL 脉冲/闪烁/旋转，`prefers-reduced-motion` 全静止）。自动轮播 4.5s 悬停暂停点击直达，`:key` 重挂载重放入场动画。文字/数字全部来自 `capabilities` 现有字段（编辑器零改动），插画是展示层常量
7. **场景适配**（Scenarios）— 照片卡 `.scn-grid` 一行四卡（760px 2 列 / 480px 1 列）：16:10 配图（`object-fit:cover` + `saturate(.82) brightness(.86)` 压暗融入，hover scale 1.045 提亮）+ 名称 + 一句话 fit；无图整块不渲染（正文顶到卡边），编辑指导文案不进展示页（填写提示只在机型编辑器 sec-hint/placeholder）
8. **可选配置**（Configurations）— 配置变体暗卡（auto-fill 300px），点卡片展开该配置说明 + 规格差异（`config_content`），展开内「用这款配置这台服务器 →」；主配置带主题色徽标
9. **完整技术规格**（Specifications）— 沉底 `<details>` 折叠（默认收起）：summary + mono eyebrow `// {机型名} · FULL TECHNICAL SPECIFICATIONS` + 双列行（key 200px / value）
10. **空内容兜底** — 机型未补充任何 product_content 时提示
- **整页主题联动**：根 div `:style="stageVars"` 挂 `--sun-*`/`--page-bg`/`--band-bg`，内容区底色（`.detail-page`）、暗带、指示灯、天幕光线全随四主题换气质；本地 token（`--text/--text-2/--muted/--line-soft/--line-strong/--font-mono/--ease`）定义在 `.detail-page`

### 数据流
- `getModel` 加载机型（含 base_config 主配置 + `configs[]` 所有变体 + product_content）
- 「下载资料」：`downloadOfficeFile(doc.url, doc.name)`（`utils/fileDownload.ts`，axios blob 带鉴权）；文件在后端 `backend/storage/model-docs/`，由后台上传（见 model-editor.md）
- 内容归一化 computed：`highlightList`（highlights 优先，旧 `features[{icon,text}]` 降级为无标题亮点行）、`scnList`（旧 scenarios 字符串 → `{name}` 对象）、`capList`；某块空则区块不渲染
- 点「配置这台服务器」/ 变体展开内 CTA → `/servers/config/:modelId`
- **无编辑入口**（配置面纯展示；配置变体归属与简介在管理面机型编辑页维护）

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/models/:modelId` | `views/server-config/ModelDetailPage.vue` |

## API 端点

| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/models/{id}` | `catalogApi.getModel` | 获取机型详情（base_config + product_content） |
| GET | `/api/server-catalog/model-docs/{file_path}` | `downloadOfficeFile` | 读取资料 PDF（`application/pdf` + nosniff；路径段防穿越） |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_models` | 机型（含 product_content JSONB，后端不透明透传） |
| `l6` | `base_configs` | JOIN 提供 form/bays/series |

## 关键约定

- **信息架构**：机型目录（`ServerModelsPage`）→ **本详情页** → 配置向导（`ConfigWizardPage`）。机型目录卡片不再直进配置，先看详情。
- `product_content` 新结构（`ModelProductContent` 类型）：tagline / overview / highlights / capabilities（含 icon 键 + metrics 关键数字）/ scenarios（对象 name+fit+image）/ specs；旧 `features`、字符串 scenarios 只读兼容（编辑器保存时自动迁移，不再写旧结构）
- 技术规格值支持换行：编辑页 textarea 录入，本页 `white-space: pre-wrap` 渲染
- Hero 是用户本人设计，**任何改动先过用户**；CTA 保持工业蓝 #1677FF
