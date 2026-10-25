---
name: llm-integration-strategy
description: 推理流接 LLM 的定调——规则+LLM 混合；⚠️2026-09-12 用户声明「离线可跑」定调已过时，系统已全面 LLM 在线智能化；接入点/护栏/UX 参考
metadata: 
  node_type: memory
  type: project
  originSessionId: 6a811e6a-b178-482c-b729-daf90e161fc7
  modified: 2026-09-14T14:32:47.160Z
---

**2026-09-12 用户定调（覆盖旧约束）：「系统必须离线可跑」已过时——系统早已转 LLM 在线智能化（llm_agent/agent_fill/助手全线在跑）。** 新设计不再受离线约束；保留降级路径仅为防代理故障（见 [[llm-provider-relay]] 的 429/掐连接问题），不是架构原则。同日定调：工具设计要平台级+考虑规模增长+结合大厂最新设计经验，别拿当前 288 件的小库当永久状态。**2026-09-14 跟进落地：全局「启用 AI 引擎」开关已整体拆除**（llm_client 四道闸 + is_llm_enabled + agent_react 两处前置检查 + AI 设置页开关；DB 里 enabled 字段留存不读）——它是离线时代残留的零粒度总闸，误碰即全平台 AI 报错；紧急止血去供应商控制台停 key，别再想加回这类开关。

2026-08-02 调研 + 用户定调：推理流接 LLM 走**规则 + LLM 混合架构**。规则当"法律"（定价/料号/兼容 100% 确定性、可审计），LLM 只在"预测比策略更重要"的点上**条件触发**。

**三个接入点（已预留为离线桩）：**
- `llm` 画布节点 → `reasoning_executor._dispatch` 已提成**显式 passthrough 分支**（`enable_llm` 默认 false → 不动 ctx）。role 三选一：`extract_enhance`(抽槽稀疏时补抽) / `question_gen`(取代 ask_user 模板) / `best_fit`(候选排序+理由)。前端 `ReasoningNodeDrawer` 的 llm 节点表单已存(prompt/model)，role/enable_llm 待第一期加。
- `chat_json()`（`llm_client.py`）—— 非流式 JSON 模式抽槽专用，**已定义为未接入桩**（raise LLMError）。与已存在的 `stream_chat()`（流式，方案助手浮动入口在用）并存。
- 已有占位保持原样：`clarity_evaluator` explain 的「未来 LLM 语料」注释、`useReasoningStream.FUTURE_STEPS.llm_best_fit`、`RequirementSample` 反哺语料模型。

**铁律（接入时必落实）：** LLM 输出**绝不裸进 match_kp/compose**（碰料号/价格/兼容）；只以 schema 校验过的结果喂回 ext，规则始终兜底。三道护栏：schema 校验(Pydantic/JSON mode)→枚举收口(未知 series 拒掉，回退规则值，见 [[series-ssot]])→失败重试一次仍失败则降级规则(LLMError 已存在，零 LLM = 今天行为)。可审计：LLM 输入输出连同规则信号记进 clarity_explain。reasoning 模型坑见 [[llm-reasoning-model-pitfall]]（结构化抽取给足 max_tokens≥8000、非流式收全文再解析，别边流边抽 JSON）。

**分期：** 第一期(question_gen+extract_enhance，体感最强 ROI 最高) → 第二期(best_fit 填 FUTURE_STEPS 占位) → 第三期(方案助手浮动入口走纯 LLM 对话，商机详情页推理流保持可审计路径不动)。触发哲学同 [[derive-must-have-manual-fallback]]：规则先跑永远跑，LLM 只在"规则快失败"时点亮；常见清楚需求全程零 LLM。

**行业三角验证（2026-08-02 三路后台调研同结论，信源已一致——下一步是建不是查）：**
- **CPQ 厂商**（Salesforce/Oracle/Tacton/Configit/D365/SAP）核心全是规则/约束引擎；LLM 是 2023-25 overlay（NL 入口/next-best-action/内容生成），**无一**让 LLM 端到端驱动提问分支 → 坐实"规则当法律、LLM 当通信层"非逆潮流。
- **经典 NLU**（Rasa/Dialogflow/Alexa/Bot Framework）**通用两层分离**：① 决定"下一槽问什么"的控制器——四家**全部规则驱动**、确定性；② 从原话抽槽值的提取器（regex→统计 ML→LLM 阶梯）。映射我们：`clarity_check→cond_clarity→_compose_question`=控制器（**永远规则**，LLM 只改措辞不路由）；`extract`(jieba+lexicon)=提取器，`extract_enhance` 就是把它上 LLM 阶梯。图驱动 executor=状态机型（Dialogflow CX/Bot Framework dialog stack），多主题配置流选这条对的。
- **question_gen 提问序用 SPIN**（Situation→Problem→Implication→Need-Payoff，Huthwaite/Rackham）当系统提示排序准绳：需求/场景先问→型号/CPU/内存→预算/规模最后。⚠️ [0.1.42] 负载菜单→drill_down→预算**已经直觉这么排**，SPIN 只是正名/成 checklist，非新增工作量。

**UX 参考（用户认可）：** https://server-configurator.com 的 Spec Assistant —— 快、对话式、emoji 友好、主动引导负载分类(虚拟化/数据库/AI/Web/存储/边缘)、推荐型号+协助配置、只聊服务器不闲聊。第一期 question_gen / 第三期方案助手照这体感做。注意"快"：reasoning 模型慢，体感靠流式(stream_chat 边出字)。
