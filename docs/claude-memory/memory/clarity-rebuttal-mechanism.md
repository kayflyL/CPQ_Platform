---
name: clarity-rebuttal-mechanism
description: "需求分析反问补全机制（clarity_check→cond_clarity→ask_user）；force_complete 开关语义；[0.1.39] 修三 bug；[0.1.42] Spec Assistant 式负载菜单+按 usage drill_down；碰反问/clarity/模糊需求前先看"
metadata: 
  node_type: memory
  type: project
  originSessionId: 4d154b82-9bd9-4419-b4a8-49bb8f52e5a9
  modified: 2026-08-02T15:29:57.338Z
---

需求分析推理流的「反问补全」机制：模糊需求暂停在 `ask_user` 节点反问，补齐后再跑。碰反问/明确度判定/force_complete 前先看。

**架构**（图驱动，[reasoning_executor.py](../../../../D:/CPQ_Platform_V1/backend/app/services/reasoning_executor.py)）：`extract → clarity_check → cond_clarity(条件分支) → ask_user(反问,叶子) / select_baseline(选型)`。
- `clarity_check`：调 [clarity_evaluator.py](../../../../D:/CPQ_Platform_V1/backend/app/services/clarity_evaluator.py) `evaluate_clarity(ext,budget,rules)`，按 clarity 规则集判定 level(explicit/partial/unclear)+missing_fields。
- `cond_clarity`：simpleeval 求值表达式选分支。**表达式 = `clarity != 'explicit' and not clarity_capped`**（[0.1.39] 改；旧 `=='unclear'` 只对 unclear 反问，partial 漏网）。
- `ask_user`：`_compose_question` 按 missing_fields 挑 rebuttal 话术(priority 排序,top-2)→broadcast `need_input`→ctx.awaiting_input=True。run_pipeline 见 awaiting_input 发 `pipeline_paused`。
- 四类规则在 `rules.requirement_rules` 表（[requirement_rule_repo.py](../../../../D:/CPQ_Platform_V1/backend/app/repository/requirement_rule_repo.py) DEFAULT_RULES）：clarity(明确度信号)、rebuttal(反问话术)、**workload(负载原型+drill_down)**、budget(预算→选配策略)。前端编辑器 RequirementRuleList.vue（按 ruleType 参数化，workload 编辑器含 drill_down 增删）。

**force_complete 开关**（**不是全局开关，是每次请求的 ctx 参数**）：
- **试运行 playground**(`/test-run`)：默认 **true**(跳过反问一键出方案)；[0.1.39] 加「启用反问补全」复选框可关。
- **真实入口**(商机详情页 `/api/reasoning/generate`)：默认 **false**(会反问)；点「跳过反问」按钮才 true。
- `clarity_check` handler 见 force_complete=true → 直接 partial + missing=[] 跳过。
- ⚠️ 试运行/诊断务必用 **backend/.venv** 的 python（有 simpleeval）；hermes-agent venv 没装 simpleeval → `_eval_condition` 永远返 True 污染结果。

**[0.1.39] 修的三个叠加 bug**（症状：模糊需求直接出方案不反问）：
1. cond_clarity 阈值写反（只 unclear 反问）→ 改 `!= 'explicit'`。
2. R-9 兜底的 usage='通用计算' 被当"用户说清"→ extract 加 `usage_inferred` 标志，clarity_evaluator 的 `has_usage` 改"用户明说"。
3. `model_token_in_category` 子串匹配永不命中(EPYC9354 不含"CPU") → 改型号→品类关键词表(`_MODEL_CATEGORY_KEYWORDS` + `_classify_model_token`)。

**话术增强**：unclear 首轮前置"现成配置清单可贴上来"一问（`clarify_round<=0` 才抛，用户已开始答 chips 后不重复）；新信号 `no_model_in_category`/`has_memory_capacity`；新话术 CPU型号/GPU型号/内存容量/硬盘(带 chips)；`seed_missing_defaults` 按名非破坏补种。

**反问记忆（[0.1.40]，重要）**：补充回填**必须累积跨轮持久化**，否则每轮只拼最新一句、丢失已答字段 → 重复问同一问题（"没记性"）。`run_pipeline` 用 `extra_fields.requirement_clarity_base`（原文，变了=新提问重置）+ `requirement_clarity_supplements`（累积串）；每轮 append 新回复再重跑 extract，已答字段自然从 missing 消失。前端每轮重发同一原文，故累积在后端 extra_fields。`_compose_question` 按 `clarify_round<=0` 控制 config-list 只首轮。死循环防护：`MAX_CLARIFY_ROUNDS=3`，超限 clarity_capped=True 强制走选型出方案。

⚠️ **[0.1.43] 关键修复（曾致反问机制整体失效）**：`round` 必须**在「重新点生成报价」时重置 0**（run_pipeline 收到无 supplement 的请求 = 全新对话），只有反答回复（supplement）才 +1。`requirement_intel_service.py:546`。否则 round 跨会话单调累积→用户多测几次到 MAX(3)→`clarity_check` line 433 永久 clarity_capped→反问只问 1 句就出方案。**诊断盲区**：diag 脚本每次新进程传固定 round=0，**测不出此累积**——验证真实链路必须用**完整 opportunity_id**（非截断）跑 run_pipeline 看 round 副作用。2026-08-02 三台商机全卡 round=3 即此症；同步重置存量 + 改重置逻辑。

**负载菜单 + 按 usage drill_down（[0.1.42]，Spec Assistant 式·纯规则）**：把 usage 检测从"猜"翻转成"选"。`_compose_question` 三条路径：
- **路径 A**（首轮 + usage 未显式）：抛负载菜单——各 workload 原型 label(emoji) 当 chip。用户点选含触发词的 chip → 补充 → 重抽 → usage 显式设定（复用 [0.1.40] 累积循环，零 schema 改动）。
- **路径 B**（usage 显式 + 命中原型）：原型决定性 drill_down **优先抛出**（选 AI→立刻问 GPU），用 `_field_satisfied`(读 ext categories/cpu_signal/mem_signal/budget) + requirement_text 含选项 双重判断防重复追问。
- 其余：扁平 rebuttal 模板（按 priority）。
6 原型(AI/存储/数据库/虚拟化/通用/渲染)落 `type='workload'` 规则，body={value,emoji,label,triggers[],drill_down:[{sets,options,question}]}。⚠️ AI 原型 triggers 必须含 "ai"/"加速计算"——extract 经 config 词表把 usage 解析成规范名 "AI / 加速计算服务器"（不是 "AI训练"），triggers 要能子串命中规范名。这是第一期 question_gen 的规则基底（[[llm-integration-strategy]]），LLM 来了只让措辞变自然。

**自测**：`python -X utf8 scripts/diag_clarity.py`（单条看 clarity 判定）/ `scripts/diag_clarity_convo.py`（多轮对话看负载菜单+drill_down+防重复）；cwd=backend。期望多轮：R0模糊→负载菜单(6 emoji chip)→R1选AI→问GPU→R2答H100→不重复问GPU、转问CPU→R3答4U→封顶出方案。

**待办**：①硬盘 auto-fire 需确认 drive 品类命名(现模板仅在编辑器palette)；②试运行反问不接回复(回复交互仍到商机详情页)；③cond_clarity 自愈只认旧值，用户若手动改回旧值不会再自愈(可接受)。

关联：[[strategy-center]]、[[reasoning-flow-viz]]、[[reasoning-match-enhanced]]。
