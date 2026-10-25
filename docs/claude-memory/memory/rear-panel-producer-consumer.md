---
name: rear-panel-producer-consumer
description: 后面板选料权属——基准配置下拉选功能产 defaults、配置页只调数量；两页 UI 不同共享数据
metadata: 
  node_type: memory
  type: project
  originSessionId: 2d167dfc-2df5-4e83-87ba-083c5eabdc59
  modified: 2026-08-07T14:20:03.719Z
---

后面板「选料 vs 调数量」的权属定调（2026-08-07 用户拍板，模型 C 最终态）：

- **基准配置编辑器 = 选料件（类型卡 + 卡内料号组成）**：每槽列「类型卡」(X8/X16/SATA/NVMe = option_type，来自 rear_io 目录)；每张卡内"+加料"下拉逐件选具体料号 PN（按 io_slot+option_type 过滤，候选 = 该 option 的 items）。**多料组成一张捆绑卡**（SATA=模组+供电线+SAS线 三件一卡，价=合计）；**一槽可多类型**（IO1 可同时配 X16 和 X8）。数据存 `rear_slots[].defaults` = **PN 料号列表**（不是 option_type）。
- **服务器配置页选了基准机箱后 = 消费/调数量**：`rearOptionsLocked`（L6ChassisConfig 计算属性）把 rear_io 目录**按基准选中的 PN 过滤**——只留基准选中的类型卡、卡内 items 只留选中的料号（重算 total_price）。这让**配置页"显示哪个料"完全受基准配置管理**（不再系统按 option_type 属性自动列全部）。`seedRearFromDefaults` 用 `pnsToTypes`（按目录 PN→option_type）播种 `rear`（每类型卡数量=1），只能给整张卡调数量不能换料。旧基准/未配槽位（defaults 空）→ 返回全目录自由选（向后兼容）。
- **关键：数量是给「整张类型卡」加的，不是给卡内单个料加**。X8 卡里哪怕 2 个料，X8 卡数量=2 = 2 套这组料（不是 4 个料）。SATA 三件同理，点数量整组乘。这正是配置页 option 卡片模型（一张卡一个数量、价=捆绑合计）。
- **硬锁 vs 软默认**：**后面板 + 前面板线缆 = 硬锁**（机箱定义，配置页不能换料只能调数量）；**电源 = 软默认**（配置时功率要随 GPU 调，能改）。基准配置存默认线缆 `config_content.front_cables`（按盘类 SATA/SAS/NVMe）+ 默认 PSU `config_content.default_psu_pn`。前面板：配置页 `frontCableLocked`（基准选了该盘类就锁死、不渲染选择器，没选的盘类回退自由选）；电源：`effectivePsuPn` = 手改 overrides 优先 → 基准默认 → 空（可改不锁死）。基准编辑器②前面板/⑦供电已接入（2026-08-07）。
- **两页 UI 故意不同**（基准=类型卡内选料号 / 配置页=类型卡调数量），任务不同；共享 PN→type 数据 + `useRearState.ts`。

rear_io 目录机制：`rear_io_repo.py` 从 `parts_master.specs` 纯聚合——按 `io_slot`(数组,一料可跨多槽) + `option_type` 分组，同槽同 option_type 的料自动成一捆（**无显式 bundle 字段**）；`chassis` 过滤机型。所以"类型卡"= option_type，"卡内料"= 该 (slot,option_type) 的 items（捆绑件是该功能所需料的物理组，不可拆）。后端 JSONB 透传 defaults(PN 列表)，无独立表。

碰后面板/基准配置/配置页前先看；别在配置页加回自由选料（已降级 qty-only 料号锁），别把基准 defaults 当 option_type 用（是 PN 列表，配置页要 pnsToTypes 转换）。文档 `docs/frontend-pages/servers/base-config-editor.md`。关联 [[ocp-is-networking-not-pcie]] [[rear-panel-unified-to-parts-master]] [[template-json-opaque-blob]]。
