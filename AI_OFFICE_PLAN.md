# AI Office 需求分析 Skill 执行状态

> 最后更新：2026-09-01（提示词/节点契约已改 DB 唯一权威并删除种子文件，见「2026-09-01 定案」节）（机型/配件 AI 接地：phase_model_reason 与 phase_kp_reason 均走受约束库内候选选型，见「2026-08-31 定案」节）。本文件描述"当前真实代码"，不是历史快照；每次架构变化后必须同步更新。
> 当前分支：`codex/skill-plan-refactor`（未提交）。⚠️ 2026-08-27 起由新会话接管维护；此前版本对"已跑通/280 passed"的描述与实测不符，勿引用。

## ⚡ 设计宪法（任何会话改代码前强制自查，用户可拿三条否决任何 PR）

1. **同一时刻整个系统只有一个会思考的脑袋**：AI 角色（skill_chat 驱动的 ReAct 循环与 agent_fill）。进入六步后由确定性引擎（skill_plan_runtime 硬阶段机，零 LLM）执行。永不并存、永不嵌套。角色给引擎的是填好的登记表，引擎给角色的是产物或缺口数据。
2. **凡是模型能理解的事，禁止用数据表替代**：话术、关键词、意图猜测、措辞模板一律禁止。数据表只允许存业务事实（目录/案例/规格/规则/价格）。
3. **新增任何机构前必须先回答：删掉了什么、合并了什么。** 没有删的部分方案不完整。

## 两器官架构（2026-08-28，本版真实架构）

```
AI 角色（对话脑：skill_chat.handle_skill_chat_turn，run_react_loop 循环）
  手里三样东西：update_requirement_slots / submit_registration / catalog_search
  职责：对话、理解、推荐（目录+价格+理由）、接闲聊拉回、登记需求、判断何时提交
    │ 场景已明 → submit_registration（门槛=model_signals_ready）
    ▼
Skill 引擎（纯执行：run_skill_plan_core，六阶段固定，零对话能力）
  normalize(对话路径零LLM) → model(受约束选型) → kp_gate → kp(确定性) → compose → output
  产出：done(bom_scheme) 或 gaps([{slot, options, reason_code}] 纯数据)
    │ 缺口 → 角色用自己的话问（结构=缺口数据，文案=模型转述，chat_json）
    ▼
  产物 → business_artifact 卡 + 商机落库（与旧版一致）
```

- **角色线程记忆**：`reasoning_state.skill_chat.{ext}`（登记表跨轮持久）；旧 pending workflow/slot_state 大快照机器已删。
- **触发**：绑定了 requirement_analysis 的角色，全部消息走对话脑（含 Skill Studio 右侧栏——entry bypass 已删）。普通聊天阶段不读 Skill 节点内容；检测到配置服务器需求后先总结上下文、等用户确认，确认后同一大脑调用 submit_registration，再由 agent_fill 抽槽后进入引擎。独立路由 LLM（skill_router.py）已删。
- **守卫语义**：登记表在提交时由 AI 角色 agent_fill 一次性抽取；kp_mode 业务选项值必须原样（parse_kp_mode 精确匹配两个业务值）。
- **试运行**：Skill Studio 试运行/画布预览先走 AI 角色 agent_fill，再进入同一确定性引擎；force_complete 默认 False→返回 gaps 数据；True→带标注推荐出方案，响应含 `engine_result`。

关键文件：`skill_phases.py`（引擎阶段+缺口构造，22 函数零话术）、`skill_plan_runtime.py`（编排+engine_result_of 协议）、`skill_chat.py`（对话脑接线+三工具实现）、`colleague_turn_service._run_skill_chat`（路由+收尾）。

## 验证（2026-08-28 晚，真实 LLM 全旅程，277 passed）

- 泛指「我需要一台服务器」→ 角色自然语言问场景（13.5s，非模板）。
- 「你能给我推荐一个吗」→ **角色查目录推荐**：ES22V3-P（Orion，¥11537）vs ZS22V2-P（Polaris，¥15604）+性价比理由+顺势问场景（28s）——"只会问不会推荐"根治。
- 「就 ES22V3-P 吧，跑数据库用」→ 角色登记+提交 → 引擎（零抽取调用）锁定 → kp_mode 缺口 → 角色转述（56s）。
- 点「只要整机底座（L6）」→ ✅ BOM（l6:9 / kp:0 / ¥11536.83，28.5s）。
- 硬编码普查：skill 链路零话术表/零关键词表；唯一残句=转述失败时的数据拼装兜底（非话术）。

## 本轮删除清单（两器官改造）

- 引擎话术层：`_SLOT_ASK/_SLOT_WHY/_slot_ask/kp_mode_ask/kp_recommend_ask/kp_desc_ask/pause_for_ask/apply_skill_decision 遗族`——引擎只产缺口数据。
- 对话机制：收敛计数器（_no_progress_streak）、delegate 机制（_delegate_slots/DELEGATE_OPTION_VALUE）、kp_desc_rounds、点击快速路特判——全部由角色对话自然吸收。
- 路由与装配：`skill_router.py`（独立路由 LLM）及其测试、entry_point bypass、pending workflow 三函数+大快照搬运、`_run_tool_turn` 内 461 行 skill 分支。
- 工具合并起点：catalog_search 入列（旧 4 个浏览类工具仍在 specs 供其他角色，待退役）。

## 真实剩余

- 中转通道（cc-switch）不稳：本轮实测多次 httpx 10054；角色对工具失败的诚实话术（"拉不到数据，不编造"）行为正确。
- 缺口转述偶发走兜底句（chat_json 指令已对齐，需观测）。
- 闲聊拉回：提示词规则已给角色，未做专项 E2E（待用户实测）。
- 待修：数据分析师 query_cpq_data 报 `'Query' object has no attribute 'split'`；旧 4 浏览工具退役；ReasoningNodeDrawer 的 fallback_order 字段说明更新。
- P1：run 表+回放、eval harness（用户出题→案例库金标准）、Langfuse、试运行路径抽取降延迟、双聊天面板合一。
- 临时观测点（稳定后清理）：assistant.py 的 `GET /api/assistant/_debug/event-loop`（dump 挂起协程栈）与回合出口 INFO 日志。

## 2026-08-30 任务模型：Claude Code 式（同意制入口 / 底部任务胶囊 / 中途消息排队）

对齐 Claude Code 的任务语义，三件事全部机制层，判断全部归 LLM（唯一大脑）：

1. **入口同意制**（requirement_prompt 规则 2，三分支）：
   - a) 客户明确要求出方案（「帮我配一台」）→ 当轮登记完直接提交，同意已给出；
   - b) 咨询式对话信息渐齐 → 角色**主动提议**（复述已登记需求 + 自然预告流程步骤 + 问是否开始）→ 客户确认后提交；
   - c) 任务进行中客户的回答 = 继续任务（先登记再直接提交，禁止重新提议）。
   同意判断纯语义（LLM），程序零字符串匹配；流程预告素材来自画布节点 label/description（数据驱动）。
2. **步骤单源 `skill_steps_view(flow_configs)`**：pipeline_start 事件与角色提议话术共用同一份步骤清单；画布上改节点 label/description，提议话术与任务胶囊两处同步变。客户可见里程碑只含 model_reason/kp_reason/compose/output（input/agent_fill 在对话里自然发生）。
3. **前端任务胶囊 TaskStepper**：替换原顶部进度条。收起态=输入框上方小胶囊（状态图标+任务名+完成数/总数+当前步骤）；点击展开浮层看全部步骤（状态/摘要/耗时）。状态机 taskPhase ''|running|paused|done 由 WS 事件驱动（pipeline_start/paused/done、analysis_finished、business_entity_ready、analysis_cancelled）；done 后下一条消息发送时自动复位。双面板（AssistantPanel + OfficeColleagueChatPanel）统一接入。
4. **中途消息排队**：per-thread lock 分支从"拒绝并提示等待"改为排队（保存完整回合参数），当前回合 finally spawn drain 串行续跑；stop/取消清空队列。排队时只广播 chat_status 提示，不落库拒绝消息。

黑盒边界（回答"requirement_prompt 是不是不可配置黑盒"）三层：
- **DB 可配层**：人设、步骤 label、节点 description、工具勾选——画布改了就变；
- **代码契约层**：requirement_prompt 的机制规则（同意门槛、登记完整性、禁编造）——等价于 Claude Code 的产品 system prompt + 工具 description，测试锚定（test_task_model.py）；
- **数据驱动接线**：代码只负责把画布数据注入提示词（flow_steps 块有则注入无则不出现），不做内容决策。

E2E（干净线程全绿）：T1「我想要一台服务器」→问场景（无任务启动）；T2「主要跑数据库」→查目录确认类型（无任务启动）；T3「好，开始吧」→pipeline_start（title=需求分析，6 步）→机型缺口卡（带价格选项）；T4 点选机型→任务继续不重新提议 + 中途补预算消息排队提示。353 passed（新增 4 契约测试）。

## 2026-08-30 定案：转接只在群里（绑定会话永不转接）

用户拍板：**系统级转接只发生在团队群**；与方案助手（或任何同事）私聊时锁定身份——角色自己能办的事自己办，只有请求超出其 skill/工具/数据范围时，由**角色在对话里口头建议**找哪位同事（LLM 语义判断），客户决定。

- **路由机制**（`ai_colleague_service.resolve_chat_target`，post_message 调用）：thread 绑定了 colleague_role_key（含 `assistant`）→ 锁定身份，判官零调用；只有未绑定线程（团队群，group-resolve 创建）→ @点名确定性路由 / LLM 判官按名册转接（落 handoff 可见标记）。旧 bug：绑定 `assistant` 的私聊线程因判别条件写成 `!= "assistant"` 落进判官分支，是「我想要一台服务器被转给技术支持工程师」的根因。
- **口头提议提示**（`colleague_turn_service._handoff_hint`，三个 persona 装配点注入）：名册摘要（`colleague_roster_digest`，与判官共用 `_dispatch_roster` 单源——DB 业务数据）+ 规则契约（能覆盖的请求一律自己完成；超出能力范围才建议**一位**合适同事，由客户决定；禁止来回推）。
- **前端**：浮动助手默认进方案助手 1:1（原默认团队群）；团队群从侧栏显式进入。Portal 经 `ensureActiveRole` 本就偏好 assistant，随路由修复一并受益。
- **skill 绑定 = 能力（2026-08-30 用户铁律）**：需求分析（方案配置）本职属技术支持工程师，方案助手绑这个 skill 只是数据配置——**群内配置请求判给技术支持工程师是正确转接**（判官按名册 skills/职责）。给谁绑定 skill 谁就会，解绑即失去（回落普通对话，超出能力时按提示词口头提议转接）。禁止把「角色↔技能」写死在代码：能力路由全走 `colleagues[].skills`（DB），`DEFAULT_SKILL_BINDINGS` 仅新库种子不覆盖已有配置；测试锚 test_capability_follows_skill_binding。

E2E：私聊方案助手「我想要一台服务器，主要跑数据库」→ colleague=assistant 不劫持 ✓；群内「帮我算一下成本」→ 判官正确选 cost_analyst（带理由）✓。357 passed。

## 2026-08-29 定案：「卡住不回话」根因链（已修复）

1. **uvicorn --reload 重启窗口杀回合**（主因，铁证）：`--reload` 监听 backend 全树，任何代码编辑触发进程重启（本应用带全套启动迁移，重启 20-60s）；重启瞬间所有在途回合任务被无声杀掉（POST 已 200、用户消息已落库，回复蒸发）。此前"边改边测"的轮次全中此招——包括更早会话里用户「反复测不通」的体感。**纪律：用户测试期间禁止改 backend 任何文件；测试前确认日志无 reloading。**
2. **错误上报只有 WS 广播 + 应用日志黑洞**（已修）：main.py 接通 basicConfig；回合各失败路径（含取消）全部落日志；错误消息必达终态（落库，不再只广播）。
3. **空间意图前置分类器串在聊天主路**（已摘除）：办公室头像走位的 LLM 分类器曾挡在每条消息前面（误判即吞消息、多一跳 25s 延迟）；聊天主路现直达对话脑，office_intent.py 保留待画布入口重接。
4. **自由文本场景答非目录类型→提交死循环**（已修）：submit_registration 提交口前置目录词表校验，非目录类型拒绝并列出目录选项让模型当轮纠正；提示词同步「口语场景登记到信号槽或与客户确认目录类型」。实测全链路 68s：模糊输入→目录引导澄清→「深度学习训练」映射为「AI / 加速计算服务器」→选型→配件闸门选项卡。
5. react 循环 LLM 调用从默认 90s×2 收紧为 60s×2 + low 推理档（断连止损）；`_run_text_react_loop` 参数透传补齐。
6. 选项卡式追问（gaps）按设计只走 WS 推送不落普通消息——无 WS 客户端的脚本观测不到属预期，非卡死。

## 环境/红线

- Python：`D:\CPQ_Platform_V1\backend\.venv\Scripts\python.exe`；`PYTHONUTF8=1`、`PYTHONPATH=D:\CPQ_Platform_V1\backend`。
- 登录：admin / fA5zXkyWv_RyrAqe（不得删除/重置）。
- CC Switch 上限约 30-40 req/min；禁止并行大扇出；重任务一次只一个会话。
- 改动代码前先说明原因+方案并等批准；未获批准不提交。
- 诊断脚本：仓库根 `_diag_turn.py`（角色对话旅程 E2E，支持 JSON 旅程与 option_slot 点击）、`_diag_testrun.py`（引擎 test-run）。
- ⚠️ 后端**已去 `--reload` 稳定模式运行**（2026-08-29 起，launch.json）：改代码不再自动生效，必须**显式重启**后端才加载新代码；重启会杀在途回合，所以只在无测试进行时重启、每次重启要告知用户。重启=preview_stop+preview_start（端口占用时先 `netstat -ano | findstr :8000` 查 PID→taskkill //T //F）。


## 2026-08-31 定案：机型/配件 AI 接地（引擎语义层，阶段2/3）

- **动机（根因）**：kp_reason 节点配置了 list_kp_categories/select_parts/resolve_part_alias/compose_memory 等语义工具，但 `phase_kp_reason` 先前只跑确定性 `select_parts`——命中不了一律留 unmatched/spec_mismatch 当缺口，工具「只配不用」。
- **机型（已完成，phase_model_reason）**：force_complete 下把硬件信号拓宽到库内候选，交由 `_llm_pick_model` 受约束选型，落 `model_pool_broadened` 标注。
- **配件（本轮，phase_kp_reason）**：确定性 select_parts 之后，force_complete 下收集未命中/规格偏差行 → 按品类查 `KPRepository.get_by_category_with_specs`（series 适配池）→ 拼「需求原文+线索登记表+机箱能力+当前清单」事实喂 `_llm_pick_kp`（单次受约束，只许从候选 id 里选）→ `_apply_kp_ground` 校验 id 属候选、价格/数量取库值并写 `replacement_note`；无候选/非法 id/LLM 失败一律保留缺口，绝不硬顶。对话路径（force_complete=False）保持缺口交角色/用户决策。
- **验证**：backend 全量 372 passed（新增 7 条：`_kp_gap_rows`/`_apply_kp_ground` 缺口语义与非法 id 守卫、`_llm_pick_kp` chat_json 契约、`_kp_ai_ground`、`phase_kp_reason` force_complete 接地与对话路径保留缺口）。
- **待回退关注**：AI 接地为 LLM 旁路，失败/无候选是安全路径（保留缺口）；未在对话路径开启，行为可预期。

## 2026-09-01 定案：提示词/节点契约 DB 唯一权威（去种子化）

- 已删除种子文件：`skill_prompts_defaults.json`、`reasoning_node_defaults.json`、`workflow_intent_classifier.txt`（含旧 `office_intent.py` 死模块）。
- 新表（rules schema，DB 唯一权威）：
  - `skill_prompt_template`：一行一个提示词（role_prompt/extract_contract/gap_ask_prompt/price_rule_ok/price_rule_no/data_rule/plan_rule/gap_ack_template/stream_chat_contract）。前端「提示词」面板按行 GET /system-config/skill-prompts / PUT /system-config/skill-prompts/{slot} 直接落库。
  - `reasoning_node_default`：一行一个推理节点默认契约（input/agent_fill/model_reason/kp_reason/compose/output）。
- 读取端：`skill_prompts.load_skill_prompts()`、`reasoning_node_contract.node_defaults()` 只读这两张表，无种子回退、无模块常量兜底。
- 节点配置 delta-only：`reasoning_node_config` 只存相对默认的增量；`get_active_flow` 返回默认+增量合成生效值；`override_only` 保存时剥掉等于默认的字段。存量已一次性收敛，默认基线已提升为该部署真实生效配置。
- 启动：`init_rules_db` 调 `skill_config_bootstrap` 仅空表播种；运行后 DB 唯一权威、前端修改直接落库。
- `system_config.skill_prompts` / `reasoning_node_defaults` 两把 blob 已删除，代码零读取。

### 补记（2026-09-01）：功耗链家族关键词/校准字典彻底移除（引擎不做功率推断）

`candidate_search.py` 的引擎功率推断链（`_kp_signals` / `_estimate_system_load` /
`_suggest_psu_wattage` / `_infer_psu_wattage` 及 `_drive_kind`）已整体删除。它们用
`high_tdp_gpus` / `gpu_tdp_by_model` / `high_tdp_threshold_w` / `cpu_tdp_map` /
`mem_stick_w` / `mem_stick_w_by_cap` / `sata_drive_w` / `nvme_drive_w` / `nic_w` /
`raid_w` / `sys_base_w` / `default_cpu_tdp` / `psu_standard_w` / `tiers` /
`no_gpu_wattage` 等词表/校准字典来“猜”整机功耗与 PSU 瓦数，违反“AI 唯一大脑 +
数据表只存业务事实”宪法。

- 现在 `build_plan` 的 PSU 瓦数只取 AI 语义层/人工传入的 `psu_wattage`（来自
  `ext.psu.wattage`，经 `psu_override_enabled`/`psu_wattage_source` 控制），再按
  `baseline.psu_wattages`（机型物理支持档位，业务事实）用 `_clamp_psu_wattage` 收敛；
  未给值 → 留空（`bom_template_eval` 明确“PSU 瓦数未给 → 留空手填”）。
- `compose_plans`（`skill_node_runtime.py`）不再调用 `read_node_rules` 组装功耗规则，
  `build_plan` 签名去掉 `rules` 参数。
- 测试：删除 `test_kp_signals.py`（测已删 `_kp_signals`）；`test_base_config_capability.py`
  重写为只测 `_clamp_psu_wattage`；`test_bom_compare.py` 删除 `POWER_RULES` 与
  `test_psu_inference_memory_capacity_aware`。
- 保留：`_clamp_psu_wattage`（把传入值收敛到机型支持范围，属业务事实）。

### 补记（2026-09-01）：去种子化丢失的 6 个提示词槽已回填

`price_rule_ok/price_rule_no/data_rule/plan_rule/gap_ack_template/stream_chat_contract` 六个槽在旧代码里是
`skill_chat.py`/`agent_react.py` 的**硬编码字符串**（不在旧 `system_config.skill_prompts` blob 中），去种子化后误留空。
已从 git HEAD 恢复原文并回填 DB；`skill_config_bootstrap.SKILL_PROMPT_SLOTS` 同步携带这 6 份模板作空库播种。
验证：`tests/` 全量 334 passed, 1 skipped；前端 `npm run build` 通过。
