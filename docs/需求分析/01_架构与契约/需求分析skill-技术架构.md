# 需求分析 Skill —— 技术架构（现状快照）

> 生成时间：2026-09-10。本文描述**当前代码实际形态**，不是设想。行号会漂移，定位以符号名为准。
> 最后更新：2026-10-12（query_parts 双模式：流程锁换权限锁——流程外开放「日常浏览模式」（只读检索、limit 收窄 10、rows 不开放、返回 mode=browse），价格列仍由 price_access×用户 RBAC 双层门控；配套 ai_read 视图落地，opportunities 域对 query_data 只暴露排除 ai_office/deleted 的视图，详见 data_boundary._AI_VIEW_MAP）。
> 历史：2026-09-13（自选配件通道回归：整体卡常驻「我自己逐项挑」注入项 + select_parts `part_required` 契约错误 + phase_kp_reason 归属收口放宽（§10/§22/§24）；自选 e2e 10 轮 229.9s 收口（9 卡全行绑定、7 点击 kp_manual_pick 落锁）；同日早些：左栏任务规则压缩重写 24 条 4314 字 → **11 条**（机制细节归工具契约、规则只留编排与纪律），重编号 15/19/13/20→7/8/6/10；A1 与 A1 委托版 e2e 双达标（3 轮 2 卡 100.7s / 2 轮 1 卡 72.6s）；整单委托落地 delegation=full（§9）；P2 落地（pick_all→kp_accept_recommendations 批量晋升 + 信号双出口收口 §10））。

## 0. 一句话

**编排壳（壳）不认识任何具体节点；节点靠"插座插件 + 抽屉插头"接入；每一步能不能过，由一层闸门裁决；产物是真实业务表的唯一一份，上游产物对下游只读。**

---

## 1. 分层总览

| 层 | 职责 | 代码位置 |
|---|---|---|
| 能力层 | Skill（能力包/使用说明）与 Workflow（任务流）分离 | `app/repository/skill_catalog_repo.py`、`frontend/src/views/office/AiOfficeManagement.vue` |
| 编排层 | 单回合主循环、步进闸门、终检 | `app/services/skill_turn_engine.py`（`run_skill_agent_turn` → `_SkillTurnRuntime`） |
| 节点层 | 每个节点一个插件（插座）；引擎不写节点分支 | `app/services/skill_node_plugins.py` |
| 产物层 | 抽屉声明的产物槽 → 构建器 → 行整形 | `app/services/skill_node_artifacts.py`、`skill_target_contract.py` |
| 状态层 | 节点私有状态分区 + 上游冻结文档 | `app/services/skill_node_state.py` |
| 取件层 | 按需取件的检索/召回/落地 | `app/services/part_selector.py`、`skill_tools_kp.py`（检索）/ `skill_tools_open.py`（只读钻取）/ `skill_tools_select.py`（落料） |
| 工具层 | 原生 function calling schema | `app/services/agent_tool_specs.py`（实现：`skill_tools_*.py`） |

需求分析流共 6 个节点：`input → agent_fill → model_reason → kp_reason → compose → output`（键序由 `rules.reasoning_node_default` 权威给出，见 `app/services/reasoning_node_contract.py`）。

---

## 2. Skill 与 Workflow 分离

- `skill_catalog` 的条目带 `type`（`skill` / `workflow`）+ `workflow_key`。
- **Skill = 能力包**：能被角色绑定，提供"什么时候用我"的使用说明；它本身不是任务流。
- **Workflow = 任务流**：绑定到 `reasoning_flows` 的一条真实 flow（需求分析 = `flow_id=125 / skill_key=requirement_analysis`）。
- 员工页（`AiOfficeManagement.vue`）分两个 tab：`Skills` / `Workflows`，只有绑定了对应任务流的角色才会在对话里显示该流程入口。
- 入口是显式「+」（方案助手浮动聊天框），**不做"一检测到意图就自动起任务"**。

## 3. 节点插件（插座） vs 抽屉配置（插头）

`DefaultNodePlugin`（`skill_node_plugins.py:29`）定义插座的全部钩子，默认空实现：

- `bridge_ctx(engine, ctx)` —— 把上游产物桥接进本节点上下文
- `artifact_contract(node_cfg)` —— 本节点产物契约呈现给大脑的文本
- `wire_result(engine, result)` —— 大脑调完工具后，把结果落进本节点状态
- `enrich_ask_gap(engine, gap, ask)` —— 提问卡内容加工
- `extra_ask_options(engine, ask, row_key)` —— **插座给"大脑漏给的选项"补全**（不许编料号）
- `delivery_gap(engine)` —— **出路一就绪就即刻交客户**（例：机型候选池）
- `stuck_gap(engine)` —— **只在编排壳确认该步真的卡住之后才调**，不抢大脑自己提问

注册表：`register()` / `plugin_for()` / `first_delivery_gap()` / `first_stuck_gap()`。编排壳只认注册表，**不认识节点名**。

现有插件：`_FillNode` / `_ModelNode` / `_KpNode` / `_ComposeNode`，其余节点落 `DefaultNodePlugin`。

**插头**（可换，不动代码）：
- `slot` = 装什么产物（来自节点抽屉 `target.artifacts[].slot`）
- `kind` = 怎么渲染（`declared_slot` / `resolve_kind`，`skill_node_artifacts.py:238/256`）
- `tools` = 本节点可调用哪些工具（`effective_node_tools`，`skill_plan_runtime.py:102`）

已删除的硬编码兜底：`DEFAULT_KIND_BY_NODE`（现有守卫测试 `tests/test_node_artifact_contract.py:69` 断言其不存在）。

## 4. 产物槽与契约

- `BUILDERS`（`skill_node_artifacts.py:228`）：`requirement_slots` / `kp_table` / `l6_chassis` / `plans` / `bom_scheme` / `requirement_text` 等构建器。
- `LIVE_EMITTERS`：登记表这类需要边填边推给前端的产物。
- 契约文本由产物 schema 生成（`format_contract` / `format_table_contract` / `format_requirement_slots_contract`），**列定义来自真实业务表**，没有全局字段词典。
- 行整形 `shape_rows` / `shape_table_rows` 只保留"可见列 + 必要的内部键"。
- 校验：`broken_column_specs` / `unresolved_columns` / `validate_artifact`。

## 5. 编排壳：单闸门

一个回合（`run_skill_agent_turn` → `_SkillTurnRuntime.run`，`skill_turn_engine.py:610`）的主干：

1. 引擎自动 `begin`（确定性预处理：候选池/行就绪 + 上下文桥接，`_engine_begin_step`）。**模型不允许调 begin/end/submit**（`scoped_protocol`，`skill_turn_engine.py:328`）。
2. 组装本回合大脑指令：`persona + manual_rules(左栏"使用说明") + scoped_protocol + steps 清单 + 上下文块（线索登记表 / brain_notes / 待选型行清单）`，工具 schema 由原生 function calling 提供（`skill_turn_engine.py:321` `_build_step_call`）。
3. 大脑回合，调工具；`wire_result` 把结果落进节点状态。
4. 步校验 `validate_step_end(engine, step_key)`（`skill_plan_runtime.py`）+ 闸门裁决 `step_gate_verdict(pending, step_key)`（`skill_turn_engine.py:508` 调用 / `:34` 定义）：
   - `advance` → 标 done、推进下一步
   - `pause` → 有卡用卡：`first_stuck_gap` 优先，其次 `first_delivery_gap`；都没有才退回零选项 `brain_ask`
   - `deliver`
5. 冻结与越权检查：`doc_freeze_violation` → 记 `click_errors`。
6. 终检 `final_gate(engine)`（`skill_plan_runtime.py:398`）：产物齐 → `output` 交付；缺 → `_system_gap() or first_stuck_gap(engine)`。

**校验失败不出机制文案给客户**：机制 hint 只回喂大脑，客户只看到有选项的卡。

## 6. 状态分区与冻结文档

`skill_node_state.py` 把状态切成两块：

- `node_state`（`NODE_STATE_KEY`）：**节点私有**。`kp_reason` 用自己的分区——`picks` / `recommend` / `config` / `absent` / `waived` / `row_answers`。
- `frozen_docs`（`DOC_SNAPSHOT_KEY`）：**上游只读快照**。`DOC_OWNER_BY_NODE = {"agent_fill": "requirement_slots"}`——线索登记表的唯一写入者是 `agent_fill`。
  - `FrozenDocView`（`skill_node_state.py:144`）：非属主节点拿到的是只读视图，写就抛。
  - `mark_doc_frozen`（落定）/ `freeze_snapshot`（快照）/ `doc_freeze_violation`（越权检测）。
  - **下游永不回填**：`kp_reason`、`compose` 只能读线索登记表。

## 7. 工具层（原生 function calling）

`agent_tool_specs.py` 的 `_TOOL_SPECS` 是唯一权威，共 13 个：

| 工具 | 用途 |
|---|---|
| `fill_requirement` | 登记环节：把客户已明确表达的需求逐项写进线索登记表 |
| `choose_model` | 机型选配：从系统候选池锁定机型（池外拒绝；决不了就别调） |
| `query_parts` | 配件选配·精确通道：已知配哪类件，按结构化规格过滤；**双模式**（2026-10-11）：流程内=选配（rows 批量），流程外=日常浏览（只读检索 limit≤10，rows 不开放，mode=browse），价格列恒走 price_ok |
| `inspect_parts` | 配件选配·统一只读钻取：action=part 看单件完整规格 / row 看单行决策上下文 / category 看类目画像 / grep 扫全库定位词（零写入，命中与样例均非候选） |
| `select_parts` | 配件选配·落地：把登记行锁定为库内真实料号（按「类目+料号名」回库核对） |
| `ask_user` | 把需要客户决策的问题升格为结构化选项卡 |
| `catalog_search` | 查在售目录（类型/机型/配件） |
| `search_cases` | 检索历史选型配置案例作为接地参考 |
| `query_data` | 数据边界内只读 SELECT |


配件检索这一列按「广搜 → 导航/定向 → 点开看」分层（对齐 Mistral Agentic Search 的
`search` / `navigate` / `grep` / `open`）：`query_parts` 负责把料**找出来**
（只去库读、不写检索留底）；`inspect_parts(action=category)` 负责**看类目结构**（该类目有哪些
specs 字段、值域长什么样，把猜字段变成看字段）；`inspect_parts(action=grep)` 负责**拿一个词扫全库**
（定位型号/编码落在哪个类目哪个字段）；`inspect_parts(action=part|row)` 负责把**已经找到的**料/行看全
（只读，零去库）——模型不必为了看一眼完整规格再发一次广搜。钻取工具一律只读（2026-09-12 起没有任何检索
留底/接地索引）：能不能落地由 `select_parts` 按「类目+料号名」当场回库核对决定。

已删除（禁止回归）：`submit_registration`、`begin_step` / `end_step`、`build_plan` / `cost_breakdown` / `quote_draft`、文本式 ReAct 通道、`force_complete`。

两处 2026-09-10 的订正（都在检索侧，属「广搜 → 点开看」这一层的收尾）：

- `query_parts` 加了**死参数** `refresh`（schema 里有、全链路无实现读取），其描述「默认复用已检索索引」
  与 2026-09-07 起的「累积升级、只增不减」实现相反，会误导模型以为能强制重查 —— 已删除该参数，
  并把函数 docstring 订正回真实语义。
- 已退役 `suggest_parts`（2026-09-12）：原先“宽泛探针/跨类目找料”的职责由
  `inspect_parts(action=category)`（看类目结构）、`inspect_parts(action=grep)`（扫全库定位词）和 `query_parts(rows)`（按行召回）承接，
  不再保留独立工具。
  零召回时回 `note` 明确「把用途翻成库内数值/型号词（万兆→10G、千兆→1G）或改用
  `query_parts(category=...)` 看库内 `spec_keys`」。真语义召回仍挂账（见 §14）。
- 新增**只读**导航/搜索动作（对齐 Agentic Search 的 `navigate` / `grep`），并收敛为
  `inspect_parts(action=category|grep)`：category 回类目的字段画像（每个 specs 字段的出现件数/去重取值数/取值样例/
  `kind`(numeric|text)、库内件数、价格区间、命名样例；已锁定系列时另报「适配本平台的件数」，
  全类目都不适配就明说「不适配本平台」而不是「库里没有」）；grep 字面/正则扫全库，
  回「哪颗料、哪个字段、命中的片段」与类目分布，并给一个 `suggest_next`（把命中词变成候选的
  `query_parts` 调用）。两者都只读、不写状态——能不能落地由料号名回库核对决定。
  回归：`backend/tests/test_open_category_tool.py`、`backend/tests/test_grep_parts_tool.py`。

## 8. 配件行的三个结局（`kp_reason`）

| 结局 | 语义 | 落点 |
|---|---|---|
| **picks** | 锁定库内真实料号，客户已确认 | `KP_PICKS` |
| **absent** | 客户明确说这类不配（如本机不要 GPU） | `KP_ABSENT` |
| **waived** | 客户点名要某型号但**库内无料**，客户已知悉并选择"保持原需求" | `KP_WAIVED` |

- **不许编料号**：`_row_pick_options` 当场按行描述回库召回候选（`part_recall`，2026-09-12 去台账）。库里召不到 → 一张卡都不产。
- 走量兜底的两个前提同时成立才给「保持原需求」：① 该行客户点名登记过（`kp_registered_specified`）；② 该行点名的型号按**料号名**回库精确核对查无此名（`no_such_part`）。
检索零命中的两种真话：库里确实没有这个料号名（`out_of_scope` / `no_such_part`）、库里有但不适配当前机型平台（`scope_note`，`data_tools.py:42`）。
- **行引用 = 引擎铸造的 `row_id`**（P3）：行卡、pick、豁免、行回答一律按 `row_id` 落键；类目由**身份**解析（`part_selector.row_ref_meta(ref, parts, ledger)`：`row_id` → `origin` → 精确行键三档，不猜文本），不再从行引用字符串里切竖线。旧线程里留档的复合行键 `类目|描述` 仍兼容（**数据兼容分支，不是文本猜测**）。详见 §17。

## 9. 前提闸门（目录字段）

`slot_contract.py`：

- `unconfirmed_premise_fields(ext)`：目录维度（平台/系列/形态…）里**AI 推的、客户没申报**的字段。
- `customer_stated`（`apply_structured_slots(..., customer_stated=...)`）：客户原话里说过的字段直接落，不算推断。
- 推断字段在进入下游节点前必须先跟客户确认；客户说过的**不必反问**。
- **整单委托豁免（`blanket_delegation(ext)`，2026-09-13）**：客户原话明示全权委托（「一切你定/完全按推荐/你看着配」）时，大脑经 `fill_requirement(delegation="full")` 申报（与 `customer_stated` 同一溯源自报模式，只认申报不猜），`ext.delegation="full"` 后：
  - 前提闸门放行——推断的类型/平台由大脑代定，复述里说明依据，**不再逐项出确认卡**（用户定调：不然系统一点智能性都没有了）；连带机型步的前提拦截同源放行。
  - 确认收敛到**整体落定卡一次完成**：大脑把代定的类型/平台写进卡片 desc 首行（左栏规则 7/8），客户点「全部按推荐落定」时 `confirm_registration_on_bulk_click(ext)`（`skill_chat.py` 点击钩子调）把已填目录字段快照进 `confirmed_slots`（机型维度除外，走 `choose_model` 口径）；点后大脑改值即失效重求证（confirmed_slots 值失配语义不变）。
  - 实测（A1 委托版 e2e）：3 回合 2 卡 → **2 回合 1 卡**（仅整体卡），类型/平台/机型确认卡 0 张，144s 收口出 21 行整机方案。

## 10. 信号的唯一解释出口

`ask_option_signal(row_key, o, ask_slot, category="")`（`skill_plan_runtime.py:217`）：

- 选项带 `pick` / `absent` / `waived` / `qty` 等信号 → 转成对应的节点状态写入。
- **套装整体接受项**（`pick_all=true`，2026-09-13）：「全部按推荐落定」装不下逐颗料的 `pick`，走专用批量晋升信号 `{"kp_accept_recommendations": true}`（优先于行绑定）；点击后 `slot_contract.apply_structured_slots` 把 `KP_RECOMMEND` 全部行一次性晋升 `KP_PICKS`（点击=客户亲口确认的多行版），并清空推荐态。
- **整体卡常驻自选入口**（2026-09-13 晚）：P2 批量流收口后快乐路上只有整体卡，行卡不再出现，客户「从配件库自选料号/自己调数量」的通道跟着消失（用户实测报告回归）。`_KpNode.extra_ask_options` 对带 `pick_all` 的整体卡**结构性注入**「我自己逐项挑（自选料号/数量）」——无信号选项，点击落 `ask_answers`（口头回答）；大脑按左栏规则 7 逐行 `ask_user(row=…)` 发行卡，`enrich_ask_gap` 转 parts_card，前端「从配件库自选…」下拉+数量步进即回归。配套两修：`select_parts` 补 `part_required` 契约错误（new_row 缺料号名曾 `hit=None` 崩 AttributeError、整次调用报废）；`phase_kp_reason` 归属收口放宽（§22.3）。自选 e2e：10 轮 229.9s 收口，9 卡全行绑定（kp-xxx 稳定行身份）、CPU/内存/盘/RAID/网卡 7 次点击全带 `kp_manual_pick` 信号落锁。
- **只有登记表真实字段**（`slot_spec()` 里 `src_type != "kp"` 的项）才写 `{slot: value}`；兜底 slot（如 `brain_ask`）一律当客户口头回答走对话，不写不存在的字段。
- `absent` 的类目：优先取选项自带的类目名（schema 就是类目字符串）；选项没给（脏数据）时由 `category=` 兜底——调用方**按行身份**解析后传入；两者都取不到就**不产信号**，绝不把 `True` 之类写进 `kp_absent`（P3-4 回归：`test_kp_stuck_gap.py::test_row_card_for_a_row_id_ref_resolves_the_category_by_identity`）。
- 点击通路：`click_fast_path = bool(click_labels or ask_answers) and had_pending_card`——回答"无选项的卡"也算意图无歧义。
- **双出口收口（2026-09-13）**：done 兜底路的 `_emit_ask_card` 曾自带第二套选项→信号解释，与引擎缺口路漂移（`pick_all` 只加了兜底路，A1 实测引擎路点击信号全空、整段死循环）；现已改为只做行身份解析后转交本函数，全链路唯一出口。

## 11. 护栏

- `tests/test_no_undefined_names.py`：全仓未定义名扫描（symtable），挡名字写错。
- 点击落痕 `click_errors`（`skill_chat.py:214`）：点了没接上的信号会被记下来，不静默吞。
- `tests/test_node_artifact_contract.py`：禁止 `DEFAULT_KIND_BY_NODE` 回归；产物槽只由抽屉声明。

## 12. 规模（2026-09-11 拆分后）

| 文件 | 行数 |
|---|---|
| `app/services/part_selector.py`（总出口薄壳） | 97 |
| `app/services/part_row_identity.py`（行身份） | 577 |
| `app/services/part_recall.py`（检索召回） | 421 |
| `app/services/part_landing.py`（落料） | 379 |
| `app/services/part_specs.py`（规格事实） | 188 |
| `app/services/skill_chat.py` | 771 |
| `app/services/skill_turn_engine.py` | 643 |
| `app/services/skill_phases.py` | 614 |
| `app/services/skill_node_plugins.py` | 553 |
| `app/services/skill_tools_open.py` | 460 |
| `app/services/skill_plan_runtime.py` | 451 |
| `app/services/agent_tool_specs.py` | 451 |
| `app/services/skill_node_artifacts.py` | 322 |
| `app/services/skill_tools_kp.py` | 304 |
| `app/services/skill_tools_fill.py` | 264 |
| `app/services/skill_target_contract.py` | 246 |
| `app/services/skill_node_state.py` | 241 |
| `app/services/skill_tools_select.py` | 229 |
| `app/services/skill_memory.py` | 216 |
| `app/services/skill_tools_misc.py` | 200 |

拆分史：`skill_chat.py` 原 2317 行（工具实现 + 编排壳同文件、两个怪物函数 451/586 行）。2026-09-10 先做文件级拆分（10 个模块：tool_context / memory / signals / step_runtime / tools_fill / tools_model / tools_kp / tools_select / tools_misc / turn_engine），再做函数级拆分——`run_skill_agent_turn` → `skill_turn_engine._SkillTurnRuntime`、`handle_skill_chat_turn` → `skill_chat._ChatTurnRuntime`，两个入口都只剩薄封装，最大单函数从 586 行降到 92 行。

2026-09-11 第二次文件级拆分：`skill_tools_kp.py` 750 → `skill_tools_kp.py`（检索：`query_parts` 去库，2026-09-12 已退役 `suggest_parts`）+ `skill_tools_open.py`（只读钻取：`open_part` / `open_row` / `open_category` / `grep_parts`，共 460 行）。分界线当时是**是否写接地索引**（`kp_search_index`，2026-09-12 已整体移除：检索全只读，落地改按料号名回库核对，见 §24）。

布局由 `tests/test_skill_module_layout.py` 钉死：谁在哪（`OWNERS`）/ 多大 / 死代码不许复活 / 检索与钻取不许混居（`test_search_and_drill_tools_stay_separated`）。

2026-09-11 第三次文件级拆分（P4-3）：`part_selector.py` 1528 行 → 四块语义 + 薄壳（行身份 577 /
检索召回 421 / 落料 379 / 规格事实 188 / 总出口 97），依赖只能向下（§18.3）。
2026-09-11 第四次文件级拆分（P6）：`colleague_turn_service.py` **1122 行** →
`colleague_prompt.py`（289，配置 / 提示词组装）+ `colleague_turn_io.py`（132，落库 / 广播 / 溯源）
+ `colleague_turn_runners.py`（603，普通对话 / ReAct / 对话脑三种执行器）+ `colleague_turn_service.py`（207，
串行队列 + 总入口薄壳）。机械搬家、零行为改动；依赖只能向下（prompt ← io ← runners ← 壳），
布局与行数预算由 `tests/test_colleague_turn_layout.py` 钉死。
**至此「同事回合」链路不再有 >700 行的文件**——colleague_prompt / io / runners / service 分别是 289 / 132 / 603 / 207 行。服务层**仍有** 4 个 >700 行的其他文件（`llm_client.py` 1033 / `office_mission.py` 850 / `skill_chat.py` 780 / `skill_turn_engine.py` 786），体量头部另在 API / 仓储聚合层
（`api/portal.py` / `repository/kp_repo.py` / `api/ai_colleagues.py`，属 P7 可选项，见 §20）。

## 13. 实测现状（2026-09-11）

真实 HTTP + WebSocket + 真实 LLM + 真实库：

| 场景 | 结果 | 轮次 | 墙体 | 配件行 | 组装行 |
|---|---|---|---|---|---|
| 详细（兆芯） | 走到 `output` | 3 | 187s | 8 | 17 |
| 库内无料·保持原需求（B200） | 走到 `output` | 6 | 428s | 2（1 行 waived） | 12 |
| 模糊（"AMD 平台的通用计算服务器"） | 走到 `output` | 11 | 1199s | 7 | 16 |

模糊场景 P2（行清单增量化）前后对比：轮次 14 → 11、卡数 13 → 10、配件行 **11 → 7**、组装行 20 → 16、重复行 1 → 0、同类别再问 5 → 3。BOM 里两条 RAID 卡 / 两条系统盘的重复行已消失。

用时：单轮 50~200s，墙体时间几乎全在 reasoning 模型的深思考上，工具调用本身秒回。

**合规整改后复测（2026-09-11，删掉代码里的硬编码系统协议之后）**：

| 场景 | 结果 | 轮次 | 墙体 | 配件行 | 组装行 | 重复行 | 同类别再问 |
|---|---|---|---|---|---|---|---|
| 详细（兆芯） | 走到 `output` | 3 | 175s | 8 | 17 | 0 | 0 |
| 模糊（AMD 通用计算） | 走到 `output` | 11 | 1210s | 10 | 19 | 0 | 2 |

兆芯场景与整改前逐项一致（3 轮 / 8 行 / 17 行），说明删协议没有改变可用路径。模糊场景
轮次、卡数、重复行维持 P2 后水平；配件行 7 → 10 的差异来自**同一类目同义改写**（网卡被
「网卡 通用计算标配」「网卡 标配」「网卡（通用计算标配）」拆成 3 行）——这是 §14 已列的
残留①，不是协议删除引入的回归；单轮 20 分钟级、每场景仅一次，行数对比本身带 LLM 抖动。

**P4 复测（2026-09-11，暂停载荷 + 提示词守卫 + 配件层拆分 + 夹具补齐之后）**：

| 场景 | 结果 | 轮次 | 墙体 | 配件行 | 组装行 | 重复卡 / 重复行 |
|---|---|---|---|---|---|---|
| 详细（兆芯） | 走到 `output` | 3 | 171s | 8 | 17 | 0 / 0 |
| 库内无料·保持原需求（B200） | 走到 `output` | 7 | 426s | 2（1 行 waived） | 12 | 0 / 0 |
| 模糊（AMD 通用计算） | 走到 `output` | 5 | 440s | 1 | 10 | 0 / 0 |

兆芯 8 行 / 17 行与基线逐项一致；`waived` 场景 8 轮 / 重复行 4 已随夹具补齐（`"CPU": "@recommend"`）
回到 7 轮 / 0 重复行（§18.4）；模糊场景本轮 1 行 / 10 行属同一次 LLM 抖动（§14 残留①）。
回放 43 个真实线程：重复 `row_id` / `origin` = 0、同义重复行 = 0、幂等不一致 = 0。

## 14. 已知未修

> **读前必读（防误读）**：`origin` 是**每行的来源锚点**，不是「同类目只有一个 origin」。
> 同类目多行天然带序号（`reg:NIC#1` / `reg:NIC#2`、`reg:HDD/SSD#1..#4`），**一类多行完全合法**
> （1.92T 与 960G 硬盘、2 个万兆与 4 个千兆网卡）。要守的只有「**同一身份不重复发布**」。
> 引擎**明确不做**文本相似度归并：同描述的两行也不许并成一行
> （`tests/test_row_identity_minted.py::test_stamp_is_idempotent_and_never_merges_by_text`）。

- ~~模糊场景的行清单没有增量化~~ → **2026-09-11 P2 已做**（详见 §7/§12）：`bridge_ctx` 发布**全量行清单**
  `kp_rows_all`（每行带 `status` / `part` / `settled`），`ask_user` 的 `row` 收口成 `row_id` / 行键 / 裸描述
  三档解析（`resolve_row_ref`），已了结行再问直接回 `row_already_settled`（`reopen=true` 才放行），
  落行前按 `(category, 归一化描述)` 去重。实测配件行 11 → 7、BOM 重复行清零。
  **当时仍未修**（① **已由下方 P3 收口机制关闭**，实测与单测见 §17；② **已由 2026-09-12 归属收口关闭**，见 §22）：① 行身份对**同义改写**不免疫——把 `RAID卡 8口4G缓存` 写成 `8口 / 4G 缓存 RAID 卡`、
  `64G DDR5 4800 RDIMM ×8（合计 512G）` 写成 `内存 512G（64G×8，DDR5 RDIMM）` 时，归一化
  （只吃数量/排版噪声）合不上，仍会攒出第二行、多问一轮（实测残留 3 次同类别再问）；
  ② 需求**占位行**（`CPU|通用计算服务器处理器（客户未指定型号）`）在客户已点名 9654 时仍会单独提问，
  应并入客户点名行而不是各占一行。~~仍开放~~ → **2026-09-12 归属收口已关闭**（§22）：成因是两个合并分支
  口径不一致（有 picks 时只按「完全相同的 (类目,描述)」让位 → 同类目并存），以及声明行（cfg:）越权承载
  了登记表已申报的类目。一处对齐口径、一处按归属过滤，两条回归锁住。
  **2026-09-11 P3 收口机制**：行身份不再由文本派生（`origin` 铸造、描述改写不换身份），工具契约要求同类目声明必须绑定既有 `row_id`（要新增同类目第 2 行须显式 `new_row=true`），回放 43 个真实线程的同义重复行 = **0**（详见 §17）。**仍可能**出现「大脑显式声明成两条不同 `origin` 的行」——那是语义决策（如「4 个千兆」+「2 个万兆」），引擎不做词元/包含相似度判断。→ **2026-09-13 用户拍板收口（D1）**：边界写进左栏 `manual_rules`（DB 流 125，2026-09-13 合并重编号后为规则 6）「行归属纪律」——同类别补充/改口优先并入原行（同规格只保一行），确属不同规格组合（1G×4 与 10G×2 两档）才开第二行并说明分行理由；禁止同规格拆多行、禁止把客户明说的两档并成一行。引擎层维持不做归并。
- 单轮推理耗时高（60~200s），根因在模型侧，不在编排。
- ~~大脑返回**空响应**时回合静默收尾~~ → **2026-09-11 P2.5 已修**（详见 §16）：实测一次单轮 1605s
  静默空转（旁白为空、既无缺口也未完成，三件套 LLM 超时 / 空产出收口 / 失败出口全缺）。
  现在单轮有墙钟上限、零产出有可见失败出口；B200 场景从「未完成 + 1605s 静默」变成
  「4 轮 / 282s / 走到 output」。
- 类目内**定向导航**与**结果集内过滤**：2026-09-10 已补 `open_category`（`navigate`）与
  `grep_parts`（`grep`），目录结构（该类目有哪些规格键、值域/分段）与「词落在哪」都有了稳定入口。
  **仍未做**：~~① `grep_parts` 命中后不能直接锁定（只读、不入接地索引），必须再走一次
  `query_parts` 才能 `select_parts`~~ → **已由 §24 去检索台账顺带关闭**（2026-09-12 复核：
  `select_parts` 落料凭据=「类目+料号名」回库核对，`grep_parts` 结果带料号名，可直接落）；
  ② 结果集内过滤缺——想在上轮候选里二次筛选（不重新打库）只能重发 `query_parts`。
- `suggest_parts` 已于 2026-09-12 退役；跨类目找料职责由 `open_category` / `grep_parts` / `query_parts(rows)` 承接，真语义召回不再作为独立挂账。



- 顺带修一个与「定向检索」直接相关的老缺口（同日）：工作记忆 `brain_notes` 只在「本回合有工具
  调用」时才落一条，且 `engine` 每轮重建、不承接 mem——于是纯问答回合会把上一回合的检索轨迹
  抹掉，而跨轮注入读的正是 `mem.brain_notes`（`skill_turn_engine.py:354`），定向检索的轨迹
  因此常常读不到。现在 `_prepare` 从 mem 承接（窗口 3 条，与 `_note` 同一窗口）、回合末合并
  不再用空值覆盖。
  **2026-09-11 合规整改**：工作记录改成**通用渲染** `agent_tool_specs.trace_note`——记忆层不认识
  任何工具名（旧版是按工具名 if/elif 分支），每条记录只从调用实参/结果里抽事实（标量保留、长串
  截断、列表报条数）拼成 JSON。新增工具零改动即可被记录。回归：
  `test_open_tools.py::test_brain_note_summary_is_generic_and_records_drill_facts`、
  `::test_memory_layer_knows_no_tool_names`（守卫：记忆/编排层不得出现工具名）、
  `::test_engine_carries_brain_notes_across_turns`。


## 15. 提示词唯一出处 + 节点能力声明（2026-09-11 合规整改）

**唯一 AI 大脑、拒绝硬编码、前端可配置**是这套 skill 的宪法（见 `docs/skill studio设计思路.md`）。
本轮把两处「代码里另存一套提示词」清掉：

- **提示词唯一出处 = Skill Studio 左栏（DB）**：flow 级 `graph.manual_rules`（「使用说明」）。
  2026-09-12 起节点抽屉 / `rules.reasoning_node_default` 不再承载指令 prose
  （`description` / `goal` / `final_contract` 全清，`node_mission` 注入退役——原活指令增量
  已并入左栏规则 13/14/15/24，迁移 `scripts/migrate_left_panel_single_home_20260912.py`）。
  抽屉与默认契约只留机制结构（产物槽 / 开关 / 数据源 / fields）。代码里不再有第二套：
  - 删掉了 `skill_plan_runtime.AGENT_PROTOCOL`（原「系统协议（机制约定）」5 条，每回合注入 system prompt）；
  - `skill_config_bootstrap.DEFAULT_REASONING_NODE_CONTRACT` 只留**结构**（产物槽 / 开关 / 数据源），
    所有 `description` / `goal` / `prompt` 文案清空——空库播种出的是「空壳 + 待填」，不是一份藏起来的提示词；
  - 删掉 `scripts/migrate_kp_reason_prompt_sync.py`：它把代码常量当权威**反向 UPDATE 回 DB**，会覆盖左栏编辑，
    是「平行第二套」的实证；
  - 收尾迁移 `scripts/migrate_prompt_cleanup_20260911.py`：把原协议第 3 条（对客户只说确认+问题）并入
    `manual_rules`（左栏可见可改），并删掉 DB 里已废弃的 `agent_fill.prompt` 死键。
- **机制约束用代码/工具契约强制，不写劝告句**：
  - 「已了结的行不要再问」→ `ask_user` 的 `row_already_settled` 拒收（`reopen=true` 才放行）；
  - 「系统卡在场时不许自由文本抢跑」→ `skill_chat` 有结构化卡就发卡、丢弃大脑的开放式提问；
  - 「不许手拼 类目|描述 暗号」→ 工具 schema 里 `row` / `row_id` 的契约；
  - 「一步没完成不要开下一步」→ 步骤完成校验 + 工具白名单。
  `skill_turn_engine` 的上下文块只摆**事实数据**（行清单 / 候选类目 / 当前步骤结构化 JSON），不再夹劝告句。

**节点能力声明唯一真源 = `app/services/capability_spec.py`**（`CapabilitySpec`：`default_tools` /
`mechanism_tools`）。三处一律从它派生，不再各写一份清单：

| 消费方 | 派生方式 |
|---|---|
| 空库播种 `skill_config_bootstrap` | `tools_for_node()` → `default_tools` |
| 运行时保底 `skill_plan_runtime.effective_node_tools` | `MECHANISM_TOOLS = mechanism_tools_map()` |
| 前端抽屉 `ReasoningNodeDrawer.vue` | `GET /api/reasoning-flow/capabilities` → `capabilities_catalog()` |

启动时 `validate_specs()` 自检「声明了但没注册」的工具，把运行时崩溃提前到启动期。前端那份
`MECHANISM_TOOLS_BY_RUNTIME` 手抄副本（3 条且与后端漂移）已删除。

**工具轨迹记录通用化**：`agent_tool_specs.trace_note()` 从调用实参/结果里抽事实（标量保留、长串截断、
列表报条数）拼 JSON；记忆层 `_brain_note_summary` 不再按工具名 if/elif，新增工具零改动即可被记录。
守卫：`tests/test_open_tools.py::test_memory_layer_knows_no_tool_names`。

**唯一出处的守卫（2026-09-11 P4-2，2026-09-12 更新）**：`tests/test_prompt_single_source.py`——代码里不许再有
`*PROTOCOL` 注入式常量；空库播种契约与 DB 默认契约都不带 `description/goal/prompt`（节点层 prose 保持清除、
`node_mission` 不许复活）；没有脚本从代码反向 UPDATE 提示词进 `reasoning_node_default`；活证明——编排壳交给大脑的
system prompt 里指令逐字来自左栏 `manual_rules`、无节点层第二套（干净版）。

## 16. P2.5 稳健性：单轮墙钟上限 + 零产出失败出口（2026-09-11）

**事故**：B200 场景第 3 轮单轮静默跑了 **1605.5s**，旁白为空、无缺口卡、无错误事件，
编排直接停住（复盘只有 metrics 的 `last_step=model_reason`），客户对着转圈的看板干等 27 分钟。

**根因**：流式通道只有**间隔看门狗**（首字节 + 每 chunk 空隙），而慢速持续输出 reasoning 的模型
会把看门狗**无限重置**——只要还在吐字，就永远不超时。通道没有「单轮总时长」这一维。

**四道闸（由内到外，都是引擎参数，不是提示词）**：

| 层 | 改动 | 作用 |
|---|---|---|
| 通道 | `stream_agent_chat(overall_timeout=…)`（默认 `DEFAULT_OVERALL_TIMEOUT_S=240`，调用方只能收紧不能放开）+ `anthropic_channel.stream` 同步实现 | 单轮墙钟到点抛 `LLMError`，断连原因如实（区分首字节 / 间隔 / 整体） |
| 通道 | `AnthropicTimeoutError` 收口成 `LLMError`（不再误报成 `LLMNativeToolsUnsupported`） | 超时不再让上层白降级掉原生工具通道 |
| 编排 | `run_brain_attempts(round_timeout_s=180)`：每次尝试下发 `min(剩余预算, 单轮上限)`，并用 `asyncio.wait_for` 兜最后一道 | 内层再挂死也收敛成 `action="timeout"`，不静默 |
| 编排 | `_run_one_step` 认领「整轮零产出」：先按**产物**收口一次（超时前成功调用的工具已落地 → 照常 `done`），收口不成才 `_abort_step` → `engine_failure` → `status:failed` → `kind=error` | 客户看到一条如实的失败说明与「继续」出口，而不是零选项死卡或永久转圈 |

**回归**（真实 HTTP / WebSocket / LLM / 库，同一场景同一脚本）：

| 场景 | 改前 | 改后 |
|---|---|---|
| 库内无料·保持原需求（B200） | ⛔ 未完成 · 3 轮 · 1777s · 单轮峰值 **1605.5s** 静默 · 配件行/组装行均未产出 | ✅ 走到 `output` · 4 轮 · 282s · 单轮峰值 122.7s · 配件行 2（1 行 waived）· 组装行 12 · 重复 0 |
| 详细（兆芯） | ✅ 3 轮 · 187s · 8 行 · 17 行 | ✅ 4 轮 · 226s · 8 行 · 17 行（产物逐项一致） |
| 模糊（AMD 通用计算） | 11 轮 · 1210s · 无静默挂死 | 无静默挂死；本轮因脚本答案未覆盖而按设计停止，并**实机走通了新的失败出口** |

模糊场景里新的失败出口被真实命中：大脑在 `kp_reason` 连续多轮未落地，回合以
「『配件选型』这一步模型连续多次尝试后仍未给出可采用的产出，已如实停止，不会编造结果。
未落地的部分保持原样，你可以直接回复「继续」重试本步。」收尾并广播 `error`
（旧行为：弹一张零选项死卡、看板继续转圈）。

用例：`backend/tests/test_llm_wallclock_guard.py`（7 条：通道墙钟切断、超时不误报 unsupported、
`wait_for` 兜底、单轮上限下发、零产出失败终态、纯事实零产出判定、失败载荷结构化）。

## 17. P3 行身份 → 契约收口（2026-09-11，含 P3-4 回放 + 三场景 e2e）

**病根**：行身份由**文本指纹**派生（`row_id = sha1(类目|描述)`、pick 键 = AI 手拼的 `类目|描述`）
→ 同一需求换个说法就长成一行新部件，被反复提问、BOM 里出现重复行。

**改法**：把**身份**与**内容**分开（设计见 `docs/AI办公室-系统结构梳理与2026架构对照.md` §4）。

| 阶段 | 内容 | 验收 |
|---|---|---|
| P3-1 身份铸造 | `origin`（`reg:<类目>#n` 登记行 / `cfg:<类目>#n` 声明行）铸造 `row_id`，落 `node_state.kp_reason.row_ids` 台账；`row_id` 与描述解耦；`rev` 表达内容版本 | 同一 `origin` 描述改写 3 次 → `row_id` 恒定（`tests/test_row_identity_minted.py`） |
| P3-2 picks 挂身份 | `KP_PICKS` 键 = `row_id`，entry 自带 `category/description/rev`；`rev` 不一致 → 标 stale → 该行重选（**不删行**） | 描述改写 → 同 `row_id`、`rev` 变、pick stale，行数不变（`tests/test_row_identity_incremental.py` 口径改为「只认身份」） |
| P3-3 工具契约收口 | `row` 只认清单内 `row_id`（`resolve_row_ref` **删掉归一化文本猜测**）；`select_parts` 无 `new_row=true` → `row_unknown`，缺描述 → `spec_required`；**行卡按 `row_id` 绑行** | `tests/test_select_kp_parts_tool.py`（`row_unknown`/`spec_required`/`new_row`） |
| P3-4 验证 + 文档 | 真实线程回放 + 三场景 e2e + 文档收口 | 见 17.1 / 17.2 |

### 17.1 真实线程回放（`backend/scripts/replay_row_identity.py`，只读 / 零模型 / 零写库）

60 个真实线程 `reasoning_state` → 回放 43（跳过 17：无 kp 行 15 / 无状态 2）；BOM 行 275 / 发布行 273。

| 指标 | 目标 | 实测 |
|---|---|---|
| 发布行（权威行清单）重复 `row_id` | 0 | **0** |
| 发布行重复 `origin` | 0 | **0** |
| BOM 同义重复行（同类目 + 同内容 + 同料） | 0 | **0**（0 组） |
| 幂等：连跑两次身份不一致的线程 | 0 | **0** |
| 旧文本键 pick 仍能落地（升级不迁移数据） | — | 31 个线程有文本键 pick，其中 22 个回放后仍有落地行 |

用法：`.venv\Scripts\python.exe -X utf8 scripts\replay_row_identity.py --limit 60 --json <path>`。

### 17.2 三场景 e2e（真实 HTTP / WebSocket / LLM / 库）

| 场景 | P2.5 基线 | P3-4 实测 | 判定 |
|---|---|---|---|
| 详细（兆芯） | `output` · 3 轮 · 8 行 / 17 行 | `output` · 2 轮 · **8 行 / 17 行** | 产物逐项一致 ✅ |
| 库内无料·保持原需求（B200） | `output` · 4 轮 · 2 行 / 12 行 | `output` · 8 轮 · **2 行 / 12 行**（1 行 waived） | 产物逐项一致 ✅ |
| 模糊（AMD 通用计算） | ⛔ `finished=false` · 4 轮 · 停 `model_reason` | `output` · 3 轮 · **1 行 / 10 行** · 重复行 0 | 不再静默挂死 ✅ |

### 17.3 同日修掉的两个真回归（P3-3 的尾巴）

1. **行卡改绑 `row_id` 后，kp 侧仍按 `|` 切类目**（探针实测 4 处）：行卡候选为空、豁免无路、
   `enrich_ask_gap` 直接抛 `ValueError`、`absent` 把 `True` 当类目写进 `kp_absent`。
   修法：新增唯一解析口径 `part_selector.row_ref_meta`（`row_id` → `origin` → 精确行键，**不猜文本**），
   `skill_node_plugins._row_meta` / `skill_turn_engine._ask_gap` / `skill_chat._emit_ask_card` 一律由身份取类目，
   `ask_option_signal(..., category=)` 透传；`类目|描述` 只在**旧数据**上作兼容分支。
2. **`waived_categories` 多了一行提前 `return`**（P3-2 编辑残留）：豁免键是 `row_id` 时直接把 `row_id`
   当类目返回 → 终检认不出该类目已了结，客户点了「保持原需求」仍会被拦下。已删，回归见
   `tests/test_kp_waived.py::test_waived_categories_resolve_a_row_id_through_the_identity_ledger`。

另有两条「同一身份必须唯一发布」的收口：

- `bridge_ctx` 的行清单按 `row_id` 去重：组合件会让**一行**在 BOM 里落成多条明细（实测 NIC 一行 =
  网卡 + 2 个光模块共 3 条），但行清单（`kp_rows_all`）是**行身份的权威表**，同一 `row_id` 只能发布一条。
- 行清单里的 `origin` 是**每行的来源锚点**，不是「同类目只有一个 origin」：同类目多行本就带序号
  （`reg:NIC#1` / `reg:NIC#2`、`reg:HDD/SSD#1..#4`），1.92T 与 960G 这类「一类多行」完全合法。
  **「同 origin 必须合一行」= 同一身份不重复发布，不是「同类目只能一行」**。

### 17.4 残留（未修，留档）

- **`waived` 场景 8 轮 / 重复行 4**：行卡本身绑定正确（客户第 3 轮就点中「保留原需求」并把 GPU 行结掉），
  重复来自 e2e 夹具 `answers` 里**没有 CPU 项的答案**，harness 只能用 `brain_ask` 的通用文案去答 CPU 卡
  → 模型每轮重问 CPU 行，直到它自己锁定了 9654。**2026-09-11 P4 已补**夹具 `"CPU": "@recommend"`：
  该场景回到 **7 轮 / 重复行 0**（§18.4），产物仍 2 行 / 12 行。
- **兆芯首跑「配件选型」重试耗尽**（`finished=false, kp_rows=null`）复跑自愈、修完卡片回归后未再复现，
  倾向模型随机性；尚无白盒证据，不归因。


## 18. P4 收口：暂停载荷 / 提示词守卫 / 配件层拆分（2026-09-11）

### 18.1 P4-1 暂停载荷对象化（唯一中断点对象）

**病根**：暂停/恢复没有载荷对象，靠 `assistant_threads.reasoning_state` + `office_governance_items`
+ 广播扁平字段**三处重建**——多一个状态源要同步（对照 OpenAI 的 `RunState`，见
`docs/AI办公室-系统结构梳理与2026架构对照.md` §2.3 第 1 条）。`pipeline_paused` 原来只有
`failure=` 一个可选字段，中断点/待批准项/恢复所需最小状态散在各处。

**改法**（不新增表、不迁移 DB，`office_governance_items` 保持不动）：

| 件 | 内容 |
|---|---|
| 唯一工厂 | `skill_plan_runtime.pause_payload(...)` → `{kind, step, label, reason_code, pending, resumable, at, resume{steps_done, awaiting}}`；只有事实与原因码，**没有话术字段** |
| 唯一发射口 | `skill_turn_engine._emit_pause(...)`：置 `engine.engine_pause` + 广播（`pipeline_waiting`/`pipeline_paused` 旧字段照发）。5 个暂停出口全走它：大脑升格提问 `brain_ask` / 节点兜底卡 `delivery_gap` / 本步重试耗尽 `stuck` / 本步零产出 `failure` / 终检不过 `final_gate`；回合 900s 硬超时（`skill_chat`）也产同一对象（`turn_timeout`） |
| 回存 | `reasoning_state.engine_pause`（回合终态写入；本回合没暂停则显式清空，不留旧中断点） |
| 派生展示 | `office_events` 的状态词由载荷派生（`kind=failure → 流程暂停`，其余 `→ 任务进行中`），载荷对象原样带进看板（`publish_office_event(pause=...)` → `office_hub` 白名单 `pause`），不再靠扁平话术还原中断点 |

守卫：`tests/test_pause_payload.py`（工厂形状只有事实键 / 暂停广播不许绕过 `_emit_pause` 手搓 /
失败出口带载荷并随终态回传 / 办公室状态由载荷派生）。

### 18.2 P4-2 提示词唯一出处的守卫

见 §15 末：`tests/test_prompt_single_source.py`（5 条，含「活证明」——system prompt 里的节点使命逐字来自 DB）。

### 18.3 P4-3 配件层拆分（`part_selector` 1528 → 4 模块 + 薄壳）

| 模块 | 行数 | 语义 |
|---|---|---|
| `part_specs.py` | 188 | 规格事实：单位换算 / 规格比对 / 系列适用性 / 库句柄解析口 |
| `part_row_identity.py` | 577 | 行身份：行装配 / 行键 / 身份铸造 / pick 绑定 |
| `part_recall.py` | 421 | 检索召回：类目解析 + 候选池 + 别名 |
| `part_landing.py` | 379 | 落料：ground / select / manual |
| `part_selector.py` | 97 | 总出口薄壳（re-export，现存 import 一律不用改） |

依赖只能向下：**specs ← identity ← recall ← landing**（无环、无同层依赖）。
`part_selector.KPRepository` 这条「换库缝」由 `part_specs.kp_repository()` 在运行期解析保留
（桩测试仍从总出口替换句柄，行为不变）。守卫：`tests/test_skill_module_layout.py`
（薄壳不许长实现 / 分层不许反向 / 单文件 700 行预算）。拆分由机械拆分器完成
（AST 切块 + 显式归属表 + 覆盖校验 + 按真实引用来生成 import），零行为改动。

### 18.4 P4-4 夹具补齐与三场景复测

`scripts/e2e_scenario_waived.json` 的 `answers` 补 `"CPU": "@recommend"`（原缺 → harness 只能拿
`brain_ask` 的通用文案答 CPU 卡，模型每轮重问）。

| 场景 | 结果 | 轮次 | 墙体 | 配件行 | 组装行 | 重复卡 / 重复行 |
|---|---|---|---|---|---|---|
| 详细（兆芯） | `output` | 3 | 171s | 8 | 17 | 0 / 0 |
| 库内无料·保持原需求（B200） | `output` | 7 | 426s | 2（1 行 waived） | 12 | 0 / 0 |
| 模糊（AMD 通用计算） | `output` | 5 | 440s | 1 | 10 | 0 / 0 |

`pytest tests -q`：**575 passed**（新增暂停载荷 4 条 + 提示词守卫 5 条）。
回放 `scripts/replay_row_identity.py --limit 60`：43 线程全绿（重复 row_id/origin = 0、同义重复 = 0、幂等不一致 = 0）。

## 19. P5 盘点：机制文案欠账 + 宪法守卫机制（2026-09-11）

宪法 → 守卫机制已落地：守卫文件 `backend/tests/test_constitution.py`（6 条宪法条款、4 条守卫，
含元测试「条款 ↔ 守卫」一一对应），文档映射表在 `skill studio设计思路.md` 顶部。
守卫核心是一张**欠账棘轮** `PROSE_BASELINE`：= 代码里「教大脑怎么做」的句子数，只许降不许升，
降了必须同步下调基线，否则测试红——这就是「避免重复返工」的抓手。

盘点口径：字符串常量命中祈使/流程词（先调｜不许｜严禁｜不再要求｜交客户｜如实告诉｜才能｜由系统…），
docstring 不算、工具参数契约与状态词不算。

| 文件 | 条数 | 主要形态 |
|---|---|---|
| agent_tool_specs.py | 19 | 工具目录 description 里夹的任务流程句 |
| skill_node_plugins.py | 12 | validate / prepare 的 hint（事实＋规则混写） |
| skill_tools_open.py | 11 | 插头返回里的「先调…／交客户…」 |
| skill_tools_fill.py | 11 | 登记工具返回与参数说明 |
| colleague_turn_service.py | 6 | 聊天兜底与风格提示 |
| skill_tools_select.py | 4 | 行落料返回 |
| skill_tools_misc.py / agent_react.py / skill_plan_runtime.py / office_brain.py | 各 3 | — |
| skill_tools_kp.py / skill_phases.py / skill_chat.py / skill_turn_engine.py / data_tools.py | 各 2 | skill_chat 是缺口转述提示词 |
| skill_tools_model.py / agent_tool_handlers.py / office_mission.py | 各 1 | — |
| **合计** | **88** | |

分类与去向：

- **规则（搬左栏）** 约 60 条：「先调哪只工具／该不该问客户／不许静默丢弃／如实告知」。
- **工具契约（留代码）** 约 20 条：参数必填、越界拒收、返回字段含义。
- **状态词（留代码，必要时换词）** 约 8 条：「AI 建议」「待处理」。
- **不变式** 约 10 条：「不许跳步」（end_step 校验＋compose 拒跳）、「不许凭记忆报料号」（接地索引只读）、
  「不要既填又追问」（agent_fill 抽屉已有）。
- **真·第二套提示词 1 处**：`skill_chat._transcribe_gap` 的 gap_prompt／ack_rule ——
  整段注入式系统消息（带 `<<ACK_RULE>>`／`<<GAP_DATA>>` 占位），尚未搬左栏。

本轮已修：

- 左栏/配置层旧工具名归一：flow 125 任务规则 14/15、model_reason 用户配置、ai_colleagues 四个角色
  `tool_ids`（`select_model→choose_model`、`search_kp_parts→query_parts`、`select_kp_parts→select_parts`、
  `spec_filters→required_specs`、`begin_step` 删句；退役项 build_plan／cost_breakdown／quote_draft 移除）。
  脚本 `scripts/migrate_left_panel_tool_names_20260911.py`（幂等，跑第二遍 0 变更）。
  历史记录 `assistant_threads.reasoning_state` 原样保留（那是回放，不是配置）。
- 死码 `part_specs.compose_memory()`（零调用方）删除，转出口与归属表同步收掉。
- `pytest tests -q`：**582 passed**（新增宪法守卫 4 条）。

### 19.1 P5-A 三波收口：已完成（2026-09-11）

| 波次 | 范围 | 结果 |
|---|---|---|
| 波 1 | 节点 hint（`skill_node_plugins.py`）12 → 0 | hint 只留事实（「目录字段还缺：X」），规则句搬任务规则 18/19/20 |
| 波 2 | 插头返回（`skill_tools_*.py`）32 → 0 | 工具返回只摆事实；价格纪律、登记纪律进左栏 |
| 波 3 | 注入式消息 + 工具目录 + 角色层 | 见下 |

波 3 明细：

- **真·第二套提示词搬左栏**：`skill_chat._transcribe_gap` 的 `gap_prompt/ack_rule` 整段注入式系统消息，
  规则搬进任务规则 21（缺口语术纪律），代码只留占位符 + JSON 契约；缺口转述回合改为**同源注入左栏任务规则**
  （`skill_step_runtime.manual_rules_block`，与步骤大脑共用一份）。
- **工具目录契约化**：`agent_tool_specs.py` 19 → 0（description 只讲参数/返回/越界，流程句回左栏）；
  `agent_tool_handlers.py`、`data_tools.py`、`skill_plan_runtime.py`、`skill_turn_engine.py`、`skill_phases.py`、
  `skill_node_state.py`、`part_row_identity.py`、`selection_engine.py` 全部 → 0。
- **角色层上收**（AI 同事 / AI 办公室的提示词也是「提示词」，不能住代码）：
  经迁移写进 `rules.system_config.ai_colleagues.behavior`，前端**行为编辑器「提示词（高级）」**可改：
  `brain.system_prompt / user_rule / minutes_prompt`、`mission.agent_system_prompt / lead_system_prompt`、
  `charter.handoff / workflow_list / chat_default / tool_usage`。
  代码里 `AGENT_SYSTEM_PROMPT`、`NATIVE_TOOL_SYSTEM_HINT`、`_DEFAULT_CHAT_SYSTEM_PROMPT` 已删，
  运行期只读 DB；收尾汇报纪律进左栏 `output` 节点使命。
- 守卫同步：`MECHANISM_FILES` 增补 `skill_node_state / part_row_identity / selection_engine / colleague_memory_service`；
  `_left_panel_text()` 扩到**角色层配置**（`system_config.ai_colleagues`）——所以「搬去 AI 设置」也算有出处；
  `PROSE_BASELINE` 全部归 0；`MOVED_RULES` 增补 19 条留痕锚点。
- 迁移脚本（幂等，跑第二遍 changed=0）：
  `scripts/migrate_p5_wave3_left_panel_20260911.py`（任务规则 21/22/23 + 规则 15/19 补句）、
  `scripts/migrate_p5_wave3_role_prompts_20260911.py`（角色层 9 处 + output 节点收尾纪律）。

兜底口径：配置为空 = 该处不注入提示词（代码不再备第二套），不再有「代码里悄悄兜底一套」。

**明确不在范围内的「非机制文案」**（扫描不计，避免误伤）：
`app/api/*`、`app/repository/*` 的面向操作员的校验提示（「请先…」）、兼容性规则数据、`solution_seed.py`
的领域知识文案、`system_config_repo.py` 里 AI 角色的**首次播种**默认值（运行期唯一来源仍是 DB）。

`pytest tests -q`：**582 passed**（含宪法守卫 4 条 + 元测试）。

### 19.2 P5-D 兜底提示词清零（2026-09-11）

> ⚠️ 本节「迁 DB `behavior.charter`」的落点已被 **§19.4 整块退役**取代：判官 / 记忆抽取改为注入**相关员工自身**
> 的 `system_prompt`，`office_behavior_config.py` 与前端那两栏均已删除。**本节只作历史留痕，不作为现行口径。**

「提示词唯一出处」再扫一遍全仓（AST 扫 模块级常量 / `or` 兜底字符串 / `prompt|hint|rule|system` 关键字），
揪出并处理 4 处代码侧提示词副本：

| 位置 | 性质 | 处置 |
|---|---|---|
| `llm_client.DEFAULT_SYSTEM_PROMPT` | 全局兜底人设（5 个调用点插入首条 system，DB 里另有一份不同的总助人设 → 必然漂移） | **删除**；无 system 的调用不再被塞人设（`chat_json` 只保留「输出 JSON」契约句） |
| `ai_colleague_service._DISPATCH_SYSTEM_PROMPT` | 总助转接判官提示词 | **迁 DB** `behavior.charter.dispatch_judge`（前端可改）；空则不注入 → 转接退回确定性路由（@点名） |
| `colleague_memory_service._EXTRACT_SYSTEM` | 同事记忆抽取归并提示词 | **迁 DB** `behavior.charter.memory_extract`（前端可改）；空则不抽取 |
| `skill_registry.DEFAULT_SKILL_LIBRARY`（含 `prompt` 种子） | 技能元数据种子 + 提示词副本，且 `default_skill_library()` **零调用方**（死码） | **整块删除**；技能元数据真源 = DB `rules.skill_catalog` |

统一读取口：`app/services/office_behavior_config.py`（纯读、无副作用、无兜底——键缺失即「该处不注入」）。
前端：`OfficeBehaviorEditor.vue`「提示词（高级）」新增「总助转接判官 / 同事记忆抽取归并」两栏；
`api/office.ts` 的 `BehaviorConfig.charter` 同步。

迁移：`scripts/migrate_p5d_role_prompts_20260911.py`（幂等，第二遍 changed=0），文本逐字取自原常量。

守卫：`MECHANISM_FILES` 增补 `llm_client.py / ai_colleague_service.py / office_behavior_config.py`（基线全 0）；
新增 `test_no_code_side_fallback_prompts`——「提示词形状」的模块级常量（名含 PROMPT/SYSTEM/PERSONA 且值含中文）
一旦出现即红，旧符号（`DEFAULT_SYSTEM_PROMPT` 等）复活也红。

`pytest tests -q`：**583 passed**（+1 新守卫）。

### 19.3 开场白 / 审批兜底文案去重（2026-09-11）

- `api/assistant.py._DEFAULT_OPENING`（硬编码「服务器配置顾问」开场白）+ `_opening_message()`（读一个 DB 里根本不存在、
  也无人写入的 `system_config.assistant_opening`）**整段删除**。新建会话的开场白改为读「员工配置」
  （Manage Teams · 员工 · 开场白）：未点名同事即 `assistant` 本人，与团队群、员工会话同源。
  盘点结论：6 名在职员工 DB 里各自都有 `system_prompt` + `opening_message`（`EmployeeManager` 可改），
  代码侧全局开场白是唯一的第二套；`system_config_repo.py` 里那 5 条开场白是**首次播种默认值**（运行期唯一来源仍是 DB），不算第二套。
- `colleague_turn_service` 审批 activity 的兜底句「AI 已生成草稿，等待用户确认后再继续。」**删除**（改 `or ""`）：
  同处第 609 行已有事实句 `等待审批：<工具名>`；`GovernancePanel` 对空 `payload.message` 直接不渲染该行。
- 守卫升级：`test_no_code_side_fallback_prompts` 的扫描范围从 `app/services/*.py` 扩到 `app/**`（含 `api/`），
  并把 `_DEFAULT_OPENING` 加进禁用符号表——它正是漏在 services/ 之外才活过上一轮的。

`pytest tests -q`：**583 passed**（守卫加强，条数不变）。

### 19.4 「提示词（高级）」整块退役（2026-09-11）

用户判定：**冗余**——每个员工已有自己的提示词，workflow 运行口径 = 编辑器左栏任务规则（2026-09-12 起节点抽屉不再承载指令）。整块删除，不留第二套。

| 层 | 处置 |
|---|---|
| DB | `rules.system_config.ai_colleagues.behavior` 下 `brain.{system_prompt,user_rule,minutes_prompt}`、`mission.{agent_system_prompt,lead_system_prompt}`、`charter`（整块）删除。迁移脚本 `scripts/migrate_retire_advanced_prompts_20260911.py`（幂等，二跑 changed=0） |
| 后端 | 11 处消费点全部收口；删 `services/office_behavior_config.py`；删两个会把旧键写回的迁移脚本（`migrate_p5d_role_prompts_*` / `migrate_p5_wave3_*`）；`office_brain` / `office_mission` / `agent_react` / `colleague_turn_service` 去 charter 拼接 |
| 前端 | `OfficeBehaviorEditor.vue` 删整块「提示词（高级）」；`api/office.ts` 的 `BehaviorConfig` 同步删键 |
| 内部工序 | `dispatch_judge`（转接判官）/ `memory_extract`（记忆抽取）改注入**相关员工自身**的 `system_prompt` |

**唯一出处新口径（替代旧口径）**：

1. 角色层提示词 = 员工自己的 `ai_colleagues.<role>.system_prompt`（Manage Teams · 员工 · 提示词），**唯一一处**。
2. workflow 运行口径 = 编辑器左栏「任务规则」（`graph.manual_rules`，2026-09-12 起唯一；节点抽屉只留机制配置）。
3. `behavior` 只剩开关与数字（`brain.*` / `mission.*` 的非文本项），不再承载任何提示词。

守卫同步：`test_no_code_side_fallback_prompts` 扫描范围 `app/services/*.py` → `app/**/*.py`（`_DEFAULT_OPENING` 加禁用符号表）；
`test_constitution.py` 的 `MOVED_RULES` 撤销 9 条已退役锚点（**有意退役**，非能力丢失），`MECHANISM_FILES` / `PROSE_BASELINE` 去掉 `office_behavior_config.py`。
`pytest tests -q`：**588 passed**。

### 19.5 P5-B/P5-C：暂停断点一致性 + e2e 取证（2026-09-11）

| 项 | 内容 | 证据 |
|---|---|---|
| B1 断点唯一 | `skill_turn_engine._prepare` 只认 `mem.engine_pause` 作断点；`steps_done` 取 `pause.resume.steps_done or mem.steps_done`；载荷与 mem 不一致时只**记事实**（`engine["resume_mismatch"]`），不改写 | `tests/test_pause_resume_consistency.py`（3 条） |
| B2 胶囊按事实显示 | `TaskStepper` 新增 `pause` 入参，标题按「中断在 <label\|step> · <原因>」渲染；原因码 → 文案的映射就在**前端组件本地**（`REASON_LABEL`），不复制后端任何话术；`assistantChatWs` 暴露 `taskPause`（`pauseFactsOf` 原样透传），两个面板接线 | `npx vue-tsc -b` 通过 |
| B3 审批中断同源 | `colleague_turn_service` 的 `approval_required` 广播带上同一份 `pause_payload(kind="approval")` | `tests/test_pause_payload.py::test_approval_pause_uses_the_same_payload_object` |
| C1 e2e 取证 | 新夹具 `scripts/e2e_scenario_stall.json`（需求不全且不补答）；`e2e_skill.py` 报告新增「暂停 / 断点」段，指标加 `pause_events / pause_kinds / pause_reason_codes / pause_facts_incomplete / pause_kinds_unknown` | 真机跑 1 轮：`kind=brain_ask reason=brain_ask step=agent_fill resumable=True pending=['server_type']`，未登记 kind = 0 |
| C1 守卫 | `PAUSE_KINDS` 登记表必须**等于**真实发射点（AST 扫 `_emit_pause` 首参 + `pause_payload(kind=…)`），新增出口忘了登记 = 红 | `tests/test_pause_payload.py::test_e2e_pause_kind_registry_stays_in_sync_with_emitters` |
| C2 文档 | 「体量最大头」按实测改准（§12）；`AI办公室-系统结构梳理…` 的旧 §4 执行方案冻结，只留「明确不做」红线 | 本文件 §12/§19.4、另一文档 §4 |

## 20. 「还剩几个 P」总账（2026-09-11 定档）

口径先说清：**P = 有明确产出物与验收门的施工轮次**，不是无限续杯。到 P5 为止，机制欠账
（提示词第二套 / 兜底话术 / 暂停无统一对象 / 单文件巨型）已全部收口，剩下的都是**有界**的。

| 轮次 | 内容 | 状态 |
|---|---|---|
| P0–P2 | 结构盘点 + 行身份模型修正 + 提示词唯一出处 | ✅ |
| P2.5 | 单轮墙钟上限 + 零产出失败出口 | ✅ |
| P3 | 行身份铸造 → 工具契约收口 | ✅ |
| P4 | 暂停载荷对象化 / 提示词守卫 / 配件层拆分 | ✅ |
| P5 | 机制文案欠账清零 + 高级提示词退役 + 暂停断点一致性（B1/B2/B3） | ✅ 本轮 |
| P6 | 拆 `colleague_turn_service.py`（1122 行 → 3 模块 + 薄壳，机械搬家、零行为改动） | ✅ 本轮 |
| **P7**（可选） | 拆聚合层大文件：`api/portal.py` 2086 / `repository/kp_repo.py` 1219 / `api/ai_colleagues.py` 1136 | 2026-09-13 拍板：**暂缓**，排到配件规格验收+规则中心设计之后（并行工作面上拆文件=撞车） |

**做完 P6 就收敛**：同事回合链路已拆到 ≤700 行（守卫 
`tests/test_colleague_turn_layout.py`：归属表 + 行数预算 + 依赖方向 + 重导出完整性）。
P7 属 API / 仓储聚合层，是体量治理的**可选项**，不影响机制正确性——你不点头就不计入欠账。

**不占 P 编号的两件挂账（产品决策，不是欠账）**：

- ~~`grep_parts` 命中后是否直接锁定候选（现在必须回 `query_parts` 检索一次）~~ → 已由 §24 关闭（落料改按料号名回库核对，见 §14）。
- ~~结果集内二次过滤（现在只有第一次检索）~~ → 2026-09-13 拍板：**不做**（库 288 件打库 <1s 无感；触发条件=库 >2K 件或候选翻页 >2 页再立项）。

**终点定义**：P6 已完成（2026-09-11）；主线残留②已于 2026-09-12 关闭（§22）。~~剩下「三件产品决策拍板
残留①的语义边界（大脑显式声明两条不同 origin 的行，属语义决策不是引擎缺陷）」即为本主题结项。~~ →
**2026-09-13 全部拍板收口**：残留①语义边界=左栏规则 6「行归属纪律」（见 §14）；grep_parts 直锁=§24 已关；
结果集内二次过滤=**决定不做**（库 288 件打库 <1s，等库 >2K 件或候选翻页超过 2 页再立项）。本主题结项。

## 21. 仓库级重复文件审计 + 清理（2026-09-11，P6 同轮；21.4 为仓库级挂账，不属于需求分析功能）

**审计口径**：文件级 3-gram 相似度（465 文件）+ 函数级 AST 比对（1847 个函数）+ 精确
引用扫描。结论：**不存在整段复制粘贴**（最高相似度 0.285；跨文件完全相同的函数仅 6 处，
且多为合理样板）。真正的病是**「同一个概念被两次建成」**——这是多轮 AI 接手留下的痕迹。

### 21.1 已删（零风险死码）

| 对象 | 依据 |
|---|---|
| 13 个废弃提示词脚本（`refine_prompt` / `rewrite_prompt` / `update_flow_prompt` / `update_agent_fill_prompt` / `refine_named_model` / `read_db_prompt` / `read_flow_cfg` / `patch_cap` / `patch_hasmodel` / `dump_think` / `dump_think2` / `check_models` / `e2e_summary`） | 全部 `refs=0`；前 5 个读**已不存在**的 `reasoning_prompt_defaults.json`；其中 3 个会**反向写库**提示词，与「唯一出处」冲突 |
| `app/schemas/__init__.py`（0 行空壳） | 全仓零引用 |
| 6 个前端真孤儿：`components/flow/DocumentCard.vue` / `components/assistant/NodeTraceList.vue` / `utils/reasoningNodeIo.ts` / `utils/reasoningStepCopy.ts` / `composables/reasoningTypes.ts` / `types/l6.ts` | 固定字符串精确匹配命中 0 文件 |
| `composables/useL6ChassisConfig.ts`（241 行） | 它自己是 `/api/l6-chassis/*` 的唯一前端消费者，而它零引用 → 整条链在前端是死的（**后端那 26 条路由仍未删，见 21.4**） |
| `api/admin.py` 13 条注释掉的 deprecated 路由（782 → 763 行） | 只删注释，45 条活跃路由逐项不变 |
| 仓库根 52 个 `tmp_*` 一次性诊断产物（含 14.5 万 / 22.3 万行 json 日志） | 历史 AI 的临时输出 |

### 21.2 合并去重（零行为改动）

- **三个 WebSocket Hub 收敛 + 修一个真 BUG**：新增 `app/services/room_hub.py`
  （房间注册 + **有界广播**）。`assistant_hub` / `feed_hub` 改为继承 `RoomHub`；
  `office_hub`（全局单房间 + 角色过滤，语义不同）改用 `send_bounded()`。
  **修的是什么**：`await ws.send_text` 对半死连接（页面重载 / 网络瞬断 / 客户端停止读取）
  会因 TCP 背压**永久阻塞**，拖死整个回合任务——这是「流程卡在配件选型永远不出结果」的
  实测根因之一。该修复当初**只加在 `assistant_hub`**，`feed_hub` / `office_hub` 漏了
  （同一个 bug 只修了 1/3）。现在三条链路统一 5s 有界等待，超时即判死连接移除。
- **系列枚举去重**：`composables/useSeries.ts` 与 `stores/series.ts` 逐行同逻辑
  （后者注释自认「替代原来的 useSeries」）。`RequirementForm.vue` 是最后一个旧消费者，
  迁移后删除 composable——「全平台系列权威源」回到**唯一出处**。
- **P6 拆分**见 §12 / §20。

### 21.3 不动的两个（用户裁定）

- `store/` 与 `stores/` 两目录：**不是内容重复**（一个管域 store，一个管引擎 store，
  无同名文件），只是命名约定分裂；统一要改 40 处引用、收益有限 → 不做。
- 模板 / 配件 API / 料号库页面三处「同一概念两套」（详见 21.4）→ 属产品决策，未动。

### 21.4 仍挂账（仓库级重复文件，非需求分析功能；需拍板）

- **`spec_template` vs `univer_template` 两套模板**：`app/api/spec_templates.py` 与
  `app/api/univer_templates.py` 的 `update` / `delete` / `set_default` **函数体 100% 相同**，
  两端前端页面都在用。
- **配件 API 三套路由**：`api/admin.py`（45 活跃路由）/ `api/parts.py` / `api/kp_config.py`
  都注册在 `main.py`，前端全塞在 `api/serverConfig.ts` 一个文件里调。
- **料号库两个活页面**：`views/admin/Parts.vue`（`/parts`）与
  `components/server-admin/PartsLibrary.vue`（`/servers/admin` 页签）——同一实体的两套管理界面。
- **`/api/l6-chassis/*` 26 条路由前端零调用**（随 `useL6ChassisConfig.ts` 一起变死）；
  但 `L6ChassisRepository` 仍被 `quote_service.py` 使用，删路由要单独确认。

## 22. 归属收口：行只由属主产生（2026-09-12）

### 22.1 节点 / 产物 / 写入权（复盘，防再走偏）

6 个节点，每个节点只写自己的表；上游产物只读，属主该步落定即冻结：

| 节点 | 填哪张真实表 | 唯一写入者 | 下游读 |
|---|---|---|---|
| `input` | （无表）需求原文 | `input` | `agent_fill` |
| `agent_fill` | 线索登记表（`ext.requirement_slots`） | `agent_fill` | `model_reason` / `kp_reason` / `compose` |
| `model_reason` | 方案配置表 **L6 部分** | `model_reason` | `kp_reason` / `compose` |
| `kp_reason` | 方案配置表 **KP 部分** | `kp_reason` | `compose` |
| `compose` | 完整方案配置表 `plans` | `compose` | `output` |
| `output` | 方案配置卡 `bom_scheme`（落库） | `output` | 商机详情页 / AI 办公室 / 聊天窗 |

**可修改性**：属主节点在工作期间可改自己的表；该步 done 时打快照
（`skill_node_state.DOC_OWNER_BY_NODE` → `frozen_docs`），此后任何写入在回合末判红。
**下游永不回头回填**——这也是「行身份必须由来源铸造（`reg:`/`cfg:`）」的由来。

### 22.2 病灶（主线残留②的一手成因）

配件行 = 「要配什么」。这条事实只有两个来源：① 客户申报 → 线索登记表部件行（`reg:`，
属主 `agent_fill`）；② 客户原话未覆盖、AI 判断要配 → `kp_reason` 声明行（`cfg:`）。
两处把「两个来源」当成了「两条可以并存的身份」：

- `capabilities._merge_kp_rows_locked`（有 picks）只按「完全相同的 (类目,描述)」让位，
  而 `_merge_kp_rows_incremental`（无 picks）是「同类目覆盖」——同一件事两套口径，于是
  `CPU|通用计算服务器处理器（客户未指定型号）` 与点名后的 `CPU|兆芯 9654` 同类目并存。
- `skill_phases.phase_kp_reason` 把声明行与登记行一起并入，但没按归属过滤：登记表已申报的
  类目（CPU/Memory/HDD/SSD/GPU/Raid card/NIC）又被声明一行 → 同一需求两条身份
  （`reg:CPU` + `cfg:CPU`），客户后补型号时旧行还在。

### 22.3 修法（3 处代码 + 2 条回归）

| 件 | 改动 |
|---|---|
| `slot_contract.registration_owned_categories()` | 新增。登记表已申报类目的唯一事实来源 = `slot_spec()` 里 `src_type == "kp"` 的 category（由 `kp_slot_group_map` 配置合成，5s 进程内缓存）。 |
| `capabilities._merge_kp_rows_locked` | 未锁旧行让位口径改为「新表提到该类目」→ 与增量合并的「同类目覆盖」对齐；**已锁行仍冻结**（P0 保护不动）。 |
| `skill_phases.phase_kp_reason` | 声明行按归属过滤：类目 ∈ 登记表已申报 / 已是登记行 → 不再声明；Bridge/HBA/NVSwitch 仍可声明。**2026-09-13 放宽**：过滤依据从「类目 ∈ registration_owned_categories（全量属主类目）」改为「登记表已有该类目行」——全量过滤把 AI 铸的属主类目推荐行（客户没提 CPU/内存等，`cfg:` 身份）下一轮直接丢弃，自选流没有 pick_all 晋升通道，行就此消失、大脑下轮重铸循环（自选 e2e 实测根因）；登记表后来出现同类目行时 `cfg:` 行仍让位（防双身份），其 pick 由 `ensure_pick_rows` 兜底。 |
| `tests/test_locked_rows_freeze.py`（+2） | 占位行 + 客户后补型号 → 同类目只留一行；已登记类目集合 == `slot_spec` 的 `src_type=kp` 集合。 |
| `tests/test_row_identity_incremental.py`（改 1） | HDD/SSD 只剩 `reg:` 一条；HBA 仍铸 `cfg:`——原断言把「两个来源 = 两条身份」当普适规则，现按归属收窄。 |

**没做**（避免过度）：不在 `select_parts` 硬拦 `new_row=true` 的已登记类目。同类目多行
（NIC 千兆 + 万兆、硬盘 1.92T + 960G）是合法需求，登记表本身就允许一类多行；拦在那里会误伤。
归属过滤只回答一个问题：**声明行能不能成为一条新身份**。

### 22.4 验收

- `backend` 全量测试：**596 passed**（基线 594 + 2 条新回归），56.97s。
- 前端本轮零改动。

## 23. 线索登记表回归真实表：影子存储 ext 退役（2026-09-12）

### 23.1 病根（一句话）

同一张线索登记表在系统里有**两份真相**：人工页写真实表 `opportunities.opportunity_requirements`，
AI 对话流写会话记忆里的 `mem["ext"]`，只在最后交付时才落库。归属、冻结、判红、行身份这一整
套守卫，全是在给这个影子容器补漏（补丁永远盖不全：点击通路拿 `dict(mem["ext"])` 副本，
绕开了下游只读视图）。

顺带查出一个真 BUG：`persist_requirement_*` 三个函数的闸门写作
`ctx.get("business_mode") != "opportunity_flow"`，而 `business_mode` **全仓从未被设置过**
→ 条件恒真 → **AI 流的成果从来没有进过真实需求单**（真实表 244 行全部来自人工页）。

### 23.2 改法（AI 流直接读写真实表）

| 件 | 改动 |
|---|---|
| `portal_flow_adapter.seed_ext_from_requirement_draft` | 新增。每轮开始按商机读需求单（草稿优先，其次当前版本）的 slots 播种登记表；无需求单（会话试运行）回空。调用点 `skill_turn_engine._SkillTurnRuntime._prepare`。 |
| `portal_flow_adapter.save_requirement_draft` | 新增。每轮把登记表写回**草稿行**（与人工页同一个存储、同一个接口），写库前按 `requirement_slots_from_ext` 过滤 schema——缓存类中间态（如 `confirmed_slots`）不进业务表。没有草稿行、只有已交付版本且内容未变 → 不新开草稿（否则交付后每轮留一张重复行）。 |
| `portal_flow_adapter.persist_requirement_and_bom_from_ctx` | 交付 = **提交对话期间一直在写的那张草稿**（`submit_requirement_draft`），与人工页「提交需求」同一动作；旧实现 `initiate_requirement` 新开一版，草稿原地留下 + 新 current 内容重复。 |
| 三个 `persist_*` 的死闸门 | 改为只看「有没有 opportunity_id」。 |
| `skill_turn_engine._SkillTurnRuntime` | `_prepare` 用 `seed_ext_from_requirement_draft` 播种；每轮写回走 `save_requirement_draft`，**6 处**会话记忆落盘全部收口到 `_store_mem`（先写业务表=真相，再写记忆=缓存）。`mem.ext` 由此降级为**当轮工作副本**（像编辑器的表单模型：读草稿→改→回写）。 |

### 23.3 验收

- `backend` 全量：**604 passed**（新增 `tests/test_requirement_draft_store.py` 8 条）。
- 真实 e2e（HTTP/WS/真实 LLM/真实库）跑了两次：2 轮 / 138s 与 4 轮 / 235s 均 `finished=true`、
  `repeat_rows=0`/`repeat_cats=0`、8 行配件 / 17 行组装、走到 `output`。
- 真实库核对（`ai-...` 商机）：v1 draft 由 AI 每轮写入 → 交付时**原地提交为 v1 current**；
  内容未变的后续轮次不再制造草稿行；内容变化才开新草稿。slots 只含登记表 6 字段 + `kp_rows`，
  其中 `HDD/SSD` 3 行（480G×2 / 1.92T / 6T×4）、`NIC` 2 行（千兆 / 万兆）——**一类多行合法，
  同一身份不重复发布**。

### 23.4 还没做（可选清理，不再影响正确性）

- 守卫机制 `frozen_docs` / `FrozenDocView` / `doc_freeze_violation` 暂留：影子语义已消失，
  它们现在只保护「轮内下游节点不写上游表」。删它属于纯代码瘦身，有回归面，未做。
- `mem.ext` 里仍混着 `confirmed_slots` 这类非业务键（只是当轮缓存，不再进业务表）。

### 23.5 订正：实际落地的函数名（2026-09-12 后续轮次）

§23.2 已按实际落地名称订正；本小节保留当时修正记录与调用点：

- 读回播种 = `portal_flow_adapter.seed_ext_from_requirement_draft`；调用点
  `skill_turn_engine._SkillTurnRuntime._prepare`（仅 `write_mode == "draft"` 且有商机时）。
- 每轮写回 = `portal_flow_adapter.save_requirement_draft`；调用点
  `skill_node_plugins._FillNode.wire_result` → `portal_flow_adapter.persist_requirement_from_ctx`。
- 交付原地提交 = `portal_flow_adapter.submit_requirement_draft`（取 `save` 回的 version），
  不再 `initiate_requirement`。
- 落库闸门 = `portal_flow_adapter._write_mode` / `_can_persist_draft`：由入口显式给
  `write_mode`（`colleague_turn_runners._skill_write_mode`：试运行入口 → preview；有商机 →
  draft；都没有 → none），`business_mode` 彻底不再被读。
- 中途方案配置草稿 = `portal_flow_adapter.save_scheme_progress_from_ctx`（用
  `skill_node_runtime.build_plans` 的同一份组装口径）。
- 回归：`backend/tests/test_write_mode_persistence.py`（10 条）。当前全量 **606 passed**。

## 24. 去检索台账：落料改按料号名回库核对（2026-09-12，A1/A2/A4）

### 24.1 病根（一句话）

`query_parts` 把「大脑本轮检索过的候选」写进 `kp_search_index` 留底，`select_parts` 只认这份
留底——于是「接地」变成了**上一轮检索动作的副作用**：换个关键词、翻页、或直接用 `grep_parts`
找到的料，都可能因为「不在留底里」而被拒；而 `part_id` 只是自增行号，不是业务料号，拿它当
落料凭据本身就是错的口径。

### 24.2 改法

| 件 | 改动 |
|---|---|
| `skill_tools_kp.py`（`query_parts`） | 删掉写留底的两处；检索变成纯去库读。 |
| `skill_tools_open.py`（`open_part` / `open_row` / `open_category` / `grep_parts`） | 只读库，不读也不写任何留底（原本已是直连，残留引用一并清掉）。 |
| `skill_tools_select.py` | 删 `not_searched` / `not_in_search_results` 两档拒绝；落料凭据改为**料号名**：按「类目+名称」（忽略大小写/空格差异）回库精确核对——唯一命中→落行（价格取库内最新值）；同名多命中→未落料、原样回全部同名行让 AI 确认；零命中→白盒 `no_such_part`。`part_id` 只留历史 pick 的兼容直读通道。**2026-09-13 补 `part_required` 契约错误**：pick 缺 name/part_id（new_row 只给 category+spec 铸行）曾一路走到 `hit=None` 崩 AttributeError、整次调用报废（同批已铸行被丢回、下一轮重铸循环），现循环顶早退白盒错误并指向 fill_requirement(kp_rows)。 |
| `skill_node_plugins._waived_options` | 「库里没有点名的型号」的判定从「本轮留底为空」改成当场 `lookup_parts_by_name` 核对，与行卡候选同源、两条出路可并存。 |
| `agent_tool_specs.py` / `agent_tool_handlers.py` | 工具说明与 handler docstring 删「接地索引」「不在 select_parts 的可锁定范围」「只能从 query_parts 的结果中选取」这类台账口径。 |

### 24.3 左栏同步（C1）

提示词唯一出处是左栏 DB：`rules.reasoning_flow` 125 的 `graph.manual_rules` 第 15 条原写
「先逐行调 query_parts 检索 → 再从检索结果 select_parts 批量提交」，已改为「按料号名落行、
同名料号多命中回候选、零命中白盒说明」，其余 22 条原样不动。
`backend/scripts/migrate_left_panel_rule15_20260912.py`（幂等，可 `CPQ_DRY=1` 预演）。

### 24.4 验收

- `backend` 全量：**606 passed**（A5 改的 14 个文件 + B 阶段新增
  `tests/test_write_mode_persistence.py` 10 条）。
- 四数字对账（DB ↔ API）：`opportunities` 按 status `ai_office 251 / active 164 / deleted 3`；
  `/api/opportunities/list` total = 164；`/api/opportunities/ai-leads` total = 251；
  `/api/dashboard/summary?period=week` kpi = `{total_opportunities: 160, total_configs: 415,
  new_opportunities: 4, new_configs: 8}`。两个 total 与 DB 分桶一致。
- 已完成：A3（`suggest_parts` 退役）——`suggest_parts` 加入 `tool_names.RETIRED_TOOL_IDS`，DB 配置读取时自动剔除。

## 25. S4 平台推导：CRE 选型规则接到登记阶段（2026-09-12，C 段）

### 25.1 形态（推断摆桌，不落槽）

「平台类型」这类目录字段不再只靠 AI 裸猜：CRE 加一条赋值型 derive 规则
（`平台：CPU 兆芯/KH → Polaris`，rules.compatibility_rules id=27，随 startup
`seed_missing_defaults` 自动流库），登记阶段对**空缺**目录槽跑 `eval_assign_value`
首命中，推导值以事实行进 agent_fill 的【步骤准备】——标注「推断值」。

分层：规则本体住 CRE（唯一真相源）；登记表侧只接线
（`selection_engine.registration_rule_context` 登记表→求值 ctx +
`plan_rule_apply.catalog_derivations_for_registration` 空缺槽首命中 +
`_FillNode.prepare` 摆桌）。**推断值不落槽**：落槽仍走 fill/ask_user + 前提闸门
（`unconfirmed_premise_fields`），确认口径住左栏规则 6/8——引擎不发卡（唯一大脑）。

### 25.2 验收

- `tests/test_platform_derive.py` 6 条（ctx 暴露 / 兆芯命中 AMD 不命中 / 只推空缺 /
  prepare 摆桌 / 规则读失败降级）；全量 629 绿。
- zhaoxin e2e：platform_type 卡带「Polaris（推荐）」标注（改前同卡无推荐），
  5 轮 227.9s、repeat=0、8 行配件全落地、机型锁 ZS22V2-P（兆芯 KH50000 双路匹配）。
- 映射拍板留档：AMD→Orion 猜测成立但 `kp_part_compat` 近空无法证实；Intel
  series 枚举在但 base_configs 零行；海光无件无机型——三条不写规则，待业务确认
  后由策略中心补。
