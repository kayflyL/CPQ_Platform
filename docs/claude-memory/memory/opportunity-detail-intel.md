---
name: opportunity-detail-intel
description: 商机详情页智能化 = 整机方案级组合(Path A 本地)：推理流(jieba+选baseline+配KP+组整机方案)+方案卡+BOM详情抽屉(复用BomTable)+确认转草稿；规则全落 system_config；二期项面板灰显
metadata: 
  node_type: memory
  type: project
  originSessionId: 3045d5d6-c948-44e1-bc00-564c2a6f2ede
  modified: 2026-07-25T13:10:34.311Z
---

2026-07-25 商机详情页（`OpportunityDetail.vue`）智能化改造**已落地**，**粒度从零件级改为整机方案级**：客户需求 → 点「生成报价」→ 后端本地 pipeline（jieba 分词 → `select_baselines` 选 1-3 个基准机型 → `pick_kp_parts` 按需求品类配 KP → `build_plan` 组整机 BOM）→ `ReasoningPanel` 推理面板实时显步骤 + **2-3 张整机方案卡** → 用户看方案卡 / 点「查看 BOM 详情」（抽屉复用 `BomTable`）/ 「确认转为报价单」→ 草稿进右栏 → 跳工作台调价。布局：左=需求+生成入口+推理面板，右=报价单(上)+存档区(下)；工作台加利润率告警。

**演进注记**：初版（一期）做的是**零件级候选清单**（l6/kp 散件多选 → 预填草稿），用户定调**做错了粒度**——要的是整机方案级（系统组合整机，不让用户拼散件）。遂按 **Path A（先本地组合，不调 LLM）** 重构为当前形态。零件级 `search_candidates`/`Candidate` 类型保留供 REST 调试，pipeline 不再走它。

**用户定调（碰这块前必看，别推翻）**：
1. pipeline **纯本地、不调 LLM**（jieba 分词 + 选 baseline + 配 KP + 组方案）；"判断最合适"是语义问题，本地规则只给"符合硬性条件的组合"，**留待 LLM 增强层**（届时 `llm_client.stream_chat` 加 `tools`，本地组合退成候选供给）
2. 「生成报价」产出**整机方案卡**（每张 = 基准机箱底盘件 + 配齐 KP），不是散件；**多品种轴 = 不同 baseline**（不搞同 baseline 不同 KP 负载）；用户**选一张确认**转为草稿（不自动成 BOM、不散件多选）
3. **推理面板为主，助手聊天窗只简要提示**（不弹窗接管 pipeline）；推理流走独立 WS `/api/reasoning/ws/{oid}` + `reasoning_hub`，与聊天 `assistant_hub` 物理隔离
4. **所有数值规则落 `system_config`，绝不硬编码**：`profit_margin_alert_threshold`(0.08)、`default_markup_coefficient`(0.10)；前端读走 `usePricingRules`

**Why:** 用户要整机方案而非散件；本地组合稳/快/免费，语义择优后置给 LLM；候选精度受 KP spec 稀疏限制，必须人工核验兜底（[kp-spec-coverage-sparse]、[derive-must-have-manual-fallback]）。

**How to apply:**
- 核心组合逻辑在 `backend/app/api/candidate_search.py`：`select_baselines(series,form)`（精确→补同系列→补同形态→兜底全量，封顶 3）、`pick_kp_parts(categories,keywords)`（型号 token 命中优先 via `get_latest_prices`，否则品类代表件 via `get_by_category` 取最低价，qty 默认 1 不做 derive）、`build_plan(baseline,kp_parts)`（baseline 底盘件→L6 行 + KP→KP 行，组装 `cfg{bom_source:'excel',bom_excel_rows}`）、`compose_plans(...)` 入口
- pipeline 编排在 `backend/app/services/requirement_intel_service.py` `run_pipeline`（5 步：extract/select_baseline/match_kp/compose/review），`candidates_ready` 下发 `{plans}`（非 candidates）；`extract_keywords` 不动
- 前端：`api/reasoning.ts`（`Plan` 类型；`cfg.bom_excel_rows` = base_config_parts 平铺 L6 行 + KP 行）、`composables/useReasoningStream.ts`（`plans` ref）、`components/opportunity/ReasoningPanel.vue`（**对话式消息流**：头部 RobotOutlined + 状态、每步完成弹一条自然语言 AI 消息、方案卡作为消息推入、三点 typing、二期脚注；Glass Console 原生——白玻璃气泡 `overlay-w6`+`radius-md`、方案卡左渐变 signature 描边；粘顶 `clamp(260px,calc(100vh-400px),600px)`）、`OpportunityDetail.confirmPlan`
- **L6 转模板格式**（用户定调：L6 要按基准配置的 BOM 模板格式，与工作台左栏一致，不要平铺散件）：`composables/usePlanBom.ts` 的 `buildPlanCfg(plan)` 按 `plan.config_id` 取 `bomTemplateApi.getForBaseConfig` 模板行 + `baseConfigApi.get` 底盘件 → 跑前端 `evalBomContext(rows, ctx)` 求值出 `bom_context`（ctx 是 baseline-only 近似：parts=底盘件、vars 从 parts 派生 bays/gpu_qty/drive_count、rear/frontCables 空 → 相关行回落，主干 CPU/内存/GPU/电源/机箱 行 part_field 正常解析）→ BomTable live 模式渲染。无模板/取失败 → 回落 excel 平铺。drawer + confirmPlan 共用 buildPlanCfg
- `confirmPlan` seeding（via `saveItems` 的 `config_l6_picks`，store 载入时读 `base_config_id`/`bom_source`/`bom_template`/`bom_context`/`bom_excel_rows`/`l6_custom_price`）：`bom_source:'live'` + `bom_template`+`bom_context`（无模板时回落 `bom_source:'excel'`+`bom_excel_rows`）+ `base_config_id` + `l6_custom_price`(=`summary.l6_cost`) + `l6_profit_margin`(10)；KP 走 `items`。一商机一草稿，已有则 `Modal.confirm` 替换
- BomTable excel 模式拆分键：L6 行 `category='L6'|'整机'`、KP 行 `category='Key Parts'`（L6 无 cost 列、KP cost=base_price）
- **flexbox 坑（踩了几轮）**：ReasoningPanel 的 feed 是 flex 列 + 固定高度内滚，方案卡 `.rp-plan` 因设 `overflow:hidden`（裁左渐变描边）触发"自动最小高度归零"——feed 一比内容短，卡被**压扁纵向裁字**（字只剩一半）。修法：feed 所有直接子项加 `flex-shrink:0` 保固有高度、超出靠 feed 滚。同理任何 `overflow:hidden` 的 flex 列子项都要 `flex-shrink:0`
- 二期项（面板内灰显 + 「二期」标签占位，别误删）：LLM 语义择优、历史 BOM 向量相似度、自动调参、历史报价接入定价、精细化客户分层/阶梯加成、线上特价审批、驳回自动回流
- 关联 [[assistant-skeleton]]（助手隔离）、[[opportunity-identity]]、[[systematic-cleanup-not-whackamole]]、[[autonomy-large-tasks]]、[[kp-spec-coverage-sparse]]、[[derive-must-have-manual-fallback]]
