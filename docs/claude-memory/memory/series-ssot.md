---
name: series-ssot
description: 系列(Orion/Polaris/Intel/工作站)统一到 system_config.server_series 单一源；兆芯=Polaris 已迁移；碰系列枚举先查 useSeries
metadata: 
  node_type: memory
  type: project
  originSessionId: d5ae4918-14a1-48a1-a3c6-ed6832daf7e3
  modified: 2026-07-23T09:08:33.645Z
---

"服务器系列 / 平台类型"枚举的**唯一权威源** = `system_config.server_series`（rules schema，存 `[{value,label}]`，经 `/api/base-configs/series` 返回 `{series:[value], items:[{value,label}]}`）。全平台四项：Orion·AMD / Polaris / Intel / 工作站。

**Why:** 用户定调（2026-07-23）——系列之前散落多处硬编码/自存（商机筛选下拉、基准配置默认值、料件 `specs.chassis`、图表配色 `PLAT_COLOR`、L6 rear-IO 分桶），改名/新增要改 N 处。确立 SSOT 后只改 server_series 一处即全站生效。业务语义：兆芯=Polaris 别名（已迁移，但 DB 实际 0 脏值——导入时 `normalize_platform` 早已清）；Intel、工作站是独立系列（服务器侧暂无对应基准配置/rear-IO，下拉里出现但料件数 0）。

**How to apply:**
- 前端取系列读 `useSeries()` composable（`composables/useSeries.ts`，模块级缓存），别再硬编码 Orion/Polaris、别各自调接口。消费点：OpportunityList 筛选、BaseConfigEditorPage、PartsLibrary（侧栏+chassis 字段）。
- 改系列名/加系列：只改 `server_series`（PUT `/api/system-config/server_series`，或 `system_config_repo.init_defaults` 种子）。
- **已知局限**：L6 rear-IO 仍按 `series==='Polaris'?'Polaris':'Orion'` 二元分桶（L6ChassisConfig.vue `loadReference`），Intel/工作站 暂复用 Orion 选项；待这些系列有独立 rear-IO 时改动态分发。
- 一次性迁移脚本 `backend/scripts/migrate_series_unify.py`（`--commit` 已于 2026-07-23 apply）：扩 server_series 成 4 项 + 兆芯→Polaris（实测 0 命中，数据早干净）。
- 颜色映射集中 `frontend/src/constants/platform.ts`（PLAT_COLOR），未数据驱动；未来可给 server_series 每项加 color 升级。
- 料号库 chassis 字段经此改造走"权威源 + 自由输入兜底"（free-tags 的 options=useSeries().items），不再是上轮的历史聚合。料件 specs.chassis 语义 = 适用系列，引用权威源值域。
