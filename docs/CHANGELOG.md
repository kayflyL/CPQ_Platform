# 更新日志

> 最后更新：2026-08-10
>
> 定位：**轻量变更索引**（接手导航）——每条 = 变更 + 根因一句 + 涉及面；细节与 why 以代码注释为准。
> 图例：🔄 撤回/纠正 · ⚠️ 破坏性/严重 · 💡 认知定论（最值得看）。

---

## [0.1.57] - 2026-08-10 — 历史遗留清理（双路图/逐节点开关/migrate代码/extract前端残留，净 -936 行）

### 三批清理（每批后跑测试确认）
- **批次1·死注释/死引用**（7 文件）：capabilities.py/requirement_intel_service.py 删 requirement_parser 悬空引用；models/reasoning_flow.py 旧 5 步描述改 AI-first 单路链；llm_extract_enhance/llm_client/reasoning_intel 删双路旧描述。
- **批次2·逐节点开关**：删 `ai_mode`(4处死字段) + `enable_llm`(llm_audit 只认全局开关 + 删 orchestrator `audit_llm` 预算字段) + `proposal_mode`(kp_reason 固定 llm_propose，删 react/rule 分支 + 死符号 `_KP_REASON_PROMPT`/`_collect_kp_from_react`)。测试：删 `test_disabled_skips_llm`(节点级开关已不存在)。
- **批次3·结构性删除**：
  - `DEFAULT_GRAPH`(v9 双路种子图) 删除 + `seed_default_if_empty` 改 seed V11（新环境直接建单路链）
  - `active_is_current` 删 v9 死检查（understand 提前返回已覆盖）
  - **21 个 migrate/upgrade 方法**删除（reasoning_flow_repo -815 行）+ **startup.py 19 个 migrate 调用**删除（只留 seed + active_is_current 检查）
  - `_VALID_NODE_KEYS` 收敛 + 补全 orchestrator/result_check（修保存 400 潜在 bug）
  - extract dispatch 改静默跳过（返回 None）；`understand_fallback` 死信号删除
  - 前端 extract meta/IO/stepCopy/抽屉 buildConfig/form 全清理；NodeIndexOutlined 未用导入删

### 验证
- 后端 371 passed（原 372，删 1 个废弃测试 test_disabled_skips_llm）
- 前端 vue-tsc 0 error + npm test 60/60 全绿
- 净节省 **-936 行**（1011 删 / 75 插入），reasoning_flow_repo.py 从 ~1393 行降到 ~605 行

---

## [0.1.56] - 2026-08-10 — 正则解析路径物理删除（requirement_parser 包移除，约 -2600 行）

### 删除清单（AI-first 后死代码物理清除）
- **整个 `requirement_parser/` 包**（signals 1266 行 + knowledge 109 + tokens 9 + __init__ ~90 ≈ **-1474 行**）：`extract_keywords` 正则理解自由文本 + 全部字段级正则提取器（`_extract_budget/_extract_mem_signal/_extract_cpu_signal/_extract_psu_signal/_extract_drive_groups/_extract_gpu_groups/_extract_raid_groups/_nic_line_filters/_split_requirement_fields/_mem_group_from_each/_normalize_table_rows` 等）——均已无生产调用
- `capabilities.run_rule_understand`（extract 节点 handler，~-40 行）
- `reasoning_flow_repo._v11_node_configs` 的 extract 默认配置 + 过时注释（~-15 行）
- 测试：`test_nic_qty_binding.py`（全测已删正则，~-245 行）+ `test_requirement_intel.py` 死块（~-900 行，90+ 个死正则测试）
- **净节省 ≈ -2650 行**（迁入 requirement_intel_service 的 `_load_series_values`/`_CN_STOPWORDS` 仅 +25 行）

### 保留
- `_load_series_values`（系列白名单权威源）+ `_CN_STOPWORDS` → 迁入 requirement_intel_service（调用方 llm_extract_enhance/reasoning_executor/reasoning_flow_repo 导入路径不变）
- 其余共享能力（CATEGORY 词表经配置、MODEL_TOKEN_PATTERN 在 clarity_evaluator 本地）不受影响

### 验证
- 后端全量 pytest **372 passed**（删 94 个死测试后）+ 前端 vue-tsc ✓；导入健康检查通过
- 职责边界：AI-first 后节点职责 = 理解(LLM)/机型(规则+放宽)/配件(LLM提议+库校验)/组装(确定)/校对(judge)/反问；extract/规则正则理解已彻底退出历史舞台

---
## [0.1.55] - 2026-08-10 — 正则理解路径（extract_keywords）生产调用全摘除

### 背景
用户问"AI 失效走手动配置，后端为什么还保留正则解析"。核查发现：AI 失效（关 AI）确实走目录手动选型、不碰正则；但正则解析还挂在**两条边缘路径**：① 线性兜底（整个图/orchestrator 异常时第 1 步还在跑 run_rule_understand）；② 旧图兼容（画布显式放 extract 节点）。

### 改动
- `_run_linear_fallback` 第 1 步：正则解析 → **诚实降级**（广播"⚠️ AI 推理不可用，请手动选择机型与配件"+ 空 ext），不再产出可能错误的 BOM
- `_dispatch("extract")`：返回 `{deprecated: true, ...}` 占位，不再调 requirement_parser
- **保留**：`extract_keywords` 函数本体 + `requirement_parser.signals` 字段正则（`_extract_raid_groups`/`MODEL_TOKEN_PATTERN` 等仍被 merge/清晰度评估/测试使用，不可整删）；生产路径已不再调用

### 验证
- 后端全量 pytest **466 passed**（+ 前端 60，vue-tsc 绿）
- AI 失效路径不变（目录手动选型）；图/orchestrator 异常路径从"假智能正则"改为"诚实降级提示"

---
## [0.1.54] - 2026-08-10 — AI 路线清理：画布/抽屉/旧开关全面瘦身（用户主导）

### ① 画布收敛
- active flow 从 10 节点 → **9 节点全连通**：移除 extract（正则理解已废弃）；llm_ask（反问配置）、spec_compliance（合规红线）、audit_fix（自纠）**连线保留**（此前孤立）
- 新边：understand→llm_ask、kp_reason→spec_compliance→compose、llm_audit→audit_fix→review
- palette 移除 extract / gap_analyze / scene_decide（已并入理解；meta 保留供旧图渲染）

### ② 右上角「LLM 节点」按钮移除（旧版逐节点开关 LLM）
- ReasoningFlowCanvas：按钮 + LLM 节点总览抽屉 + openLlmNodes/toggleLlmNode/setAllLlm 全删
- 后端 `GET /api/reasoning-flow/llm-nodes` + `list_llm_nodes` 删除；前端 api `llmNodes()` 删除

### ③ 抽屉旧开关清理（AI-first，后端默认行为保留）
- **ai_mode（智能实现）**：4 处单选全删；`_ai_enabled` 简化=只认全局 AI 开关（规则只作失败兜底）
- **proposal_mode（提议方式）**：ReAct/纯规则选项删除；后端默认 llm_propose + 失败自动降级规则
- **deterministic（确定性红线）开关**：删 UI；后端默认红线集合（compose/llm_audit/review/audit_fix/spec_compliance/result_check）照旧
- **llm_audit「启用 LLM 方案校对」**开关删（默认走 judge，由编排预算控制）
- 清理 DEFAULT_DETERMINISTIC 常量 / toggleLlm / isCapabilityNode 等死代码

### ④ 剩余项：专家分析 issues 前端渲染
- `_dispatch` understand 返回透出 `issues`；试运行步骤里渲染「专家分析」问题清单（标题+依据+建议），像方案助手一样先给建议再进选配
- requirement_parser 收敛为纯结构化工具：保留为 dormant（画布兼容），不在主线使用

### 验证
- 后端全量 pytest **466 passed** + 前端 vue-tsc + 60 tests ✓
- 8 卡需求真实 flow：KP 全对（8×32G/9361-8i/双口网卡/2700W）、spec_compliance 无重跑循环
- 说明：本轮 e2e 慢是模型当前坏期（understand 91s/kp 79s），非功能回归；链路顺序与清理前一致

---
## [0.1.53] - 2026-08-10 — 需求分析智能化改革 · Phase3：诚实降级 + 清理规则路径残留

### ① 删 ai_mode: rule（纯规则模式）
- `_ai_enabled` 删除 rule 分支（rule 不再作为独立模式，规则只作失败兜底）；前端 4 处「纯规则」单选项移除
- 遗留配置 ai_mode="rule" 自动按 auto 处理（跟随全局）

### ② AI 不可用 → 明确告知 + 目录手动选型（诚实降级）
- orchestrator ai_off 路径广播「⚠️ AI 引擎暂不可用（网络/额度），以下按手动选型引导，选项均来自在售目录」
- 不再用正则假装理解自由文本；extract 仅当用户显式连入画布图才执行

### ③ 画布试运行（run_graph_executor）同步去 extract 自动兜底
- 与方案助手一致：extract 不再因 understand_fallback 自动执行（旧正则理解路径全链路下线）

### 验证
- 后端全量 pytest **466 passed**（1 deselected：既有数据依赖）；前端 vue-tsc + 60 tests ✓
- test_scene_analyzer 改 hermetic（注入 ext + 关 LLM，不依赖已删的 ai_mode=rule）；套件从 ~7min 降到 ~17s（测试不再碰真实 LLM）

---
## [0.1.52] - 2026-08-10 — 需求分析智能化改革 · Phase2：理解升级「专家分析」+ 默认链收敛

### ① 理解节点「专家分析」（第 5 个子任务，并行）
- `UNDERSTAND_STEPS_DEFAULT` 新增 `analysis` 步：LLM 像资深售前一样输出**硬问题清单 issues[]**（issue/evidence/suggestion，最多 5 条）——检查电源/内存通道/RAID 存储/网卡/散热
- 8 卡需求实测 5 条：电源需 4×2700W、内存 256GB 通道不匹配、数据盘容量不足、10GE 瓶颈、缺专用 GPU 机箱 —— 与方案助手分析同级
- issues 进 `ctx.analysis_issues` + understand 步 payload（step_done 带 issues，前端可展示）

### ② 理解节点自带「场景/缺口」（为去 gap/scene 做准备）
- run_understand 现在同时产出 `ctx.scene`（由类型/系列/形态确定性给出，与 scene_decide 同构）+ `ctx.clarity`（充分→explicit / 不足→partial）+ missing_fields
- 默认链不再依赖 gap_analyze/scene_decide；_needs_llm_decision 反问门控照常工作

### ③ 默认链收敛
- `DEFAULT_GRAPH_V11` 收敛为 6 节点：understand(专家分析) → model_reason(多级放宽) → kp_reason(提议+库校验) → compose → llm_audit(judge) → review（llm_ask 反问侧枝）
- active flow 已更新；迁移框架（migrate_v12_spec_audit 等）幂等补回 spec_compliance/audit_fix/extract 三个**确定性安全门**（0s；GPU 必配/自纠/兜底，不碎片化 LLM 智能）——gap/scene/budget 等 LLM 碎片节点已移除
- 旧节点保留在 palette 可拖回（图=能力注册表，回退=画布改图）

### ④ 实测（真实 active flow，8 卡需求）
- 155.6s | plans=1（ESA24V3-P Orion-Switch）| 专家分析 5 条
- KP 全对：9354×2 / R9700×8 / 32G×8 / 480G×2+960G×2 / 双口1G+双口10G(光) / 9361-8i×1 / PSU 2700W
- 模糊需求（6 节点链）：18s 反问"主要用途？"（真实选项）

### 验证
- 后端全量 pytest **466 passed**（1 deselected：既有数据依赖）；前端 vue-tsc + 60 tests ✓
- 测试更新：ready_deps/线性链/retry 链/derive 均收敛到 6 节点；retry 测试 hermetic（mock _decide_retry_targets）

---
## [0.1.51] - 2026-08-10 — 需求分析智能化改革 · Phase1：KP「LLM 提议 + 库校验」+ 删 extract 理解路径

### 背景
8 卡需求实测：方案助手（纯 LLM）又快又准，需求分析（规则匹配）又慢又错（内存 16G×1 / RAID 缺失 / 网卡 400G / 电源 2000W）。根因=LLM 整体推理被"字面抽取+死规则匹配"丢弃（正式方案见《需求分析智能化改革-执行方案.md》）。

### ① KP「LLM 提议 + 库校验」（kp_reason 改革·核心）
- 新 `_kp_llm_propose`：LLM 读需求+理解摘要+机型通道 → 确认需领域知识的项（内存条数/RAID 型号/网卡口数/电源）→ `pick_kp_parts` 库校验执行（真实料号/价格，防幻觉）
- `proposal_mode` 可配：llm_propose(默认) / react(旧 ReAct) / rule(纯规则)；失败自动降级规则
- 8 卡需求实测：内存 16G×1→**32G×8**、RAID 缺失→**LSI 9361-8i×1**、网卡 400G→**双口1G i350 + 双口10G+光模块**、电源 2000W→**2700W×4**（确定性 TDP 计算）

### ② 配套子修复
- memory 槽位加 `total_gb`：只给总量（256GB DDR5-4800）不丢，LLM 提议按通道拆条（8×32G）
- RAID：S4 允许按规格推断型号（2GB缓存+8口→9361-8i）；修复 stage-1 关键词 + raid_groups 双路径双计 qty（×2→×1）
- 网卡：S4 "N×speed" 解释为 N 口双口卡（2x 1GE→ports:2,qty:1）
- PSU：`_kp_signals` 改按 GPU 实际 TDP（配件库 specs.tdp 优先 → `gpu_tdp_by_model` 配置表 → 词表兜底），删对硬编码清单的强依赖；`high_tdp_threshold_w` 可配

### ③ 删 extract 理解路径（AI 失效第二套智能）
- orchestrator 不再路由 `understand_fallback` → extract 正则理解（诚实降级：理解失败→缺口反问）；extract 仅画布兼容保留
- 遗留：ai_mode=rule 抽屉选项、requirement_parser 收敛到结构化解析（Phase3 清理）

### 验证
- 8 卡需求 KP 对标技术员方案（CPU/内存/RAID/网卡/盘/GPU/电源 全部对齐）；PSU 确定性推断 2700W
- 后端全量 pytest **466 passed**（1 deselected：既有数据依赖 test_raid_applicable_orion_default_9540）；前端 vue-tsc ✓
- kp_reason 抽屉新增 proposal_mode（LLM 提议+库校验 / ReAct / 纯规则）

### ⚠️ 误删恢复说明
Phase1 实施中替换区间误删 capabilities 的 run_llm_ask/run_llm_confirm/白名单辅助（_catalog_whitelist/_filter_catalog_options/_catalog_fallback_options/_FORM_WHITELIST 等），已按 tests/test_llm_ask_catalog.py 契约 + 原实现语义重建并全绿。

---
## [0.1.50] - 2026-08-10 — 需求分析 agent 化：理解拆步子任务 + 选型多级放宽 + 混合脊柱编排 + judge 校对（全部可配，白盒）

### 背景（💡 根因实测定论）
用户反馈"AI 智能体像假的、5 分钟跑不完、不出方案"。逐层实测定位：
1. **理解节点空回**：deepseek-v4-flash（reasoning 模型）对"10+ 字段一次性大填表"过度思考，把 max_tokens=8000 烧在思考阶段（finish_reason=length）→ 正文空回（40-60% 失败、慢 42-64s）。**轻 prompt 只缓解不根治**，拆成聚焦小子任务 reasoning 骤降（228~1414 字）→ ~100% 成功。
2. **plans=0 根因**：需求点名 Intel 平台 AI 机型，目录里 AI 机型全是 Orion（AMD）→ select_models 按 series 硬过滤返 0 → 白等 4 分钟没方案。
3. **编排层浪费**：每步都调一次 LLM 决策"下一步跑哪个节点"（~10 次 × ~8s），拓扑已确定时纯属重复劳动。

### ① 理解节点 agent 化（分步子任务，可配）
- `UNDERSTAND_STEPS_DEFAULT` 4 个子任务：类型/系列/形态 · CPU/内存 · 硬盘/GPU · 网卡/电源/RAID，每步 3-5 字段、prompt 聚焦、领域知识按 kind 注入（`build_domain_knowledge_map` 按需检索）
- 并行执行（`parallel_sub_steps` 默认开）→ understand 从 78s+空回降到 **~9s 稳定**；子任务失败单独便宜重试（`sub_step_retries`），仍失败只丢该子字段、交反问，不再整表失败
- 开关：`split_steps` 总开关 / `steps.{key}.enabled` / `parallel_sub_steps` / `sub_step_retries`（understand 节点抽屉全可配）；`split_steps=false` 走 legacy 单次填表
- 实测：8-GPU 需求 4/4 子任务成功，正确抽出 类型/GPU×8/内存×16/盘3

### ② 选型多级放宽（A 方案，非硬编码）
- 接上 model_reason 抽屉里**早已存在但未实现的 `fallback_order`**（exact→same_series→same_form→all，用户可配）：严格条件无货时按配置逐级放宽
- `select_models` 每条候选带 `match_stage` + `fallback_note` 白盒说明（数据驱动：如"库内无 Intel 平台 4U 全匹配机型，已放宽【平台系列】，按最接近给出候选"）
- 规则路径（run_select_baseline_rule）与 LLM 工具路径（_tool_select_models）同源生效

### ③ model_reason 短路（可配）
- `skip_react_when_model_missing`（默认开）：需求点名了不在在售目录的具体机型（机型代码特征检测，`model_missing_token_pattern` 可配）→ 跳过注定失败的 ReAct，直走规则降级 + 白盒说明（实测 model_reason 15.9s→0s）

### ④ 混合脊柱编排（LLM 只做决策，规则跑腿）
- `_needs_llm_decision` 门控：信息明确（clarity=explicit）且无异常 → 按拓扑序确定性跑，不为"下一步"反复调 LLM；只在 信息不足/选型落空/收尾总结 这些真正需要判断的点让 LLM 介入
- 编排 LLM 决策 ~10 次 → 0-2 次；保留反问（llm_ask）、重跑选子集（_decide_retry_targets）、终局总结

### ⑤ llm_audit 升级独立 judge（防同模型自批判塌缩）
- 独立裁判人设 + 规则硬校验结果（audit_plan）作为事实喂入 + 每条要求引用需求依据 + confidence（0-1）
- 规则判通过但 judge 认为有意图级问题必须明确指出；judge 与规则冲突可采样人工评级（llm_trace）

### ⑥ 执行预算（0.1.49 补充）
- orchestrator `budgets`：墙钟/步数/工具调用/反问轮数，抽屉可配；超限自动停止反问与 LLM 决策、按确定性链收敛（实测 240s 耗尽后正确线性收敛）
- 每步广播 `plan_progress`（剩余计划 + 预算用量），plan_preview 可配

### 实测（8-GPU 需求：WA5480 G3/2×Intel 6530/8×RTX 5090/16×64G/盘/25G/4×2700W/RAID）
| 阶段 | 基线 | 现在 |
|---|---|---|
| understand | 78s + 空回 | ~9s，4/4 子任务 |
| model_reason | count=0（series 硬过滤） | count=4（多级放宽 + 白盒说明） |
| 方案 | plans=0 | plans=4（Orion/Polaris 4U） |
| 总耗时 | 258.5s 无方案 | **70-95s 出方案** |
| 模糊需求「我要一台服务器」 | — | 20.5s 反问"工作负载？"（真实选项+why） |
| 中等需求「2U 通用 EPYC 64G*16 2*960G 预算20万」 | — | 51.4s 直接出方案 ES22V3-P |

### 验证
- 后端全量 pytest **464 passed**（1 deselected：既有数据依赖 test_raid_applicable_orion_default_9540，配件库无 9540，与本次无关）；前端 vue-tsc ✓
- 编排测试改为 hermetic（stub `_dispatch`，不再碰真实 LLM，20 tests 17s）
- 新增单测：分步/限长/few-shot 限量/预算/judge 事实注入/select_models 多级放宽/model_reason 短路（+32）
- ⚠️ 未提交（历阶段累积，用户未让 commit）

---

## [0.1.49] - 2026-08-09 — 需求分析编排优化：编排配置节点 + 方案自检节点 + 结构化记忆 + 延迟优化（全部可配，不黑盒）

### 背景
对照主流 agent 架构评估（ReAct / Orchestrator-Workers / Graph / Reflection / HITL）：架构方向达标；短板在「编排行为是黑盒、无显式计划、多轮记忆靠文本、端到端延迟高」。用户拍板：P1-2（结构化记忆）+ P1-3（延迟优化）+ P2-4（执行中自检），且全部做成画布可见可配置。

### ① 画布新增「编排配置」节点（orchestrator，不执行，只提供配置）
- **AI 增强预算**：省时间(快=ReAct 3 轮+校对纯规则) / 均衡(默认=4 轮+LLM 校对) / 最优(6 轮+LLM 校对)——控制 model/kp 的 ReAct 轮数与 llm_audit 是否走 LLM，预算优先于节点种子默认
- **结构化记忆**：跨轮续接把「已确认槽位/缺口/场景/候选/已完成」摘要喂回编排 agent（`_state_summary` + 会话持久化 `orchestrator_memory_summary`），对话文本只作补充；摘要开关/字段/对话保留轮数可配——解决"多轮反问后忘记早期确认"
- **推进策略**：确定性能力并行（默认关；链式图一次只就绪一个、无收益，分叉图才有；DAG 保证并行能力互不依赖，无竞态）
- 未画该节点时用默认值（均衡），零配置即可用

### ② 画布新增「方案自检」节点（result_check，确定性，画布可见）
- 与「规格合规校验」分工：spec_compliance 查配置是否符合目录/兼容规则；result_check 查方案有没有缺漏/自洽
- 检查项可勾选：方案非空 / 核心件齐全（CPU/内存/盘）/ 数量合理性（配 GPU 有供电线、有内存条）
- 失败处理：仅标记需修改 / 自动触发确定性重跑（compose→预算→自检，重建脊梁强制保留，LLM 不可跳过）
- `_dispatch` 支持 + orchestrator 派发，两条执行路径（方案助手/画布试运行）通用

### ③ 延迟优化实测
- 同需求「2U 通用 32G 2×1T」：**quality(6 轮≈原默认) 246s vs balanced(4 轮·默认) 126s，约快 49%**（含审计重跑差异，样本级）
- 三项核心逻辑均有自检：模拟对话 3 场景（模糊→反问→续接出方案 / 详细一键出方案含自纠重跑 / 闲聊引导）全部通过，result_check 集成 passed

### 验证
- 前端 vue-tsc + 60 测试 ✓；后端全量 pytest 421 ✓（orchestrator/agent/audit/spec 相关 52 先跑）
- 浏览器实测：palette 出现「编排配置」「方案自检」，抽屉表单可配
- 未改 active flow（13 节点/13 边不动），新节点从 palette 拖入即生效

 - 2026-08-09 — BOM 模板配置说明：拒绝黑盒，行/规则/模板分类三处可查

### 背景
用户反馈 BOM 模板"只有配置没有说明"：每一行要填什么、根据什么配件填充、内容来自哪里完全靠猜；不同服务器（2U/4U、直连/Switch）模板格式不同，但没人解释为什么。

### ① 基准配置页文档入口（BomTemplateManager.vue）—— 单一数据源
- 「新建模板」旁新增「📖 模板说明」按钮 → 抽屉，**实时拉取文档库《BOM 模板配置指南》（module=selection）用 MarkdownView 渲染**；每次打开同步最新，用户在文档库编辑后此处自动变化
- **不维护第二份拷贝**：删掉上一版硬编码的行类型/模板分类/规则 kind 常量（约 130 行）；文档被改名/删除时抽屉给兜底提示

### ② 文档库完整指南（唯一内容源，用户可编辑，v2）
- `docs/策略中心/02-选型配置域/BOM模板配置指南.md` → 已发布至「策略中心 → 选型配置 → 📄 文档库」（操作指南）
- 含行类型速查（11 种）/ 模板分类差异 / 规则 kind 速查 / 常见问题；kind 中文名随界面术语同步（模板拼接/取料号字段/按结构自动生成…）

### ③ BOM 模板编辑大改版：降门槛 + 表格化 + 实时预览（用户主导，BomTemplateManager.vue / BomRuleSourceEditor.vue）
- **从现有模板复制**：新建时可选择已有模板（2U12标准/4U8-GPU直连/4U8-Switch），整份行骨架+规则带入，改名即用
- **新行默认规则自动填充**：按行类型带推荐规则（heatsink→取料号/料号数量、cable→配置 cable_desc/固定 1…），保存即合理，⚙ 从"必做"变"进阶微调"
- **行列表表格化 + 列头**（# 行类型 左栏标签 槽位/形态 解析规则 操作）；规则列显示摘要（不开 ⚙ 也懂：`料号 heatsink.name / 料号数量 heatsink`），点摘要展开精细编辑
- **实时预览**：编辑弹窗底部用演示数据跑求值引擎，随编辑刷新每行"规则解读 + 效果示意"（标注演示数据）
- **控件自解释，去掉小字**（BomRuleSourceEditor 重写）：
  - kind 下拉大白话：固定文字/取料号字段/模板拼接/按结构自动生成/取配置参数/手动填写（存储值不变）
  - 料号品类 category 从下拉选（heatsink/fan/rail/backplane/psu/cable），不再自由输入
  - 模板拼接：点选「插入变量」下拉（中文标注）自动插入，输入框下实时渲染预览（`${bays}*3.5 ${bp_type_desc}` → `24*3.5 SATA/SAS/NVMe`）
  - 结构计数 scope 按行类型限定（io_slot 行只给 riser 选项、rear_summary 行只给汇总选项）
- 行类型下拉分「系统自动计算 / 需人工填写」两组，选项带中文说明
- **修复**：行类型下拉选项为空（`a-select-optgroup` 组件名写错 → 改为 `a-select-opt-group`，下拉分组+选项正常显示）
- **布局**：编辑弹窗改左右两栏（modal 860→1120px）——左栏行骨架表格、右栏实时预览，顶部对齐、预览独立滚动
- **预览可读性**：右栏预览从三列挤排改为卡片式——每项「行标签 + 效果示意」同一行（space-between）、规则解读在下方一行，窄栏下不再挤压
- **预览对齐工作台左栏**：实时预览改为与工作台 BomTable 一致的 L6 配置单表格（Catalogue/Description/Qty 三列 30/58/12%、表头 sticky、空值显示 [空]、空行隐藏）——视觉统一，宽度按工作台左栏同等列宽分配
- 联网核实差异依据：2U=通用平衡（≤4 张 L40S 级风冷 GPU）；4U=全高 PCIe+多 GPU+大风道；Direct=点对点直连（省线缆）vs Switch=NVSwitch 全互联（训练场景，需背板/更多线缆/常配 RAID）

### 验证
- 前端 vue-tsc -b ✓、node --test 60/60 ✓；后端 pytest 421 全量 ✓

 - 2026-08-09 — 需求分析「配置体验优化」：装修减负 + 数据自愈 + 试运行交互

### 蓝图落地（`docs/策略中心/02-选型配置域/需求分析配置体验优化-蓝图.md`）
- **P0 信息架构**：节点元数据统一到 `utils/reasoningNodeMeta.ts`（中文名/职能/来源/图标/分组，palette/节点卡/抽屉共用真源）——修复 10 个新节点在画布上职能说明为空的旧问题；palette 搜索/拖拽添加/已用角标/空态引导；节点 label 去英文后缀（时间线/弹窗用中文名）
- **P1 画布交互**：网格吸附（snap-to-grid）、自动布局（按边拓扑分层，零依赖手写）
- **P2a 抽屉减负**：4 处 JSON 文本框 → 可视化表格编辑器（char_fixes / noise_patterns / cpu_mem_type_rules / category_aliases），业务用户不再手写 JSON
- **P2b 该删的删掉**：清理 8 个 palette 已无法添加的旧节点分支（normalize_input / slot_validate / confirm / llm / llm_understand / llm_agent / 独立 ask_user / 独立 clarity_check / scene_analysis）——模板 + buildConfig + 相关 refs 全删，抽屉 1374 → 1117 行
- **P2c 试运行交互式反问**：暂停反问时给选项按钮 + 回复输入 + 继续，模拟客户回复拼进需求文本重跑（forceComplete=false 保持可继续反问），页面内走完完整对话流；加快速样例下拉（模糊/中等/详细/闲聊）

### 设置-AI设置「会话记录」管理（回收站 + 历史数据清理）
- **背景（用户反馈）**：方案助手会话删除是软删除，消息/推理状态/反馈样本/调用痕迹只增不减，数据越堆越多
- **功能**：AI 设置新增「会话记录」tab——统计（总会话/回收站/消息总数）、会话表格（全部/正常/回收站筛选，标题/创建人/消息数/最后活跃/状态）、操作：查看（只读消息）/ 删除（进回收站）/ 恢复 / 彻底清除（物理删消息+状态）
- **历史数据清理**：LLM 调用记录（保留最近 N 天）+ 需求反馈样本（保留最近 N 条/清空），删除不可恢复
- **后端**：`GET /threads?scope=all`（管理员含回收站+消息数）、`POST /threads/{id}/restore`、`DELETE /threads/{id}?hard=1`（物理删）、`POST /admin/cleanup/trace|samples`（rules schema 走 Rules_SessionLocal 遵守 schema 隔离）
- 验证：前端 vue-tsc/测试/构建 ✓；后端全量 421 ✓；端点冒烟（清理 365 天/10000 条=0 无害、恢复/硬删不存在会话=404）

### AI-first 容量匹配：理解交给 AI、规则可配置（盘/内存/GPU 显存）
- **根因（用户实测）**："1T以上的硬盘" → LLM 照抄 capacity="1T以上" → 归一函数不认 → 盘需求被静默跳过 → 方案零硬盘 + 审计误报
- **契约反转（AI 干理解的活）**：drives/memory/gpu 槽位新增 `capacity_gb`/`per_stick_gb`/`capacity_gb`（数值）+ `comparison`（gte=以上/至少，lte=以下/最多）；两个理解 prompt 加示例（"1T以上"→1024+gte、"一tb/一t/1tb"→1024、"48G以上显存"→48+gte）。AI 把千变万化的自然语言归一成数值，不再靠正则枚举词
- **规则可配置（kp_reason 抽屉·匹配参数）**：新增「容量匹配策略」（容差近似/严格下限≥需求）+「容量容差 %」（默认 10）；AI 识别出 gte/lte 时自动按严格语义执行，不受默认策略影响
- **匹配器消费**：`_drive_spec_substitute`（盘）支持 comparison/strategy/tolerance；`_pick_mem_groups`（内存）按单条容量过滤；`_pick_gpu_groups`（GPU 显存）支持纯显存组（无型号）+ comparison/策略过滤——"48G以上显存"→ 选 ≥48G 件
- **实测**：①"兆芯+1T以上硬盘"→ comparison gte → 配出 1T NVMe（1024G），不再 960G；②"AI 服务器+2张48G以上显存"→ 配出 2× NVIDIA L20 48G；审计均 ok
- 测试：新增 ~12 个（盘 gte/strict_min/lte/容差、merge comparison 透传、GPU 显存过滤/纯显存组），后端全量 **421 通过**（412→421）；前端 vue-tsc + 60 测试 ✓

### 方案A：画布试运行改流式（完成一步显示一步）
- **根因**：试运行原为「同步 HTTP 一次性跑完 + 前端 setTimeout 快速回放」——后端含 LLM 单步 20~40s、13 步总耗时 1~3 分钟，期间前端干等，跑完才 3 秒内一口气列完所有步骤（用户反馈「等好久突然一口气列出」）
- **改法**（复用方案助手 WS 基建，不另起炉灶）：后端新增 `POST /test-run/start`（只注册 run_id，**首个 WS 订阅者连上后才启动后台任务**，杜绝漏掉首个 step_start）+ `WS /test-run-ws/{run_id}`（复用 `assistant_hub` 房间）；前端 `useTestRun` 从 HTTP 回放改为 WS 实时驱动——`pipeline_start` 预置全部步骤 pending → `step_start/step_done` 逐个亮起 → 终态带 ext/kp_by_model/plans/awaiting_input
- **实测**：真机跑通——`pipeline_start`(0s) → 需求理解 running → 29.7s 完成 → gap/llm_ask/scene/model(37.5s)/kp(123s)/…/review → pipeline_done，步骤逐步到达；`need_input`/`candidates_ready` 照常（P2C 交互反问不受影响）；旧 `/test-run` 端点保留兼容
- 验证：前端 60 测试 + build ✓；后端 412 全量 ✓

### 修复（真 bug，非装修）
- **💡 连线全损坏 + 弹窗风暴根因**：VueFlow 的 `isValidConnection` 会对**加载的每条边**也跑校验（`createGraphEdges`），查重函数用 `edges.value.some(...)` 时边还在列表里 → 每条边把自己判成「重复」→ 全部丢弃 + 刷「已存在相同连线」。修复：校验移到 `onConnect`（只在手动连线时），加载的边原样渲染
- **💡 active 流丢边自愈**：v12/v13 图重建时旧边引用旧节点 id 被过滤、新边未回填 → active 流 13 节点 0 连线（画布全节点「孤立」、编排器退化为无依赖平坦链）。新增 `migrate_v14_restore_default_edges`（幂等，启动自愈：默认节点集 + 0 边 → 恢复 v11 链），已修复线上数据
- 抽屉保存修复：extract / spec_compliance / audit_fix 三个节点之前不在 CONFIGURABLE → 保存按钮不出现（表单能编辑但存不进去），已补
- scene_decide 抽屉里「场景映射 JSON」是死配置（buildConfig 不保存）→ 删
- `ReasoningNodeKey` 类型补全 extract/spec_compliance/audit_fix；model_reason 也加载推荐策略（原只在 select_baseline 时加载 → 下拉为空）
- 非 condition 边的 source_handle（缺口/足够/答完回理解）VueFlow 找不到 Handle 不渲染 → 加载时归一到默认出口

### 🔄 撤回/纠正（去「屎山」层）
- 移除 persist 防误擦/防污染守卫全套（lastLoadedGraph / edgeDeleteIntent / lastReloadToast / applyFlow / 弹窗限频）——层层补丁产物，persist 回到「编辑即保存」；数据保护交给后端幂等迁移
- 移除「孤立未连线」黄色警告条、连线校验弹窗（其引入的 bug 已修复，校验不再需要）

---


### B：反问选项锚定产品目录（根治「问塔式但我们没有塔式」）
- **形态白名单从目录派生**（`capabilities._catalog_whitelist`）：forms 取目录机型的 `form` 字段（真实在售形态，去重），目录空才回退常量——系统里有什么形态就问什么
- **空选项兜底**（`_catalog_fallback_options`）：LLM 选项全被白名单过滤（如只给塔式）→ 按缺失项从目录给合法选项（形态→forms / 类型→types / 系列→series），反问永远带真实在售选项
- **委托选项放行**：不确定/你推荐/随便 这类选项保留（AI 开与 AI 关目录引导一致，客户随时可把决定权交回系统）
- **删死配置 `use_catalog_options`**：后端逻辑从不读它（白名单过滤是硬保证不是可选开关），误导性配置按「该删的删掉」移除（默认配置 + 画布抽屉 + 存量 DB 键）；`_LLM_ASK_PROMPT` 去掉硬编码形态表（形态由 user 消息动态给）
- 验证：`tests/test_llm_ask_catalog.py` 9 用例（塔式过滤 / 空选项兜底 / 委托保留 / 形态派生 / 回退）
- **形态来源修正（2026-08-09 追问「目录加形态 AI 会自动加吗」发现）**：机型自身无 `form` 列，真实来源是 `l6.base_configs.form`（当前目录实际只有 2U/4U）。此前 `_catalog_whitelist` 读 `m["form"]`（空）→ 回退硬编码常量 `1U/2U/4U/5U/6U/8U`——**反过来会反问目录里没有的 1U/5U/6U/8U**。已改为读 `base_config.form`（顶层 form 兜底），目录加形态（如新增 3U 基准配置）→ 白名单/AI 反问自动出现（已实测）

### C：审计意见喂回编排 agent（自纠有 LLM 参与，仍受确定性红线约束）
- 新增 `_decide_retry_targets`：audit_fix 检出问题后，把审计意见（llm_audits/spec_issues）作为 observation 喂给编排 agent，由它决定**可选重跑项**（llm_audit 再审 / audit_fix 再自纠 要不要）
- **重建脊梁强制保留**（kp_reason→spec_compliance→compose→budget_check，retry_scope 子集配置驱动）：修复的确定性后果，LLM 不能跳过、不能改数据、不能提前 final
- `_retry_mode` 重跑链改为**只跑目标能力**，跑完退出恢复正常 LLM 编排（不越跑、不提前 final）；AI 关/LLM 失败 → 全量重跑（现状兜底）
- 修复真实调用问题：prompt 缺 "json" 字样导致 json_object 格式被 API 拒（400），已补
- 验证：orchestrator 新增 4 用例（脊梁保留/越界丢弃/失败兜底/重跑模式只跑目标后恢复）；真实 LLM 实测——AI 服务器缺 GPU 场景，LLM 决策只重跑脊梁、不再重复审计（符合预期）

---

## [0.1.45] - 2026-08-09 — 编排器读画布拓扑（A 方案）：能力链不再硬编码

- **背景**：Graph Orchestrator 的能力清单/依赖是代码硬编码（`CAPABILITIES` 11 步链），执行只读 `node_configs`，**不读画布图的 nodes/edges** —— 用户在画布上改图对执行无感（「画布改了没反应」根因）
- **图 → 编排器**（`reasoning_orchestrator._derive_capabilities`）：从 active 流画布图实时派生能力链（拓扑序）
  - 节点分类：能力节点（type 有后端 handler）/ `llm_ask`（反问动作）/ `extract`（AI 失效兜底）/ `condition`（透明桥，入边源→出边目标直连）
  - deps = 过滤后的直接前驱能力节点；边 handle/condition 不参与（能力池全执行、LLM 选顺序）
  - 图缺失 / 能力 DAG 成环 → 兜底默认链（由 DEFAULT_GRAPH_V11 种子图经同一套推导函数算出，非第二份硬编码拓扑）
- **确定性红线去硬编码**：`deterministic` 移到节点配置（画布抽屉开关），默认 = 原硬编码集合（spec_compliance/compose/budget_check/audit_fix/review）；编排 prompt 的动态红线清单从配置读
- **按 type 派发**：`_dispatch` 传节点 type 而非 id（用户加第二个同类型节点如 `model_reason_2` 也能真正执行）
- **配套修复**：`_VALID_NODE_KEYS` 补齐 v12 key（此前 understand/model_reason/… 抽屉保存会 400）；新增 `migrate_v13_cleanup_orphan_configs` 清理图里已不存在的孤儿配置（cond_gap/ask_user 残留）
- **验证**：新增 6 个图派生单测（v12 图=兜底链逐节点一致 / 改图跟随 / condition 透明桥 / 成环兜底 / 空图兜底 / 确定性配置驱动）；实验：model_reason 拆两个节点 → 编排器按新图执行且真正出结果；后端全量 399 通过、vue-tsc ✓、npm test 60 ✓

---

## [0.1.44] - 2026-08-08 — 智能体 search_cases 案例检索升级：字符 2+3-gram + TF-IDF 加权（A 方案）

- **背景**：CBR 案例检索原为裸字符 2-gram 集合重合——英文词（GPU/NAS）被拆成噪声 2-gram、长需求因字多天然得分高（长度偏差）、每条都有的「服务器/机箱」淹没「深度学习/训练」等有区分度的词
- **方案**（`case_provider.py`，零依赖，不引 jieba / rank_bm25 / Whoosh / 向量库）：查询与案例需求先归一化（小写、去空白标点，只留 CJK+字母数字），取字符 2+3-gram；IDF=log((N+1)/(df+1))+1 平滑加权，案例/查询向量=(1+log tf)×idf，TF-IDF 余弦相似
- **行为**：3-gram 保英文词与中文短语；罕见有区分度的词由 IDF 放大；余弦消掉文档长度偏差；标签命中仍各 +0.3 加权（tags_keyword 默认模式，tags / keyword 两种旧模式保留）；案例库长大再走 ExternalRagProvider（向量检索）
- **验证**：新增 `tests/test_case_provider.py` 9 用例（归一化 / gram 计数 / TF-IDF 排序 / retrieve 排序含 mock session）；真实案例库 6 条对比——AI/GPU 查询命中 AI·8卡GPU 案例、不再被长文本通用 2U 案例压过；`test_nic_qty_binding` 端到端 3 个改为注入假 baseline（不再依赖 select_models 从文本猜机型，与 extract 收窄新语义对齐）；后端全量 393 通过

---

## [0.1.43] - 2026-08-08 — 基准配置「机箱能力约束」可配置化（PSU 档位 / CPU·内存上限 / 每路通道数）

- **背景**：对照 ES22V3-P 用户手册（AMD 9004/9005、24 DIMM DDR5、PSU 仅 1300/1600/2000W），发现 PSU 推断可能产出机型不支持的 2700W、CPU TDP 表缺 9005 500W、内存/CPU 数量无上限校验、内存选型按 Intel 8 通道启发式（EPYC 应为 12ch/路）——均为硬编码/黑盒
- **基准配置新增 4 个可配能力字段**（`l6.base_configs`，机箱能力卡可配、缺省走全局兜底，拒绝硬编码）：
  - `psu_wattages`（JSONB）：允许的 PSU 瓦数档位，如 ES22V3-P=[1300,1600,2000]；空=不限沿用全局
  - `max_cpu`（默认 2）、`max_dimm`（默认 24）、`mem_channels`（默认 12，EPYC 12ch/路）
- **推理链路消费**（`candidate_search.py`）：
  - `_infer_psu_wattage` 结果收敛到机型档位（`_clamp_psu_wattage`：取 ≥ 推断值的最小档，超上限取最大档）
  - CPU TDP 优先读配件库 `specs.tdp`（9005 等新 SKU 在配件库配即可，不再改代码），型号表仅兜底
  - `_pick_memory_part` 目标条数按 `mem_channels × CPU 路数`、上限按 `max_dimm`（未配保持旧行为）
- **校验规则**（`compatibility_rule_repo` 默认规则 +2）：CPU 颗数超 `max_cpu`、内存条数超 `max_dimm` → `selection_alerts` warning（规则引擎 WHEN 支持 `config.max_cpu` 交叉寻址）
- **前端**：基准配置页机箱能力卡新增 PSU 档位（tags 多选）/ CPU 上限 / 内存上限 / 每路通道数输入；`chassisMeta.PSU_WATTAGE_OPTIONS` SSOT
- 验证：pytest 新增 7 用例（PSU 收敛/TDP 数据驱动/内存目标条数/超上限规则）全过；vue-tsc ✓；npm test 56 ✓；test_scene_analyzer 3 个图级失败为既有环境问题（stash 验证与本次改动无关）

---

## [0.1.42] - 2026-08-05 — 配件管理：分类移到顶部胶囊条，侧栏只留规格筛选

- **左侧栏瘦身**：分类列表（全部 + 各分类 + 计数）从 `category-sidebar` 上移到页头下方的分类胶囊条（`category-nav-bar`）；「管理分类」入口移到胶囊条右侧齿轮按钮
- **侧栏只留筛选**：侧栏 `v-if="hasSelectedCategory"`，仅渲染 Brand + 规格维度折叠组；未选分类时侧栏隐藏、内容区全宽；选中分类但无筛选维度时显示提示
- 复用此前预留的 `cat-chip` 胶囊样式，修正其 hover 依赖的未定义 token（`--cpq-overlay-a6` → `--cpq-overlay-a8`）
- **筛选交互改列表勾选**：左侧筛选从胶囊 chips 改为「勾选框 + 名称 + 计数」列表（勾选框在左）；点行文字 = 单选切换（该维度只看这一个值，再点一次取消），点勾选框 = 多选累加/取消，不再点一下误选；「已选」横条（搜索栏下方）整条删除，清空入口移到侧栏「筛选」标题行右侧
- **筛选列表不再重排**：去掉「已选优先显」排序，勾选/点选后列表保持原有顺序、选中项原地高亮，不再跳到首行
- 验证：vue-tsc ✓


## [0.1.42] - 2026-08-05 — 配件管理：分类移到顶部胶囊条，侧栏只留规格筛选

- **左侧栏瘦身**：分类列表（全部 + 各分类 + 计数）从 `category-sidebar` 上移到页头下方的分类胶囊条（`category-nav-bar`）；「管理分类」入口移到胶囊条右侧齿轮按钮
- **侧栏只留筛选**：侧栏 `v-if="hasSelectedCategory"`，仅渲染 Brand + 规格维度折叠组；未选分类时侧栏隐藏、内容区全宽；选中分类但无筛选维度时显示提示
- 复用此前预留的 `cat-chip` 胶囊样式，修正其 hover 依赖的未定义 token（`--cpq-overlay-a6` → `--cpq-overlay-a8`）
- **筛选交互改列表勾选**：左侧筛选从胶囊 chips 改为「勾选框 + 名称 + 计数」列表（勾选框在左）；点行文字 = 单选切换（该维度只看这一个值，再点一次取消），点勾选框 = 多选累加/取消，不再点一下误选；「已选」横条（搜索栏下方）整条删除，清空入口移到侧栏「筛选」标题行右侧
- **筛选列表不再重排**：去掉「已选优先显」排序，勾选/点选后列表保持原有顺序、选中项原地高亮，不再跳到首行
- 验证：vue-tsc ✓

## [0.1.41] - 2026-08-04 — IO/Riser 数据补齐 + 基准配置编辑器补 UI + 防简介保存清字段

- **IO 空根因**：ZS22V2-P 基准配置（bc 20）`config_content` 只有测试残留（`{"spec_diff":"22222","description":"123123"}`），没配 `standard_riser`/`riser_x16` → 模板 eval 走"未配置留空手填" → IO1/IO2 空
- **bc 20 数据补齐**（Polaris 2U12 三模版）：`standard_riser={"IO1":"1*X16+1*X8 FHFL","IO2":"1*X16+1*X8 FHFL"}`、`riser_x16="1*X16+1*X8 FHFL"`、`standard_mem_speed="4800"`（技术员单口径；顺带清掉 UI 会显示的测试残留文案）
- **基准配置编辑器补 UI**：原页面只有 rear_slots（IO1-4 + 容量），`config_content` 无编辑入口（文档超前于 UI）→ 新增「IO/Riser 与内存速率」编辑区：各 IO 槽 `standard_riser`（按槽位 dict）+ `riser_x16` 升级规格 + `standard_mem_speed`；留空的槽不落库=手填；`ConfigContent` 类型同步扩展
- **修 clobber 坑**：ModelEditorPage 保存"简介"原来整体替换 `config_content`（只带 description/spec_diff）→ 会把 standard_riser 等字段清掉 → 改为合并保存（保留 riser/内存字段）
- 实测验证：该需求重跑 → IO1/IO2 = 1*X16+1*X8 FHFL、Memory = 32GB DDR5 4800（对齐技术员单）；pytest 282 · vue-tsc ✓ · npm test 56 ✓

## [0.1.40] - 2026-08-04 — 代码瘦身第一轮：删一次性脚本/死代码/死依赖（-4k+ 行）

- **一次性脚本 36 个（~3100 行）**：`backend/scripts` 45→9。删 migrate_*/seed_*/drop_*/clean_*/diag_*/update_bom_template_* 等已执行完的脚本；保留 6 个长期工具（replay_cases/simulate_requirement/online_verify/audit_reasoning_batch/strategy_insights/analyze_kp_data）+ 3 个被前端注释当同步契约的脚本（seed_pricing_strategies/seed_strategy_fields/migrate_base_config_capability）
- **requirement_check 死代码整段拆除**：0.1.36 已从流程删节点，本轮把残留全清——executor handler、linear fallback 调用、PIPELINE_STEPS 条目、`_VALID_NODE_KEYS`、默认节点配置、v6 迁移方法 + startup 调用、`check_plan` 全家桶（DEFAULT_CHECK_CONFIG/load_check_config/helper）+ 9 个对应测试、前端 RequirementCheck 类型/字段/IO 定义/步骤文案/节点抽屉表单；DB 清 30 条孤儿 node_config；`audit_plan`（review 校对）保留
- **死文件/死依赖**：`bom_similar.py`+test（experience_alerts 引擎，0.1.38 已下线，零引用）、前端 3 个零引用组件（ActivityStream/ShowcasePreviewModal/SelectionNode）、`selectionConfig.ts`（已删画布的配置）、`dagre.d.ts`+package.json 移除未用 `dagre` 依赖、旧 `scripts/_backup/` 6 个 BOM 模板备份
- **死常量**：`requirement_checker._PLATFORM_SERIES`（只定义未引用）
- **过期注释 3 处**：startup.py / ruleMeta.ts / bomRuleEngine.l6.test.ts 里指向已删脚本的引用
- **llm 占位节点拆除**：通用 `llm` 节点（role=extract_enhance）从未被任何流程图连接（34 个 flow 全无），其能力已被 extract 节点自带 enable_llm 增强取代 → 删 executor handler/默认配置/_VALID_NODE_KEYS/前端 palette/抽屉表单/IO 定义 + 2 个 dispatch 测试 + DB 32 条孤儿 node_config；extract/scene/review 三节点自己的 enable_llm 开关保留
- 验证：pytest 284（-18 测试：9 check_plan + 5 bom_similar + 4 其他）· vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归（BI 0 差异）

## [0.1.39] - 2026-08-04 — 国产 CPU 厂商分家：Polaris=兆芯，KH-50000 不再标"海光"

- **根因**：系统只有"系列"维度没有"芯片厂商"维度，Polaris 被当成"信创大杂烩"桶（兆芯+海光+飞腾+鲲鹏混装），"海光"又被当成 Polaris 代称 → 用户需求 `KH-50000`（兆芯开胜）被整条链路当成海光
- **口径定论（用户确认）**：Polaris 只配兆芯、Orion 只配 AMD；海光/飞腾/鲲鹏/龙芯不是 Polaris
- **改动（代码 + 配置双修）**：
  - 系列词表摘除海光/hygon：extract 节点 lex_series（默认 + active 流配置）+ scene_mapping series_hints（默认 + system_config）→ `KH-50000/兆芯/zhaoxin/开胜/开先` 独属 Polaris
  - CPU 平台过滤按厂商分家（candidate_search）：需求点名厂商 → 只留该厂商家族（海光需求绝不落兆芯 KH/KX）；只写"信创/国产"或平台=Polaris → 留兆芯家族；`_XINCHUANG_RE` 补"国产"；修中文前缀 `KH` 词边界不匹配问题
  - review 校对厂商感知（requirement_checker）：海光/飞腾/鲲鹏/龙芯需求不再提示"应为 Polaris"，海光需求配 Polaris（兆芯）也 blocked
  - 系列确认别名（requirement_intel_service）："海光"→Polaris 别名删除，只留兆芯/开胜/信创/国产
  - 前端 chassisMeta 常量 `REAR_SLOTS_2U_HAIGUANG` → `REAR_SLOTS_2U_POLARIS`（Polaris=兆芯）
- **验证**：pytest 298 · vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归；`KH-50000` 需求实测 → ZS22V2-P（Polaris）CPU=KH50000×2、事件零"海光"、audit ok；`海光` 需求实测 → 系列 None + 校对 blocked（Polaris 是兆芯不能替代海光）

## [0.1.38] - 2026-08-04 — experience_alerts 在线展示下线（案例库防偏差误报噪音）

- **用户实测**：ZS22V2-P（兆芯 KH-50000）需求被 `attach_experience_alerts` 拿 ES22V3-P（AMD）案例做规格级对照 → 跨平台满屏差异（CPU platform/HDD cap/iface/Memory speed/NIC/数量…）
- **处理**：review 节点不再挂 `experience_alerts`（案例库对照只保留在训练 bom_compare/重放），PlanCard 撤掉 experience_alerts 展示；在线"重大偏差"由 audit_plan 硬校验兜底（缺件/平台冲突/严重超预算）
- 方案卡最终只剩「校对通过 ✓ / 需修改：…」，零噪音警告
- 验证：pytest 290 · vue-tsc ✓；海光需求实测：requirement_check 不存在、experience_alerts=0、selection_alerts=[]、audit ok

## [0.1.37] - 2026-08-04 — 阶段 2：LLM 接入（extract/scene/review 三节点增强 + 节点级开关 + 槽位清单可视化）

- **LLM 三节点接入（每个节点抽屉独立开关 enable_llm && 全局「设置-AI 设置-启用 AI」双重约束）**：
  - extract：LLM 结构化抽取并入 extract 节点（`run_extract_enhance`，schema 收口 + merge 只补缺、规则赢、能力声明不产配置）；失败降级规则结果
  - scene_analysis：`run_scene_infer` 规则推不出系列时 LLM 从语义补推断（如 A800 8卡→Orion），明说/已定不动
  - review：`run_llm_audit` 语义校对（方案是否真满足需求意图），规则硬校验兜底；LLM 存疑 → status=review（需人工确认）
- **节点抽屉 UI**：extract/review/scene_analysis 抽屉顶部加「启用 LLM 增强」开关；llm 节点保留（通用）
- **槽位清单可视化**：新增 `SlotListEditor.vue` 放 clarity_check 抽屉（编辑全局 `requirement_slots`：L0/L1/L2 层级 + label + default_ok + 反问阈值），替换已弃用的信号规则编辑
- **降级验证**：extract enable_llm=True 但 LLM 未配置 → chat_json 失败 → 静默降级规则，不阻塞主流程
- 验证：pytest 290 · 前端 vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归

## [0.1.36] - 2026-08-04 — 需求分析流程重构（R29）：槽位覆盖度 + 系列确认 + AI 统一开关 + 删差异报告

- **删 requirement_check**：在线「需求核对差异报告」实测警告泛滥（把库缺口/替代/措辞全当警告）→ active flow 移除节点 + PlanCard 撤警告行；`bom_compare`/重放（训练对照）保留
- **明确度=槽位覆盖度**：`requirement_slots` 期望清单可配置（L0 底线[场景/系列/CPU/内存]/L1 重要[形态/GPU/网卡]/L2 推导[RAID/电源]），`evaluate_slot_coverage` 按已填槽位差距判 explicit/partial；存储 default_ok（缺了给默认盘），AI 场景缺 GPU 反问
- **系列确认 confirm_series（新节点）**：scene_analysis 输出 `series_source`（explicit=需求明说 / inferred=系统推断）+ `scene_determined`；cond_scene 判据改 `scene_determined`；推断系列→问「是否 XX 系列？」，推不出→列在售系列选，明说/已确认→直接选型；答复（是/不是/系列名/平台别名）解析持久化 `requirement_confirmed_series`
- **review 改校对**：`audit_plan` 阻塞式 通过/不通过 + 必改项≤2（缺 CPU/内存、信创需求配非信创、严重超预算），挂 plan.audit，PlanCard 展示「校对通过 ✓ / 需修改：…」
- **AI 统一设置**：`llm_config.enabled` 全局开关（设置-AI 设置-API 设置「启用 AI」），`llm_client.stream_chat/chat_json` 统一 gate + `is_llm_enabled()`；关闭后所有 AI 能力走规则/不调 LLM，llm 节点双重开关（节点 enable_llm && 全局）
- 验证：pytest 290 · 前端 vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归（BI 0 ✓）

## [0.1.35] - 2026-08-04 — ESA24V3-P（4U）首测：RAID 显式型号分组 + NIC SKU 归一 + PSU 冗余数量

- **RAID 显式型号分组（R28）**：需求逐行给阵列卡型号（`RAID卡：LSI 9560 16i 8G缓存 *1`）→ `_extract_raid_groups` 归一 `9560-16i` 按组精确出件（不再泛配 9540-8i）；stage-1 跳过 RAID 组 token（含完整型号串，修 BI/LLW 回归），无型号（RAID 0,1,10）交回 I22 applicable 兼容选件
- **NIC 型号归一**：`X710DA2BLK` 去 BLK 后缀 → 命中库件 `Intel X710-DA2` 含光模块（原选国产无光模块件）；连字符归一放匹配侧（保留 ConnectX-6 形态）；`光口含模块/含模块` 识别为光模块信号
- **PSU 冗余数量（R28）**：`2700W 2+2/3+1冗余` → 4 个（N+M 求和；原按「冗余=双电源」出 2）；4U 8 卡机电源 2700W×4 对齐技术员单
- **噪音过滤**：`TDP360W`（CPU TDP 连写）不再当型号 token 报 unmatched
- **新案例入库**：ESA24V3-P · HK-2026-0707（4U8-Switch，model_id=16 / bc25 / tpl3），校对 BOM 以技术员单为准；待确认：GPU A800 需求 ×2 vs 技术员 ×8、Switch 行 `3*X16` 口径、L6 文案 KH50000 vs AMD 实配
- 验证：pytest 283 · 重放 5 案例（BI 0 差异 ✓ / ESA24 3 [GPU业务+2库缺口] / YLL 1 / YC 1 / LLW 3 已知）

## [0.1.34] - 2026-08-04 — IO/Riser 配置经验沉淀 + 对照引擎 riser 内容级比对

- **riser 数据驱动落地（R25/R26/R27）**：`config_content.standard_riser`（默认，per-slot dict、大小写不敏感）+ `riser_x16`（GPU/100G 升级）；未配置留空手填，零硬编码。ES22V3-P 三连版=满配 `1*X16+1*X8 FHFL`、直连版=预算 `1*X8 FHFL`（对上 LLW/BI/YLL 技术员单）
- **对照引擎新增 riser 内容级比对**：行数一致时比槽位规格（`_riser_signature` 归一，`2*X8` vs `1*X16+1*X8` 报 l6 差异；FHFL 形态词/槽位顺序不算）→ 重放立即抓出 YC IO2=2*X8 缺口（待更多样本定 per-slot 覆盖）
- **经验与规则入系统**：文档写入「策略中心-选型配置-📄文档库」（`rules.policy_docs` module=selection，操作指南「IO 与 Riser：配置经验与填充规则」）——联网调研 + 4 案例实证 + 填充规则 + 改哪里
- **Riser 配置优先级文档**：文档库新增操作指南「Riser 配置优先级：系统自动填充规则」（sort_order=4）——系统自动填充 IO1/IO2 的可执行优先级（GPU→全槽 riser_x16 / 100G+ 网卡→IO1 riser_x16 / 否则 standard_riser / 未配置留空手填）+ 实测输出表 + 数据改哪里
- 验证：pytest 277 · npm test 56 ✓

## [0.1.33] - 2026-08-03 — 需求分析收尾：意图感知开场白 + 完整清单直接出 BOM + 推理 BOM 完整性

- **对话更聪明**：意图感知开场白（你好→问候 / 我要服务器→问用途 / 贴规格→识别）；"你帮我推荐/你定"= 全局授权直接出方案（区别于"还没定"只跳当前字段）；负载原型按原文匹配（最近补充 > 全文 > usage），修"数据库/OLTP"被 server_type 词表折叠后错配"通用/Web 业务"；删开场白"现成配置清单"引导（已贴清单还问清单=荒谬）
- 💡 **完整配置清单直接出 BOM**：clarity 新增 4 规则（品类≥4+内存/型号→明确、型号token≥3→明确、品类≥3+内存+用途→明确）；无规则命中兜底改按信号推导缺口（修"请补充需求描述不够具体"假死循环）
- **推理 BOM 完整性**：`buildPlanCfg` 接料号库后面板数据——IO1/IO2=1×X16+1×X8、OCP=X8、按 KP 盘型推线缆（SATA/SAS÷8、NVMe÷2，镜像 CRE）、NVMe→背板 tri；模板 Cable 行 manual→推导（改动已备份 `backend/scripts/_backup/bom_template_1_20260803.json`）
- **内存解析**：`DDR564G*8`=DDR5-64G×8=512G（原把代际"5"算进容量→564G→9 条）；`_extract_mem_signal` 加代际剥离 + 单条×条数
- 验证：pytest 92 · `npm run build` ✓ · `npm test` 48 ✓

## [0.1.32] - 2026-08-02~03 — 需求分析对话机制（反问修复+负载引导+会话重置）

> 合并原 0.1.39 / 0.1.40 / 0.1.41 / 0.1.42 / 0.1.43 / 0.1.44 六条。
- **反问三连修**：① cond_clarity 阈值写反（只对 unclear 反问、partial 放行）→ 改非 explicit 都反问；② 补充不累积"没记性"→ `requirement_clarity_base/supplements` 跨轮持久化；③ round 跨会话不重置→重新生成报价=新对话重置 round=0（清理 3 存量卡死商机）
- `model_token_in_category` 原失效（"EPYC9354"不含"CPU"）→ 型号→品类关键词表；extract 加 `usage_inferred` 区分"用户明说/系统兜底"
- 死循环防护：轮次上限 3→6；修 R-22 编辑事故（赋值行丢失→NameError→假死循环）+ 防回归测试
- **Spec Assistant 式引导**：新规则类型 `workload`（6 负载原型 + drill_down 追问树，策略中心 ask_user 节点可 CRUD）；首轮抛负载菜单、选 AI→问 GPU；`_field_satisfied` 防跨轮重复问
- **M1 会话语义**：`_merge_clarify_text` 新对话清空旧补充（修"重复上一轮"）；一次一问 take=1；"不确定/你推荐/还没定"=已答只跳当前字段；推理面板「🔄 重新开始」按钮
- LLM 预留（不接，离线可跑）：llm 节点 passthrough + `chat_json()` 桩（extract_enhance / question_gen / best_fit 三 role）

## [0.1.31] - 2026-08-02 — 需求→BOM 引擎校正（训练循环）

> 合并原 0.1.33 / 0.1.34 / 0.1.35 / 0.1.36 / 0.1.37 / 0.1.38 六条。
- 🔄 **BOM 填充层位纠正**：PSU/后面板填充从 `build_plan.bom_excel_rows` 回退（那是无模板 excel 兜底路径，模板模式不读）→ 改 `chassis_signals.psu_wattage` + 前端模板渲染；修 `deriveVars` gpu_qty/drive_count/psu_qty 全 0 bug（GPU/盘不在机箱件里）
- 🔄 OCP 不再自动填（2 轮真实样本：网络走 PCIe 网卡 KP 件、从不占 OCP，推翻 Dell 行业假设）；IO1/IO2 有 GPU 才填 X16 Riser
- PSU 瓦数按 GPU 分档：≥8 高功耗→2700W / 有 GPU→2000W / 无→1600W（修 R9700 误估 2700）
- KP 数量串台(R-6) + 过匹配(R-8)：数量解析改位置绑定+方向感知（修 SSD 盗内存 16、GPU 漏 ×1、NIC 串 8）；stage-1 跳纯容量碎片、Memory 交容量反推
- 型号正则修 H100/A100 漏匹配(R-15)：加 `[A-Za-z][0-9]{3,}` 分支；非 AI 需求 abort 修复（规格清单无用途词→usage 兜底"通用计算"）
- 🔄 撤回 4U 补件：4U=整机箱 lump 是有意的（未拆件，L6 行偏粗是预期）；GPU电源线属按 GPU 数人工加、不属机箱标配层；风扇占位件 `S.E.M.0000501` 挂 2U ×6（价 0 待补）
- R-17 Cable 调研（未实现）：SAS→Mini-SAS 线、NVMe→PCIe/MCIO；模板 `struct_count(front_cables)`+`frontCableQty` 机制已备、仅推理喂 0

## [0.1.29] - 2026-08-02 — 机箱能力主数据对齐

> 合并原 0.1.31 / 0.1.32 两条。
- 15 份真实配置校准 5 类底座（AMD/海光 × 2U/4U × 直连/Switch）；4U GPU 槽恒 8；OCP 是 AMD 平台特性（海光 2U 无、4U 有）
- 后面板槽位标准化：`chassisMeta` `REAR_SLOTS_2U_AMD/HAIGUANG/4U` + `rearSlotsFor(form,series)`；「恢复标准布局」按 form+series 取模板
- 能力档案回填 `backfill_chassis_capability.py`（4U→psu=4/gpu=8、2U→psu=2、2U 海光去 OCP），10 条校正（不覆盖已填值）
- 🔄 4U 后面板纠正：`REAR_SLOTS_4U` 从误克隆 IO1-4+OCP → 仅 OCP（GPU 槽与 IO 槽物理分区）；4U GPU 走 gpu_slots=8 + gpu_arch(direct/switch)
- 待确认：ZSA24V2-P gpu_arch 建议 switch；id=21/24/26 数据不一致；内存速率分档待权威 MT/s

## [0.1.28] - 2026-08-01~02 — 选型配置重构（L0/L1/L2 架构）

> 合并原 0.1.28 / 0.1.29 / 0.1.30 三条。
- 💡 **两层兼容架构**：L0 机箱能力档案（base_config psu_bays/rear_slots/gpu_slots/max_tdp）+ L1 配件适配（料号库 specs 声明，`partFit.ts`）+ L2 跨件规则 CRE（require/exclude/derive/recommend）
- CRE 双端：`selection_engine.py`（Python 移植 selectionEngine.ts），DB 规则 SSOT 双端共用；补 3 条 exclude 互斥（同型号不混搭）；`seed_missing_defaults` 按名补种
- 硬编码清零：`chassisMeta.ts` SSOT、L6ChassisConfig 清 5 处硬编码、GPU 架构读 `gpu_arch_default`
- 兼容规则加"业务分类"维度（category 列，仅组织用；编辑器分类过滤条+主题分组；API `?category=`）
- 机箱能力并入 `BaseConfigEditorPage`（修 save payload 写死 gpu_arch_default='none' 的 clobber bug）；删冗余 ChassisCapabilityEditor；选型配置瘦身两标签；PartFitMatrix 迁服务器管理（L0/L1 目录主数据归服务器管理、仅 L2 CRE 归选型配置）

## [0.1.27] - 2026-08-01 — 推理流编排可解释性

- 节点 IO 元数据（`reasoningNodeIo.ts` consumes/produces）+ 试运行步骤显示输入/输出；方案卡「回溯路径」高亮生成链；palette 三环节分组；condition 分支必连校验（防路由死路）
- 明确不做：全改显式变量系统、单节点调试、LLM 节点化（二期）

## [0.1.26] - 2026-08-01 — 需求分析试运行 + 两个潜伏 bug

- 画布加试运行 playground：`POST /api/reasoning-flow/test-run` 复用线上 `run_graph_executor`（force_complete 跳反问），节点逐步高亮+IO 明细+候选方案；抽 PlanCard/useTestRun 共享
- ⚠️ simpleeval 从未进 requirements（缺它 `_eval_condition` 永远 True → cond_clarity 永远反问）；build_plan 货币混算（USD 件当 RMB 混加，按 `store/quote.ts` 口径折算成含税 RMB）

## [0.1.25] - 2026-07-31 — 策略文档库

- 报价策略加左目录（定价策略/策略文档）；文档复用 `rules.strategies`（domain=policy，零新表）；marked+dompurify Markdown 渲染；5 篇定价手册种子（空表才灌，绝不覆盖用户改动）
- 推迟：版本快照/回滚（改动直接覆盖）

## [0.1.24] - 2026-07-30 — 报价策略重构：查表→加法定价引擎

- 💡 定价模型：查表三档 → 六维加法叠加（平台+行业+区域）×订单×成本×台数，夹 [保底,封顶]；7 条维度策略、零新增列
- 纯 TS 引擎 `pricingEngine.ts`+单测；`pricingMeta.ts` 维度元数据 SSOT；VueFlow 固定流水线画布+维度抽屉+演算器；工作台告警 floor 改 guardrail（仍只警告不锁价）
- 移除旧 scope→三档模型（PricingStrategyCanvas、MarginTier、seed）；L3 溯源输出 pricing_additive

## [0.1.23] - 2026-07-30 — 选型配置大整理：清退 DerivationEngine

- 💡 线缆/背板规则收敛进 CRE 唯一真相源：删 `derivation_engine.py`、`/api/derive`、DerivationRulesPanel；SATA/SAS÷8、NVMe÷2、GPU 供电线、背板 tri（含 NVMe→tri）迁入 CRE；删整机功耗/PSU/Switch 三条规则
- `ruleMeta.ts` 元数据 SSOT（规则类型标签/语义色/算子符号/ctx 字段）；选型配置页重做（紧凑卡片+弹窗编辑+三列因果流拓扑）
- 修 NVMe 线缆恒 0（`"NVME".includes("NVMe")` 恒 false）→ 引擎层 `normalizeDriveKind` 大小写无关 + 优先读 KP specs
- 移除"按商机平台过滤候选机型"filter 规则（只过滤候选机型、与基准配置下拉表现不一致）

## [0.1.22] - 2026-07-30 — 回退 Excel 表头自适应列定位

- 🔄 移除 0.1.20 引入的 `header_labels` 自适应列定位：频繁定位错列（子串匹配误命中）、扫描窗口难覆盖所有排版、与显式 `col` 双真相冲突 → 回归固定列字母 `source_config.col`（所见即所取）；存量 header_labels 自动忽略无需迁移

## [0.1.21] - 2026-07-30 — 趋势洞察下沉为方案助手快捷指令

- 删商机线索页趋势洞察卡片、`/api/dashboard/ai-insights`、`ai_insights_config` → 并入助手「📈 分析本期趋势」快捷指令
- 快捷指令 prompt/context 支持函数；AI 设置可配 prompt 模板；新增 `/api/dashboard/trend-overview`（周/月/近半年聚合+重点商机，LLM 输出 8 段报告）
- 修 `get_trend_overview` 裸调路由函数 500（Query 默认对象被 strptime）——带 Query 默认值的路由函数不能当普通函数裸调

## [0.1.20] - 2026-07-29 — 清理 pricing_engine 历史包袱

- 💡 `pricing_engine` 1094→425 行（-61%）：拆纯算法引擎 + 业务服务（QuoteService，商机 CRUD 迁入）+ 解析器（ExcelParser）；删 7 个遗留解析方法、Excel 导出样式块、死导入；parse_file 统一走规则驱动（异常直接暴露而非旧实现掩盖）；`_safe_eval_math` 移入 excel_parser（替换 eval()）
- 删 l6/kp_region_config 残留（rules_repo/models/api 共 -263 行）+ 物理删表脚本 `drop_l6_kp_region_config.py`
- 商机详情页报价单解析预览弹窗（热力图+区域/字段规则可调）；Excel 表头自适应列定位（0.1.22 回退）
- 修报价单列表价格/利润不显示（回退误加的按 items 重算逻辑，直接读 quotation 表存量值）

## [0.1.19] - 2026-07-28 — 商机存储文件夹可读命名 + 附件清理

- 文件夹 `OPP-xxx` → `客户名_OPP-xxx`（客户名变更自动重命名+同步路径）；迁移脚本 `migrate_opportunity_folders.py`（--dry-run）
- 修附件物理文件残留：存档区删除、永久删除报价单 Feed 附件时同步清磁盘文件

## [0.1.18] - 2026-07-28 — 料号库体验

- 分页（50/页）、批量导入/导出（解析预览标注新增/更新/无效）、响应式（侧栏可折叠/移动端覆盖层）、卡片去圆角
- 修卡片泛白（玻璃层嵌套叠加近纯白）；PN 可编辑（此前不可编辑是误判）

## [0.1.17] - 2026-07-27 — 工作台规格书 + 行级货币 + 推理流增强

- 工作台规格书预览（SpecSheet+打印 PDF，后端零改动）；KP 行级 RMB/USD（QuotationItem.currency，按币种联动重算）
- ⚠️ 修 USD 计价放大 ~9 倍（税率/汇率是字符串，`1+"0.13"="10.13"`，源头统一 Number()）
- 推理流：结构化 BOM 解析（`3.84T×4+960G×2` 按件独立计数）、per-机型 KP 套餐、预算驱动选件、underspend/超预算双向标注
- 料号库 description 拆 `spec_text`/`description`；系列枚举统一 `system_config.server_series` SSOT；推理流硬编码挪前端抽屉可配（机型套餐/数量格式/型号正则/underspend/select 策略）

## [0.1.16] - 2026-07-23 — 料号库/驾驶舱/主题

- 料号库机型系列筛选；背板回归普通配件（不再走 bp_tri_pn/bp_dc_pn 特殊字段）；驾驶舱自定义时间区间+图表粒度自适应；列表排序
- 修主题切换被浏览器扩展篡改（MutationObserver 守护+首屏预写主题）、L6 价格历史快照丢失（l6_repo 写错 schema）、序列未同步（`sync_sequences.py`）、料号编辑 500
- 服务器管理面接入玻璃视觉系统；文档：Frontend_Style_Guide 重写（Soft Glassmorphism）

## [0.1.15] - 2026-07-17 — 清理

- 修预览数据不完整（preview 接口缺 quotationId）；移除冗余 `confirmed_price`（统一 base_price+final_price）、item 冗余 model_name/server_model

## [0.1.14] - 2026-07-16 — 修导出模板编辑器边缘发灰（Dark 主题暗角装饰罩住全屏编辑器，z-index 提升）

## [0.1.13] - 2026-07-16 — 修导出模板 L6/KP 保修字段预览错位（动态绑定插行未同步静态绑定行号，改用行偏移表累加）

## [0.1.12] - 2026-07-16

> ⚠️ 破坏性：SQLite 四库 → 单一 PostgreSQL（schema 隔离 opportunities/kp/l6/rules/l6_history/public），必须跑迁移脚本，旧 SQLite 不再兼容；`DATABASE_URL` 环境变量替代硬编码路径。

## [0.1.11] - 2026-07-11 — 导出模板 + 文档

- 动态绑定自动保存（bindingForm 深度 watcher，修切 tab 绑定丢失）；新增 CLAUDE.md / Pricing_Engine.md / Excel_Parsing.md / Engineering_Guide.md + API 路由文档补全 119 端点

## [0.1.10] - 2026-07-09 — 硬编码清理

- 后端路径 `DATA_PATH` 环境变量；前端 14 组件 100+ 处色值改 `--cpq-*` CSS 变量；CORS 读环境变量；新增 docs/README.md、Deployment.md

## [0.1.9] - 2026-07-04 — 项目文件管理

- 拖拽多文件上传、新建项目自动建标准文件夹；修详情页路由白屏、文件列表加载失败（filename vs file_name 字段名不匹配）

## [0.1.8] - 2026-07-04 — L6 三栏对比 + 导出模板引擎

- L6 三栏对比（需求/匹配/定价）；导出模板引擎（`${xxx}` 变量 + `#for` 循环块）+ 卡片 CRUD + 所见即所得编辑器；配置页预览复刻 Excel 结构
- L6 匹配：主板降级、机箱模糊匹配；修匹配引擎空指针、导出合并单元格错位、Excel 空行渲染横线

## [0.1.7] - 2026-07-03 — 文件归档/评论

- 文件按项目自动归档+实时扫描+重命名/删除/上传/打开；项目评论（@提及/回复）；工作台侧边栏（文件列表+评论流）双栏
- ⚠️ 修文件下载路径穿越（路径白名单校验，拒绝 ../）

## [0.1.6] - 2026-07-03 — 质保独立计算

- 质保服务费 L6/KP 独立计算；质保年限自动识别（"质保3年"→3 年）；质保卡片重构

## [0.1.5] - 2026-07-03 — 质保可编辑 + 修复

- CPU 价格 0 警告；质保可编辑（年限/费率）；L6 匹配状态显示；价格失焦重算；修前端税率多乘 13%、综合毛利率口径不一致

## [0.1.4] - 2026-07-03 — 导出规则 + 评论

- 导出描述引擎：循环块、动态分类（按配件类别自动分组）、拖拽排序、智能展开（空行自动跳过）；工作台侧边栏评论流

## [0.1.3] - 2026-07-02 — L6 价格库

- 五维规格匹配筛选（机箱/机型/盘位/PSU/主板）；卡片网格重构；抽 `L6SpecFilter` 公共组件

## [0.1.2] - 2026-07-02 — L6 匹配规则可视化

- 规则可视化配置页（拖拽排序/降级开关/模糊规则/多结果手选）；L6 匹配引擎增强（主板降级、机箱模糊）；"基准价格"更名"KP价格库"

## [0.1.1] - 2026-07-01 — 四库分离 + 规则在线化

- kp/l6/rules/cpq_platform 四库分离；规则在线化（Excel 锚点/L6 维度/KP 映射/主板映射）；KP/L6 在线 CRUD+价格历史趋势图；回收站软删除；项目管理看板

## [0.1.0] - 2026-06-29

> ⚠️ 破坏性：从旧系统 0.2.5（Streamlit 单体）全面重写为 Vue3+FastAPI 前后端分离，数据不兼容。

- 智能上传（Excel 拖拽→自动解析→多配置拆分→入库）；报价工作台（实时精算/独立调价/财务三维联动）；五维匹配引擎；质保按需；WYSIWYG 导出
- 技术栈：Vue3+TS+Vite+AntD+Pinia / FastAPI+SQLAlchemy / SQLite×4（0.1.12 迁 PostgreSQL）
