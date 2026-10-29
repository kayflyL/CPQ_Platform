---
name: reasoning-testrun
description: 推理流试运行 playground(2026-07-31)：三栏(左节点palette/中画布/右试运行)输入需求→复用 run_graph_executor→节点逐步高亮+每步明细+方案；复用 PlanCard/STEP_COPY；踩 simpleeval 缺失坑+货币折算(USD×汇率×(1+税)→RMB，BomTable 按原币种显符号)；碰试运行/调试推理流前先看
metadata: 
  node_type: memory
  type: project
  originSessionId: 6682c6cd-e258-4e7b-8135-c8d1465d0d6c
  modified: 2026-08-01T08:26:14.868Z
---

2026-07-31 策略中心·需求分析域加「试运行」playground（[[reasoning-flow-viz]] P2 之后）。管理员改完 extract 词表 / match_kp 规则后，三栏（**左节点 palette / 中画布 / 右试运行**，参考导出模板页 UniverTemplateEditor；演进：下方内嵌→两栏→三栏——下方画布吃滚轮缩放、两栏加节点仍靠 dropdown，三栏左 palette 常驻点加最顺手）→ 右栏输入需求(+可选预算) → 中栏画布节点逐步高亮(extract→…→review，running 蓝边 / done 绿边 + 徽标如"配6件") + 左栏每步 IO 明细 + 候选方案卡。配置→验证闭环不再断在命令行 `simulate_requirement.py`。

**后端**（仅改 1 文件 `api/reasoning_flow.py`）：加 `POST /test-run` —— 读 active flow，构造**收集 broadcast**（append 到 list 而非走 WS），调 `run_graph_executor("test-run", text, flow, collect, initial_ctx={budget, force_complete:True})`，从 ctx 取 ext/kp_by_model/plans 组装响应。**`opportunity_id` 是摆设**（executor 内从不引用）→ 可解耦商机。`force_complete=True` 让 clarity_check 置 partial/capped → cond_clarity 走 false → 选型一步出方案。**不回退 linear**（调试工具，报错原样暴露）。明细全在 ctx，无需扩展 step_done payload（它只是计数摘要）。

**前端**：`composables/useTestRun.ts`（同步 HTTP + setTimeout 按 events 顺序回放 step_start/step_done → 经 `applyNodeState` 回调写画布 nodes 的 execState/badge）+ `ReasoningFlowCanvas.vue`（工具栏按钮 + 下方面板：输入/步骤时间线/PlanCard + BOM 抽屉）+ `ReasoningNodeVf.vue`（execState class + badge）。**节点高亮按 node id 精确匹配**（`event.step === node.id`，不是 stepType——同 type 可能多节点 `extract_1`）。共享文案抽 `utils/reasoningStepCopy.ts`（STEP_COPY + STEP_BADGE，ReasoningPanel 也用）+ `components/reasoning/PlanCard.vue`（方案卡从 ReasoningPanel 抽出，emit view-bom 带 plan；ReasoningPanel 的"确认转报价单"经 #extra-actions slot 注入）。

**⚠️ simpleeval 缺失坑**（本次踩到，根因排查绕了弯）：condition 求值靠 `simpleeval`（executor 顶部 try/except import）。**它从未写进 requirements.txt**，缺它 `_eval_condition` 静默永远返回 True → 所有 condition 走 true 分支（cond_clarity 永远反问、试运行永远卡在 ask_user 走不到选型，plans=0）。**已补 `simpleeval>=0.9.11` 到 requirements.txt** + 装进 backend/.venv。线上若 condition 行为异常（反问死循环 / 分支总走一边），先查 simpleeval 装没装（`python -c "from app.services.reasoning_executor import HAS_SIMPLEEVAL; print(HAS_SIMPLEEVAL)"`）。关联 [[app-startup]]（装包用 `uv pip install --python backend/.venv/Scripts/python.exe simpleeval`，.venv 是 uv 精简 venv 无 pip）。

**货币折算（build_plan，2026-07-31 顺带修）**：推理流方案总价曾把 USD 的 KP 件（如 KH50000 96C CPU）当人民币混加还贴 ¥（`build_plan` line 737 直接 `baseline.total_price + sum(kp.unit_price×qty)`，不看 currency；baseline currency 写死 RMB）。已按报价工作台口径（[[strategy-center]] `store/quote.ts:194`）修 `candidate_search.build_plan`：USD 件 `price × usd_to_rmb × (1+tax_rate)` 折成含税 RMB（system_config 读默认 7.0/0.13），RMB 件已含税直用，`summary` 统一 `currency:"RMB"` + `rates`。实测 KH50000 USD 3500×2 → 55370 RMB，total 73504→121874。影响所有 build_plan 消费方（test-run + 商机详情页方案卡）；报价工作台不走 build_plan（它有自己的 quote_service）。前端 KP 明细按原币种显 $/¥（currencySymbol）；**BomTable（BOM 详情抽屉，共用组件）Cost 列同样按 `row.currency` 显符号**（line 47 原 `¥` 写死 → currencySymbol；kpRows 加 currency 字段；工作台/详情页/test-run 一并修对，工作台 items 无 currency 时默认 RMB 行为不变）。**⚠️ 后端 --reload 改 build_plan 后要全新重启**（reload 过渡态 worker 引用缓存，curl 可能命中旧 build_plan；停后端要杀 multiprocessing spawn helper 孤儿，见 [[app-startup]]）。

**vue-flow 控件深色化（三层白坑，2026-08-01）**：推理流画布（`ReasoningFlowCanvas`）vue-flow 的 MiniMap/Controls 默认白底，深色模式突兀。要覆盖**三层**：① `.vue-flow__minimap` 容器 bg（默认 `#fff`）② `.vue-flow__controls-button` bg（默认 `#fefefe`）③ **`.vue-flow__minimap-mask`** 视口遮罩 fill（默认 `rgba(240,240,240,.6)`——这个最隐蔽，容器改深了它还浅灰白雾，看着像"白框没变化"）。scoped `:deep()` 覆盖：`.center-panel :deep(.vue-flow__minimap){background-color:var(--cpq-bg-secondary)}` + controls-button 同 + `[data-theme="dark"] .center-panel :deep(.vue-flow__minimap-mask){fill:rgba(0,0,0,.45)}`。**抓白源用 preview inspect `getComputedStyle(el).fill/.backgroundColor`**（screenshot 不可用，见 [[scoped-global-pitfall]]）；`--cpq-bg-secondary` 双主题（深 #101217 / 浅 #F0F4FA），glass-* 是半透明不能做不透明控件底。PricingFlowCanvas 同 vue-flow，主题化照搬。

**工作流编排可解释性完善（2026-08-01，借鉴腾讯元器，见 docs/工作流开发/）**：
- **P0 节点 IO 元数据**（`utils/reasoningNodeIo.ts`）：声明每节点 consumes/produces 变量（描述性，执行走隐式 ctx 不变）。试运行步骤展开顶部显「←输入（上游来源）/→输出（下游消费）」。参考腾讯元器显式输入/输出变量。**未全改显式变量**（侵入 10 handler 太大），用元数据拿 80% 可解释性。
- **P1 路径回溯**：方案卡「回溯路径」按钮 → 画布高亮**实际执行过的所有节点**（steps 里 status=done 的，含 clarity_check/budget_check/review，**非硬编码 4 个**——曾因只取 extract→select→match→compose 数据主链被吐槽"没实质"）+ **生成链连线高亮**（数据流向，rf-edge--trace 蓝/dim 淡）+ 其余节点/边 dim；**回溯模式下点任一高亮节点 → 右栏展开该步 IO+明细**（onNodeClick 加 traced 分支，读实际数据）；退出恢复。参考腾讯"点输出反高亮路径"。
- **P2 palette 三环节分组**（信息收集/判断处理/分支控制/预留）+ **condition 分支必连校验**（danglingBranches computed，缺 true/false 告警）。参考腾讯节点分类 + 分支必连。
- **推迟**：全显式变量系统（侵入大）/ 单节点独立调试（mock ctx 复杂，整条试运行已够）/ LLM 节点化（二期 Path A 本地）/ 聚合·循环·批处理（无场景）。

**批量验证（2026-08-01，`scripts/audit_reasoning_batch.py`）**：工具层收口后改打「验证优先」——拉库里真实 `customer_requirement_text`（6 条多样样本：AMD/兆芯/鲲鹏、2U/4U、带 GPU/不带），逐条跑**真路径** `run_graph_executor`（force_complete，与 test-run 同源；simulate_requirement 是线性直调不忠实）。结论：**执行成功 6/6，选型命中仅 4/6**。两大 gap：
- **【严重·数据】4U 需求 100% 空跑（2/6）**：`server_catalog` 全库**只 3 个机型且全是 2U**（通用 Polaris ZS22V2-P / AI Orion ES22V3-P / 存储 Orion），**0 个 4U**。兆芯 4U + 鲲鹏 4U 需求全部出 0 方案。根因是数据建模缺口——4U 还在老 L6 机箱库（`_old` 表，见 [[l6-chassis-legacy-flow]]）没迁进 server_models，**不是 select_models 算法问题**（它的去 type 兜底逻辑合理，是无米下锅）。`select_models` 早返空只在 4 信号全空时触发，有 form 不会早返。→ 补 4U 机型是运营/数据工作，非推理流代码。
- **【中·配置】extract.series_keyword_map 空导致系列不识别（4/6 series=—）**：active flow 的 series 词表是**空 `{}`**，一条触发词没配。兆芯 KH-5000/KH-50000（应→Polaris，见 [[series-ssot]] 兆芯=Polaris 已迁）、鲲鹏 920 全靠字面 `SERIES_KEYWORDS` 兜底（中文/型号触发词为 0）。2U 没炸是因为 form 兜住了，但影响 pricing 的 `platform_baseline` 维度 + recommend 标注。→ 画布 extract 节点补 series 词表即可（用户可配层，非代码）。
- 【轻·噪声】"型号未命中"幻影 unmatched（3/6）：需求里的型号 token（KH5000/9334/920/4090）精确 PN 没命中→落成 category="型号未命中" 的 unmatched 件，看着像失败实为预期（客户描述词非真 PN）。展示层摘出即可。
- 【观察】CPU 双路信号漏识别（#3 "48C\*2" 明确双路却 cpu_signal=—）；6/6 预算全空（样本特性，budget_check 无机会触发）。
- **审计脚本可复用**：`scripts/audit_reasoning_batch.py`（拉真实需求→run_graph_executor→逐条审计+gap 汇总），与 `simulate_requirement.py`（线性直调）互补，后者不忠实。改完 extract/match_kp 规则可重跑回归。
