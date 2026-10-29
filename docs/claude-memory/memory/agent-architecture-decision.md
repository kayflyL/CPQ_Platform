---
name: agent-architecture-decision
description: 推理流 agent 方向定调 B2 收窄版——确定性管道当编排器/事实源，agent 仅做 grounding 节点（业界共识，A 是反模式）
metadata: 
  node_type: memory
  type: project
  originSessionId: 351c2cea-bcbd-4c60-b025-08db1d053dab
  modified: 2026-08-06T18:12:07.598Z
---

2026-08-07 定调（联网核查 2025-2026 生产级案例后）：
推理流往"智能体"改的方向 = **B2 收窄版**，不是 A（agent 吞掉后半段）。

**业界共识（微软 Conductor / Praetorian / Backbase / KongHQ / Shaped.ai）**：确定性编排包裹 LLM；确定性引擎是唯一事实源，做校验/拍板；AI agent 只做推理/推荐。模式「AI(概率) → 确定性引擎(校验) → 结果」。A（让 LLM 做路由/接管配置流水线）是被点名的反模式（上下文陷阱/不可检视/贵/幻觉规则）。

**落地**：确定性推理流图（select_baseline→match_kp→compose→budget_check→audit→review）当编排器和事实源，**不动**；AI 路把最弱的 llm_extract 换成 llm_agent（一个内部跑 ReAct 工具循环的「推理增强接地节点」）。llm_agent 默认挂两个**只读**工具：`select_models`（接地 server_type/系列/形态）+ `search_cases`（查 rules.bom_cases 案例库作参照，CBR-RAG，只检索不入库）。**不挂 pick_kp_parts/build_plan**——配 KP/组方案/算价是确定性后半段的活，agent 不越界（越界就滑回 A）。工具在 backend/app/services/agent_tools.py，画布 llm_agent 节点 config 可勾选启用 + 配案例检索参数（case_source/top_k/match）。

⚠️ CBR 旧接入在 llm_understand.py（原 llm_extract 用）已成死代码（llm_extract 被 llm_agent 替换），待 task #26 清理；案例检索现走 agent 的 search_cases 工具。

**"智能体"在此的准确含义**：不是自治配置器（反模式），是确定性管道里一个推理增强的 grounding 节点；agentic 部分（ReAct 工具循环）收敛在节点内，宏观系统确定性编排。可靠、便宜、可检视、复用验证过的后半段。

关联 [[reasoning-flow-viz]] [[llm-provider-relay]] [[strategy-center]] [[derive-must-have-manual-fallback]] [[llm-integration-strategy]]。
