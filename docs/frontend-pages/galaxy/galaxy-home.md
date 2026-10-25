# 星河首页（Galaxy）

> 最后更新：2026-09-27

品牌首页。不是 vue-router 路由，是 `frontend/public/galaxy/` 下的**静态镜像页**（BlueYard 源码本地品牌化改造，内部演示路线），经 DefaultLayout 顶栏「首页」整页跳转进入。

## 访问地址

| 入口 | 地址 | 说明 |
|------|------|------|
| 应用入口 | 顶栏「首页」 | `window.location` 整页跳转 `/galaxy/index.html`，不走 router |
| dev 直达 | `http://localhost:5173/galaxy/index.html` | **必须带 `index.html`** |
| 构建产物 | `dist/galaxy/index.html` | `npm run build` 后更新；生产环境看到的是这份 |

> ⚠️ 踩坑（2026-09-24）：访问 `http://localhost:5173/galaxy`（不带文件名）时，Vite 不会补目录默认页，而是回退到 **Vue 应用壳**（标题 CPQ Platform）——看起来像"星河页没变化"，实际根本没进星河。星河页必须 `/galaxy/index.html` 全路径。

## 字体调试编辑器

```
http://localhost:5173/galaxy/index.html?debug-editor=1
```

- **仅带 `?debug-editor=1` 参数时激活**（之后写入 localStorage，普通打开不再出现；面板「退出调试」清除）。普通访客零感知。
- 进星河并点「进入」后，面板接管 6 张机型铭牌，右侧滑块**实时生效**：
  - **铭牌 SVG**：型号名/meta 字号、字距、基线 y、透明度、画幅宽高
  - **铭牌显示高度**（铭牌组首项）：CSS `.company__item canvas` 显示高度——铭牌实际渲染大小 = 该高度 × 字号 ÷ 画幅高，是可读性的第一杠杆
  - **页面文字层**：星座 kicker / 查看机型 / **机型描述 / 服务器详情链接**（点开一张铭牌卡后可见，定位会自动进星座页并点卡展开）/ 落地入口 / loader 进入 / intro / legal
- **09-26 定稿已固化进管线**：kicker 25px/.18em、查看机型 19px、机型描述 21px/1px、服务器详情 20px/4.2px、落地标题 23px/副题 15px、铭牌显示高度 74px（≤400px 保留 90px/描述 30px 两档）；铭牌 SVG 画幅 400×128、名 68px、meta 32px。落点：`fix_text_final.py` ZH_TYPE_CSS + `apply_card_layer.py` svg_text；调试器滑块默认值已同步为定稿基线
- **每根滑块带「定位」按钮**：不知道滑块管哪块？点「定位」自动走页面链路（loader→intro→落地页→北极星星座页 / About→legal 弹窗）跳到目标元素面前**金框连闪 7 次**（loader/intro 两项会重载页面后自动连闪）。链路里的点击每秒自动重试直到页面就绪（站点在场景加载完成前会吞点击），滑到哪一步失败状态栏都会写明原因。滑块下方同时显示它控制的真实文字（如 kicker 行标「北极星 · 国产化系列」）。
- 面板底部有**渲染估算行**（如"型号 ~25.5px · meta ~12.2px"），拖动实时变化。
- 调好后点「**复制配置**」导出 JSON——这只是浏览器本地参数，**必须交给管线固化才算改到"生产"**：CSS 部分进 `_by_mirror/fix_text_final.py`（ZH_TYPE_CSS），铭牌 SVG 部分进 `_by_mirror/apply_card_layer.py`（svg_text），然后重跑管线 + `npm run build`。

## legal 弹窗（关于我们 → 法律信息）

单条霄擎条目（公司名/演示声明/官网链接）+ 底部「关闭」返回钮（原版 `data-popup-close` 结构，bundle 全局点击监听驱动）。`fix_text_final.py` 第 6 步**结构化幂等**维护：换条目内容，检测到 `data-popup-close` 缺失就自动补回按钮（09-27 修复：旧正则把原 Return 钮吃掉导致弹窗无法退回）。zh-type 层含 `.popup__legal .popup__legal-item{width:100%}`——原站 CSS 按六条目三列网格把条目钉在 33.33% 宽，中文长句会被挤成碎行。

## 机型卡选中态的「关闭」返回钮（底部居中）

点开一张铭牌卡后，屏幕底部居中出「关闭 + 圆形×」（`.navigation__companies-back-to-sector`，`position:fixed;bottom:0;left:50%`）。09-27 修复过一次「× 飘到屏幕中间」：根因是 **crypto 第 0 张 div 卡结尾误写成 `</button>`**——div 不闭合，浏览器把后面的机型墙和整个 companies 容器（按钮的父级）解析进卡内；卡片选中态被站点 JS 加 transform，**transformed 祖先会让 `position:fixed` 相对该卡而非视口定位**，`bottom:0` 就落在了卡片盒子上。不变量：`[data-companies-sector]` 容器必须是 `MAIN` 的直接子元素（改卡区结构后用这条验收）。

## 服务器详情浮层（独立打开时页内弹出，09-27）

「服务器详情」链接 onclick 双分支：iframe 内嵌（应用内 `/galaxy` 路由，GalaxyHome.vue）→ postMessage 弹父页 a-modal；**独立打开（顶栏「首页」整页进入）→ `__xqModel('/servers/models/:id')` 在星河页内部弹居中浮层 iframe 内嵌真详情页**，关闭浮层（右上「关闭 ×」钮/点背景）即回到原状。此前独立打开走 href 默认导航整页跳走，返回时 /galaxy/index.html 整页重载、loader+intro 全部重播——已废弃该兜底。注入器 `_by_mirror/apply_model_overlay.py`（幂等，管线步：apply_card_links 之后），z-index 9999 盖过站点全部层。

## 改动生效链路（重要）

`public/galaxy/` 是源，`dist/galaxy/` 是产物：

1. 页面 HTML/SVG/文案改动：改 `_by_mirror/` 管线脚本（build_clean → bundle 补丁 → apply_card_layer → apply_card_links → fix_text_final → apply_debug_editor[调试器注入，可选]），不要手改 `public/galaxy/index.html`（重建即丢）
2. 改完必须 `cd frontend && npm run build`，否则生产入口（dist）看不到任何变化

**管线源头模型（09-27 起）**：`_by_mirror/index.html` = **已批准页面的整体副本**（不再是半旧 legacy 版）。历史教训：SRC 曾停留在 legacy span 卡时代（PO2-3350 旧命名/og=BlueYard Capital/favicon 死链），按它全量重建会把 public 已批准的设计整页打回旧版（09-27 实际踩中，靠 dist/galaxy 恢复）。现在的口径：public 上验收通过的改动要**整体回植 SRC**（`apply_sector_glyphs.py` 的 `backport_source` 负责 header/卡区/墙块三段），重建后用「快照-重建-diff」往返测试确认一致再交付。

## 星座导航图标（sector glyph，09-27 替换）

四星座的圆形图标已在**两处**统一替换为自绘填充图元版（`_by_mirror/apply_sector_glyphs.py` 一键重写，幂等，同时写 `public` 与 `_by_mirror` 两份 index.html）：① navigation__sectors 底条（`data-sector` 键）② landing 落地页徽章（`landing__sector-link` + `data-target` 键）。**blueyard 枚（底条+落地「关于我们」）09-27 起换成公司官方 logo 的符号部分**（`62977de534b6.svg` 最后一条 cls-1 path：六边包容立方晶格，原样嵌入 s=0.592）——替换了 BlueYard「BY」字标残留。

| 星座 | 概念 | 几何 |
|------|------|------|
| crypto 北极星 | 导航信标 | 双六边形立方 + 定向八芒（主轴长副轴短） |
| biology 猎户座 | 腰带箭矢 | 腰带三星菱形阵列连线延伸成箭头指向天狼星点 |
| engineering 天琴座 | 琴弦信号阵 | V 琴架 + 横杆 + 三弦 + 底部亮星（织女） |
| economics 仙女座 | M31 星系盘 | 对旋双臂点链螺旋 + 亮核 + 两颗伴星系 |
| blueyard 霄擎 | 官方标志符号 | 六边包容立方晶格（CloudPrime logo 符号 path 原样） |

**技术约束（改 glyph 必读）**：站点 CSS 会覆盖 SVG 的 stroke/presentational fill（`.icon__content *{fill:var(--icon-color)}` 三层 shine 机制），且 `.icon__round :not(circle)` 排除 circle（会落黑）——所以几何必须全部用**无 fill/stroke 属性的填充图元**：线段=细 `<rect rotate>`、星点=`<polygon>` 菱形、辉光=低 opacity 同心形。每图标 3 份拷贝（icon__content / -shine / -shine-permanent），配色随各 sector 的 `--icon-color` 自动生效。

**重建 durability（09-27 补齐）**：header logo img、logo 墙 img 区块已回植进 `_by_mirror/index.html`；`build_clean.py` 场景基底改为复制本地化 `scene.json`（权威副本已同步进 `_by_mirror/assets/data/scene.json`），`scene.blueyard.json` 仅作原版备份不再当基底。重建管线跑完 glyph 不会丢。

## 3D 星座背景图（scene.json，09-27 统一重绘）

四个 sector 的 3D 背景折线图（星座视图里发光线条+粒子云的"星座形状"）已统一为导航 glyph 的忠实 3D 化：**北极星=双六边立方+八芒 45° 族（26 段，s=0.004、线宽 12）**、猎户=腰带箭矢、天琴=琴弦（+纯粒子响星）、仙女=M31 星系盘（+伴星系）。**四星座都是单一干净 group**——crypto 原版 g1（672 段星尘云，原神像 ±0.07 缩在云 ±0.08 里）已在 09-27 删除：放大后的新图与云重叠就是用户五轮截图里「叠加感/老设计没清除」的根源。生成器 `_by_mirror/apply_scene_glyphs.py`（幂等，写 public+_by_mirror 两份）。

**scene.json 格式与渲染语义**（bundle 反编译）：`sector = [group,...]`，`group = {settings:[7], paths:[...]}`，每条 path = 6 浮点 = **一条 2 点线段**，同时是粒子发射器（emitter rate = 线段数）。`settings = [曲线重复数, 噪声幅度%, 发射间隔, 发射参数, 线宽×5e-4, 闪光%, opRamp]`。原 biology `[15,85,…]`（15 次重复×85% 噪声）就是旧版乱麻团的来源，已改干净线。**视图元素构成（09-27 反编译定案）**：星座视图里看到的画面 = ① scene.json[sector] 折线 group（intro 结束后 `introFinished()` 把 shape.scale 0→1 才可见）② 铭牌卡（DOM，位置取 `icons[0].paths[0]` 32 点行阵，x ±0.55）③ **星云立方星**（nested-cube 发光方块精灵=全站背景星空，ani-tiles.exr 布局 + color-tiles.png 8×8 精灵图集，水平面 ±300，与 scene.json 无关、四星座都有）④ hp.gridPts（`icons[0]` 同源的 THREE.Points）材质 `visible:false` 是死调试件。**icons[0]（铭牌锚点）脚本绝不触碰**。

## 已知约束

- 卡片铭牌 canvas 高度固定 140px、宽度随图片宽高比；显示高度由 CSS 钉死（桌面 74px / ≤400px 90px）
- 铭牌 3D 摆位锚在 `scene.json` 的 `icons[0].paths[0]` 点阵（全星座共用），卡片按 DOM 序取点、随 x 坐标绕 Y 轴倾斜；两卡锚点已改为 ±0.0368 对称（09-26 修「两牌高度不一致」）
- `data-sector`/`data-target` 等键名是承重结构，文案只换 `>显示文本<`
- 管线细节、bundle 补丁清单、镜像资源史的权威记录在项目记忆 `galaxy-mirror-baseline`
