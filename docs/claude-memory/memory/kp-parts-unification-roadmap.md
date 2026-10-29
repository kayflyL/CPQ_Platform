---
name: kp-parts-unification-roadmap
description: KP配件体系——L6件与KP件分开管理(用户定调) + derive已知bug + 阶段进度(1/2完成,3修derive)
metadata:
  node_type: memory
  type: project
  originSessionId: 756f8d5d-bc9b-4c15-8de0-b3d945e69a15
---

**重要更正（2026-07-18）**：本条原名"unification roadmap"，早期基于 `migrate_to_parts_master.py` 脚本误判"长远统一到 parts_master"。**用户明确纠正：L6 机箱件和 KP 部件本来就分开管理，不合并**。方向已纠正，下面是正确版本。

## 正确方向（用户定调）
- **L6 机箱件（`parts.parts_master`）和 KP 部件（`kp.kp_parts`）分开管理**，不合并、不迁移
- 理由：两类性质不同——L6 件=底盘/结构件/电源/背板，随机型固定（base_config 引用）；KP 件=CPU/GPU/内存/硬盘/网卡，用户动态选配。属性/管理页/生命周期都不同
- 合并的硬伤：配件列表页（`/base-pricing` 管 parts_master）会混入 CPU/GPU；产生重复数据需同步；且丢掉 KP 的 6 表规范化模型（brand/系列/价格历史压成 JSON 损失表达力）
- `migrate_to_parts_master.py` 是**早期被放弃的统一尝试**（KP 件从未真迁进去），别当成长期任务
- derive 混合查询是合理的（L6 查 parts_master、KP 查 kp_parts），保持
- brand 独立成列、applicable.series 用 JSON 数组（不用 kp_part_compat 表）—— 在 kp_parts 上做（阶段2 已完成）

## 现状（2026-07-18 更新，两张表严格分开）
- **KP 配件 = `kp.kp_parts`**（190 条）：CPU/GPU/内存/硬盘/网卡/NVSwitch/NVLink。brand（72）+ CPU applicable.series（22）已回填；tdp 部分（AMD 9554/9654=360）。oem_sku 多为空→pn=name；例外：H100/A800/NVSwitch/NVLink 有正式 oem_sku（S.E.E.xxx，阶段4 从 l6 迁来）。**管理页 = BasePricing（`/base-pricing`，走 `/api/admin/kp` CRUD）**——能编辑 tdp（规格参数 key=tdp）/brand/applicable.series（2026-07-18 加的多选编辑器）/价格/类别。查询接口 `/api/kp`（ConfigWizard 用）是另一套，只有 GET。
- **L6 配件 = `l6.parts_master`**（36 条）：机箱/主板/散热/背板/电源/Riser/线缆等。表结构 `pn/name/category/sub_type/unit_price/specs(jsonb)/tdp/cables_per`（**无 applicable 列**，适配信息在 specs）。`PartsMasterRepository`（`/api/parts`、料号库页、BaseConfigBuilder）查它；`base_configs.bp_tri/bp_dc` + `base_config_parts.pn` 的 FK 指向它
- ~~`parts.parts_master`~~：**已删除**（原是被 FK 引用的废弃第三张表；整理时 3 个 FK 改指向 `l6.parts_master` 后 DROP）。注意 `base.py` 里 `parts_engine`（schema=parts）是历史遗留、无人用
- **避坑**：之前误查 `parts.parts_master`（36 条 L6 件）当作料号库，导致一系列误判。真料号库是 `l6.parts_master`（PartsMasterRepository 用 `l6_engine`）
- series 取值 `Orion / Polaris`（`l6.base_configs.series`）

## derive bug（2026-07-18 已修，功耗推导已验证生效：9554×2→cpu=720）
4 个 bug 全修，在 `backend/app/api/derive.py` + `backend/app/engine/derivation_engine.py`：
- `_kp_part_by_pn` 查询：`WHERE p.oem_sku=:pn`（oem_sku 空）→ `COALESCE(NULLIF(oem_sku,''),name)=:pn`
- 列名：`ph.unit_price/effective_date`（不存在）→ `price/price_date`
- cat 命名：前端传 `CPU/HDD-SSD`，derive 判 `cpu/drive` → 加 `CAT_NORMALIZE` + `_norm_cat` 归一化
- tdp 类型（latent）：`kp_part_specs.spec_value` 是 text，tdp 读出是 str，`int += str*int` TypeError → `_power_parts` 加 `float(tdp)` 容错（数据来了才暴露）
- specs 聚合：`_kp_part_by_pn` SELECT 补 `jsonb_object_agg(kp_part_specs)`，让 tdp 能被读到

## 阶段进度
- **阶段1 完成**：`frontend/src/components/server-config/ConfigWizard.vue`（注意：不是 `L6ConfigWizard.vue`）5 核心类别常驻 + CPU 过滤
- **阶段2 完成**：kp_parts 加 `applicable jsonb` + brand 回填 + CPU `applicable.series` + `/api/kp/parts` `?series=` 过滤 + 前端数据驱动。脚本 `backend/scripts/migrate_kp_brand_series.py`（幂等）
- **阶段3 derive 代码修复完成（2026-07-18）**：4 bug 全修，功耗推导链路通。tdp 数据仅 4 条 AMD（9554/9654=360）已回填（`scripts/migrate_kp_tdp.py`），其余 41 条（AMD 其余 8 含 Orion 默认 7A23 / Intel 4 / 国产 CPU 6 / GPU 27）待用户补——tdp 是业务关键数据（影响电源 BOM），不猜值。**注意：Orion 默认选 CPU=AMD EPYC 7A23（无 tdp），默认功耗仍 0**，需补 7A23 tdp 或调默认选中。
- **阶段4 三表整理完成（2026-07-18）**：删第三张表 `parts.parts_master`；`l6.parts_master` 混入的 6 条 KP 件（CPU/GPU/NVSwitch/NVLink）移到 `kp_parts`（9654/9554 去重，H100/A800/NVSwitch/NVLink 新增 + 建 NVSwitch/NVLink 类别）；`parts.` 的 33 条 L6 件并入 `l6.parts_master`（applicable 并进 specs）；3 个 FK（base_configs.bp_tri/bp_dc、base_config_parts.pn）从 `parts.` 改指向 `l6.parts_master`。脚本 `migrate_consolidate_parts.py`。**最终两张干净表**。
- **遗留**：① Intel 4 条 CPU `series=[]` 待确认归属；② tdp 41 条待补（`scripts/migrate_kp_tdp.py` 框架在）；③ ~~locked 标注错~~ **已修**（BaseConfigBuilder 文案改 + 不写 locked:true + ConfigWizard 去 🔒 标记，2026-07-18）；④ 基准配置只选底盘件+背板、未含 CPU/GPU——若要"整机选料"需大改（`base_config_parts.pn` FK 指向 `l6.parts_master`，存 KP 件 pn 会违反 FK，需重构关联模型），待用户定。
- **避坑**：① 之前误查 `parts.parts_master`（废弃表）当作料号库，真料号库是 `l6.parts_master`；② 删 `parts.parts_master` 后要扫代码里的 `parts.parts_master` 引用——`base_config_repo.py` 的 JOIN/SELECT 已改成 `l6.parts_master`（get_parts、check_bays_match），其余在 scripts/ 下的一次性脚本不影响运行。

**Why:** 早期误判统一方向，用户纠正为分开。两类件性质不同，合并制造问题（重复数据+管理混乱+丢规范化模型）。
**How to apply:** KP 工作就在 `kp_parts` 上做（长期数据源，别废）；L6 件在 `parts_master`；derive 各查各的。**别再提"统一到 parts_master"**。相关：[[app-startup]]
