# 商机驾驶舱 (OpportunityList)

> 最后更新：2026-08-12

## 功能概述

商机线索模块的主入口页面，提供数据可视化仪表盘 + 商机列表管理。

### 核心功能
1. **KPI 指标卡** — 总商机数、总配置数、周期新增商机、周期新增配置（带 sparkline 趋势）
2. **图表区** — 4 张 ECharts 图表（Bento 2×2）：
   - 趋势分析（**商机趋势 / 机型趋势** 切换；商机=柱状+平台分线，机型=Treemap 矩形树图，每机型一块矩形面积=周期内报价次数；机型维度用细粒度 PN，从 `quotations.config_server_models` 抽取归一；配色对齐结构分布图 segmentBorder+实心平涂色，主题感知）
   - 结构分布（平台/机箱切换；环形图 / 玫瑰图，可点击下钻）
   - 业务排行（横向条形，按销售商机数 Top5 + 其他可展开）
   - 线索转化（**线索转化 / 机型利润** 切换；转化=销售直列清单 线索量/成交量/成交率%，机型利润=boxplot 箱线 各 PN 利润率分布+散点，样本<4 折进"其他机型"）
3. **商机列表** — 右侧面板，支持：
   - 列表项以**客户名称**为主锚点（点击进入详情），副信息：销售/平台/机箱/数量/配置/创建日期
   - **桌面折叠**：右上「折叠」按钮收起 → 48px 竖排窄条（顶部 ▶ 图标 + 竖排「商机列表」标签，`writing-mode: vertical-rl`），内容区 `display:none` 彻底隐藏杜绝文字溢出裁切；整条可点击展开还原。展开态显示「折叠 ◀」按钮
   - 业务结果筛选（进行中/已中标/已丢标/已过期）
   - 业务结果标签可点开**内联切换**（进行中/已中标/已丢标/已过期），即时保存、同步图表，无需进详情页
   - 平台类型多选筛选
   - 机箱形态多选筛选
   - 排序（更新时间 新→旧 / 旧→新）
   - 关键词搜索（客户/销售/备注）
   - 图表下钻联动筛选
   - 批量选择 → 批量移至回收站
4. **新建商机** — Modal 弹窗，输入客户名称（必填）+销售人员（可选）；其余信息在商机详情页补全
5. **时间周期切换** — 本周/本月/本年 + 自定义（上周/上月/去年/近30天/近90天/指定月/任意区间）
6. **移动端响应式**（`max-width: 768px`，由 `isMobile` ref + matchMedia 驱动）：
   - **顶部导航 → 汉堡菜单+抽屉**（全局，`DefaultLayout`）：窄屏隐藏横向 `a-menu`，顶栏左侧放汉堡按钮（配「菜单」文字，NN/g 易发现性）；点击触发 `a-drawer` 从左滑入，内嵌同一份菜单（inline 模式）。桌面端保持横向菜单不变
   - **商机列表 → 抽屉**：窄屏列表脱离文档流（默认移出视口 `translateX(100%)`），右下浮动「📋 商机列表」FAB 触发滑入；抽屉从 **topbar 下方（top:50px）** 开始，不盖顶栏（导航始终可用），配遮罩点外关闭、✕ 关闭按钮；桌面端保持原右侧栏 + 48px 折叠
   - **图表区 → 单列纵向流**：Bento 2×2 降级为 flex 纵向，顺序 趋势→结构→排行→转化，每图固定 220px；KPI 4 格改 2×2
   - **方案助手 → 全屏**：`AssistantPanel.panelStyle` 窄屏分支返回 100vw×100vh，不再贴 FAB 锚定；`AssistantFloatingButton` 缩成 48×48 圆形（`justify-content:center`+`line-height:1` 让 SVG 图标精确居中，藏"方案助手"文字）并上移避开列表 FAB
   - 容器 `.cockpit` 去 `overflow-x:auto`（防横向滚动条），改 `flex-direction: column`

## 前端路由

| 路由 | 组件 |
|------|------|
| `/opportunities` | `views/opportunity/OpportunityList.vue` |

## API 端点

| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/dashboard/summary` | — | 获取驾驶舱统计数据（KPI + 图表 + 结构分布） |
| GET | `/api/opportunities/list` | `projectApi.list` | 商机列表（分页 + 筛选 + 排序） |
| POST | `/api/opportunities` | `projectApi.create` | 新建商机 |
| POST | `/api/opportunities/batch-trash` | `projectApi.batchTrash` | 批量移至回收站 |

### 查询参数 (list)
- `page`, `page_size` — 分页
- `search` — 关键词搜索
- `result` — 业务结果筛选 (pending 进行中 / won 已中标 / lost 已丢标 / expired 已过期)
- `platform` — 平台类型（逗号分隔多选）
- `chassis` — 机箱形态（逗号分隔多选）
- `sort_by` — 排序字段 (默认 updated_at)
- `sort_order` — 排序方向 (desc/asc)

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `opportunities` | `opportunities` | 商机主表（opportunity_id, customer_name, status, platform_type, chassis_form, sales_person, created_at, updated_at, extra_fields） |
| `opportunities` | `quotations` | 报价单（统计 config_count；机型河流 chart2 从 `config_server_models` 抽 PN 归一按月计数；机型利润箱线 chart5 从 `profit_margin` 按 PN 聚合五元组） |
| `rules` | `system_config` | 系统配置（server_series 平台系列枚举） |

## 关键组件

- `CountNumber.vue` — 数字动画计数
- `useChartTheme()` — 图表主题 composable
- `useSeries()` — 平台系列选项 composable（读 system_config）
- `PLAT_COLOR` — 平台颜色常量 (`@/constants/platform`)
- echarts 注册：LineChart / BarChart / PieChart / ThemeRiverChart（机型河流）/ BoxplotChart（利润箱线）+ Grid/Tooltip/Legend/Title/VisualMap 组件
