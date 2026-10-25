---
name: requirement-analysis-dual-route-redesign
description: 需求分析双路线重构定调(2026-08-06 多轮讨论结论)：AI路=方案助手多轮引导对话;本地路=全点选引导wizard;extract_keywords正则必删;workload优先于series;pick_kp_parts/CRE/选型配置不动;待用户拍板执行
metadata: 
  node_type: memory
  type: project
  originSessionId: 753f8001-1119-4541-8a2f-4b183c982b83
  modified: 2026-08-10T08:47:47.830Z
---

> **⚠️ 2026-08-10 已被 AI-first 改革大幅取代（codex 落地）。** 本条记录的双路线(route_fork 分叉、v9.2 active=106、正则作本地路)**已全部废弃**，现行状态：
> - **正则解析物理删除**：整个 `requirement_parser/` 包移除（≈-2600 行），`extract_keywords` + 全部字段级正则提取器清掉。下面「阶段 3 待办：删正则」= **已完成**。
> - **执行路径统一为 orchestrator 单路**：`_run_linear_fallback` 删（异常诚实降级不再假装出方案），`_dispatch` 删 9 个 v9 handler，画布试运行改走 `run_orchestrator`（原 `run_graph_executor` 仅测试/脚本残留）。
> - **双路图废弃 → V11 单路 AI-first 链**：`DEFAULT_GRAPH`(v9 双路种子)删，`seed_default_if_empty` 改 seed V11，`active_is_current` 删 v9 检查，**21 个 migrate/upgrade 方法 + startup 19 处调用全删**（呼应 [[reasoning-flow-migrate-gate]]，这次彻底拆干净）。active flow 不再是 id=106。
> - **Agent 架构实装**：新增 `agent_react.py`(文本式 ReAct，见 [[llm-provider-relay]] 为何不用原生 function-calling) + `agent_tools.py` + `agent_understand.py` + `reasoning_orchestrator.py` + `capabilities.py` + `case_provider.py`；**删 `llm_understand.py`**。
> - **逐节点 LLM 开关全删**：`ai_mode`/`enable_llm`/`proposal_mode` 等 UI 开关清掉，AI-first 后只认全局 AI 开关，规则只作失败兜底。
> - 节点职责新边界：理解(LLM)/机型(规则+放宽)/配件(LLM提议+库校验)/组装(确定)/校对(judge)/反问。
>
> 下面的历史细节（设计定调、v9 回退/migrate 教训）**仍作为背景保留**——尤其「带 startup 迁移钩子的功能回退必须同退迁移代码+还原 DB」「改 DEFAULT_GRAPH 删节点须查 migrate 链」这两条通用教训没过时。但**任何「当前定调/active flow/拓扑」类陈述以本 banner 为准**，碰推理流前另看 [[strategy-center]] [[agent-architecture-decision]] [[agent-understand-pure-llm]]。

---

需求分析（策略中心-需求分析 = 商机详情/方案助手的需求→BOM 推理流）将重构为双路线，按 AI 开关分叉。2026-08-06 多轮讨论定调，待用户最终拍板后分阶段执行。

**核心决策：**
- **AI 路线**（LLM 开）：复刻 server-configurator.com 的 spec assistant 模式——LLM 多轮引导对话（工作负载→决定性关键问题→推荐具体机型带理由→配置维度让用户挑），方案助手主导，到点调用确定性工具(select_models/pick_kp_parts/build_plan)。**「需求分析」与「方案助手」在 AI 模式下合流**（最近 commits 已在往这走：方案助手会话内跑推理流生成 BOM）。
- **本地路线**（LLM 关）：**全点选引导 wizard**，系统主导、步步收窄，绝不让用户一次性自由发挥。结构同 AI 路但确定性：工作负载按钮→档位按钮(小/中/大)→机型列表→配置维度菜单。点选为主→几乎不需要文本解析。脊柱=现有 catalog_guide 状态机扩展。
- **workload 优先，不是 series 优先**：第一问是「工作负载/用途」(虚拟化/数据库/AI/Web/存储/边缘)，映射到 catalog server_types；series(Orion/Polaris/Intel)是 workload 推出来的结果不当输入。用户原说"系列(AI/通用/存储)"其实是 server_types 叫法问题。
- **选择题推迟到选完机型**：入口不让用户做选择题（先自由输入/点工作负载）；只有选完具体机型后才问「系统推荐配置 vs 自己配置」（自己配置→ConfigWizard，系统推荐→引导逐项输入）。
- **extract_keywords（2028行正则）必删**：两路都不需要 one-shot 文本 NLU（AI 用 LLM；本地全点选）。删主体 + _extract_mem/drive/gpu/nic/psu/raid_groups + R1~R28 + clarity 信号规则 + requirement_normalizer 表格归一。**保留**：pick_kp_parts/build_plan/select_models（确定性选件组装，吃 slots 不吃文本）、catalog_guide、llm_understand、RequirementSlots 契约、slots→ext 适配(apply_llm_merge)、纯小工具(_normalize_capacity/_drive_term_gb)、整个选型配置域(CRE/base_config/ConfigWizard/Workspace 不动)。
- **模型听 AI 设置**：llm_config 已模型无关(step-3.7-flash 只是占位文案/注释，运行时无硬编码)。step-3.7-flash 文案/注释/.env默认将清中性，但保留「reasoning 模型耗尽 max_tokens」告警知识。
- **正则删最后做**：先建两路(flag 并存)→R1~R28 语料+真实案例评测双路覆盖正则所有 case→删正则+迁单测。中间可回退。

**参考**：server-configurator.com spec assistant transcript——workload-first / 问决定性问题 / 语义档位+数字双收 / 模糊与改主意优雅重问 / 推荐机型带理由 / 配置阶段用户挑维度。差异：它不显价(询价制)且**停在推荐**；我们有定价引擎且**终端是真实带价 BOM**（再转报价单），推荐只是中间步——这是优势。

**三条确认（2026-08-06 用户强调，别漂）：**
- **终端永远是 BOM**：推理流止于 `build_plan(baseline,kp_parts)`([candidate_search.py:1681](backend/app/api/candidate_search.py))→`plan.cfg.bom_excel_rows`=基准配置的 L6 件行 + 匹配 KP 件行，带 l6_cost+kp_cost=total_cost。用户审 BOM→转报价单。两路**终于 BOM**；"系统推荐 vs 自己配置"只是**到 BOM 的方式**（自动填槽 vs 开 ConfigWizard），不是要不要出 BOM。
- **基准配置是脊柱，机型是把手**：`baseline`(基准配置).parts 直接成 L6 BOM 行——选机型=选基准配置=选了大半个 BOM。一机型可多套基准配置(直连/tri-mode)，`select_baseline` 已消歧。workload"收场"是落到一套基准配置上。**收场主杠杆=基准配置能力标签正确+workload→基准配置映射准(都已存在,属CRE域不动)，不是营销文案。**
- **主用户=FAE/技术，熟产品；要兼顾不熟练者 → 专家快车道+新手引导道**：引导 wizard 不能强制专家逐题过。专家快车道=跳过 workload 引导→直接选机型/基准配置→BOM→微调 KP（即"自己配置"分支，对专家是一等公民非兜底）；AI 路自适应——熟练用户直说机型+配置时 LLM 跳过问卷直出 BOM。**`product_content` 卖点/场景降级为新手阐释+推荐理由(次要)，不再是收场门禁。**

**Why:** 正则怪兽每训练一轮膨胀(R1~R28)、不可维护；引导式 wizard 把"一次解析一整段"拆成"逐个点选小问题"，复杂度归零。两路分工清晰，离线不依赖 LLM 也能用([[llm-integration-strategy]] 离线可跑)。

**执行稿（自洽，新会话可直接执行）**：`docs/需求分析双路线重构方案.md`（⚠️该执行稿 2026-08-06 已随回退删除；原含现状校验表/要点/Mermaid流程图/删留清单/开工前检查）。2026-08-06 核验细化三点：① extract_keywords 被**两处**调用(图 extract 节点 + `_run_linear_fallback`:1840)，删要同改；② llm_understand 现为"补缺"定位需升级为"主理解+驱动多轮"；③ 需求分析策略页=reasoning-flow DAG 编辑器，话术直接入 `node_configs.llm_understand.system_prompt`，别另起配置。用户定调：分流按**输入明细程度**(非专家/新手标签)；不搞独立评测脚本(抽查 R1~R28 代表case+真实样本确认不劣于正则即可)；终端永远=BOM。

**进度（2026-08-06）：阶段 0/1/2 已完成，剩阶段 3（删正则）。**
- 阶段 2 关键发现：**「多轮引导 + 合流方案助手」在 P1/P2 已落地**（llm_understand 早产出 questions/missing/coverage → 注入 ask_user 反问；assistant.py 已把 need_input/need_confirm + BOM 当对话回合）。**真正缺的只有「主理解」一刀**：原 `apply_llm_merge→merge_into_ext` 全程 setdefault/「规则赢只补缺」→ LLM 理解了也被正则盖掉（"接了和没接一样"根因）。
- 解法：新增 `merge_into_ext_primary`（LLM 抽到的槽位**覆盖** ext，过同一套白名单/数量闸门）+ `apply_llm_merge(..., llm_primary=False)` 路由 + llm_understand 节点 config 加 `llm_primary`/`system_prompt` 开关（抽屉可配，**默认关=旧行为原样**，flag 并存可回退）。改了 llm_extract_enhance/requirement_slots/llm_understand/reasoning_executor + 抽屉/copy。烟测：主控 form2U→4U/cores4→16 覆盖生效；非平台系列 9004/非法 10U 被闸门拦下。
- 阶段 1 定调偏离：**没扩 catalog_guide 状态机**（本地路用前端 LocalRouteWizard 点选 + catalog_pick pin 机型，不经文本反问，故不必加 workload→档位 后端阶段）；route 开关=system_config.requirement_route（ai/local），放需求分析页头。
- 阶段 3 待办：删 extract_keywords 主体+_extract_*_groups+两处调用点(图 extract 节点 + `_run_linear_fallback`)+requirement_normalizer+迁单测；删前抽查 R1~R28 代表 case + 真实样本确认两路(尤其 llm_primary=on)不劣于正则。

**⚠️ 2026-08-06 下午：v9 双路线实现已整体回退（用户要求）。** 一次只退代码不够——根因在 DB：`startup.init_rules_db` 调 `migrate_v9_dual_route_if_needed`，每次启动把 active flow 迁成 v9(route_fork 7节点)，且 deactivate 只关 `.first()` 一条、旧 active 不清，**active 堆到 25 条全是 v9**（画布读 active=v9，故"画布没恢复"）。彻底回退两层：① 代码退 10 文件到 HEAD（reasoning_flow/repo/executor/**startup** + llm_extract_enhance/llm_understand + 前端 canvas/drawer/vf/reasoning.ts，**含 startup 去掉 migrate_v9 调用**）；② DB `UPDATE rules.reasoning_flow SET is_active=(id=41)` 切回 **id=41（v8 17节点正则链, node_config 17/17 完整）**。兜底：patch=`v9-dualroute-canvas-rollback-20260806.patch`+`requirement-route-changes-20260806.patch`（根目录）、DB active 快照=`backend/tmp_flow_active_backup.json`（101条，恢复 v9=反向 apply patch + 用快照还原 active）。**教训（通用）**：带 startup 迁移钩子的功能回退，`git restore` 不够——迁移已改持久化数据，必须同退迁移调用代码 + 手动还原 DB active/数据；migrate 类函数要保证幂等 + 清旧 active。设计定调是否保留用户未示（再碰双路线**先问**当前定调）。两个未跟踪残留 `LocalRouteWizard.vue` + `docs/需求分析双路线重构方案.md` 2026-08-06 已按用户要求删除；`OpportunityDetail.vue` 的本地路入口（routeLocal/onLocalPick/import/模板用法）随同回退，仅保留一处非双路线文案改动（报价卡 multi-cfg-tag「综合」→「首个/共N」）；前端 `npm run build` 验证通过。OpportunityDetail 改动备份=`opportunity-detail-rollback-20260806.patch`（根目录）。

**✅ 2026-08-06 晚：v9.2 双路线重新落地（已生效，不同于下午回退的 v9）。** 用户重提需求并定调，重做双分叉拓扑，active flow 切到 **id=106**（旧 id=41 v8 完整保留、is_active=False 作回退锚点）。与下午回退的 v9 的关键差异：① 分叉用**全局 AI 开关** `llm_config.enabled`（非独立 requirement_route），condition 白名单加 `llm_enabled` + run_graph_executor ctx 注入 `is_llm_enabled()`；② **保留 v8 正则链作本地路**（非 catalog_pick wizard）；③ **染连线**（v9 只染节点）—— ROUTE_BY_TYPE 前端派生：llm_extract/llm_audit=ai 蓝、extract/slot_validate=local 橙、其余 shared 灰 + 顶部图例；④ **做减法**删 llm_understand（被 llm_extract 取代）+ confirm（default_accept 死重）+ apply_confirm_decisions/_confirm_llm_items/test_confirm confirm 用例。拓扑（**v9.3：两路 select_baseline 前彻底分开**，用户要求 AI 路不被本地机械反问/场景干扰）：normalize→**route_fork**(头,true→llm_extract→**llm_guide** / false→extract→slot_validate→clarity_check→cond_clarity→[ask_user|scene_analysis→cond_scene→confirm_series])→select_baseline→共用中段→budget_check→**cond_audit**(尾,true→llm_audit/false→review)。llm_extract=AI 路主理解（复用 run_llm_understand worker，ext 从空起、enable_llm 默认 True）。**llm_guide**=AI 路 uncertainty 门控（基于 [SAGE-Agent arXiv 2511.08798](https://arxiv.org/html/2511.08798v2) Heuristic 版，联网研究定调非拍脑袋）：判 server_type_name+(series|form)+coverage.missing_l0 空→放行（ctx.series_ready）；不满足→反问最关键 1 问（取 llm_extract 已产的 questions，避已问方面=冗余惩罚 λ，纯规则不调 LLM）；force_complete/反问轮次封顶强制放行。多轮靠 run_pipeline 重跑整图（用户回复→llm_extract 重理解→llm_guide 重评，节点不自管轮次）。select_baseline 加 awaiting_input 跳过（反问中不选型）。前端 ROUTE_BY_TYPE llm_guide=ai 蓝。19 节点。激活=幂等 `ReasoningFlowRepository.upgrade_to_dual_route()` 新建 flow+activate（**不挂 startup**，避开 v9 每次启动重复迁移堆 active 的坑），脚本 `backend/scripts/upgrade_reasoning_flow_dualroute.py`（含 `--rollback <id>`）。condition 节点画布双出口 Handle（真/假）。验证：pytest 18 passed + npm build OK + DB active=106 拓扑正确。⚠️坑+治本：激活新 flow 时若画布开着旧 flow，前端 `persistGraph` 会把画布内存里的旧 graph 写回新 active（id=106 上线即被用户开着的 v8 17 节点视图覆盖，updated_by=system），是画布既漏（persist 无条件写 active）；已给 persistGraph 加 active id 漂移校验（GET 比对，不一致则放弃回写+load 刷新）。**激活/切换 active flow 后，画布必须硬刷新重新 load**，否则旧内存会污染新 active。⚠️坑2+治本（端到端验证时发现）：startup migrate 链 migrate_v6/v7 检测 `llm_understand`/`confirm` 是否存在，v9 删了这俩 → 重启检测不到 → 新建 flow+activate（链式漂移到 v7 名字的 flow，updated_by=migrate，active 跑到 id=120）。已给 migrate_v6/v7 加 `route_fork/llm_guide in node_ids → return None` 早退。**通用教训：改 DEFAULT_GRAPH 删节点，必须同步查 startup migrate 链里检测该节点的函数，否则重启无限新建 active（v9 回退坑变体）。** 另修 llm_guide 一个 typo：判据 `clarity_round` 应为 `clarify_round`（少个 i 导致轮次封顶永不触发、实际会死循环）。**llm_guide 升级为 spec assistant 式对话引导（2026-08-06 晚，一套服务两入口）**：阶段机 workload→recommend→done，LLM 分阶段生成回复（workload 用 server_types 选项引导 / recommend 用 select_models 候选 + product_content 组织「推荐 X 因为…」理由）。方案助手 analyze + 商机详情 generate 都跑图 → 都过 llm_guide（会话状态 thread.reasoning_state vs opportunity extra_fields 隔离）。**全 config 驱动（拒绝硬编码，用户定调）**：画布抽屉可配 system_prompt / enable_llm / recommend_limit / ask_threshold / enable_config_stage。LLM 失败降级 missing_l0 判据（保底）。新增 `backend/app/services/llm_guide_prompt.py`（LLM_GUIDE_SYSTEM_PROMPT + LLM_GUIDE_SCHEMA + build_messages + run_llm_guide，照 llm_understand 骨架）；run_pipeline 注入 dialog_stage/collected/session 到 ctx（`_read/_write/_reset_dialog_state`，与 catalog_state 并列，AI 路专用）。llm_guide 把 collected.server_type 桥接给 ctx.catalog_type_name（select_baseline 读它选型）。端到端跑通（deepseek：模糊需求→workload 引导「请告诉用途 1.通用 2.AI 3.存储」→答 web→recommend「推荐 ES22V3-P…适合 Web」+ 理由→done→3 方案 BOM）。待优化：recommend 护栏（LLM 推荐机型 vs BOM 机型一致性，防幻觉编型号）+ config 阶段（逐维配置，第一刀 enable_config_stage=false 关）。踩坑：_persist 内 json 未 import / llm_guide 内重复 `from...import select_models` 致 _dispatch 局部变量 UnboundLocalError / _candidates_text 假设 product_content 是 str 实为 dict / recommend→awaiting 触发 select_baseline skip——均已修。

**How to apply:** 碰需求分析/推理流前先看：**v9.2 双路线已落地**（active flow id=106，分叉靠全局 AI 开关 `llm_config.enabled` 而非独立 route 开关）。回退：`cd backend && python -X utf8 scripts/upgrade_reasoning_flow_dualroute.py --rollback 41`（id=41 v8 完整保留）。视觉（画布连线蓝/橙/灰 + 图例 + condition 双出口 Handle）待用户 dev server 确认。相关 [[strategy-center]] [[opportunity-detail-intel]] [[llm-integration-strategy]] [[assistant-skeleton]] [[derive-must-have-manual-fallback]] [[systematic-cleanup-not-whackamole]] [[no-patch-on-patch]]。
