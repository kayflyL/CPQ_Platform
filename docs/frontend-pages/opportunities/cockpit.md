# 商机驾驶舱 (OpportunityList)

> 最后更新：2026-09-21（新增「配件筛选」：按报价单明细搜商机，条件行 + 型号建议 + 命中配件列；详见下文专节）

## 功能概述

商机线索模块的主入口页面，左右两栏布局（顶栏 → 左图表栏 / 右列表栏）。

### 页面结构

1. **顶栏** `.page-head`（通栏）
   - 标题「商机驾驶舱」+ 数据区间副标
   - 图标按钮：📊 图表（左栏显示/隐藏开关）、🤖 **AI 线索**（→ `/ai-leads`）、🗑 回收站（→ `/recycle-bin`）
   - 主按钮「新建商机」（Modal：客户名必填 + 销售可选）
2. **左栏** `.charts-panel`（430→`clamp(360px, 34vw, 660px)` 视口比例宽度，随窗口缩放自适应）
   - KPI 2×2 胶囊（总商机数/总配置数/周期新增商机/周期新增配置）
   - 周期 pills（本周/本月/本年/自定义 popover：上周/上月/去年/近30/近90/指定月/任意区间）
   - **图表单列纵向堆叠**（4 张卡占满栏宽、上下滚动栏内浏览）：
     - 趋势分析（商机趋势/机型趋势切换）
     - 结构分布（平台/机箱切换，可点击下钻）
     - 业务排行（仅全量权限可见；Top5+其他可展开）
     - 线索转化（线索转化/机型利润切换；仅全量权限可见）
   - 图表本体验见 `OpportunityCharts.vue`，与旧版完全一致（零删改，仅外层布局变化）
3. **右栏** `.table-side`
   - **筛选行** `.filter-row` — 搜索框（客户/业务，300ms 防抖，首位）+ 状态（单选）/ 平台（多选，选项来自 `useSeries()`）/ 形态（多选）/ 业务（`page.opportunities_all` 角色可见）+ 重置 + 总条数
   - **宽表** `.table-card` — 服务端分页 `a-table`：
     - 列：☐ 多选 | 客户/状态（名称 + 状态 tag 内联下拉；第二行元信息 = 行业 · 订单类型 · N 份报价）| 业务 | 平台 · 形态（单行 "Polaris · 2U"）| 数量（N 台）| 配置（N 套）| 创建时间 | 更新时间（MM-DD HH:mm + 相对时间「N 小时前」第二行；更新时间默认降序可排）| ⋯ 行菜单
     - **pageSize 随视口高度自适应**：按表格卡片高度（`clientHeight`）÷ 行高(~60px) 计算每页行数，窗口缩放/左栏收展实时重算始终填满；用户手选 pageSize 后停止自适应
     - 行菜单：打开 / 重命名（Modal + `PUT /{id}/meta`）/ 移至回收站（`Modal.confirm` + `POST /{id}/trash`）
     - 勾选任意行 → 底部悬浮批量条（已选 N · 移至回收站 · 取消）
4. **图表下钻** — 结构分布点击 → `drill-on` → 筛选行下方提示条 + 列表/图表联动过滤
5. **配件筛选**（2026-09-21，详见专节）— 筛选行尾部「配件筛选」按钮 → 条件行弹层；chips 回显 + 命中配件列

### 状态持久化

分页/筛选/下钻/排序/**配件筛选行**存 sessionStorage（key `opp_list_state`，`part_rows` 字段），跳详情返回可恢复；详情页返回用 `router.push('/opportunities')` 不带 query，URL 方案会被击穿。

## 配件筛选（按报价单明细搜商机，2026-09-21）

业务场景：「查一下近一个月，有没有 6530+8卡5090 或 AMD+8卡5090 配置的相关报价」——复合条件 + 数量 + 时间窗，普通搜索框做不到。

- **入口**：筛选行尾部「配件筛选」按钮（桌面 + 手机抽屉同款，组件 `OpportunityPartFilter.vue`），激活态变蓝带指示点。
- **条件行弹层**（a-popover）：`[类别 select] [型号关键词 tags] [数量 ≥ N]` × N 行
  - 类别来自 `GET /api/opportunities/part-categories`（报价明细真实出现过的 part_category，按小写归并、按次数排序）
  - 型号关键词输入即建议（`GET /api/opportunities/part-suggest?category=&q=`，250ms 防抖；a-auto-complete，选项 = catalogue + 使用次数）
  - 两端点只统计**列表可见商机**（排除 AI 办公室/回收站）的报价，建议出来即可匹配
  - **多行 = 同时满足**（同一张报价单里都含）；**同行多关键词 = 任一命中**；数量按「同一报价 × 同一配置页签」内命中行求和判定（防两个配置各 4 卡凑 8 卡）
- **应用后**：条件回显为 chips（筛选行下方，单删/清空，尾标实时显示 `报价时间 · 不限/本周/…`）；周期筛选改落**报价创建时间**——**默认不限**（周期控件没动过时不叠加默认「本周」，动过 pills/自定义区间后才限定；左栏周期区提示卡同步显示当前范围）；表格出现「命中配件」列（`OpportunityTable` 的 `showPartHits` prop，徽标 = 报价日期 · 配置页签 · 型号×N，**不带 PN/价格**，红线）。
- **驾驶舱同口径**：`part_filters` 同参传 `/api/dashboard/summary`，KPI/图表与列表同一份匹配器（`opp_part_filter.py`）；配件筛选生效时商机创建时间窗不再叠加（时间已在报价层过滤）。
- 匹配器：`backend/app/repository/opp_part_filter.py`（列表与驾驶舱共用；命中摘要每商机最多 3 条、日期新在前）。

## 前端路由

| 路由 | 组件 |
|------|------|
| `/opportunities` | `views/opportunity/OpportunityList.vue` |

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/dashboard/summary` | 驾驶舱统计（KPI + 图表 + 结构分布），随周期/筛选联动 |
| GET | `/api/opportunities/list` | 商机列表（分页 + 筛选 + 排序，`has_committed_requirement` 只显示已提交需求单的商机） |
| GET | `/api/opportunities/part-categories` | 配件筛选类别下拉（报价明细 part_category，小写归并 + 次数） |
| GET | `/api/opportunities/part-suggest` | 配件筛选型号建议（catalogue ilike + 类别过滤，按使用次数 Top8） |
| GET | `/api/opportunities/sales-options` | 业务筛选下拉选项 |
| PUT | `/api/opportunities/{id}/meta` | 内联改状态 / 重命名 |
| POST | `/api/opportunities/{id}/trash` | 单条移至回收站 |
| POST | `/api/opportunities/batch-trash` | 批量移至回收站 |

### 查询参数 (list)
- `page`, `page_size` — 分页
- `search` — 关键词搜索
- `result` — 业务结果筛选 (pending/won/lost/expired)
- `platform`, `chassis` — 平台/形态（逗号分隔多选；由当前需求单 slots 派生值过滤）
- `part_filters` — 配件筛选条件行 JSON（`[{category, keywords[], qty_min}]`；生效时 period/start/end 改落报价创建时间，`period=all` = 不限时间——前端在周期未动过时自动传）
- `sort_by` (updated_at/created_at), `sort_order` (asc/desc)

## 权限

- 页面路由 perm：`page.opportunities_all`
- 业务筛选列 & 排行/转化图表：`canViewAll` = `auth.can('page.opportunities_all')`；无权限走个人视图（隐藏业务筛选与两张排行卡）

## 关键组件

- `OpportunityCharts.vue` — 4 张图表（横滑轨道内）
- `OpportunityPartFilter.vue` — 配件筛选触发按钮 + 条件行弹层（应用态在父页面）
- `CreateOpportunityModal.vue` — 新建商机
- `useChartTheme()` — 图表主题（canvas 不能读 CSS 变量，走真实色值）
- `useSeries()` — 平台系列选项 composable（读 system_config.server_series）

## 移动端（≤768px，2026-09-19 重构 = 纯驾驶舱 + 列表抽屉）

- **KPI 2×2 置顶**：手机端在图表区上方单独渲染 KPI 条（`.kpi-strip-mobile`，数据同 `summary.kpi`），原右栏 KPI 随 `.table-side` 整体隐藏——修复 KPI 卡沉到页面底部的问题。
- **内联表格下线**：`.table-side` 手机端 `display:none`，「商机列表」磁贴点击改为 `a-drawer`（placement=right，宽 92%）全高右滑出，抽屉即唯一列表（原为平滑滚动到下方表格）。
- **抽屉结构**：头部（商机列表 + 总数 + ✕）→ 筛选行（搜索 + 状态 + 平台 + 形态 + 业务[canViewAll] + 重置，与桌面共用 `filters` 状态）→ drill 提示（可选）→ **与桌面同一张 OpportunityTable**（8 列完整表格，横向滚动 `scroll.x=860`；创建/更新时间列排序、状态 tag 内联改、行内客户名进详情、勾选批量回收站全量可用）；抽屉内 antd 暗色覆盖因 portal 命不中 `.opp-page :deep()`，在全局样式块按 `.opp-list-drawer` 同口径补了一份。
- **跳详情收抽屉**：点客户名进详情时路由 watch 收起抽屉（KeepAlived 页面状态不收会盖住详情页）；该关闭不回写 LIST_STATE，返回时 onActivated 依 `list_drawer=true` 恢复抽屉；手动关闭则正常回写 false。
- **状态恢复**：抽屉开合态写入 `LIST_STATE`（sessionStorage），从详情页返回自动恢复；pageSize 手机端固定 10（跳过自适应）。
- **桌面零改动**：以上全部在 ≤768px 分支或 `isMobile` 门控内。
- 全局配套见 README「移动端底部导航」（DefaultLayout 级底栏 + 更多面板 + 桌宠避让）。
