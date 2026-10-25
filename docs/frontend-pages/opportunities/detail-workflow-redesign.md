# 商机详情页 · CPQ Workflow 式工作流改造方案

> 更新：2026-09-14 ｜ 参考页面：https://cpq-dashboard-v2.vercel.app/ 的 CPQ Workflow 页（access code 2693）
> 状态：**范围已评审确认（2026-09-13）**，本文不含代码改动 ｜ 可交互原型：`detail-workflow-redesign-mock.html`

## 1. 结论先行

参考页是「四步线性向导 + 三栏工作台」。它的优秀之处可以拆成三层，我们在每一层的差距也很明确：

| 层 | 参考页做法 | 我们的现状 |
|----|-----------|-----------|
| 布局 | 左 288px，可折叠到 60px ｜ 中自适应 ｜ 右 360px | 左 minmax(190px,230px) 固定不可折叠 |
| 信息密度 | 中栏工作卡**默认全部折叠**，只露标题 + 一行摘要 | 折叠机构已有，但 4 个状态位默认全开 |
| 侧栏↔中栏 | 点侧栏子步骤 → 自动展开对应卡 + 滚动定位 | 子步骤能滚，但卡没开就滚不到内容 |

已从线上打包文件核实的两条关键实现：

- 折叠卡壳的 `defaultOpen` 是 `false`，只有外部命令式 `open()` 才展开；
- 侧栏折叠是 `width: 288 ↔ 60` 的容器动画，折叠态改渲竖向图标条，不是简单收起。

## 2. 参考页源码级拆解

### 2.1 三栏骨架

- 中栏 `flex-1`，`overflow-y: auto`，内容容器 `max-width: 896px; margin: 0 auto; padding: 32px` —— **限制正文宽度**，长表单不会拉成超宽行；
- 右栏固定 `360px`，独立面板（暗色）；
- 折叠切换按钮是**绝对定位的独立元素**，不占布局：`top: 50%` 垂直居中，`h: 48px / w: 24px`，只留右侧圆角，`left` 随折叠状态在 `60 / 288` 之间切换，箭头旋转 180 度，带 title 提示。

### 2.2 左栏：可折叠步骤条（折叠后仍然可读）

- 折叠动画：容器宽度 `288 → 60`，300ms easeInOut；
- 折叠态**保留竖向图标条**：每步一个 40×40 圆角块 —— 完成=绿底白勾 / 当前=深灰底白数字 / 未开始=浅灰底灰数字且半透明，hover 显示步骤名；
- 顶部进度总览：标题 + 总进度条（2px 高，填充宽度 0.8s 动画）+ 「Overall Progress / Step 1 of 4」+「Step 1 Progress / 83%」；
- 中部步骤卡三态：
  - 已完成：白底 + 绿底勾 + 绿点「Completed」；
  - 进行中：白底 + 深灰底数字，**卡内再嵌一条子步骤进度条** +「x of y complete」+ 百分比；
  - 未解锁：浅灰底 + 整体 50% 透明，不可点；
  - 卡与卡之间用一条 2px 宽 32px 高的竖线连接，形成流程感；
- 点击卡头展开子步骤（箭头旋转 90 度），子步骤缩进并带左侧竖线，每项左侧是状态点（绿勾 / 深色空心环 / 灰色空心环），未开始项整体 60% 透明；
- 底部固定区：Quote Owner / Assigned To + 一个呼吸的绿点 +「Auto-saving enabled」；
- 值得注意的克制：**只有当前步骤卡内嵌进度条**，其余步骤只给状态，左栏噪音很低。

### 2.3 中栏：默认折叠的工作卡（本次借鉴的核心）

折叠卡壳的接口：`icon`、`iconBg`、`title`、`status`（completed / attention）、`summary`、`children`、`defaultOpen = false`。

- **折叠态卡头就是一张完整的摘要卡**：
  - 左：40×40 圆角图标块，底色随状态（完成绿 / 待办琥珀）；
  - 中：标题（14px semibold）+ **一行灰色摘要且超长截断**（12px）—— 摘要只在折叠态显示，展开后隐藏；
  - 右：状态徽标（完成=浅绿圈勾 / 待办=浅灰圈感叹号）+ 箭头（展开时旋转 180 度）；
- 展开动画：`height: 0 → auto` + 淡入，300ms easeOut，内容区顶部有一条分隔线；
- 卡外观：白底、8px 圆角、浅边、`shadow-sm`，hover 升到 `shadow-md`；
- 中栏顶部不重复卡片标题：`h1` 是当前步骤名，副标题固定文案「Complete all sections below to proceed to the next step」，右上角是「Learn the System」按钮；
- 命令式联动：中栏向外暴露 `scrollToSection(key)`，内部先 `cards[key].open()`，再延迟 ~100ms 执行 `scrollIntoView({ behavior: smooth, block: center })`（Fast Mode 下退化为 instant）；
- 阶段收口：**当本步骤所有子项都完成时**，中栏底部才出现「Save Draft」（次要）+「Save & Next」（深色主按钮）；
- 卡内内容有统一范式：先一块蓝色说明框讲「现在要做什么」，再给一个全宽琥珀色主行动按钮（`py-3`、加粗、带投影，hover 加深）；完成之后同一位置替换成绿色成功框 + 关键单号（BAN 号 / Order Number 用 24px 加粗突出）。

> 这套「说明框 + 一个主行动按钮」的范式，是它能做到每张卡打开就知道干什么的关键。

### 2.4 右栏：实时摘要面板

- 卡片规格：`rgba(30,41,57,0.6)` 底 + `rgba(54,65,83,0.5)` 边 + 14px 圆角；
- 顶部：「Live Snapshot」胶囊标题（深灰渐变、圆角 10px、带投影）+「Fast Mode」开关（44×24 滑轨，开启时琥珀色）；
- 分区结构：SERVICE ADDRESS / PRODUCT CATEGORY / CURRENT STEP PROGRESS / PRODUCT SUMMARY，每个分区标题都是「小图标 + 12px 大写字 + 0.05em 字距」的形式；
- 服务地址卡可展开（`height: auto ↔ 70px`），展开后列候选地址，选中项是绿底绿边；
- 进度卡：36×36 图标块 + 标题 + 状态文案（Pending / Approved / 单号），完成绿、待办琥珀；报价卡内还带 MRC / NRC / Total 三行小计；
- 摘要卡：label 12px 灰色 与 value 14px semibold 左右对齐。

### 2.5 三个跨页面的细节（容易被忽略，但很提体验）

1. **Fast Mode**：一个全局开关，打开后所有过渡时长为 0、滚动改为瞬时。演示、录屏、低配机器非常实用；
2. **Learn the System**：教学讲解层。点击后逐区域高亮讲解，背景加模糊 + 半透明遮罩，鼠标悬停左栏也会触发讲解；
3. **自动保存指示**：左栏底部呼吸绿点 + 「Auto-saving enabled」，让用户敢随手改；
4. **悬浮动作 FAB**：右下角黄色渐变圆钮 + 红色数字徽标 + 轻微上下浮动，只在需要动作的步骤出现。

### 2.6 可复用的设计语言（最小集合）

- **色**：中性灰底 + 白卡；语义色只有三个 —— 绿（完成）、琥珀（待你行动）、蓝（说明框）；深灰做主按钮；
- **字**：12 / 14 / 16 三级；标题 600-700；摘要 12px 灰；
- **形**：卡片 8px 圆角、图标块 8px、面板 14px、按钮 8px；
- **动**：入场 `opacity + 位移`、展开 `height auto`、箭头 `rotate`，统一 200-300ms easeOut，不做花哨弹簧；
- **原则**：每个可折叠卡的头部都要能「折叠态自解释」—— 标题 + 摘要 + 状态徽标，缺一不可。

## 3. 本地现状（已核对代码）

- `frontend/src/components/opportunity/OpportunityProcessBoard.vue`（64KB，三栏实际承载者）
  - 三栏栅格在 :1375 —— `minmax(190px, 230px) minmax(0, 1fr) clamp(280px, 22vw, 360px)`；
  - 中栏同一时刻只渲染 `activeNode` 一个节点的工作台（:718），带 `node-fade` 过渡；
  - 折叠机构其实已经有了：`card-chevron` + `card-collapse`（:1436 / :1444），但 `reqInfoOpen / requirementOpen / bomingOpen / costingOpen` 全部 `ref(true)`（:97-100），等于默认全开；
  - 联动已有雏形：`scrollToNode`（:420）/ `scrollToSubstep`（:432），靠 `[data-substep~="节点.序号"]` 定位，但**不负责展开卡片**；
  - 右栏是 `board-aside` 里的时间线 + `ApprovalFlowPanel`。
- `frontend/src/components/opportunity/OpportunityProcessRail.vue`（7KB）：进度头 + 步骤列表，仅 active 节点展开 `SUBSTEPS`；
- `frontend/src/views/opportunity/OpportunityDetail.vue`：`page-header`（返回 / 客户名 / 状态 / 创建日期）+ 按三栏占位的骨架屏；
- 设计系统：Soft Glassmorphism，浅色默认 + 暗色可切，颜色/圆角/投影只走 `--cpq-*`（见 `docs/前端设计/视觉风格指南.md`）。

也就是说：**骨架我们和参考页已经很接近，真正缺的是「左栏可折叠」和「中栏默认折叠」这两条。**（评审后范围已收窄，见 §4）


## 4. 范围裁定（2026-09-13 评审结论）

| 模块 | 结论 | 说明 |
|------|------|------|
| 左栏（流程线） | **完全采纳** | 按原型实现可折叠 |
| 中栏（工作卡） | **仅采纳「默认折叠」** | 卡片默认收起，点开才看详情；其余不改 |
| 右栏（审批） | **不动** | 保留 `ApprovalFlowPanel` 时间线现状 |

相应地，原方案 §4 里的 P1（统一徽标、阶段 CTA、右栏分区化）与 P2（教学层、FAB）**本期全部不做**。

## 5. 落地范围（修订后）

### 5.1 左栏：完全采纳

| # | 改动 | 细节 |
|---|------|------|
| 1 | 折叠 / 展开 | 宽度在 230px ↔ 64px 之间过渡，用 `--cpq-dur-2` + `--cpq-ease-smooth`，不引入动画库 |
| 2 | 折叠态图标条 | 换成竖向图标块：完成=成功色底白勾 / 当前=主色底白数字 / 未解锁=灰底灰数字，`title` 提示步骤名 |
| 3 | 边缘切换按钮 | 贴左栏右缘垂直居中，48×24、只留右圆角，箭头旋转 180°，`title` 提示「收起 / 展开」 |
| 4 | 状态记忆 | `localStorage` 记住上次状态 |
| 5 | 进度头 | 保留「总体进度 + 本阶段进度」，折叠时随面板一起隐藏 |
| 6 | 步骤卡视觉 | 标题单行省略；**当前阶段卡内嵌子步骤进度条 + x / y 项 + 百分比**（原方案没有这条，按原型补齐） |
| 7 | 底部信息区 | 业务 / FAE / 报价人 + 最后更新时间 |
| 8 | 窄屏规则 | ≤1080px 强制展开并隐藏折叠按钮（原因见 §6） |
| 9 | 保持不变 | 点步骤切节点、点子步骤滚动定位、`disabled` 不可点、现有状态文案 |

涉及文件：`frontend/src/components/opportunity/OpportunityProcessRail.vue`（主体）、
`frontend/src/components/opportunity/OpportunityProcessBoard.vue`（列宽变量 + 传参）、
必要时 `frontend/src/styles/tokens.css`（若需新增左栏宽度变量）。

### 5.2 中栏：仅默认折叠

只改一件事：把 `reqInfoOpen / requirementOpen / bomingOpen / costingOpen`（`OpportunityProcessBoard.vue:97-100`，现在全是 `ref(true)`）合并成一张 `cardsOpen` 映射，默认**只展开「当前待办」的那张卡**，其余折叠。

折叠 / 展开的交互、`card-chevron` + `card-collapse` 的结构与样式**一律不动**。

**明确不做**：不加「全部展开 / 全部折叠」、不加底部阶段 CTA、不新增卡头摘要行、不改三态徽标与进度文案。

> 已知取舍：折叠后卡内结果不可见（BAN 号、报价单号等），用户需要点开才看得到。
> 如果之后觉得信息量不够，最小增量是给折叠态卡头补一行摘要（原型里有示例），只动头部模板。

### 5.3 右栏：不动

保留现状。原型中的右栏分区化、Live Snapshot 式摘要面板不采纳。

## 6. 对原方案的两处修正（代码核查后）

1. **取消「窄屏默认折叠」**：`OpportunityProcessBoard.vue` 在 `max-width: 1080px` 时 `.board-body` 已经变成单列堆叠（:1788），左栏横向占满整行，此时再折叠更难看。改为：窄屏强制展开 + 隐藏折叠按钮，折叠只作为宽屏下的用户偏好。
2. **取消「自动保存已开启」指示**：商机看板目前没有自动保存机制（全站只有 Univer 模板编辑器与报价工作台有），写「自动保存中」是不实状态。左栏底部改为展示「最后更新 MM-DD HH:mm」，取 `opportunity.updated_at`（`frontend/src/types/opportunity.ts:10` 已有该字段）。

## 7. 落地步骤与验收

| 步 | 内容 | 主要文件 | 验收点 |
|----|------|---------|--------|
| 1 | 左栏折叠骨架：列宽改变量 + 折叠态切换 + localStorage 记忆 | `OpportunityProcessBoard.vue`、`OpportunityProcessRail.vue` | 折叠/展开过渡顺滑、刷新后保持 |
| 2 | 折叠态图标条 + 边缘切换按钮 + 窄屏规则 | `OpportunityProcessRail.vue` | 折叠后仍能看出走到哪一步、窄屏自动展开 |
| 3 | 左栏打磨：步骤卡内嵌进度条、底部信息区 | `OpportunityProcessRail.vue` | 当前阶段卡显示 x / y 项与百分比；底部信息正确 |
| 4 | 中栏默认折叠 | `OpportunityProcessBoard.vue` | 进页面只有当前待办卡展开，其余收起且仍可点开 |

工作量分布：左栏占约 3/4，中栏是改默认值 + 少量联动，约 1/4。

## 8. 待确认（4 条，都不阻塞开工）

1. 中栏默认展开粒度：只展开「当前待办」卡（原型做法，推荐），还是**全部折叠**一个都不开？后者改一行默认值即可。
2. 左栏折叠态宽度：**64px**（原型值，留一点内边距）还是 56px（更紧凑）？
3. 左栏底部信息区是否要「业务 / FAE / 报价人 + 最后更新」这一组？不加就维持现状（只有进度 + 步骤）。
4. 点左栏子步骤时，如果目标卡是折叠的，要不要顺手展开它？这算中栏的「其他」范畴，我默认**不展开**，仅滚动定位。

## 9. 原型

可交互原型：`docs/frontend-pages/opportunities/detail-workflow-redesign-mock.html`（单文件，浏览器直接打开）

| 状态 | 截图 |
|------|------|
| 默认态：中栏只有「待办」卡展开 | `detail-workflow-mock-default.png` |
| 左栏折叠：换成图标条 | `detail-workflow-mock-rail-collapsed.png` |
| 回看已完成阶段：卡片全折叠 | `detail-workflow-mock-stage-done.png` |

> 原型是探索稿，含未采纳部分（右栏分区化、阶段 CTA、全部展开/折叠等）；落地范围以 §4、§5 为准。

## 10. 实现记录（2026-09-13 已落地）

改动文件：

| 文件 | 改动 |
|------|------|
| `frontend/src/components/opportunity/OpportunityProcessRail.vue` | 折叠态 + 图标条 + 阶段进度条 + 底部信息区（重写模板/脚本，样式为增量） |
| `frontend/src/components/opportunity/OpportunityProcessBoard.vue` | `cardOpen` 默认折叠规则、左栏列宽变量与折叠按钮、窄屏规则、折叠卡 padding 修复 |
| `frontend/src/views/opportunity/OpportunityDetail.vue` | 向看板透传 `opportunity.updated_at` |

实测（本地真实数据，非原型）：

- 四个阶段进入时的默认展开：线索登记 → 商机信息折叠 / 需求单工作台展开（待办）；方案配置、成本核算（均已完成）→ 卡片折叠；报价单（无折叠卡）不受影响；
- 左栏折叠：230px ↔ 64px，图标条按 `pending / current / done` 着色，刷新后保持（localStorage），折叠态点图标可切阶段且保持折叠；
- 窄屏 1024px：单列堆叠下强制展开、隐藏折叠按钮、左栏占满整行；
- 手动点卡头折叠/展开正常；`typecheck (vue-tsc -b)` 与 `vite build` 均通过。

**过程中的一个真实缺陷（已修）**：折叠卡残留 16px 高度、露出首行内容。原因是 `.card-collapse` 用 `grid-template-rows: 1fr↔0fr` 折叠，而内层 `.card-collapse-inner` 的 `padding: 0 16px 16px` 会顶起 `0fr` 行的最小行高（`min-height:0 + overflow:hidden` 压不掉 padding）。修法是折叠时同时清零上下 padding。默认展开时看不见，改成默认折叠后必现。

| 状态 | 截图 |
|------|------|
| 左栏展开（默认态） | `detail-workflow-impl-expanded.png` |
| 左栏折叠 | `detail-workflow-impl-rail-collapsed.png` |
| 回看已完成阶段（卡片折叠成一行） | `detail-workflow-impl-stage-done.png` |

## 11. 二轮修订（2026-09-13 晚，实测反馈驱动）

首轮落地后实测暴露三个问题，本轮修正；§8.4 的取舍（点子步骤不展开）就此反转：

| # | 问题 | 根因 | 修法 |
|---|------|------|------|
| 1 | 报价单节点没有默认折叠 | 折叠状态模型 `cardOpen` 没收录报价单：QuoteWorkbench 两个面板 `upstreamOpen/quoteOpen` 硬编码 `ref(true)`，`applyCardDefaults` 无 quoting 分支 | 两面板纳入 `cardOpen`（`quoteUpstream`/`quoteEditor`），QuoteWorkbench 改受控 props（默认 true 向后兼容），`applyCardDefaults` 加 quoting 分支——与其他节点同规则：**未完成→展开，已完成→收起** |
| 2 | 点左栏小节点，中栏卡不展开 | `scrollToSubstep` 只切节点 + 滚动定位，从不打开 `cardOpen`；且手动置 true 会被 `watch(activeNode)→applyCardDefaults` 折回去 | 建立 substep→card 映射，点击先展开目标卡并计入 `cardTouchedByUser`（防折回），再滚动 |
| 3 | 左栏小节点标题与中栏对不上 | SUBSTEPS 是「每节点两区块」旧文案；中栏早已合并为每节点一张工作卡，且 boming/costing/quoting 两锚点挂同一元素，第二段名存实亡 | 文案对齐中栏真实实体，每节点 = **[工作台， 附件]**：`方案配置工作台/方案附件`、`成本表工作台/成本附件`、`报价单工作区/报价附件`；第二段点击 = 展开卡 + 直接打开对应附件抽屉（复用卡内按钮同源参数）；quoting 锚点从外壳移到 QuoteWorkbench 内 `qw-editor` 面板，`报价单工作区` 可精确落位 |

涉及文件：`OpportunityProcessRail.vue`（SUBSTEPS 文案）、`OpportunityProcessBoard.vue`（CardKey/cardOpen 扩容、applyCardDefaults quoting 分支、setCardOpen、scrollToSubstep 联动、模板绑定）、`QuoteWorkbench.vue`（upstreamOpen/quoteOpen 改受控 computed + update 事件、qw-editor 挂 data-substep 锚点）。

产品决策（2026-09-13 用户拍板）：第二段小节点统一为「附件」入口；报价单两面板都按待办规则折叠。

## 12. 三轮修订（2026-09-13 晚）：顶部进度区精简

**问题**：header 同时显示 Overall Progress 75% + Step 1 of 4 + Stage Progress 50%，三条信息互相打架——Step N of N 反映的是「正在查看」的节点（自由回看时与完成度必然矛盾），Stage Progress 与当前节点卡内嵌的阶段进度条（`x / y` + %，同一 `stagePercentOf` 计算）完全重复，且 requirement 子步骤按数据判定会与节点「已完成」状态冲突（50% vs 已完成）。

**裁定（用户拍板）**：只留 Overall Progress 一条 + 一行当前节点状态（`activeLabel`，如「线索登记 · 已完成」）；删除「Step N of 4」与 header 的 Stage Progress；阶段进度只保留在当前节点卡内那条。

**改动**：`OpportunityProcessRail.vue`——模板删 `rail-progress-step`（Step N of 4）与 Stage Progress 两条子进度条；脚本删 `currentStepText`、`stagePercent` 两个 computed；样式删 `.rail-progress-head-sub / .rail-progress-track-sub / .rail-progress-step` 三段死 CSS。

## 13. 四轮修订（2026-09-14）：编辑需求弹窗表格输入框底色

**问题**：「编辑需求」弹窗里部件清单表格每个单元格输入框都有明显的玻璃底色+边框，而「编辑方案」弹窗里的同款表格输入框是无缝透明的。

**根因**：单元格输入框的抹平规则（`background: transparent !important` 等）不在组件里，而在全局 `antd-overrides.css` 的 `#app .portal-sheet-modal .sheet-table .ant-input` 上——只有挂了 `wrap-class-name="portal-sheet-modal"` 的弹窗才生效。「编辑方案」（BomSchemeWorkbench）挂了，「编辑需求」（OpportunityProcessBoard 的 detail a-modal）没挂；全局 `#app .ant-input` 玻璃规则是 ID 优先级，组件内 `:deep()` 抹平规则全部打不过它（RequirementForm/SchemeEditor 里的那两段因此是半死代码，只贡献 height/padding 等尺寸声明）。

**改动**：

| 文件 | 改动 |
|------|------|
| `OpportunityProcessBoard.vue` | detail a-modal 补挂 `wrap-class-name="portal-sheet-modal"`（抹平规则只命中 `.sheet-table` 后代，弹窗内普通表单输入不受影响） |
| `RequirementForm.vue` | 补浅色主题 `:root[data-theme='light'] .req-form` 的 `--sheet-*` 调色板（此前只有暗色默认值，与 SchemeEditor 不对齐） |
| `KpPartsEditor.vue` | 行 hover / 单元格 focus-within 底色改走 `var(--sheet-hover, …)` token，与 SchemeEditor 同源 |
