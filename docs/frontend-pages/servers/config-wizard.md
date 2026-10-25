# 配置向导页 (ConfigWizardPage)

> 最后更新：2026-10-02（KP 卡/电源数量控件按基准配置能力档案硬夹紧 + 机箱能力上限规则补齐为五类全配）

## 功能概述

四步配置流程，引导用户完成服务器配置。

### 核心功能
1. **面包屑导航** — 「返回」：有站内来路（如从机型详情页进入）原路返回；直接打开 URL 才回机型目录
2. **配置向导** — ConfigWizard 组件：
   - Step 1: 基础信息（型号、数量、描述）
   - Step 2: 部件配置（CPU/内存/硬盘/GPU/网卡/电源等）
   - Step 3: 推导与校验（功耗/PSU/GPU线缆/背板自动推导）
   - Step 4: 确认与保存

### 数据流
- 加载机型信息（含关联的基准配置）
- 用户逐步配置各部件
- 推导引擎自动计算（带手填兜底）
- 保存为报价单配置

### 性能六维雷达（2026-09-19）

右栏「性能参数」块顶部 = 六维雷达（[PerfRadarChart.vue](../../../frontend/src/components/server-config/PerfRadarChart.vue)），原始数字卡原样保留在图下方；维度 chip hover 出打分明细 popover（锚点 + 行级构成）。

分层铁律（锚点数值可调零发版，代码只写形状）：
- **锚点表**：system_config `performance_score_config`（type=json），每维 `anchors`（0/60 主流线/100 旗舰线）分段线性插值；`enabled:false` 可剔除维度；管理面先挂系统配置 JSON 编辑
- **聚合公式**：[performanceScore.ts](../../../frontend/src/utils/performanceScore.ts)（纯函数）+ ConfigWizard 内 `perfRaw` computed——CPU=Σ核数（FP64 specs 覆盖低，按核数折算并注明）；内存=容量主锚点+带宽副锚点（Σ条数×速率×8B 估，权重 0.55/0.45，速率缺→只按容量）；存储=类型加权盘位（NVMe 1.0/SAS 0.6/SATA 0.4）；网络=Σ口数×端口速率；GPU=Σ卡数×单卡 FP16 峰值（specs 键候选表匹配）；可靠性=命中冗余项（PSU≥2/RAID 卡/MTBF）
- **缺数据策略**：原始值缺失的维度 `score=null`——雷达顶点缩到圆心+灰标「未维护」，**不编造**
- **数据维护**：GPU 口径=FP16/BF16 **dense** TFLOPS（NVIDIA 官网稀疏值÷2；TOPS 是 INT8/FP4 口径，引擎拒收防爆分）。2026-09-19 已回填 35 件（31 GPU FP16+CPU 9J14 Cores+3 NIC Ports，脚本 [backend/kp_spec_backfill.py](../../../backend/kp_spec_backfill.py)，dry-run 默认/--commit 落库/只补空缺）；智铠100、壁仞166C 等 14 件公开资料无确证值留空待厂商公布

### 数量上限夹紧 + 机箱能力规则（2026-10-02）

基准配置能力档案（`l6.base_configs` 的 max_cpu/max_dimm/gpu_slots/bays/psu_bays）走**双通道**约束配置数量，此前只有规则告警一条腿且覆盖不全（GPU/盘/电源连规则都没有），数量控件完全不受限：

- **控件级夹紧（A）**：[KpCategoryCard.vue](../../../frontend/src/components/server-config/KpCategoryCard.vue) 新增 `maxQty` prop，加号/手输夹到上限（减号仍夹 0）；`+` 到顶置 disabled。上限按**类别总数**算（`clampQty` 扣除同类其他行已占），多行分摊。类别映射：CPU→max_cpu、Memory→max_dimm、GPU→gpu_slots、HDD/SSD→bays；**未配置/≤0 → 不夹紧**（NIC 等无能力字段的类别不受限）。机箱弹窗电源步进器同步夹到 `psu_bays`（[L6ChassisConfig.vue](../../../frontend/src/components/quote/L6ChassisConfig.vue)）。注入映射 `maxQtyFor` 在 [ConfigWizard.vue](../../../frontend/src/components/server-config/ConfigWizard.vue)。
- **规则侧告警（C）**：规则库（`rules.compatibility_rules`，category=机箱能力校验）现有五条上限规则全 active：CPU 颗数(id 25)/内存条数(id 26) 原有，新增 GPU≤gpu_slots(id 35)/硬盘≤bays(id 36)/电源≤psu_bays(id 37)，均为 `recommend/warning`（右栏规则面板黄条，不进生成规格书确认弹窗——阻断级仍只有 conflict/require，手改优先定调不变）。规则上下文补注入 `config.bays` + `config.psu_qty`。
- 后端 AI 方案链路同源：[plan_builder.py](../../../backend/app/services/plan_builder.py) 组规则上下文时以 DB 基准配置行补齐能力字段（baseline 来自候选层可能缺 gpu_slots/bays），`plan_rule_context` 透传 gpu_slots/psu_bays/bays/psu_qty，五条上限规则在需求分析出方案时同样触发。报价工作台同套逻辑见其文档。

## 前端路由

| 路由 | 组件 |
|------|------|
| `/servers/config/:modelId` | `views/ConfigWizardPage.vue` |

## 移动端双抽屉（≤768px，2026-09-19）

桌面三栏（左配置卡 / 中图纸 / 右结果）映射为「主屏配置卡流 + 双抽屉」，改动集中在 `ConfigWizard.vue` 手机分支（`isMobile` matchMedia ≤768），桌面三栏零改动：

- **主屏**：机箱卡 + KP 类别卡 + 虚线新增卡（输入主场）；顶部 `sc-steps` 步骤条手机端退役（卡片自带序号即步骤流）。
- **左抽屉**（placement=left，宽 94%）：服务器图纸卡整体复刻（含前/后视图 radio、上传图纸优先逻辑、`anatomyCounts` 实时联动），`sc-map-card` 高度改 auto 适配抽屉滚动。
- **右抽屉**（placement=right，宽 88%）：配置结果卡整体复刻（规则结果 / 电源功率 / 性能六维雷达 + 指标 / 生成规格书按钮），与桌面右栏同一 computed，实时联动。
- **底部 sticky 摘要条** `.sumbar`（fixed，`bottom: var(--cpq-tabbar-inset)` 避让全局底栏）：规则徽标（conflict 红 / 其余黄，取 `selectionActions` severity）+ 建议电源主值（`powerSummary.psuText/loadText` 同源实时）+ 📐图纸入口 + 「配置结果 ›」CTA。
- **互斥**：`openDrawer: null | 'drawing' | 'result'` 单状态；开 L6 机箱细配弹窗自动收抽屉（watch chassisModalOpen）。
- **外壳样式**：`.opp-sc-drawer` 固定暗色玻璃（本页为固定暗色链路，色值不接主题开关），走组件内全局 style 块（portal 够不到 scoped）。
- 原型：[docs/prototypes/server-config-mobile.html](../prototypes/server-config-mobile.html)

## API 端点

### 机型与基准配置
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/server-catalog/models/{modelId}` | `catalogApi.getModel` | 获取机型详情（含基准配置） |
| GET | `/api/base-configs/{id}` | `baseConfigApi.get` | 获取基准配置详情 |
| GET | `/api/server-catalog/performance-score-config` | `catalogApi.getPerformanceScoreConfig` | 性能六维打分锚点表（system_config `performance_score_config`；未配置返回 `{}`，前端回落内置默认锚点） |

### 配件查询
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/parts` | `partsApi.list` | 配件列表（选择部件） |
| GET | `/api/parts/categories` | `partsApi.categories` | 配件分类 |
| GET | `/api/kp/categories` | `kpPartsApi.categories` | KP 分类 |
| GET | `/api/kp/parts` | `kpPartsApi.listByCategory` | 按分类获取 KP 配件 |

### 推导引擎
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| POST | `/api/derive` | `deriveApi.derive` | 传当前配置状态，返回推导结果 + 约束校验 |

### 配置输出
serverconfig 不再落库保存配置方案；生成规格书仅在前端渲染，用于查看/打印。

### 规格书模板
| 方法 | 路径 | 前端函数 | 用途 |
|------|------|----------|------|
| GET | `/api/spec-templates/default` | `specTemplateApi.getDefault` | 获取默认规格书模板 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `l6` | `server_models` | 机型信息 |
| `l6` | `base_configs` | 基准配置（预填部件） |
| `l6` | `base_config_parts` | 基准配置料件 |
| `l6` | `parts_master` | 配件主数据（查价） |
| `kp` | `kp_parts` | KP 配件 |
| `kp` | `kp_categories` | KP 分类 |
| `rules` | `compatibility_rules` | 兼容性规则（CRE 选型规则，含五条机箱能力上限） |
| `rules` | `system_config` | 系统参数 |
| `rules` | `spec_templates` | 规格书模板 |

## 关键组件

- `ConfigWizard.vue` — 四步配置向导主组件
  - 机箱配置（L6 via stepper modal）
  - KP 配件按分类（CPU/Memory/HDD-SSD/GPU/NIC + 用户自定义分类）
  - 计算总计（L6 + KP = 总价）
  - 保存配置方案并生成规格书
