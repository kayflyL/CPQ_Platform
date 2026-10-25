---
name: glass-console-system
description: Soft Glassmorphism 视觉系统入口（token/工具类/signature 位置）+ 用户视觉偏好；默认浅色，暗白边/浅冷蓝灰 hairline 边玻璃+马卡龙语义色
metadata: 
  node_type: memory
  type: project
  originSessionId: 95a658bf-38d4-4794-92cc-55312dce6dc1
  modified: 2026-09-27T09:07:20.292Z
---

CPQ 前端视觉语言 = **Soft Glassmorphism**（柔和轻量玻璃拟态，2026-07 从深空 Glass Console 转向浅色 SaaS 仪表盘风格）：浅天蓝渐变 + 三级通透白玻璃 + 白边玻璃高光（hover/激活切蓝边）+ 极淡冷蓝投影 + 马卡龙语义色。**默认主题 = light**（曾为 dark）。

**入口（改视觉先看这里）**：
- 设计 token：`frontend/src/styles/tokens.css`（:root 共享主色/玻璃/动效；`[data-theme='dark']`/`[light]` 各自的背景渐变/玻璃/读数发光）
- 玻璃工具类：`frontend/src/styles/glass.css`（`.glass`/`.glass-light`/`.glass-strong`，三级）
- 读数/LED/动效：`frontend/src/styles/console.css`（`.cpq-reading`/`.cpq-led--*`/`.cpq-stream-edge`/`.cpq-rise`/`.cpq-fade`）
- 数字滚动：`composables/useCountUp.ts` + `components/common/CountNumber.vue`（补间+千分位+尊重 reduced-motion）
- 主题切换：`store/theme.ts`（暗/浅，跟随系统 + localStorage，顶栏灯泡按钮）

**Signature**：配置流程总价条（`.sc-total`）+ L6 合计条（`.l6-total-bar`）挂 `.cpq-stream-edge`（青色流光）+ CountNumber，呼应"实时计算"。KPI/价格用 `.cpq-reading` 或读数样式（等宽蓝发光，dark 专属）。

**用户视觉偏好（feedback，未来视觉决策依据）**：
- 主色克制工业蓝 `#1677FF`，**不要塑料荧光青**（`#00F5D4` 已全站清除，accent 青 `#36CFCF` 只用于 signature 读数/流光，极小面积）
- 语义色走**低饱和马卡龙浅色系**：success 薄荷绿 `#52C9A0`（原 antd `#52c41a` 偏硬已换）、danger 珊瑚红 `#FF6B6B`（原 `#ff4d4f`）、Medium 中度蓝；warning/info/purple 不变
- 玻璃边缘**暗色白边 / 浅色冷蓝灰 hairline**（hover/激活统一切 `--cpq-glass-border-strong` 蓝边）。**2026-07-27 修正**：浅色 `--cpq-glass-border` 从白 `rgba(255,255,255,0.65)` 改冷蓝灰 `rgba(120,144,176,0.38)`——白边叠在近白底 `#F2F6FC` 上完全看不见（用户报"卡片边缘看不清"）；**白边签名保留在 inset 内顶高光**（`inset 0 1px 0 white`）。dark 仍白 `rgba(255,255,255,0.11)` 不动。**坑**：`--cpq-overlay-w10/20` 浅色下也是白，被当卡片边框用就是隐形的——非 `.glass` 类的卡片别用 overlay-w 当 border，改指 `--cpq-glass-border`（如 Workspace 的 `.card-kp`/`.kp-card` 已 repoint，hover 切 `--cpq-glass-border-strong`）
- 喜欢**通透白玻璃**：light 三级 0.40/0.55/0.75（曾 0.55/0.72/1.0 偏实），靠**富蓝渐变背景**透出天空感避免发灰；dark 0.06/0.09/0.75
- **弱磨砂** blur 10/12/16（light，参考词 8–12px；曾 12/16/24）；dark 12/16/22（曾 16/20/28）
- **投影极淡冷蓝** light `rgba(22,119,255,0.06~0.10)`（曾黑色）；dark 减重到 0.40/0.50/0.60（曾 0.6/0.7/0.85）
- **圆角统一加大** sm8/md12/lg16/xl20（曾 6/10/14/18）
- **antd 容器也玻璃化**（曾实色）：card→glass-2、modal/drawer/tooltip/select-dropdown→glass-3、input→glass-2，**表格单元格保实色**（数据可读性）
- **浅色 overlay 语义拆分（关键，别再混用）**：浅色主题 `--cpq-overlay-w*`/`b*` 全改**白玻璃**当卡片/面板底色（曾反转成黑 rgba(0,0,0,*) 导致全站卡片泛脏灰，2026-07 修正）；**投影色另用 `--cpq-shadow-color-soft/strong`**（浅色冷蓝 0.08/0.14、暗色黑 0.30/0.50），**别再用 overlay-b 当 box-shadow 色**（会变白雾失悬浮感）；`--cpq-overlay-b85` 全屏遮罩保暗
- 科技感但克制（流光慢 2.4s + 淡；动效尊重 reduced-motion；浅色发光关闭保持干净）

**踩过的坑**：[[scoped-global-pitfall]]（scoped :global 别和后代混用）、[[charts-canvas-no-css-var]]（图表色必须真实值走 useChartTheme）、**JS 算色直塞 inline `background` = 主题盲区**（09-27 AI办公室任务看板日历/甘特条实色+写死 `#fff` 夜间刺眼；正解=传 `--status-color` 自定义属性，CSS 里 `color-mix(状态色 14~18%, var(--cpq-bg-card))` tint 底+状态色文字，即 `.tc-status` chip 同款语法，明暗自适应）、**玻璃层别嵌套**（`.glass` 套 `.glass` → 内层 backdrop-filter 模糊到外层白雾、两层 blur 叠成死灰发糊；卡片是唯一玻璃层直坐背景，分组用透明布局容器，别再套 `.glass`；详见 `docs/Frontend_Style_Guide.md` §3.4）。本环境 screenshot 工具返回 Unsupported，验证视觉必查 `getComputedStyle`/`getBoundingClientRect` 确认渲染值与尺寸。

**已知遗留（非本次回归，可后续系统性清理）**：OpportunityList 滤镜栏的 `.dark-select` 有 scoped 覆盖 `.dark-select[data-v] .ant-select-selector{bg:var(--cpq-overlay-w5)}`，压过全局 `#app .ant-select-selector` 玻璃规则（命名是 dark-first 遗留，实际值主题感知，浅色下不发黑）；全站若还有同类 scoped 残留，按 [[systematic-cleanup-not-whackamole]] 一并迁玻璃 token。**2026-07-20 已迁**：server-admin 4 组件（PartsLibrary/ModelManager/BomTemplateManager/BaseConfigBuilder）的 `.panel` 原是 dark-first 实色 `var(--cpq-bg-card)`+圆角10，现已挂 `.glass`、料号库 `.part-card` 挂 `.glass-light`（scoped 只留布局，外观交玻璃工具类）；剩 `.dark-select` 待清。**2026-07-21 已迁**：报价工作台 Key Parts 区——摘掉外层 `.card-kp` 的 `.glass`（正是上面"玻璃层别嵌套"的坑，两层玻璃 dark 下发灰），excel 模式 `.kp-card` 改用机型目录页 `.sc-type-card` 同款配方（`glass-1-bg→glass-2-bg` 渐变 + shadow-md + inset 高光 + hover 蓝边环）成为单层玻璃卡；同时 L6 利润率条置顶、KP 合计置底，两卡对称（利率在上、总价在下）。

**2026-07-23 重构**（取代 07-21 的"利润率置顶/合计置底横条"布局，用户要"两张卡+层次感+口径统一"）：报价工作台硬件选配=两张卡。①**机箱卡**=ChassisCard 玻璃本体吸收利润率（加具名 `footer` slot 装 PriceTriple + 可选 `heroPrice` prop 让卡头显售价而非成本）。②**KP 配件大卡**=`.card-kp` 升级为**结构性容器**（弱白底+边框+20圆角，**故意非玻璃**——避嵌套坑），头部用 `PriceTriple` 统一成本/利率/售价，内部子卡降级去玻璃为扁平分段（`KpCategoryCard` 加 `flat` prop / excel `.kp-card` CSS 降级）。**关键模式**：共用组件（ChassisCard/KpCategoryCard 被 ConfigWizard 和 Workspace 共用）用纯加法分叉——新增可选 prop + 条件 class + 默认空 slot，ConfigWizard 不传新 prop → 渲染 100% 原样零回归。新建 `components/common/PriceTriple.vue` 锁死三联口径（成本/利率%/售价，售价槽挂 stream-edge）。
