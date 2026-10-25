---
name: rear-panel-unified-to-parts-master
description: 后面板 IO/网络统一到 parts_master.specs 驱动；旧 l6_rear_panel_items 新流程退役；含两条用户定调(机型差价靠拆PN、数量默认填满槽)
metadata: 
  node_type: memory
  type: project
  originSessionId: 736e9464-71b5-4d05-80fd-ede1b053282a
---

后面板 IO 与网络(2026-07-20 重构)从「两张割裂的表」统一为**单一数据源 parts_master**：

- **数据层**：后面板语义全部存 `parts_master.specs`：`io_slot`(string[],能插的槽位)、`option_type`(代号 x16/x8/nvme/sata/ocp_x8/ocp_x16)、`chassis`(string[],适用机型)。**bundle(多料捆绑)无独立字段**——由 `(io_slot ∩ option_type)` 分组派生(如 IO3/sata = 模组+miniSAS线+电源线 3 颗)。option.total_price = Σ member.unit_price(每件1×),数量由配置页步进器定。
- **后端**：`rear_io_repo.py` 改查 parts_master(不再读 `l6_rear_panel_items`)；`parts_master_repo.list()` 加 `specs_filters` 参数(JSONB `@>` 过滤,数组字段传 list)。
- **旧表 `l6_rear_panel_items` 保留不删**——legacy 流程(`l6_chassis_repo.py` CRUD + `L6ConfigWizard.vue`/`useL6ChassisConfig.ts`)仍读它,属 [[l6-chassis-legacy-flow]] dormant 态,不碰。
- 回填脚本：`backend/scripts/backfill_rear_specs.py`(以旧表为权威源,把当年 migrate_to_parts_master.py 写降级的 specs 修正：io_slot 修成数组、option_type 用代号非中文、chassis 剔2U只留机型系列、丢 quantity 键)。

**两条用户定调(别再推翻)**：
1. **机型差价靠拆 PN,不靠一料多价**——一颗料一个 unit_price；Polaris 变体若真不同价就另起独立 PN。`chassis` 仅作筛选属性。现状 S.E.E.0001561/0002346 在旧表有 Orion/Polaris 两价 → 已 prominently 报告,等用户手动拆 Polaris PN(脚本不擅自造 PN)。
2. **数量纯配置时定,默认填满槽**——料号表不存 qty。规则:`incOption` 首次点击 IO3/IO4/OCP → 默认 cap；IO1/IO2(组合槽,1×X16+1×X8)→ 默认 1。步进器仍可任意手改(遵循 [[derive-must-have-manual-fallback]])。已验证精确复现旧表全部默认数量。

**料号编辑表单(PartsLibrary.vue)两段化**：砍掉中段「规格参数」,只剩 基础信息 + 扩展属性。扩展属性由 `constants/partSpecFields.ts` 的 `ATTR_SCHEMA` 字典驱动渲染：`enum-single`(如 option_type)下拉单选 / `enum-multi`(io_slot/chassis/backplane)下拉多选 / `free-tags`(form/drive_bays,输入回车成标签,antd `a-select mode="tags"`) / number / text。未知键默认 free-tags。类别切换按 `SUGGESTED_KEYS_BY_CATEGORY` 预填空行。

**已知遗留**：旧存档 quotation 的 `config_l6_picks.rear[slot]` 用旧语义(option_type 出现1次=含qty的total_price)；新模型 rear[slot] 出现N次=N实例×per-instance价。重载老报价单时后面板价会变(单料选项不受影响,多实例选项需重选)。未做迁移(过渡态系统,老单很少)。

相关：[[parts-section-taxonomy]]、[[ocp-is-networking-not-pcie]]、[[derive-must-have-manual-fallback]]、[[l6-chassis-legacy-flow]]。
