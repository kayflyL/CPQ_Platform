# 商机驾驶舱 (OpportunityList)

> 最后更新：2026-07-31

## 功能概述

商机线索模块的主入口页面，提供数据可视化仪表盘 + 商机列表管理。

### 核心功能
1. **KPI 指标卡** — 总商机数、总配置数、周期新增商机、周期新增配置（带 sparkline 趋势）
2. **图表区** — 4 张 ECharts 图表（Bento 2×2）：
   - 趋势分析（商机/平台趋势切换；柱状+折线 / 面积折线）
   - 结构分布（平台/机箱切换；环形图 / 玫瑰图，可点击下钻）
   - 业务排行（横向条形，按销售商机数 Top5 + 其他可展开）
   - 线索转化（销售直列清单：每行 线索量/成交量/成交率%，成交率色码 高绿·中蓝·低灰 一眼区分；行均分填满卡高，点「其他 N人」展开逐人明细、收起按钮折叠；成交量=周期内 `result=won`，随周期/筛选变化）
3. **商机列表** — 右侧面板，支持：
   - 列表项以**客户名称**为主锚点（点击进入详情），副信息：销售/平台/机箱/数量/配置/创建日期
   - 业务结果筛选（进行中/已中标/已丢标/已过期）
   - 平台类型多选筛选
   - 机箱形态多选筛选
   - 排序（更新时间 新→旧 / 旧→新）
   - 关键词搜索（客户/销售/备注）
   - 图表下钻联动筛选
   - 批量选择 → 批量移至回收站
4. **新建商机** — Modal 弹窗，输入客户名称（必填）+销售人员（可选）；其余信息在商机详情页补全
5. **时间周期切换** — 本周/本月/本年 + 自定义（上周/上月/去年/近30天/近90天/指定月/任意区间）

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
| `opportunities` | `quotations` | 报价单（统计 config_count） |
| `rules` | `system_config` | 系统配置（server_series 平台系列枚举） |

## 关键组件

- `CountNumber.vue` — 数字动画计数
- `useChartTheme()` — 图表主题 composable
- `useSeries()` — 平台系列选项 composable（读 system_config）
- `PLAT_COLOR` — 平台颜色常量 (`@/constants/platform`)
