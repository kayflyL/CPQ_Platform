---
name: sticky-clearance-spacer-pattern
description: 全局顶栏让位必须用占位div不能padding（sticky偏移从滚动容器padding内沿起算会双计）；嵌套滚动容器内吸顶一律top:0不吃全局变量；满高页height需calc减clearance
metadata: 
  node_type: memory
  type: project
  originSessionId: 1469bebd-79c3-4889-8785-7a990a640ada
  modified: 2026-09-17T16:24:44.078Z
---

顶栏让位机制（2026-09-17 定稿，DefaultLayout.vue）：

- **铁律**：`.main-scroll`（唯一滚动容器）的顶栏让位用 `.scroll-clearance` 占位 div（`height: var(--cpq-header-clearance)`，desktop 72 / mobile 64），**绝不能改回 padding-top**。
  **Why:** CSS sticky 的 top 偏移从滚动容器 padding 内沿起算。padding 让位时，页内吸顶元素实际停靠位 = padding + 变量值（60+72=132px），页面未滚吸顶条就被提前顶下来压住内容——报价工作台三症状（大片空白/配置条压内容/表头盖描述行）的单一根因，实测复现于 2026-09-17。
  **How to apply:** 页面里写 `top: var(--cpq-sticky-top)`（60/56）即视口绝对停靠位，`top: calc(var(--cpq-sticky-top) + Npx)` 同理；改布局时别往 main-scroll 加 padding。

- **嵌套滚动容器（overflow-y:auto 的列/抽屉/弹窗/overlay）内的吸顶表头/工具栏一律 `top: 0`（或该容器自身 padding 值），不吃 `--cpq-sticky-top`**——CSS 变量沿 DOM 继承会穿透进嵌套容器，60px 会悬在列内容中段盖住行。已按此修：BomTable/SchemeEditor/CostSheetEditor/RequirementForm 表头、ConfigWizard 规格书工具栏(top:32)。

- **满高页**（height:100% 直挂 main-scroll 的路由页）必须写 `height: calc(100% - var(--cpq-header-clearance, 0px))`：已改 Portal/AiOfficeView/ConfigWizardPage（PortalWorkstationView 的 min-height 同理）。新做满高页忘写只多出 72px 可滚动（显性症状），比 sticky 双计的静默错位安全。

- **hero 型页面垫到导航条下**（2026-09-17 详情页落地，ModelCatalog 同法）：hero 容器 `margin-top: calc(-1 * var(--cpq-header-clearance,0px))` + `min-height` 加同量；页内绝对定位子元素改挂 `--stg: var(--cpq-header-clearance,0px)` 锚点（`top: calc(22px + var(--stg))` 式），原百分比锚点改写为 `calc(var(--sky) * N)`（`--sky: calc(100% - var(--cpq-header-clearance,0px))`）保像素级原位；导航条压住的露天空区用 `::before` 条带涂主题渐变首色。配套：页面挂载 `document.documentElement.dataset.heroDark='1'` 切导航浅字，滚动态色带 `--hero-band-bg`（各主题自己的天空色）设 documentElement，卸载两者都清。

09-27 补：ExcelParser.vue 与 UniverTemplateEditor.vue 两个满高工作台根曾写 height:100% 漏扣 clearance（整页超高 72px、底部要下滑），已改 calc(100% - var(--cpq-header-clearance))；新做满高页先查这条。
