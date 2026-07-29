# 策略中心设计（Strategy Center）

> 最后更新：2026-07-26

## 目标与核心判断

把资深方案员的隐性经验固化为显性策略，统一需求拆解 / 选型 / 报价 / 市场口径，让配置、报价、AI 助手能引用 + 溯源。

**核心判断（codegraph 摸底后定）**：不新建独立系统，复用项目现成三套底座——
- `rules` schema（`MatchingRule` / `ParseFieldRule` / `KPCategoryMapping` 等）
- BusinessField 治理四件套（`FieldUsageStats` 引用埋点 / `FieldAuditLog` 版本审计 / `FieldReference` 引用关系）
- `bomRuleEngine`（BOM 行 desc/qty 求值 DSL，primary + fallback）

策略中心 = 把这些按 4 域组织 + 补 `strategy` 表 + 分域视图 + 统一入口。

## 完整蓝图（标期）

### ① 需求分析策略（requirement 域）—— ✅ 已落地（2026-07-26 需求分析智能化）
- R1 关键词→系列/形态映射　[✅ extract 节点]
- R2 需求字段抽取规则　[✅ extract 节点]
- R3 需求完整性校验/追问　[✅ clarity_check + ask_user 节点 + requirement_rules 表]
- R4 baseline 候选排序　[✅ select_baseline]
- 详见末尾「需求分析智能化」段

### ② 选型配置策略（selection 域）—— 一期做硬规则
- S1 整机机型选型（推荐/不推荐+包装点）　[二期]
- S2 配件搭配规范（必配/选配）　[二期]
- **S3 禁配避坑 conflict / require　[一期 C1-C3]**
- S4 行业标准 BOM 模板　[二期]
- S5 容量/算式校验（功率/槽位/通道）　[二期，依赖配件 specs 补齐]
- S6 性能建议（内存通道填充等）　[三期]

### ③ 报价&毛利策略（pricing 域）—— 一期做三档
- **P1 基准毛利三档（底线/标准/优质）　[一期 B3]**
- P2 直销/渠道双基线　[二期]
- P3 分场景浮动（集采/框架/竞标/非标）　[二期]
- P4 维保加价分层　[二期]
- P5 特价审批触发 + 台账　[❌ 砍掉，依赖用户系统]
- P6 报价超区间锁提交　[二期]

### ④ 行业市场作战策略（market 域）—— ❌ 砍掉（2026-07-26 调整）

三期方向调整：market 域（M1-M4）整体砍掉。三期重点转为**方案助手增强 + 自动生成报价 BOM**（见末尾「三期（调整后）」）。

### 通用配套
- **G1 strategy 表 + 4 状态 + 版本 + 异动留痕　[一期 B1]**
- **G2 StrategyRepository + API　[一期 B2]**
- **G3 strategy 管理页（4 域列表+编辑）　[一期 D1]**
- **G4 引用埋点 + 使用率统计　[一期 D2]**
- G5 全局检索　[二期]
- G6 权限分级　[二期]

### 联动（4 价值落地）
- **L1 工作台选配校验（读 selection）　[一期 C2]**
- **L2 报价分层告警（读 pricing 三档）　[一期 B4]**
- L3 报价单标注策略依据（溯源）　[二期]
- L4 推理流读 requirement/selection　[二期]
- L5 AI 助手 provider 注入策略　[三期]
- L6 AI 自动生成方案文案（市场）　[三期]

### 数据底座（前置依赖）
- **D1 商机补行业/客户类型/结果字段　[一期 A1-A2]**
- D2 配件库 specs 补齐（功耗/槽位/接口）—— 独立专项，解锁 S5
- D3 商机结果状态有真实数据积累 —— 解锁 M4，需时间

## 一期范围（12 步，4 阶段）

**A. 补商机字段，解锁未来数据**
- A1　`business_fields` 加 3 个 enum 字段种子（行业 / 客户类型 / 商机结果）+ 跑
- A2　`archived → 失标` 迁移脚本 + 跑 + 验证填充率

**B. strategy 底座 + 毛利三档**
- B1　建 `rules.strategies` + `rules.strategy_usage_log` 两张表
- B2　`StrategyRepository` + `/api/strategies` CRUD + 按 domain 列表
- B3　毛利三档种子（按 platform_type 分层：floor/standard/premium）
- B4　前端 `usePricingRules` 扩展读三档 + 报价工作台分层告警

**C. 选型硬规则**
- C1　`selection.conflict` / `selection.require` 种子（各几条，凭行业经验列）
- C2　选配校验逻辑（工作台/配置向导引用 strategy 校验）
- C3　校验提醒 UI（提醒为主、能拦的拦，不强锁）

**D. 治理收尾**
- D1　strategy 管理页（admin-card 模式：4 域列表 + 编辑 modal）
- D2　引用埋点（选配/报价引用策略时写 `strategy_usage_log`）
- D3　docs 同步 + 商机字段录入引导

## 关键约束（执行时对照，勿漂移）

1. **数据用 BusinessField enum 字段**（options 后台可改，不写死列）—— 用户定调"后期可改"
2. **scope 起步只用 platform_type**（唯一有真实数据的维度；行业/客户类型等积累后再加）
3. **选型规则 4 分类**：conflict / require [一期] · capacity / perf [二期]；一期不依赖配件 specs
4. **新建 `strategy` 表**（不塞 MatchingRule，避免污染现有 Excel 解析规则）；治理逻辑照搬 BusinessField 那套
5. **archived 历史 → 失标**（写 extra_fields，可改；用户说 archived 大部分可视为失标）
6. **一期不做数据挖掘**（真实数据不足：109 商机但只 2 导出、需求原文 6 条、市场维度字段几乎不存在）
7. **执行小批量**：每轮工具调用个位数、串行推进（用户踩过批量读写触发错误的坑）
8. **KP 单件兼容性走配件库** `applicable.series` / `compat_servers`，**不进策略中心**（用户纠偏）

## 二三期概要

- **二期**：requirement 全域、selection S1/S2/S4/S5、pricing P2-P6、配套 G5/G6、联动 L3/L4
- **三期（2026-07-26 调整）**：~~market 全域、S6、联动 L5/L6~~ → 砍掉 market 域（M1-M4）+ 砍掉依赖用户系统的 P5 特价审批；**三期重点改为：方案助手增强 + 自动生成报价 BOM**

## 三期（调整后）：方案助手增强 + 自动生成报价 BOM

方向从「沉淀市场打法」转为「让 AI 真正参与方案生成」。初稿（待细化）：
- **方案助手增强**：策略注入助手 provider（pricing/selection 规则作为 AI 上下文）、多轮需求追问、方案文案生成
- **自动生成报价 BOM**：推理流输出（baseline + KP 配件）→ 自动组 BOM 行（数量/价格/利润率），减少人工拼装
- **前提**：推理流成熟 + 配件 specs 补齐（D2）

## 状态记录

- **一期（A/B/C/D 12 步）✅ 2026-07-26 全部完成**
- **二期核心 ✅**：pricing 场景化重构（pricing_scenario + margin_tier 连线 + 可视化画布）、warranty_markup、selection S1/S2、L3 报价单溯源、G5 全局检索、priority 彻底清理
- **二期暂缓**：~~requirement 全域~~（✅ 2026-07-26 已落地，见末尾「需求分析智能化」）、S5 容量算式（待 specs 补齐）、G6 权限分级（待用户系统）
- **三期调整（2026-07-26）**：砍 market 域 + 砍 P5，转「方案助手增强 + 自动生成报价 BOM」
- **需求分析智能化 ✅ 2026-07-26 落地**：clarity_check/ask_user/budget_check 三节点 + requirement_rules 独立规则表 + 反问对话流（详见下节）

## 需求分析智能化（2026-07-26 落地）

把推理流第一步 extract 从"分词参数面板"重定位为**会生长的业务知识库**：判定规则 / 反问话术 / 预算映射独立建表，运行中积累、越跑越聪明，为未来引入 LLM 喂语料。

**新增三个图节点（推理流图 v3，DEFAULT_GRAPH 自动 migrate v1→v2）**：
- `clarity_check`：读 `requirement_rules[clarity]` 评估明确度（explicit / partial / unclear），不明确触发反问。等级优先级 **explicit > unclear > partial**（保守判定优先，避免 partial 压过 unclear 漏反问）。
- `ask_user`：叶子节点，按缺失字段挑 `requirement_rules[rebuttal]` 话术（按 priority 排序）→ 广播 `need_input` → pipeline 暂停（`pipeline_paused`，区别于 `pipeline_done`）。
- `budget_check`：compose 后给每个方案注 `over_budget` 标注（不剔除），前端方案卡显示「满足需求但超预算 ¥XX」。
- `cond_clarity`（condition 节点）：expr `clarity == 'unclear' and not clarity_capped`，true→ask_user / false→正常选型。⚠️ false 边必须显式 `source_handle:"false"`（executor 把缺省 handle 当 true）。

**`requirement_rules` 表**（照 `Strategy` 模式，schema=rules）：type ∈ {clarity, rebuttal, budget} / scope(JSON) / body(JSON) / status / version / **hit_count 内联**（越跑越聪明的高频读）。配套 `requirement_samples`（反哺标注 + 未来 LLM 语料）。三类规则 body schema 见 `requirement_rule_repo.DEFAULT_RULES`。

**反问机制（前端重跑，不做真暂停）**：当前架构 WS 无状态 + asyncio.create_task，真暂停（PausedSession 序列化 ctx+queue+visited）过重。采用前端重跑——用户在 ReasoningPanel 回复 → POST /generate 带 `supplement_text` → 后端拼「原需求 + 补充」重跑 pipeline。死循环防护 `MAX_CLARIFY_ROUNDS=3`（存 `extra_fields.requirement_clarity_round`，超限强制 partial）；`force_complete` 跳过反问；`pipeline_id` 透传过滤并发/过期消息。

**预算驱动选件**：`match_kp` 的 representative_pick 由 `requirement_rules[budget]` 区间映射动态决定（高预算→max_price / 低预算→min_price），节点 config 显式指定优先。

**规则按节点分散（职责对齐）**：明确度规则在 `clarity_check` 节点抽屉 / 反问话术在 `ask_user` 节点抽屉 / 预算映射在 `budget_check` 节点抽屉（均实时 CRUD 调 `/api/requirement-rules`，立即生效）；`extract` 抽屉只留提取参数（分词 + 词表/系列映射，走 `updateNode` 保存）。每个节点的抽屉配它自己消费的规则库——抽屉跟着节点走，不再全压在 extract。

**关键文件**：`backend/app/services/clarity_evaluator.py`（评估算法）、`reasoning_executor.py`（三节点 handler + condition 白名单）、`requirement_intel_service.py`（run_pipeline 重跑 + apply_budget_check）、`requirement_rule.py` + `requirement_rule_repo.py` + `api/requirement_rules.py`（规则库 CRUD）；前端 `RequirementRuleList.vue`（统一规则编辑器）、`ReasoningNodeDrawer.vue`（ABCD 抽屉）、`useReasoningStream.ts`（need_input/pipeline_paused）、`ReasoningPanel.vue`（反问输入区 + 超预算标注）。
