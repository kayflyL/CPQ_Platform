---
name: reasoning-flow-viz
description: 三期可视化推理流调研结论：当前推理流已天然DAG(5步硬编码顺序)+WS分步广播现成；选型AntV X6(用户定调)；P0只读思维链低成本高价值
metadata: 
  node_type: memory
  type: project
  originSessionId: 8bd06509-d133-4f58-a982-bcad04e81549
  modified: 2026-07-31T14:14:56.865Z
---

三期重点「自动生成报价 BOM」的核心抓手 = 把 BOM 推理流做成可视化 DAG（用户只读看推理过程 + 管理员可视化编排步骤），方案助手复用同一引擎。

**当前推理流现状（requirement_intel_service.py:125 `run_pipeline`）**：5 步硬编码顺序 `extract→select_baseline→match_kp→compose→review`，无分支/回退。WS（`reasoning_hub`）已分步广播 `step_start/step_done/candidates_ready/pipeline_done` 六类事件——**只读思维链展示的数据通路现成**。仅 `select_baseline` 接 `model_recommend` 策略（标注不驱动）；pricing/bom_spec/requirement 未接入 pipeline。`extract` 的 jieba 分词/CATEGORY_LEXICON 词表是黑盒（节点内部不可配，只暴露"关键词输出"）。

**选型：AntV X6（用户定调 2026-07-26，优先于 Vue Flow）**——蚂蚁官方维护、国内文档/案例丰富、通用图编辑能力强（未来血缘图/ER 图可一并覆盖）。Vue3 集成用 `@antv/x6-vue-shape` 让节点直接渲染 Vue 组件（antd-vue + 玻璃卡），比 Vue Flow 多一层 wrap 但不影响功能。备选 Vue Flow（~80KB 更轻、聚焦 DAG、Vue3 原生）。**借鉴**：Dify 类型化端口+节点配置抽屉、Coze 推理回放高亮、n8n 左画布右配置、ComfyUI（已 Vue 重写节点编辑器，先例）。

**路线**：P0 只读思维链（前端 X6 渲染现有5步 + WS 事件驱动节点高亮 + 每步 IO 浮层，不改后端，2-3天）→ P1 节点抽象+图持久化（5步抽 schema 存 DB + 后端 pipeline executor 读图执行，~1周）→ P2 可视化编排（管理员拖拽节点/连线/分支 + 右配置抽屉，1-2周）→ P3 方案助手复用同一 executor。

**Why:** 用户要"看清 AI 怎么推出来的"+"可配置推理步骤"，做好后方案助手+BOM 共用引擎，整个智能化流程清晰。
**How to apply:** 从 P0 起步（WS 数据现成、立刻见效、为 P1/P2 验证视觉交互），用户感受后再定 P1/P2。相关 [[strategy-center]] 三期方向、[[opportunity-detail-intel]] 推理流现状、[[assistant-skeleton]] 方案助手复用。

**实施状态（2026-07-26，P0+P1 合并完成）：** 后端 reasoning_flow 表（图+节点config）+ repo + API + seed v1 + run_pipeline 读 active flow config 透传（extract lexicon/limit、select_baseline max_plans/recommend_strategy_id、match_kp aliases/representative_pick）+ 三层兜底（DB 异常回退模块常量）+ candidate_search 签名扩展（默认值=原行为）。前端 **X6 弃用**——@antv/x6 3.1.7 在 Vite 下 view 层不渲染（model 有 cells、stage DOM 空，x6 3.x ESM/CJS 打包问题），改原生 SVG（参考 [[glass-console-system]] 的 PricingStrategyCanvas 模式）：dagre LR + 玻璃卡节点(ReasoningNode.vue) + SVG 贝塞尔连线 + 点击开配置抽屉(ReasoningNodeDrawer.vue)。挂载：Strategies.vue requirement 域（v-if !searchText && activeDomain==='requirement'）。验证：5 节点 4 连线渲染、点节点开抽屉、暗色视觉正确、后端存储闭环（PUT→GET 一致）。**P2 完成（2026-07-26，三阶段全完）：** X6/vue-shape 已卸载（Vite 下 view 不渲染，无用）；前端原生 SVG → **vue flow**（@vue-flow/core + background/controls/minimap，Vue3 原生 Vite 友好）。ReasoningFlowCanvas 重写为 vue flow 画布（拖拽/连线/加删节点 + debounce 持久化）；自定义节点 ReasoningNodeVf + 配置抽屉按 type 渲染（加 condition expr / llm）。**图驱动 executor**（reasoning_executor.py）：handler 注册表（复用 extract_keywords/select_baselines/pick_kp_parts/build_plan）+ 拓扑 BFS 执行 + condition simpleeval 安全求值选分支（变量白名单 series/form/categories/keywords）；run_pipeline 入口派发（有 active flow → 图 executor，异常/无 → `_run_linear_fallback` 原线性 5 步，三层兜底全保留）。端到端验证：真实 active flow 跑通 extract→select_baseline(3)→match_kp(2)→compose(3)→review，输出对齐 linear；condition 求值 series=='Polaris' 正确判 True/False。删除节点（抽屉内「删除节点」按钮）/ 删边（点边即删）。WS 协议不变，ReasoningPanel 零改。详见 docs/frontend-pages/strategies/strategies.md「推理流编排」段。**残留**：端到端（真实商机触发推理走图 executor 路径 + condition 分支用例）待用户真实操作验证；llm 节点 P2.3 预留未接入实际 LLM 调用。

**试运行 playground（2026-07-31，详见 [[reasoning-testrun]]）：** 画布下方内嵌面板，输入需求→复用 `run_graph_executor`→节点逐步高亮 + 每步 IO 明细 + 候选方案卡（复用 PlanCard/STEP_COPY）。⚠️ 顺带修了 **simpleeval 从未写进 requirements.txt** 的坑——缺它 `_eval_condition` 静默永远返回 True，所有 condition 走 true 分支（cond_clarity 永远反问、走不到选型）；已补 `simpleeval>=0.9.11`。
