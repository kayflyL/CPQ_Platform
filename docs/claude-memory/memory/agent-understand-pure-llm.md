---
name: agent-understand-pure-llm
description: AI 路需求理解 = 纯 LLM 填表(RequirementSlots) + 确定性 resolver；extract 只留离线兜底；抽不全→反问
metadata: 
  node_type: memory
  type: project
  modified: 2026-08-07T12:06:37.368Z
  originSessionId: 351c2cea-bcbd-4c60-b025-08db1d053dab
---

2026-08-07 P1 定稿：AI 路（llm_agent 节点）= **纯 LLM 填表 + 确定性 resolver**（非混合、非 regex）。

**架构**（[agent_understand.py](backend/app/services/agent_understand.py) `run_agent_understand`）：
- LLM 把需求填进固定表 `EXTRACT_ENHANCE_SCHEMA`（= RequirementSlots：cpu/memory/drives/gpu/nic/psu/raid/form/series/server_type），catalog 白名单锚定（类型/系列/形态只从在售清单选）。
- 确定性 resolver `merge_into_ext`（[llm_extract_enhance.py](backend/app/services/llm_extract_enhance.py)）把表归一成 ctx["ext"] 信号（mem_groups/drive_groups/gpu_groups/cpu_signal/...）。resolver 不碰自由文本、不打地鼠（结构化→结构化）。
- 下游 select_baseline/match_kp/compose 一行不改。
- **抽不全**（缺 server_type 等关键字段，`_is_sufficient`）→ sufficient=False + missing_critical → dispatch 广播 need_input 反问最关键一件（SAGE 门控）。force_complete（训练重放）跳过反问。
- LLM 关/失败 → extract_keywords 离线兜底（系统离线可跑）。

**为什么纯 LLM 不是 regex/混合**：regex 不泛化（打地鼠）；可靠性测试（[test_llm_extraction_reliability.py](backend/scripts/test_llm_extraction_reliability.py)，每输入 10 次）证明纯 LLM 填表关键字段 ~100% 命中。曾一度改混合（extract 基底+LLM），但 extract 自己的 bug（Raid 数量 1↔2 抖动、"25G光口"误切内存组）会经"rules win"传播、LLM 改不了——用户质疑后回归纯 LLM。**extract 从 AI 路彻底摘除，只留离线兜底**。

**P1.2 补 merge_into_ext 三缺口**（纯 LLM 必需）：raid_groups 直写 {model,qty,cache}、CPU 型号 token 进 keywords、server_type（schema 加字段 + catalog 白名单锚定）。单测 [test_llm_extract_enhance.py](backend/tests/test_llm_extract_enhance.py) 23 + [test_agent_understand.py](backend/tests/test_agent_understand.py) 7。

**验证**：replay_cases 加 `--ai` 开关注入 llm_enabled=True。纯 LLM 路 BOM 质量与本地路相当（5090 案例 7→5 改善；边界案例有 BOM 级波动，extract 自己也有）。**打地鼠停止**：新格式差异改 [agent_understand.py](backend/app/services/agent_understand.py) AGENT_UNDERSTAND_SYSTEM_PROMPT（X*N 数量约定等），extract 冻结不加 regex。

**已知/后续**：① BOM 级波动 → temperature=0 已加（[llm_client.chat_json](backend/app/services/llm_client.py) 加 temperature 参数、抽取调 0 确定性化）+ P4 CBR few-shot 进一步降；② LLM 偶漏字段（口语化 messy 输入）→ P4 CBR few-shot + prompt 迭代；③ escalate_grounding（ReAct 接地）config 默认关，server_type 缺时可选启用。**绝不退回加 extract regex**。

**白盒化（P2 已落地）**：run_agent_understand 透传 broadcast/step_id，发 step_progress 子事件（llm_understand「AI 理解中」→ understood「理解到：...」摘要）。前端 ReasoningStep/AssistantAnalysisStep 加 substeps 字段；useReasoningStream/useAssistant/useTestRun 接 step_progress → pushSubstep；ReasoningFlowCanvas 步骤时间线实时渲染 substeps（运行中也显示）+ llm_agent detail 改 source/sufficient 语义。

**前端**：llm_agent 抽屉理解模式表单（system_prompt + escalate_grounding + case_*），STEP_COPY/badge 走 source(llm/extract_only_*) + sufficient(反问) 语义。npm build 通过。

关联 [[bom-fill-training-loop]] [[agent-architecture-decision]] [[llm-integration-strategy]] [[reasoning-flow-viz]]。P2 白盒化（step_progress 子事件「AI 理解中→理解到」+ 前端 substeps 实时渲染）、P3 溶解 llm_guide（llm_agent→select_baseline 直连；反问并入 llm_agent 的 sufficient 判定；删 llm_guide dispatch/config/llm_guide_prompt.py/run_pipeline dialog_state/前端引用；migrate_remove_llm_guide 自愈）、P4 CBR few-shot（[case_provider._digest](backend/app/services/case_provider.py) 补 kp_lines 真实件 + [run_agent_understand](backend/app/services/agent_understand.py) `_retrieve_few_shot` 注入 prompt，config 门控 case_source/case_top_k；📚子事件）均已落地。**slot_validate 保留**（本地路功能件：写 slot_validation → clarity_check 读，折叠属可选未来清理，不在本轮）。P0-P4 全部完成。
