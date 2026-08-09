# 基准配置编辑器 (BaseConfigEditorPage)

> 最后更新：2026-08-07

## ⚠ 布局重构进行中（2026-08-07 起）

页面正从「左编辑/右摘要单卡」迁移到「按整机解剖分组」布局。当前**骨架阶段**已落地：

- **基准信息卡**（顶部原位）：名称 / 系列 / 形态 / 盘位 / BOM 模板
- **10 个解剖分组卡**（骨架，待逐节承接）：①机箱主体 ②前面板 ③后面板 ④主板 ⑤处理器 ⑥内存 ⑦供电 ⑧硬盘 ⑨扩展 ⑩散热
- **备份卡**（底部，虚线框）：现「机箱能力 / riser 升级规格 / 标准内存速率 / 底盘件」**整体收口于此**，绑定与保存链路不变；待新分组承接后删除

### 角色定调（驱动本次重构）
- **基准配置 = 选料件**：前/后面板在基准配置编辑器里选具体料件（哪根线缆、每槽哪张卡）
- **服务器配置页选了基准机箱后**：前/后面板**只能调数量**，不能换料件；改料件回基准配置编辑器。**电源例外**——PSU 型号仍在配置页选
- 「后面板」已抽出共用组件 [RearPanel](../../src/components/server-config/RearPanel.vue)（基准编辑器全选项可选 / 配置页按基准 `defaults` 锁定只调数量）；「前面板」待同模式抽取

### 进度
- ✅ **数据模型**：`rear_slots[]` 每槽 `defaults: string[]`（option_type 多重集，与配置页 `rear[slot]` 同形：重复即数量，如 `['x16','x16']`=2 条 X16）；`config_content.front_cables={SATA,SAS,NVMe}` PN。后端 JSONB 透传，**无需后端/迁移改动**（`[[template-json-opaque-blob]]`）。TS 类型 [serverConfig.ts](../../src/api/serverConfig.ts) `RearSlot`/`ConfigContent`
- ✅ **③后面板：类型卡 + 卡内料号组成（模型 C）**：基准编辑器每槽列「类型卡」(X16/X8/SATA/NVMe = option_type)；每张卡内"+加料"下拉逐件选料号 PN（按 io_slot+option_type 过滤，候选 = 该 option 的 items），多料组成捆绑卡(价=合计)、一槽可多类型（IO1 可同配 X16+X8）。数据存 `rear_slots[].defaults` = **PN 料号列表**。rear_io 目录按 `parts_master.specs`(io_slot+option_type) 聚合，捆绑件 = 同槽同 option_type 的料物理成组（不可拆）。**取代** opt-block 步进器(曾"锁死")、单类型下拉、riser 预填三套废弃方案
- ✅ **配置页接 RearPanel + defaults 播种**：配置页用 [RearPanel.vue](../../src/components/server-config/RearPanel.vue)（opt-block 类型卡调数量）；`rearOptionsLocked` 把 rear_io 目录**按基准选中的 PN 过滤**（只留选中类型卡、卡内只留选中料号）→ **配置页"显示哪个料"完全受基准管理**；`seedRearFromDefaults` 用 `pnsToTypes` 把基准 `defaults`(PN 列表)算成 option_type 播种 `rear`（数量=1，只调数量不改料）。无默认的旧基准/未配槽位回退全目录自由选。两页 UI 故意不同（基准=类型卡选料号 / 配置页=类型卡调数量）。**后面板=硬锁**（机箱定义）
- ✅ **②前面板（锁死，同后面板）**：按盘类(SATA/SAS/NVMe)选默认线缆料号，存 `config_content.front_cables={SATA,SAS,NVMe}`；配置页前面板**三张卡统一为"价格+步进器"**（无选择器，不能换料；线缆 = 基准默认，没配的盘类取料号库首件兜底），数量跟盘数 CRE 走
- ✅ **⑦供电（能力 + 软默认）**：电源槽位 `psu_bays` + PSU 瓦数档位 `psu_wattages`（推断收敛档位）+ 默认 PSU 料号（存 `config_content.default_psu_pn`）；配置页 `effectivePsuPn` 手改优先 → 基准默认 → 空（**电源型号配置页可改，不锁死**）。电源是软默认（配置时功率要随 GPU 调），与前面板/后面板硬锁区分
- ✅ **①机箱主体（固定件总括）**：机箱/辅料/线缆固定件(机箱主体/滑轨/标签/包装材料/扎带/螺丝/高速存储信号线/电源分配线缆/电源线)。能力/约束字段已归各分组（⑤处理器=CPU 颗数/TDP 上限、⑥内存=条数/通道/标准速率、⑦供电=电源槽位/PSU 档位、⑨扩展=GPU 槽上限/架构），线缆默认另由 ②⑦ 选择器选，避免和选择器重复
- ✅ **④⑤⑧⑨⑩ 固定件分组（能力 + 底盘件按分类迁入）**：通用「固定件」模板按 `SECTION_CATS` 映射驱动——④主板(主板/托盘/SCM后IO板/BMC/低速控制信号线)、⑤处理器(CPU 颗数/TDP 上限 + CPU散热器/支架)、⑧硬盘(前置硬盘背板)、⑨扩展(GPU 槽上限/架构 + PCIe Riser卡/后置SATA·NVMe模组)、⑩散热(机箱风扇/导风罩)。底盘件函数按对象操作；数据仍是 `base_config_parts` 平铺，按 category 归入对应分组显示+编辑
- ✅ **⑥内存（能力属性）**：内存条是 KP 配置件（配置页选），不进基准；这里存「内存物理边界与标准」——条数上限 `max_dimm` / 每路通道数 `mem_channels` / 标准内存速率 `config_content.standard_mem_speed`（容量反推按「每路通道数 × CPU 路数」选条数、不超过上限；需求未写速率时按标准速率选件）
- ✅ **备份卡已删除**：能力/约束字段归各分组（CPU→⑤、内存→⑥、电源→⑦、GPU→⑨）、标准内存速率→⑥、全部底盘件按分类→各分组，备份卡清空删除。10 个解剖分组全部激活，无"待填充"。`draggable`/`chassisCats`/`partsOf`/`onCatChange`/`migratedCats`/`unmigrated*`/`.backup-card` 等死码已清
- ✅ **机箱形态 form-aware（2U/4U 区分）**：切换机箱形态自动重置结构性默认——后面板布局（`rearSlotsFor`：2U=IO1-4+OCP、4U=仅 OCP）、电源槽（2U=2、4U=4）、GPU 槽（2U=0、4U=8）、GPU 架构（`formDefaults`：2U=无、4U=直通）。**GPU 架构选项按形态**（`gpuArchOptionsFor`：4U=直通(8 GPU·CPU直连)/交换(10 GPU·PCIe Switch) 二选一；2U=无 GPU）。4U 是 AI GPU 机（手册：8-10 双宽 GPU、4 PSU 3+1、12 风扇、后面板 GPU×10），与 2U 通用机（IO riser、2 PSU、6 风扇）结构不同

## 功能概述

基准配置的全页编辑器：基准信息卡（顶部）+ 10 个整机解剖分组（①机箱主体～⑩散热，全部激活）+ 摘要（右侧）。

### 核心功能
1. **左侧编辑面板**：
   - 基础信息：名称、系列、机箱形态、盘位、关联 BOM 模板
   - **机箱能力（字段归各解剖分组，非独立卡）**：电源槽位 psu_bays / PSU 档位 psu_wattages 在⑦供电；CPU 颗数上限 max_cpu / TDP 上限 max_tdp 在⑤处理器；GPU 槽上限 gpu_slots / GPU 架构 gpu_arch_default 在⑨扩展；内存条数上限 max_dimm / 每路通道数 mem_channels / 标准内存速率 standard_mem_speed 在⑥内存；后面板槽位布局 rear_slots（可增删行 + 恢复标准布局）在③后面板。默认/选项走 `chassisMeta.ts` SSOT（DEFAULT_REAR_SLOTS / GPU_ARCH_OPTIONS）；「恢复标准布局」按 form+series 取底座模板（`rearSlotsFor`：2U AMD=IO1-4+OCP / 2U Polaris（兆芯）=IO1-4 无 OCP / 4U=仅 OCP（GPU 走 gpu_slots+gpu_arch，业内 GPU 机无 IO1-4））
   - 料件清单：可拖拽排序的料件列表
     - 分类选择（全部/特定分类）
     - 料号选择（PartPicker 组件）
     - 数量设置
     - 添加/删除料件行
2. **右侧摘要面板**：
   - 料件总数
   - 成本合计
   - 功耗合计（TDP）
3. **保存/取消** — 创建或更新基准配置（save payload 含机箱能力字段；历史曾把 gpu_arch_default 写死 'none' 的 clobber 坑已修）

### 数据流
- 新建模式：空表单
- 编辑模式：加载现有基准配置（含料件列表）
- 料件从 parts_master 表读取
- 分类从 kp_categories 表读取
- BOM 模板从 bom_templates 表读取

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/base-config/:id?` | `views/server-admin/BaseConfigEditorPage.vue` |

参数：
- `id` 为空或 `new` → 新建模式
- `id` 为数字 → 编辑模式

## API 端点

### 基准配置
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/base-configs/{id}` | `baseConfigApi.get` | 获取基准配置详情（含料件） |
| POST | `/api/base-configs` | `baseConfigApi.create` | 创建基准配置 |
| PUT | `/api/base-configs/{id}` | `baseConfigApi.update` | 更新基准配置 |
| PUT | `/api/base-configs/{id}/parts` | `baseConfigApi.setParts` | 替换料件清单 |

### 配件查询
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/parts` | `partsApi.list` | 配件列表 |
| GET | `/api/parts/categories` | `partsApi.categories` | 配件分类 |

### BOM 模板
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/bom-templates` | `bomTemplateApi.list` | BOM 模板列表 |

### 系统配置
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/system-config/server_form_factor/value` | `systemConfigApi.getValue` | 机箱形态选项 |
| GET | `/api/system-config/server_series/value` | `systemConfigApi.getValue` | 服务器系列选项 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `base_configs` | 基准配置主表（name, series, form, bays, bom_template_id, model_id, config_content, **psu_bays, rear_slots, gpu_slots, max_tdp, gpu_arch_default**） |
| `l6` | `base_config_parts` | 基准配置料件（category, pn, quantity） |
| `l6` | `parts_master` | 配件主数据（查价、查功耗） |
| `kp` | `kp_categories` | 配件分类 |
| `l6` | `bom_templates` | BOM 模板 |
| `rules` | `system_config` | 机箱形态/系列枚举 |

## 关键组件

- `PartPicker.vue` — 料号选择器（分类筛选 + 搜索）
- `useSeries()` — 系列选项 composable
- `chassisMeta.ts` — 机箱能力 SSOT（DEFAULT_REAR_SLOTS / GPU_ARCH_OPTIONS / 按底座分 rear_slots 模板 REAR_SLOTS_2U_AMD·2U_POLARIS·4U + rearSlotsFor）
- `vuedraggable` — 拖拽排序
