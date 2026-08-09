# BOM 模板配置指南

> 适用模块：策略中心 → 选型配置 → BOM 模板
> 说明对象：BOM 模板每一行「要填什么 / 根据什么配件填充 / 内容来自哪里」。
> 口径来源：前端工作台 `bomRuleEngine.ts` 与后端方案助手 `bom_template_eval.py` 两套求值引擎（同一规则语义，改动模板后两处同时生效）。

---

## 1. 什么是 BOM 模板

BOM 模板定义了 **L6 配置单（服务器配置单）的左栏行骨架**：

- 每行 = **行骨架**（`type` 行类型 / `label` 显示标签 / `slot` IO 槽位 / `mode` 后面板形态）+ **解析规则**（`desc` 描述怎么算、`qty` 数量怎么算）。
- 规则跟随模板以 JSONB 存储，**不写死在代码里**，由你在模板编辑页逐行配置。
- 基准配置（服务器型号）通过 `bom_template_id` 关联一个模板；方案助手 / 工作台按模板生成配置单时，逐行求值，**全空的行自动隐藏**。
- 行求值语义：`desc` 或 `qty` 算不出 → 走**兜底 fallback**（若启用）；`manual`（手填）→ 留空，由工作台手填，不走兜底。

**消费链路**：`基准配置.bom_template_id → 模板.rows + rule → 求值引擎（bomRuleEngine / bom_template_eval）→ L6 配置单行`。求值依赖的数据来自：基准配置（bays / psu_bays / config_content / 底盘件）、KP 行（盘 / GPU / RAID / 网卡）、料号库 parts_master。

---

## 2. 行类型速查（11 种）

> 每一行要填什么、根据什么配件填充、内容来自哪里、示例。

| 行类型 | 用途 | 要填字段 | 根据什么配件 | 内容来源 | 示例 |
|---|---|---|---|---|---|
| `front_backplane` 前面背板 | 左栏第 1 行，描述前面板背板/盘位能力 | type + label；desc=template/fixed；qty=fixed | 基准配置 `bays`（盘位数）+ 背板件 `specs.bt`（tri→SATA/SAS/NVMe，dc→SATA/SAS） | 配置参数 bays、背板 bt 派生（bp_type_desc） | desc=template `${bays}*3.5 SATA/SAS` → `24*3.5 SATA/SAS`；qty=fixed 1 |
| `io_slot` IO 槽位（IO1~IO4） | 列出后面板 IO 槽位的 riser 规格 | type + slot=IO1~IO4 + label；desc=struct_count(io_slot)；qty=fixed | 不读具体件；看 GPU 数量（>0 → 全槽 riser_x16）与高带宽网卡 100G+（IO1 升级 x16） | config_content.standard_riser（按槽位默认）/ riser_x16（升级规格）；未配置留空手填 | desc=struct_count(io_slot)；qty=fixed 1 |
| `rear_summary` 后面板汇总（Direct/Switch） | 汇总后面板连接形态：direct=点对点直连；switch=经 Switch 板全互联 | type + mode=direct/switch + label；desc=struct_count(rear_all/gpu_direct) 或 config_value；qty=fixed/config_calc | GPU 数量、NVMe 盘数、后面板 IO 类型 | 按结构派生统计 | desc=struct_count(rear_all) → `2*GPU+4NVME`；qty=fixed 1 或 config_calc(gpu_qty) |
| `heatsink` 散热器 | 散热器型号/数量行 | desc=part_field(category=heatsink, field=name/pn/specs.*)；qty=part_quantity(category=heatsink) | 基准配置底盘件 category=heatsink | parts_master 料号库 + base_config_parts.quantity | desc=part_field(heatsink, name)；qty=part_quantity(heatsink) |
| `fan` 风扇 | 风扇型号/数量行 | desc=part_field(category=fan)；qty=part_quantity(category=fan) | 基准配置底盘件 category=fan | parts_master 料号库 + 数量 | desc=part_field(fan, name)；qty=part_quantity(fan) |
| `psu_requirement` 电源需求 | 电源功率需求行（如 2×2000W） | desc=template（${psu_qty}/${psu_wattage}/${psu_name}）；qty=config_calc(psu_qty) | 基准配置 psu_bays + chassis 信号 psu_wattage + 底盘件 category=psu 的 name | 配置参数 + 料号库 psu 件名 | desc=template `${psu_qty}×${psu_wattage}W ${psu_name}`；qty=config_calc(psu_qty) |
| `gpu_power_cord` GPU 电源线 | GPU 供电线行（配 GPU 才显示，不配整行隐藏） | desc=config_value(gpu_power_cord_desc)；qty=config_calc(gpu_cable_qty) | KP 行 GPU 数量（gpu_qty） | gpu_qty 派生 | desc=config_value(gpu_power_cord_desc) → `GPU power cable`；qty=config_calc(gpu_cable_qty) |
| `power_cord` 电源线 | 整机电源线行（数量跟电源数走） | desc=fixed；qty=config_calc(psu_qty) | 电源数量 psu_qty | 固定文案 + 配置派生 | desc=fixed `C13-C14 电源线`；qty=config_calc(psu_qty) |
| `rail_kit` 滑轨 | 机架滑轨套件行 | desc=part_field(category=rail)；qty=part_quantity(category=rail) | 基准配置底盘件 category=rail | parts_master 料号库 + 数量 | desc=part_field(rail, name)；qty=part_quantity(rail) |
| `cable` 线缆 | 数据线缆汇总行：RAID SAS 线 + NVMe 线 | desc=config_value(cable_desc)；qty=fixed（1 套） | KP 盘行介质数量（SAS/SATA→RAID SAS 线按 4 向上取整；NVMe→NVMe 线按 2 向上取整）+ RAID 卡型号（决定是否生成 SAS 线） | cable_desc 派生 | desc=config_value(cable_desc) → `8 SAS Cable，2 NVMe Cable`；qty=fixed 1 |
| `raid_slot` Raid slot（Switch 机型） | Switch 拓扑机型的 RAID 卡槽位行 | desc=manual；qty=manual | 无自动推导；由用户在 L6 编辑器手填 | 手填 | desc=manual；qty=manual |

---

## 3. 模板分类说明（为什么不同服务器 BOM 格式不一样）

不同服务器形态的行骨架不同，**不是随意删减，而是由机箱高度（散热/扩展）与 GPU 互联拓扑（后面板/RAID）决定的**：

### 3.1 2U 通用（如「2U12标准」）
- **定位**：机架通用计算的标准高度。2U 是散热、盘位、扩展的平衡点（业界常称"瑞士军刀"机箱），通常支持 ≤4 张 L40S 级风冷 GPU，总功耗 2~2.5kW 级别。
- **行骨架特点**：
  - **有 `io_slot` 行（IO1/IO2）**：2U 机箱矮，PCIe 卡需要 riser 转接板水平安装，每个 IO 槽位的 riser 规格不同（IO1/IO2 可不同），所以要逐槽列出。
  - 后面板多为 `direct`（GPU/NVMe 直连），无 `raid_slot`。
- **为什么这样**：2U 高度限制 PCIe 卡只能横插（riser），IO 拓扑被 riser 拆分，需逐槽说明；盘位与 IO 是折中设计。

### 3.2 4U GPU 直连（如「4U8-GPU直连」）
- **定位**：全高 PCIe 卡 + 大风道，支持 8×GPU 级别；drives / PCIe / GPU 优先，少折中。
- **行骨架特点**：
  - **无 `io_slot` 行**：4U 全高，卡直接竖插主板，不经过 riser 转接，无需逐槽说明。
  - `rear_summary` = `direct`：GPU/NVMe 点对点直连 CPU/PCIe，省线缆、扩展简单，适合推理 / 单卡任务；汇总只列 GPU + NVMe。
  - 无 `raid_slot`。
- **为什么这样**：4U 高度够，不需要 riser 转接；直连拓扑下数据盘走板载/直连，RAID 槽位不是固定骨架。

### 3.3 4U GPU Switch（如「4U8-Switch」）
- **定位**：NVSwitch 全互联拓扑（all-to-all），多卡并行通信带宽大，适合大模型训练（数据并行 / 张量并行）。
- **行骨架特点**：
  - `rear_summary` = `switch`：经 Switch 板全互联。
  - **有 `raid_slot` 行**：Switch 拓扑改变 IO 域，数据盘通常走 RAID 卡，RAID 卡槽位无法自动推导，需人工手填确认。
  - 相比直连需要 Switch 板 + 背板 + 更多线缆。
- **为什么这样**：训练场景需要 GPU 间全互联（NVSwitch 提供数百 GB/s 级 all-to-all 带宽），代价是额外 Switch 芯片、背板与线缆；IO 拓扑被 Switch 占用，RAID 等外围 IO 需要单独规划。

### 3.4 一句话总结
> 2U = 平衡通用（riser 拆分 IO → 逐槽说明）；4U = 全高多 GPU（免 riser → 无 io_slot 行）；直连 = 点对点省线缆；Switch = 全互联训练（多线缆/背板 + RAID 槽位手填）。

---

## 4. 规则来源 kind 速查

每一行的 desc（描述）与 qty（数量）独立配置，支持以下来源：

### Description（desc）
| kind | 含义 | 数据来源 | 示例 |
|---|---|---|---|
| `fixed` | 固定文字 | 写死，不引用数据 | `C13-C14 电源线` |
| `part_field` | 取料号字段 | category 匹配基准配置底盘件，读 name/pn/specs.* | category=heatsink, field=name |
| `template` | 模板拼接 | ${变量} 插值，任一变量缺失整串算不出（走兜底/留空） | `${bays}*3.5 SATA/SAS` |
| `struct_count` | 按结构自动生成 | io_slot=riser 规格；rear_all=后面板汇总；front_cables=前面板线缆 | scope=rear_all → `2*GPU+4NVME` |
| `config_value` | 取配置参数 | 读配置/派生值单值 | key=gpu_power_cord_desc |
| `manual` | 手动填写 | 不自动计算，工作台手填 | — |

### Quantity（qty）
| kind | 含义 | 数据来源 | 示例 |
|---|---|---|---|
| `fixed` | 固定数量 | 写死 | 1 |
| `part_quantity` | 取料号数量 | category 匹配底盘件，取 base_config_parts.quantity | category=fan → 4 |
| `config_calc` | 按配置数量 | 取配置/派生值：psu_qty=电源数、gpu_cable_qty=GPU 数 | key=gpu_cable_qty |
| `manual` | 手动填写 | 不自动计算，工作台手填 | — |

**可用模板变量**：`${bays}` `${form}` `${series}` `${bp_type}` `${psu_qty}` `${psu_wattage}` `${psu_name}` `${gpu_qty}` `${gpu_cable_qty}` `${standard_riser}` `${riser_x16}` `${bp_type_desc}` `${gpu_power_cord_desc}` `${nvme_count}` `${cable_desc}`

---

## 5. 常见问题

- **为什么有些行算出来是空的？** desc 与 qty 都算不出时整行隐藏（例如没配 GPU 时 `gpu_power_cord` 行）。算不出且非 manual → 优先走 fallback，再不行留空手填。
- **修改模板后哪些地方生效？** 所有关联该模板的基准配置立即生效（方案助手 + 工作台两套引擎同口径）。
- **删除模板会怎样？** 关联的基准配置变为无模板，L6 配置单不再按行骨架生成。
- **`raid_slot` / IO 槽位这类为什么不能自动算？** Switch 拓扑的 RAID 槽位、特定 riser 规格依赖机型实际布局，属人工确认项，系统刻意不硬编码。
