---
name: l6-chassis-legacy-flow
description: L6 机箱库流程(useL6ChassisConfig/L6ConfigCard/Wizard)读 _old 备份表，属过渡态；等 server-config 新流程成熟后再切换，别重构它
metadata: 
  node_type: memory
  type: project
  originSessionId: acc4b9d4-80af-40df-816b-47f1536dfa3b
---

L6 机箱库配置流程（`useL6ChassisConfig.ts` → `L6ConfigCard.vue` / `L6ConfigWizard.vue`，被 `views/quote/Workspace.vue:144` 使用）当前从 `l6_base_configs_old` / `l6_base_config_parts_old` 两张 **_old 备份表**读数据。这与 server-config 流程（`ConfigWizard.vue` / `api/base_configs.py`）用的 `base_configs` 新表是**两套不同 schema**：
- 旧（_old）：config_id / chassis / drive_bays / backplane_type / base_price
- 新（base_configs）：id / name / series / model / bays / bp_tri_pn / gpu_arch_default

前面板线缆已统一到 `parts_master`（category='前面板线缆'），见 `l6_chassis_repo.get_front_panel_items`。

2026-07-18：base-configs / front-panel 接口原本 500（表名错位指向新表 + base_price Decimal 序列化 + 前面板表缺失），已止血修复——base_configs 类查询指向 `_old` 表 + base_price float 化 + get_front_panel_items 改读 parts_master。

**Why:** 半完成迁移——后端把 L6 机箱库表 _old 化，但前端 Workspace 仍在用 L6ConfigCard。用户定调：维持 _old 止血现状，等 server-config 新流程做好后再统一切，现在不动架构。

**How to apply:** 碰 L6 机箱库 / `base_configs` 表 / Workspace 的 L6ConfigCard 时，知道这是过渡态——不要把 L6 机箱库流程迁回新表、也不要重构它。未来切换信号是"server-config 新流程在 Workspace 上线"。Related: [[kp-parts-unification-roadmap]]

---

**2026-07-18 切换已发生（更新）：** Workspace 中栏已从 legacy `L6ConfigCard` 切到新流程，与 server-config 页**共用** `frontend/src/components/quote/L6ChassisConfig.vue`（4 面板：基准/前面板/后面板/电源）。`server-config/ConfigWizard.vue` 瘦身改用此组件 + 自有 KP 面板。改动要点：
- L6 选配结果（base_config_id + rear/overrides 快照 `cfg.l6_bom_picks` + 重建的 L6 行）由 store `setL6ChassisPicks` 写回 `cfg.items`（category='L6'），供导出 `preview_data_loader` + 左栏 BomTable。`cfg.l6_bom_picks` 仅作切 tab 重挂 hydrate（不参与计价/显示）。
- `base_config_id` + `l6_bom_picks` 持久化进 quotation `extra_fields`（key=`config_l6_picks`），`quotation_repo.update` 自动往返。
- L6ChassisConfig 内部 `useServerConfig()`；`baseBpType` 用 `watchEffect` 跟踪 `baseBackplaneType`（**必须在 computed 声明之后注册，否则 watchEffect 立即执行触发 TDZ**——已踩坑）。
- 老 `L6ConfigCard`/`L6ConfigWizard`/`useL6ChassisConfig` 不再被 Workspace import，文件留 dormant。
- 自动 KP 同步（`sync_kp_prices_to_db`）默认关，改每 KP 卡片单条手动同步（`POST /api/quote/kp/sync-price`），env `KP_AUTO_SYNC_ENABLED=true` 可恢复。
- `_old` 备份表仍不碰。

**左栏 L6 配置单模板（2026-07-18 加）：** 左栏 L6 区不是 parts dump，而是 Excel 原始 L6 区那种 catalogue/desc/qty 摘要（无价），按机型族用 `l6.bom_templates` 表的行骨架渲染。已 seed 3 模板：`2U12标准`(IO1-4+FAN)、`4U8-GPU直连`(rear_summary Direct+gpu_power_cord)、`4U8-Switch`(rear_summary Switch+raid_slot)。`base_configs.bom_template_id` 关联。L6ChassisConfig 加载基准配置时取模板 + 算 `bomContext`（每行 desc/qty 从 part 数据解析，缺失留空），随 apply 吐出；BomTable 按 `cfg.bom_template.rows + cfg.bom_context` 渲染（无模板回落 cfg.items L6 行）。io_slot 汇总规则：`rear[slot]` option_type 计数前缀 N\* → "1\*X16+1\*X8"。

**预览 L6 对齐左栏（2026-07-21 改）：** `backend/app/services/preview_data_loader.py` 原先把 `data["l6_details"]` 直接取 `opportunity_items` 里 `category=='L6'` 的料号行（Chassis/Cable_xxx/三模背板…的 PN dump），与左栏不一致。已改：新增 `_load_l6_from_template(quotation)` 读 `quotation.extra_fields.config_l6_picks[cfg].{bom_template,bom_context}`，对**非 excel**（`bom_source!='excel'`）且有模板的 cfg 展开模板行（字段 key 保持 part_name/spec/qty/config_name 不变，只换取值来源 → label/desc/qty，故 Univer binding 无需改）；`bom_source=='excel'` 或无模板的 cfg 回落原料号行。用户定调的产品规则：**excel 上传→原样显示 excel 内容；新建配置(非excel)→走 BOM 模板；无论如何不直接列 L6 机箱料号 PN**。计价仍走 cfg.items（config_summary 聚合用 raw items，未改），只是 L6 区域显示换源。
