# 策略中心 (Strategies)

> 最后更新：2026-07-30

## 功能概述

一级独立模块（顶级菜单），管理 4 域业务规则，落地到推理流 / 报价工作台 / 报价单溯源。type 驱动的结构化编辑器——每种 type 有人话表单（干掉裸 JSON），未知 type 回退 JSON 高级区。

### 4 域 + 6 种 type（一期 + 二期已完成）

| 域           | type               | 说明                           | 落地点                    |
| ----------- | ------------------ | ---------------------------- | ---------------------- |
| pricing     | `platform_baseline`/`industry_adj`/`region_adj`/`order_mult`/`cost_tier`/`qty_mult`/`guardrail` | **加法定价引擎 7 维度**（2026-07-30 取代旧 pricing_scenario/margin_tier） | 演算器 + 未来方案助手；guardrail.floor → 工作台告警 |
| pricing     | `warranty_markup`  | 维保加价（y1/y3/y5）               | 工作台维保年限建议费率            |
| selection   | `require`     | 必配依赖（选 A 需配 B ≥N／规格约束） | CRE → 工作台 `selectionActions` |
| selection   | `exclude`     | 互斥（同 category 同字段值不混搭） | CRE → 工作台 `selectionActions` |
| selection   | `derive`      | 数量派生（basis÷per 取整，建议值） | CRE 提醒；算法推导归后端 DerivationEngine |
| selection   | `filter`      | 候选过滤（按字段过滤候选集） | ⚠️ 无执行消费端（见文末 roadmap ⑤） |
| selection   | `recommend`   | 推荐标注（仅提醒，非推理流方案 tag） | CRE → 工作台 `selectionActions` |
| requirement | `clarity` / `rebuttal` / `budget` | 需求明确度判定 / 反问话术 / 预算映射（独立 `requirement_rules` 表，运行中积累） | 推理流 clarity_check / ask_user / budget_check 节点 |

> ⚠️ **selection 域已重构为兼容性规则引擎（CRE，2026-07-29）**：上表 5 个 selection type 不再存 `strategies` 表，改存独立表 `rules.compatibility_rules`（domain=selection），声明式 `WHEN(条件树)→THEN(动作)`，无序可叠加。前端求值抽到 `stores/selectionEngine.ts`（纯函数 + 28 单测），消费见工作台 `selectionActions`。默认种子 3 条、治理进度与**后续 roadmap（④ 后端兜底 / ⑤ filter 消费 / ⑥ 命中埋点 / ⑦ 规则补全 / ⑧ 寻址空间）**见文末「选型配置治理与后续 roadmap」。

### 加法定价引擎（报价策略重构，2026-07-30）

pricing 域采用**多维度加法叠加**模型（取代旧的 scope 命中→预设三档查表）：

```
最终毛利率 = (平台基准 + 行业浮动 + 区域浮动) × 订单系数 × 成本阶梯 × 台数折扣 → 夹在 [保底, 封顶]
```

7 条维度 strategy（type 即维度 key，scope=null 全局系数表）：

| 维度 type | 运算 | body 结构 | 数据来源 |
|---|---|---|---|
| `platform_baseline` | base 基准 | `{Polaris:15, Orion:11, Intel:11, 工作站:13}` | opportunity.platform_type |
| `industry_adj` | add ±百分点 | `{行业→±百分点}` | opportunity.industry |
| `region_adj` | add ±百分点 | `{factors:{国内/海外/偏远}, keywords:{...}}` | opportunity.delivery_region（自由文本→分桶） |
| `order_mult` | mult ×系数 | `{customer_type→系数}` | opportunity.customer_type（订单维度） |
| `cost_tier` | mult ×系数 | `{tiers:[{max?,mult}]}` | 报价单 BOM totalCost |
| `qty_mult` | mult ×系数 | `{bands:[{min,mult}]}` | opportunity.purchase_qty（量越大让利越多） |
| `guardrail` | clamp 夹取 | `{floor, cap}` | — |

**字段零新增列**——全维度映射到已有商机字段 + 报价成本；形态 `chassis_form` v1 预留不参与。

**用途定调**：策略中心定价**只作建议值 + 演算器**，不驱动工作台售价（工作台仅用 guardrail.floor 告警，不自动改价）；真正消费方是**未来智能方案助手自动出报价单**（引擎纯 TS 可直接 import）。后端零改动（type 自由字符串、body 自由 JSON、`/api/strategies` 复用）。

### 报价策略画布（pricing 域专用视图）

pricing 域 tab 用 `views/admin/pricing/PricingFlowCanvas.vue`（替换旧 `PricingStrategyCanvas.vue`）：
- **固定流水线图**：vue flow，节点位置由公式顺序派生（`输入→平台基准→+行业→+区域→×订单→×成本→×台数→保底封顶→输出`），`:nodes-draggable=false` + `:nodes-connectable=false` 锁死拓扑（公式顺序固定，无需自由连线）
- **点维度节点** → `DimensionDrawer.vue` 按维度 type 分支编辑系数表（枚举→数值 / region 分桶因子+关键词 / cost_tier 阶梯行 / guardrail 双值）→ `strategyApi` create/update（未持久化时 create）→ `invalidatePricingRules` 刷新
- **演算器面板**（headline）：输入一笔 deal（平台/行业/区域/订单/成本）→ 实时 `computeTargetMargin` → breakdown 每步 + 目标毛利率 + 建议售价（`suggestPrice = 成本×(1+目标%)`）。即「不知道怎么加点就来跑一下」的入口
- 缺省兜底：store 加载 6 维度，缺失维度回退 `constants/pricingMeta.ts` 的 `DEFAULT_DIM_BODIES`（未 seed 也能用）

### 推理流编排（requirement 域专用视图）

requirement 域 tab 用 `ReasoningFlowCanvas.vue`（vue flow）可视化编排 BOM 推理流：
- **画布**：vue flow（`@vue-flow/core` + background/controls/minimap），自定义节点 `ReasoningNodeVf.vue`（玻璃卡 + 左右 Handle）
- **节点类型**：extract / clarity_check / cond_clarity(condition) / ask_user / select_baseline / match_kp / compose / budget_check / review（默认 v3 图，含反问分支）+ llm（预留）
- **交互**：拖节点改位置 · 拖锚点连线 · 点边删连线 · 单击节点开配置抽屉（抽屉内「删除节点」按钮）
- **持久化**：debounce → `PUT /api/reasoning-flow/graph`（graph v2：`nodes{id,type,label,position}` + `edges{source,target,source_handle?,target_handle?,condition?}`）
- **节点配置**（抽屉按 type 渲染，规则跟着节点走）：extract = 提取参数（分词+词表/系列映射，走 `updateNode`）/ **clarity_check = 明确度规则库**（实时 CRUD）/ **ask_user = 反问话术库**（实时 CRUD）/ **budget_check = 预算映射库**（实时 CRUD，均调 `/api/requirement-rules` 立即生效）/ select_baseline（max_plans/recommend）/ match_kp（pick/aliases）/ condition（expr，白名单含 clarity/budget/clarity_capped/has_budget/missing_fields）/ llm（prompt/model）

**图驱动 executor**（`reasoning_executor.py`）：`run_pipeline` 读 active flow → 拓扑 BFS 执行（handler 按 type 分发，复用 `extract_keywords`/`select_baselines`/`pick_kp_parts`/`build_plan` + 新增 `clarity_check`/`ask_user`/`budget_check`）→ condition 节点 `simpleeval` 求值选分支（白名单扩展：series/form/categories/keywords + **clarity / clarity_capped / budget / has_budget / missing_fields**）。

**反问流（前端重跑模式，不做真暂停）**：clarity_check 判 unclear → cond_clarity 走 true → ask_user 叶子节点广播 `need_input` + 置 `awaiting_input` → run_pipeline 发 `pipeline_paused`（区别于 `pipeline_done`）。用户在 ReasoningPanel 回复 → POST /generate 带 `supplement_text` → 后端拼「原需求 + 补充」重跑（新 pipeline_id，前端过滤过期消息）。死循环防护 `MAX_CLARIFY_ROUNDS=3`（存 extra_fields.requirement_clarity_round）；`force_complete` 跳过反问。

**预算校验**：budget_check 给方案注 `over_budget`（不剔除）；match_kp 的 representative_pick 按 `requirement_rules[budget]` 区间动态选（高预算→max_price / 低预算→min_price）。

**三层兜底**：无 active flow / graph 异常 / executor 异常 → `_run_linear_fallback`（线性 5 步 + 预算校验，无反问）。WS 新增 need_input / pipeline_paused 事件，ReasoningPanel 加反问输入区 + 超预算标注（非零改）。

> 详细设计见 `docs/strategy-center-design.md`「需求分析智能化」段。

> 曾试 AntV X6，Vite 下 view 层不渲染弃用，改 vue flow（Vue3 原生、Vite 友好）。

### signature

- 报价策略画布：加法定价固定流水线图（输入→平台基准→+行业→+区域→×订单→×成本→×台数→保底封顶→输出）+ 维度系数抽屉 + 演算器（pricing 域专属，体现"公式怎么叠加 + 这笔单该报多少毛利"）
- 推理流编排：vue flow DAG 画布（拖拽/连线/加删节点）+ condition 分支 + 图驱动 executor（拓扑执行 + simpleeval 安全求值 + linear fallback 兜底）

## 前端路由

| 路由 | 组件 |
|------|------|
| `/strategies` | `views/admin/Strategies.vue` |

顶级菜单（配件 → 策略中心 → 设置），ThunderboltOutlined 图标。

## API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/strategies/` | 列表（domain/status/type 过滤）|
| GET | `/api/strategies/{id}` | 详情 |
| POST | `/api/strategies/` | 创建 |
| PUT | `/api/strategies/{id}` | 更新（版本 +1）|
| POST | `/api/strategies/{id}/status` | 状态流转（draft/testing/active/archived）|
| DELETE | `/api/strategies/{id}` | 删除 |
| POST/GET | `/api/strategies/{id}/usage` | 引用埋点 / 使用率统计 |

## 数据库表

| Schema | 表 | 用途 |
|--------|-----|------|
| `rules` | `strategies` | 策略主表（domain/type/name/scope/body/status/version/change_reason）|
| `rules` | `strategy_usage` | 引用埋点 |
| `rules` | `compatibility_rules` | selection 域 CRE 规则（type∈require/exclude/derive/filter/recommend，独立于 strategies；`/api/compatibility-rules`）|

## 联动落地点

- **工作台（Workspace.vue）**：加法引擎 `guardrail.floor` → 利润率告警（**只警告不锁、不自动改价**，策略中心定价只作建议）；warranty_markup → 维保年限建议费率（空时填，尊重手填）；selection CRE（require/exclude/derive/recommend）→ `selectionActions` computed 调 `evaluateRules(ctx)`，命中渲染为图标提醒（⚠ 互斥 / ＋ 必配 / 💡 派生·推荐）；**filter 当前无执行消费端**（见文末 roadmap ⑤）
- **推理流（candidate_search.py `select_baselines`）**：`_annotate_recommend` 按 scope.series 给 baseline 附 recommend_level + selling_points（仅标注不改检索）；build_plan 透传；ReasoningPanel 方案卡显示推荐 tag + ★包装点
- **L3 报价单溯源**：导出时 `getStrategySnapshot` 写入 `quotation.strategy_snapshot`；QuotationCostDrawer 显示（**仅 source='reasoning' 单**——人工单策略只是建议，不是定价依据，标了会误导）

## L3 报价单 source

quotation.source 字段：`reasoning`（推理流 confirmPlan 转草稿）/ `manual`（工作台手动新建，default）/ `upload`（Excel 上传）。confirmPlan 末尾统一设 reasoning（draft 替换/新建都走）。

## 关键文件

- `views/admin/Strategies.vue` — 管理页（3 域 tab 容器：pricing→PricingFlowCanvas、requirement→ReasoningFlowCanvas、selection→CompatibilityRuleEditor）
- `views/admin/pricing/PricingFlowCanvas.vue` — 报价策略画布（加法定价固定流水线图 + 演算器）+ `DimensionNode.vue`（vue flow 节点）+ `DimensionDrawer.vue`（维度系数编辑抽屉）
- `views/admin/reasoning/ReasoningFlowCanvas.vue` — 推理流编排画布（vue flow + 拖拽/连线/加删节点 + 持久化）
- `views/admin/reasoning/ReasoningNodeVf.vue` + `ReasoningNodeDrawer.vue` — vue flow 自定义节点 + 配置抽屉
- `backend/app/services/reasoning_executor.py` — 图驱动 executor（handler 注册表 + 拓扑执行 + condition simpleeval 求值）
- `backend/app/services/requirement_intel_service.py` — run_pipeline 入口派发 + `_run_linear_fallback`
- `backend/app/repository/reasoning_flow_repo.py` + `models/reasoning_flow.py` + `api/reasoning_flow.py` — 推理流持久化（graph v2 + `_normalize_graph` v1→v2 平移）
- `stores/pricingEngine.ts` — 加法定价纯求值逻辑（`computeTargetMargin(ctx,dims)`/`resolveRegion`/`resolveCostTier`/`suggestPrice`，独立 12 单测，镜像 selectionEngine 范式）
- `constants/pricingMeta.ts` — 定价维度 SSOT（DIMENSION_DEFS/枚举/DEFAULT_DIM_BODIES，与 seed 同步）
- `stores/pricingRules.ts` — pricing 规则加载（Pinia）+ 加法引擎薄封装 `computeTargetMargin` + `getGuardrail` + 维保 `getWarrantyRate` + L3 `getStrategySnapshot`(pricing_additive) + `invalidatePricingRules`
- `stores/selectionRules.ts` — selection CRE Pinia store（`ensureRules`/`evaluateRules`/`invalidateRules`，薄封装）
- `stores/selectionEngine.ts` — CRE 纯求值逻辑（`evaluateRules(rules,ctx)`/`evalWhen`/`evalThen`，独立 28 单测）
- `views/admin/CompatibilityRuleEditor.vue` — CRE 编辑器（5 type 分 tab + WHEN/THEN modal，selection 域专用，取代旧 X6 画布）
- `backend/app/repository/compatibility_rule_repo.py` + `models/compatibility_rule.py` + `api/compatibility_rules.py` — CRE 后端 CRUD + seed（DEFAULT_RULES 4 条）
- `api/strategies.ts` + `api/reasoningFlow.ts` — API 接口
- `backend/app/api/strategies.py` + `repository/strategy_repo.py` + `models/strategy.py`
- `scripts/seed_*.py` — 各 type 默认策略种子（selection/pricing/result_fields/warranty_markup/model_recommend 等）

---

## 选型配置治理与后续 roadmap（2026-07-29）

selection 域已重构为**声明式兼容性规则引擎（CRE, Compatibility Rule Engine）**，取代旧的 `conflict/require/bom_spec/model_recommend` 四 type + 前端 `validateSelection`。规则存独立表 `rules.compatibility_rules`，范式 `WHEN(条件树)→THEN(动作)`，无序可叠加。前端求值抽到 `stores/selectionEngine.ts`（纯函数，`evaluateRules(rules, ctx)`，28 单测覆盖全操作符/全动作），`stores/selectionRules.ts` 薄封装读 `/api/compatibility-rules?status=active`。工作台 `selectionActions` computed 调 `evaluateRules(buildRuleContext(cfg))`，命中渲染为图标提醒（**当前为建议层，只警告不锁**）。

### 默认种子（6 条 · `compatibility_rule_repo.DEFAULT_RULES`）

> **2026-07-30 重构**：线缆/GPU线从已删的后端 `DerivationEngine` 迁入 CRE derive 驱动（拒绝黑盒，数量计算在选型配置页可视化、可配、改即生效）。规则只产出「某类型线缆要几根」，target=**线缆类型标签**（`SATA`/`SAS`/`NVMe`/`GPU线`，不碰料号库品类）；消费端 `L6ChassisConfig` 建 `ruleCtx`（含 `config.sata_qty`/`sas_qty`/`nvme_qty`+GPU qty，随 `kpSummary` 反应式）→ 跑 `evaluateRules` → 注入 `useServerConfig.derivedCableQty` 作步进器默认值（**手改 override 优先**，推导仅兜底）。

| # | type | 说明 |
|---|------|------|
| ① | filter | 按商机 `platform_type` 过滤候选机型（已接 `modelSeriesFilter`） |
| ② | derive(赋值) | 含 NVMe 盘 → 背板 `bp_type=tri`（纯 SATA/SAS/无盘 → dc 由消费端 `?? 'dc'` 兜底） |
| ③ | derive(算术) | SATA 线 = ⌈`config.sata_qty` ÷ 8⌉（改 per 即改每组盘数） |
| ④ | derive(算术) | SAS 线 = ⌈`config.sas_qty` ÷ 8⌉ |
| ⑤ | derive(算术) | NVMe 线 = ⌈`config.nvme_qty` ÷ 2⌉ |
| ⑥ | derive(算术) | GPU 线 = ⌈`kp.GPU.qty` ÷ 1⌉（每卡 1 根，改 per 调每 N 卡 1 根） |

> 内存互斥规则（原 ②）已于 2026-07-30 移除（不在第一期范围）。功耗/PSU/NVSwitch 一期不做（PSU 手选 + 默认 2）。⚠️ 线上库需 `POST /api/compatibility-rules/reset` 同步新 seed（无自定义规则则无损）。

### 已完成治理（三步）

- **① 引擎抽离 + 单测**：`selectionRules` store 纯求值抽到 `selectionEngine.ts`（无 vue/pinia 依赖），`npm run test` 28 例全过（node 24 原生 test runner，无 vitest/无 node_modules）；`tsconfig.app.json` 加 `exclude:["src/**/*.test.ts"]`（测试不进 vue-tsc build）。
- **② category 校准**：`kp_categories` 实际为英文 10 个（无中文），③④ 的 target（GPU电源线/背板）在料号库 `l6.parts_master` 不进 CRE 的 `kp.*` 寻址 → 降 `status=testing` 保留范例不假装生效；`seed_default_if_empty` 改读 `item.get("status","active")`。
- **③ 清理双轨死代码**：删 `composables/usePricingRules.ts` + `composables/useSelectionRules.ts`（零引用）；`Strategies.vue` 通用编辑 modal（`modalVisible` 无任何 true 赋值，整块打不开的死模板）全删，重写为 ~30 行 tab 容器（requirement/selection/pricing 三域各挂专用子组件）。

### bp_type 迁移到 CRE（2026-07-30）

背板类型判定（`bp_type`：含 NVMe 盘→tri 三模；纯 SATA/SAS 或无盘→dc 直通）从后端 `DerivationEngine.derive_bp_type` 死代码迁移到 **CRE 声明式 derive 规则**，在选型配置页 derive tab 可视化编辑、改即生效。用户定调：分支判定型规则要可配置生效，不接受「描述文字能改、行为不变」的假透明；公式计算型（功耗/PSU/线缆/GPU线）仍留 `DerivationEngine` + 参数可调（参数改了已真生效）。

- **赋值型 derive**：CRE 的 derive 动作原为纯算术（`basis÷per→数量`），本次新增赋值型形态 `then:{action:'derive', field, value}`（条件→固定值）。`selectionEngine.ts` 的 `evalThen` 按 then 形态分派；新增 `evalAssignValue(rules,ctx,field)` 按规则顺序**首命中**求值（具体规则放前、宽泛放后；dc 兜底由消费端 `?? 'dc'`，不 seed dc 规则）。单测扩到 32 例。
- **种子**：`DEFAULT_RULES` ⑤ derive 规则「含 NVMe 盘→三模」(`when: config.drive_kinds contains NVMe → then config.bp_type=tri`)。硬件语义：tri-mode 背板支持 SATA/SAS/NVMe 三协议、dc 直连只走 SATA/SAS，故有 NVMe 盘必须 tri；dc 不 seed（CRE 无 not-contains），由消费端 `?? 'dc'` 兜底。⚠️ **线上库已有数据不会自动 seed ⑤**，需 `POST /reset`（清自定义规则）或手动建等效规则。
- **求值落点**：`L6ChassisConfig` 用 `kpSummary.drivesByKind` 算 `drive_kinds` → `selectionRulesStore.assignValue('config.bp_type', ctx)` → 注入 `useServerConfig.derivedBpType`；`bpType()` 优先级 `手改 > 基准自带 > CRE 规则 > dc`。改规则 → `invalidateRules` → computed 重算 → 背板料号自动换。
- **清理**：`derive_bp_type` 删、`derive_all` 去 `bp_type` 字段、`DERIVATIONS` 删 bp_type 条目（透明化面板不再展示它）、`DeriveResult` 去 `bp_type`。`_drive_kinds` 保留（`derive_front_cables` 仍用）。`CompatibilityRuleEditor` derive 分支加「赋值/算术」子模式 + `whenText` 修 `any` 支持。

### 后续 roadmap（按优先级）

- **④ 后端兜底验证（推荐方案 B，待时机再加）**
  - **现状**：CRE 仅在前端跑（建议层），后端导出报价单时不复核。
  - **方案 B**：后端 Python 复刻 WHEN→THEN 求值，对照 `selectionEngine.ts` + 28 单测做**行为基准**（防前后端 drift）；导出时跑 active 规则，命中互斥/必配写入 `quotation.strategy_snapshot` 作 L3 溯源依据。
  - **可安全推迟的理由**：选型规则当前是建议层（只警告不锁）；高风险派生（功耗/PSU/线缆/GPU线）已由后端 `DerivationEngine` 承担（背板类型 bp_type 已于 2026-07-30 迁到 CRE，见上「bp_type 迁移到 CRE」），无致命缺口；前端单测保正确性下限。
  - **触发时机**：规则覆盖度补到一定程度（见 ⑦）、或希望"规则也作为报价依据"时再加。前端这轮抽出的引擎 + 单测正是它的对照基准——先跑通前端不是拖延，是在给后端兜底铺路。
- **⑤ filter 动作接消费端（✅ 已完成 2026-07-29）**：Workspace 加 `modelSeriesFilter`（商机级跑 filter 规则 → `{field,op,value}`，只依赖 `opportunity.platform_type`）+ `serverModelOptions` 按它过滤候选下拉（auto-complete 仍可自由输入，**不锁**，符合建议层）；filter 已被候选消费则 `selectionAlerts` 不重复提示，但当前选中机型系列与商机平台不符时补一条提示。ConfigWizard 不绑定商机（`buildRuleContext` 里 `opportunity:{}`），规则①不适用、无需改。已验：Polaris 商机 → 候选 3→1（只剩 `ZS22V2-P`）。
- **⑥ 规则命中埋点回写（闭环 · 代码工作）**：`record_hit` / `hit_count` API 已有但前端命中后无人调，`strategy_usage_log` 也无人写。命中时调 `/api/compatibility-rules/{id}/hit` 闭合"越跑越聪明"数据环。
- **⑦ 规则补全（业务 / 数据工作）**：种子仅 4 条且 ③④ testing。需业务侧补真实互斥/必配规则（CPU-主板、RAID-背板、内存通道…）。覆盖度取决于 ⑧ 寻址空间决策。
- **⑧ CRE 寻址空间（2026-07-30 拍板方案 A · 已落地）**：CRE 的 `ctx.kp` 只聚合 KP 配件库件（`kp.*/config.*/opportunity.*`），管「用户选型」层（CPU/GPU/内存/硬盘/阵列卡互斥·必配·推荐）。料号库件（线缆/背板/电源）是「派生出来」的物理件（数量由公式决定），归后端 `DerivationEngine`；两域用 `config.*` 字段桥接（bp_type 模式），**不把料号库件塞进 CRE 寻址**。落地：① CRE 编辑器字段下拉源从料号库 `parts_master` 改为 KP 库 `kp_categories`（spec 键按品类数据驱动，不再写死 interface/kind），消除「死候选」；② 种子移除 ③④ 假规则、线上同步删。曾考虑的「扩 ctx 纳料号库件」方案否决——会与后端派生重复 + 循环依赖。
  - **🔄 2026-07-30 更新（线缆数量改由 CRE 驱动，DerivationEngine 已删）**：寻址空间定调本身不变（线缆仍不进 `ctx.kp`），但 `DerivationEngine`/`derive.py`/`DerivationRulesPanel` 已整体删除——线缆/GPU线的**数量**改由 CRE derive 算术规则算（读 `config.sata_qty`/`sas_qty`/`nvme_qty`/`kp.GPU.qty`，target=类型标签），消费端解析为步进器默认值。即「CRE 算数量、用户选具体 PN」分工，料号库件不进 ctx 但其数量由 CRE 规则驱动。详见上方「默认种子」6 条表。
