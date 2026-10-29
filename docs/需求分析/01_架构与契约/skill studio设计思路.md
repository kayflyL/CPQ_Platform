总体原则：唯一AI大脑；拒绝硬编码；拒绝机械式正则匹配；前端可配置，拒绝黑盒运行

> 最后更新：2026-09-12（指令唯一出处收敛为左栏单一家：节点层 prose 清除、node_mission 退役）

## 宪法 → 守卫（防返工映射）

宪法是判定尺，不是口号：每条都必须有自动守卫按住，否则下一轮又会冒出来。守卫文件
`backend/tests/test_constitution.py`（含一条元测试：条款与守卫必须一一对应，条款挂空守卫 = 红）。

| 条款                          | 强制方式                       | 守卫测试                                                                                                                                                                                                                                                                                       |
| --------------------------- | -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| C1 唯一 AI 大脑：模型看到的「怎么做」只来自左栏 | 代码侧机制文案棘轮（只许减不许增）+ 提示词唯一出处 | test_mechanism_prose_only_shrinks / test_no_injected_protocol_constants_in_code / test_node_prose_layers_are_purged / test_no_reverse_writer_pushes_prompt_text_into_db / test_live_system_prompt_is_built_from_db_text / test_migrated_rules_have_a_left_panel_anchor |
| C2 拒绝硬编码：换节点/换工具 = 换配置      | 编排壳无节点名分支 + 节点注册表是唯一扩展点    | test_orchestration_shell_has_no_node_name_dispatch / test_registry_declares_every_brain_node / test_register_is_the_only_extension_point                                                                                                                                                   |
| C3 拒绝机械式正则匹配                | 行/候选按身份归并；措辞漂移一律拒收不猜       | test_stamp_is_idempotent_and_never_merges_by_text / test_resolve_row_ref_rejects_drifted_wording_instead_of_guessing / test_ask_user_rejects_drifted_wording_instead_of_guessing / test_select_parts_rejects_drifted_row_ref_without_declaring_a_row                                       |
| C4 前端可配置、拒绝黑盒               | 任务规则改左栏即生效；暂停与事件只带事实    | test_kp_turn_prompt_is_drawer_driven_and_rows_carry_answers / test_pause_payload_is_facts_only / test_every_pause_broadcast_goes_through_single_emitter                                                                             |
| C5 下游永不回填上游                 | 属主落定即冻结（只读视图落在类型上）         | test_freeze_flags_downstream_write_and_ignores_owner / test_frozen_doc_view_blocks_every_write_path / test_downstream_node_turn_gets_readonly_registration_doc                                                                                                                             |
| C6 配置即真相                    | 左栏/配置层不许留已改名或已退役的工具名       | test_left_panel_uses_current_tool_names                                                                                                                                                                                                                                                    |

规则只有一个家：左栏「任务规则」（`rules.reasoning_flow.graph.manual_rules`）。2026-09-12 起
节点抽屉/`rules.reasoning_node_default.config` 不再承载指令 prose（description / goal 全清，
原活指令增量并入左栏规则 13/14/15/24）。代码里再出现成段「怎么做」就是违规——`PROSE_BASELINE`
记的是当前欠账，只许降、不许升。

**2026-09-11 P5-A/P5-D 收口后：技能链路 + 角色层全部立到「唯一出处」，代码侧兜底清零。**

- 提示词只有两个家：**员工自己的提示词**（`rules.system_config.ai_colleagues` 里每个角色的 `system_prompt`，
  Manage Teams · 员工 · 提示词可改）与**技能链路的左栏任务规则**（`rules.reasoning_flow.graph.manual_rules`；
  2026-09-12 起节点抽屉只留机制配置，不再承载指令）。两个家之外再出现提示词 = 违规。
- **2026-09-11「提示词（高级）」整块退役（+ P5-D 兜底清零）**：`behavior.brain.{system_prompt,user_rule,minutes_prompt}`、
  `behavior.mission.{agent_system_prompt,lead_system_prompt}`、`behavior.charter` 从 DB 全删，前端行为编辑器整块删除——
  它与「每个员工都有自己的提示词」完全冗余，且是一处不可见的第二套。转接判官（`dispatch_judge`）/ 记忆抽取
  （`memory_extract`）两个内部工序改为注入**相关员工自身**的 `system_prompt`（不再有独立 `charter`）。
  `_left_panel_text()` 仍纳入 `system_config.ai_colleagues`（员工提示词在其中），但已不含 `behavior` 文本；
  `MOVED_RULES` 里 9 条挂在这些已退役键上的锚点**有意撤销**（口径见 `docs/需求分析skill-技术架构.md` §19.4）。
  代码里不再有任何兜底提示词常量：`AGENT_SYSTEM_PROMPT` / `NATIVE_TOOL_SYSTEM_HINT` / `_DEFAULT_CHAT_SYSTEM_PROMPT` /
  `llm_client.DEFAULT_SYSTEM_PROMPT` / `ai_colleague_service._DISPATCH_SYSTEM_PROMPT` / `colleague_memory_service._EXTRACT_SYSTEM` /
  `api/assistant._DEFAULT_OPENING` / `skill_registry.DEFAULT_SKILL_LIBRARY`（含零调用方死码）全部删除；配置为空 = 该处不注入。
  守卫升级：`test_no_code_side_fallback_prompts` 扫描范围 `app/services/*.py` → `app/**/*.py`（含 `api/`），
  `_DEFAULT_OPENING` 进禁用符号表；`MECHANISM_FILES` / `PROSE_BASELINE` 去掉已删的 `office_behavior_config.py`。
- 判断「该留代码还是搬左栏」的尺：**事实层**（状态词、字段名、返回字段、原因码）留代码；
  **契约层**（参数必填、越界拒收、白名单）留插头；**规则层**（先调谁、该不该问客户、怎么措辞、
  不许丢弃）必须住配置层。


# 整体设计：
我们的系统现在设计是AI角色唯一大脑，workflow只是告诉AI角色，你应该走哪些流程做事情，每一步输出什么东西给下游。

而且整个需求分析skill对应的是商机详情页的前两步，agent fill对应线索登记，机型选配和配件选配对应方案配置，他们的目标输出物就是这两个商机详情页步骤对应的表格。

也就是说AI相当于在模拟人干活，人拿到用户线索，先分析需求，登记，然后传递给下游方案配置节点，方案配置技术员拿着需求表去配服务器。

由于对应的是真实业务节点的表，所以天然比如线索登记表填完，到下游就不会被回填了。

AI角色配置skill后，获得该skill的能力，用户和角色对话过程中，AI角色根据需要选择是否调用skill，这里参考主流agent如claude code，chatgpt调动skill的模式。

调用skill后，AI角色可以拿到skill studio 具体某个skill编辑器里的左侧栏的任务规则，这是整个skill要做的事情。中部是workflow，由一系列节点组成，AI角色接下来需要按节点编排依次执行任务。当开始任务流程时，AI角色根据skill里规划的步骤一步一步完成工作，中间有不清晰的会提问，提问应该是AI角色根据上下文需要，以及节点目标组织内容提问，而不能硬编码话术写死在各个节点里。会话窗口会显示流程步骤，中部栏会显示实时进度，比如当前运行在哪个节点了，在该节点的实时输出物，完成后可在中部栏节点查看输出物详情。

每个节点都有节点抽屉，用来配置AI角色在该节点需要完成的目标输出物，以及可调用的工具、数据、规则等资源，节点抽屉有两层：

1 目标层：节点的目标输出物，可以是表格、文档、PPT甚至是图片。这一层同时也承担输出给下游的数据，下游拿到上游节点的输出物后开始工作。目标层典型的输出物是表格，表格输出物的设计是左侧是字段，右侧是表格预览，字段可勾选是否必填反问，如果勾选，那AI角色必须填这个字段，分析不出来的时候一定要反问用户。

2 资源与权限层：包括数据、规则、工具。

2.1 数据：告诉AI角色，数据从哪里来，不要自己编，在本系统中，数据来源于系统内部，代表性的有服务器目录、配件库等，理论上所有页面、所有数据都可以拿到。

2.2 工具：比如有哪些机箱可以选，去机箱目录里拿数据，有哪些配件可以选，去配件库拿。去拿这些数据，肯定不能直接把大量数据灌给AI角色，因此设计了工具来解决。AI角色可以调用哪些工具，因为每个AI角色自身是绑定了工具的，但skill是公用的，也就是说可以配给任何一个AI角色，但这个AI角色不一定有这个skill层里涉及的每一个工具，所以这时候会在任务进行过程中，只要绑定了这个skill的角色，在任务几个步骤推进过程中，就自动可以使用那个工具，即使AI角色本身没绑定这个工具。

2.3 规则：系统主要功能是服务器配置，规则层是告诉AI角色，服务器怎么配，比如根据CPU决定机箱平台，当用户选择兆芯系列芯片时，机箱就得选Polaris的，当用户选择AMD系列芯片时，机箱就得选Orion系列的，等等，这一点需要慢慢补充，当然这个前提是搭好底座，规则底座入口就在策略中心-需求分析里。

系统处于建设阶段的时候，数据、工具、规则，都是不完整的，因此我们需要先设计好主干“插座”，然后再做插头，插头可以后补，重要的是系统先跑通。

# 需求分析skill

这个skill主要是用来根据用户输入的自然语言需求，由AI角色来分析需求，完成服务器方案配置，整个skill设计分为以下五步：

[输入] -> [需求分析] -> [机型选型] -> [配件选配] -> [BOM 组装] -> [输出]

## 需求分析

该节点用来理解用户需求，并填写线索登记表，该表单对应商机详情页线索登记节点的表。从设计上，哪怕线索登记表登记的需求非常模糊，比如只有一句话：需要通用计算服务器，AMD平台的。那配件选配节点也要给出配置的。**AI = 配置器**（读需求→决定配什么→去库找→填进目标输出表）。

注意，线索登记表在该节点登记完后，不许再后面节点回填修改，比如都到了

## 机型选型

机型选型配节点对应的目标层是商机详情页方案配置环节方案配置表中的L6部分，AI角色智能分析需求，根据线索登记表选合适的机箱。

## 配件选配

配件选配节点对应的目标层是商机详情页方案配置环节方案配置表中的KP部分，根据线索登记表和上游传来的机箱，来选择适配需求和机箱的配件（配件库配件有的有明确的适配机型，要用工具拿到这个数据来选配件），步骤如下：

1） AI角色拿到线索登记表，分析用户需求；
2） AI角色调用工具，从配件库里找配件，看什么样的配件能满足用户需求；
3） AI角色会看目标输出表，把选出来的配件填入配件表中。

切记，AI角色是智能的分析需求，根据需求分析登记表来挑选配件，而不是拿着线索登记表去做正则匹配，这里典型场景分两种情况。

一种是用户需求很模糊，比如用户只说需要AI服务器，那么AI角色要根据自己掌握的AI知识，看着目标输出的表格，去分析AI服务器最关键的是要配什么，从配件库里挑配件，挑好后推荐几种选择给用户，同时选项里也给用户自己从配件库对应类型的配件里挑件和调整数量的选项，每次问一类，注意是有选择的问，比如AI服务器就重点问GPU，而不是把目标输出物的表格的字段都问一遍。

另一种是用户需求很清晰，给出了配件具体规格，那AI角色拿这个规格去配件库查，查到了就填上。差不到发现缺失，那就根据该配件性能，选能满足该性能的配件推荐给用户选。

## BOM组装

将机型选型和配件选配的内容，组成完整的方案配置表。

## 输出

将方案配置表输出为方案配置卡，通过聊天窗口推送给用户。

# 进入skill的流程

AI角色先正常和用户聊天，比如技术工程师角色，他主要就是帮助用户出服务器配置方案，因此这个角色的指令（大脑）里就写了他的主要任务。他在和用户聊天过程中，会引导用户配置服务器，并收集这个过程中用户输入的服务器配置，用户确认配置服务器后，就开始需求分析skill流程（AI角色绑定了这个skill，通过skill的描述就知道调用skill）。

在开始需求分析skill之前，AI角色-技术支持工程师不会去读需求分析skill节点里的东西，而是只引导（因为他的主线任务就是配置服务器方案），而用户如果没明确要配置服务器，那么AI角色就只会根据自己的指令，大脑以及能获取的数据、工具等和用户正常对话，提供服务。

进入需求分析skill流程，有两种情况，如果用户在在其他地方比如方案助手聊天框和AI角色对话，那是先正常聊天，检测到配置服务器需求时候（和skill的描述对应上了），AI智能判断出来用户要配置服务器，那么会开始需求分析skill，开始任务，就像chatgpt会规划任务，只是我们的设计不需要AI每次重新规划任务了，也是防止幻觉。

用户确认后开始需求分析skill流程后，第一步先根据用户上下文输入的内容开始agent fill节点，遇到信息不足，在这一步反问。而在真正进入任务之前，AI角色是不会碰需求分析skill里的节点内容的，更不会提前填表，进入任务之前，AI角色和用户之间就是正常聊天。

第二种情况是在skill studio右侧那个试运行，在那里应该直接开始需求分析任务。

联网检索到权威资料了（OpenAI Agents SDK 官方文档、MCP 规范原文；Anthropic/Google 官方域名在本环境被区域/Cloudflare 拦截，已用失败原因注明）。下面是按主流 agent 设计 + 你四点补充后完善的方案。

## 权威依据（引用《2026-09》在线的原文）

- **OpenAI Agents SDK `docs/tools.md`**（官方仓库 raw 提取，HTTP 200）：
    - `description` 取自函数 docstring；每个参数的描述与约束用 Pydantic `Field(ge/le/pattern/description)` 生成，**约束写进 schema，不写进长文**。
    - 工具级 `timeout`，默认 `timeout_behavior="error_as_result"`——超时/异常**以模型可见消息返回，让模型自己恢复**，而不是崩掉循环。
    - `failure_error_function`：工具崩溃默认给 LLM 一句"出错了"，`None` 才重新抛。
    - `needs_approval`：**审批门 = 人类在环**，运行暂停、`approve/reject` 后恢复。
    - `is_enabled`：运行期按上下文过滤工具；`defer_loading + ToolSearchTool`：工具面大时不一次灌给模型，按需加载。
- **MCP 规范**（raw 提取，HTTP 200）：工具由模型按上下文自动发现/调用（model-controlled）；**必须始终有人类在环、可拒绝**；UI 要标明暴露了哪些工具、调用时给视觉指示、对操作弹确认；`inputSchema`(JSON Schema) + `outputSchema`(结构化结果)；错误用结构化的 `isError` 返回；安全走**最小权限**。
- Anthropic / Google 官方页被拦，但其公开写过的核心原则与上面一致：**`description` 主要告诉模型"何时该用"**、`input_schema` 严格 JSON Schema、枚举/约束收口。

> 结论：主流 function calling 的"工具设计"就三件事——**短而准的 description（含何时用）+ 严格 JSON Schema（约束放字段里，不放长文）+ 人类在环（审批/确认）**。我们现在的反例正是：长文 description 全喂模型、约束写在散文里、审批/权限和工具定义分离。这次重构就是对齐这三件事。

## 我对你四点的回应

1. **按主流方式设计** —— 是，按上面三条原则，但分两条腿走：先把**工具定义**改成主流形态（summary/schema），再补**调用通道**（原生 function calling）。我建议两条腿都要，但先后落地。
2. **我来决定** —— 关键决定如下：
    - `summary` 由我按现有 description 提炼，**保留"何时用 + 关键守则"**，不超过 2 句；`parameters` 里的默认值/枚举/约束保持在字段层。
    - 默认 `tool_channel = "auto"`：能力档案支持且一次性探测通过 → 用**流式原生 function calling**；否则回退**文本式 ReAct**。保留 `tool_channel = "text"|"native"` 显式开关兜底（应对 cloudprime 代理"通道轮盘"卡慢——这是当年弃原生改文本的已知坑，所以做成开关+A/B 再默认）。
    - 审批门对齐 OpenAI `needs_approval`：现有 `approval_required` 工具保持；UI 加"工具调用指示 + 确认弹窗"。
3. **阶段A是什么** —— 是一个**可以独立交付、低风险、可回退**的下限切片，见下面【阶段A】。
4. **收敛为工具层** —— 同意。资源与权限层 = 工具层：数据源随工具 `data_sources` 自动派生（前端只做派生展示），规则在「策略中心-需求分析」统一维护，不再单列"数据/规则"。

## 工具契约（目标形态）

```
{
  "name": "select_kp_parts",        // 蛇形、动词开头、职责单一
  "summary": "把未匹配的部件行锁定为库内真实料号；仅配件选配环节使用。",   // ▲ 唯一喂模型的字段
  "description": "（原有长文，全部移到这里）",                            // ▲ 只进前端目录/抽屉详情/hover
  "parameters": {                    // 严格 JSON Schema
    "type": "object",
    "properties": {
      "row":       { "type": "string", "description": "候选池给出的 row 原文" },
      "part_id":   { "type": "string", "description": "候选池内料号 id（优先）" },
      "qty":       { "type": "integer", "description": "件数（如 64G×12 → 12）" }
    },
    "required": ["row", "reason"],   // 必填收口
    "additionalProperties": false    // strict：多余字段拒绝
  },
  "output_schema": {},               // 可选：结构化结果声明
  "data_sources": ["kp_pool"],       // 权限最小集，随工具自动派生
  "category": "selection",
  "default_enabled": false,
  "approval_required": false,
  "timeout_ms": 15000                // 工具级超时，超时以模型可见消息返回
}
```

规则：`summary` 缺省回退 `description`（老数据不炸）；`additionalProperties:false` 即 OpenAI `strict` 语义，前端配置的"必填反问"仍由参数层/字段契约决定，不变。

## 阶段A（本次实现核心）

只动**工具元数据层**，不改运行时主通道。产出：

- 全部 ~22 个工具补 `summary`，`description` 留作前端详情；`parameters` 补 `required`/`enum`/`additionalProperties` 收口。
- `ToolRegistry.schemas()` 用 `summary`、`agent_react._format_catalog` 用 `summary`——system prompt 大幅瘦身（这是当前"长描述喂给 AI"问题的直接修复）。
- `tool_catalog()` / `build_tool_registry()` 透出 `summary`+`description`；数据源随工具派生。
- 前端 `ReasoningNodeDrawer.vue`、`NodeResourceBindings.vue`：展示 `summary`（紧凑），`description` 入 hover/详情；资源与权限层改名/收敛为**工具层**。
- 补测试（schemas 用 summary、catalog 透出 summary、约束收口），保证 376+ 用例绿。
- 影响面：**低**，可回退；即刻收益：提示词瘦身、前端清爽、与主流工具定义一致。

## 阶段B（原生 function calling 主通道，建议单独排期）

- `llm_client.stream_agent_chat` 解析**流式 `tool_calls` 增量**（按 index 累积 `id/name/arguments`），yield 事件。
- `run_stream_chat_loop` 接原生 tool_calls → `registry.execute` → 结果以 `role:"tool"`+`tool_call_id` 回填继续；并行 tool_calls 支持。
- 能力探测 + 文本式 ReAct 兜底（`LLMNativeToolsUnsupported`/探测失败/显式开关）。
- 审批门、工具级超时（`error_as_result`）、UI 工具调用指示/确认。
- 风险：**高**（cloudprime 代理行为不可控），需先在代理上做原生 vs 文本的 P50/P95 耗时 + 成功率 A/B，通过后默认 `native`，否则默认 `text`。

## 落地顺序建议

先做**阶段A**（安全、立刻对齐主流工具定义）；**阶段B**单独排期、以代理 E2E 为闸门。这样既符合"参考主流 agent 设计"，又不会把已稳定跑通的技能链搞坏。

确认这个方案（阶段A 直接开工、阶段B 排期），我就开始实现。
