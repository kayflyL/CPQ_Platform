# 需求分析 Skill · 节点产物契约（锚点原则）

> 最后更新：2026-09-12（§3.6：node_mission 退役，指令唯一出处=左栏）。
> 原则（用户 2026-09-10 定调）：
>
> 1. **每个节点只写自己的表；上游产物是只读参考，下游永不回头回填。** 线索登记表一经落定即冻结。
> 2. **节点输出物不是新建的表，就是商机详情页对应节点的真实业务表（唯一一份）。** 人工流人工填，AI 流 AI 填。节点目标层 = 这张真实表的「填写契约」（填哪张表、填哪些字段、AI 结果怎么映射成字段值），不新建表、不复制。
> 3. **字段唯一权威 = 真实业务表的 schema。** 节点只引用真实表字段，不发明、不重命名、不作别名。**不做全局字段词典**（会焊死字段、破坏可换性）——防漂移靠边沿一致性校验。
> 4. **换插头 = 换成让 AI 去填另一张真实表**，始终只有一张表存在。

## 0. 契约分层

| 层 | 职责 | 节点配置驱动 | 可单测 |
|---|---|---|---|
| 产物契约层 | 每类产物 = 真实业务表的 schema + 填写契约（挑哪些列、怎么映射） | `target.artifacts` / slot 配置 | schema 校验 + 边沿一致性用例 |
| 节点行为层 | `run(ctx) -> {artifact, gaps, asks, blocked}`，只读上游声明产物、只写自己产物 | `description` / `goal` / `enabled_tools` | 伪上游 + 桩工具单测 |
| 工具层 | 数据访问 / 检索 / 选型可插拔实现 | `enabled_tools` | 桩依赖单测 |

## 1. 节点 → 真实表 → 读方 一览（同一张表，唯一份）

| 节点 | 填哪张真实表（唯一份） | 行来源 | 下游谁读 | 是否写回上游 |
|---|---|---|---|---|
| `input` | （无表，只转需求原文）`requirement_text` | 客户消息 / 商机上下文 | `agent_fill` | 否 |
| `agent_fill` | 商机详情页**线索登记表**（`ext` 里的 `requirement_slots`，冻结） | 客户原话 + 目录值域归一 + ask_user 确认 | `model_reason`、`kp_reason`、`compose` | 否（只填这张表） |
| `model_reason` | 商机详情页方案配置表 **L6 部分**（`l6_chassis`） | 候选机型池 + `template_eval` 求值 | `kp_reason`、`compose` | 否 |
| `kp_reason` | 商机详情页方案配置表 **KP 部分**（`kp_table`） | `kp_landing`（按行锁定 / 推荐确认的落地行） | `compose` | 否 |
| `compose` | 商机详情页**完整方案配置表**（`plans` = L6 + KP） | `baseline × 该机型 kp` 确定性组装 | `output` | 否 |
| `output` | 商机详情页**方案配置卡**（`bom_scheme`，落库） | `payload_map`：`plans←ctx.plans`、`ext←ctx.ext` | 商机详情页 / AI 办公室 / 聊天窗 | 否 |

## 2. 各节点产物字段契约（字段引用真实表 schema）

### 2.1 `input` → `requirement_text`（非表，仅需求原文）
- 字段：`text`（客户原始自然语言）、`context`（商机 / 账户上下文摘要）、`opportunity_id`、`role_key`
- 行来源：客户消息 + 商机上下文；无目录归一、无工具
- 写入者：`input`；读者仅 `agent_fill`

### 2.2 `agent_fill` → 线索登记表（唯一冻结文档）
基本信息 6 字段（权威 = 商机详情页线索登记表单 `requirement_sheet_form.config_fields`）：

| key | label | 候选来源 | 填写规则 |
|---|---|---|---|
| `server_model` | 机型型号 | 目录白名单 | 客户明说 → 填；未说 → 留空交 `model_reason`，登记表不猜 |
| `server_type` | 服务器类型 | 目录白名单 | 明说 → 直接选；没提 → AI 推断先选 + ask_user 确认 |
| `platform_type` | 平台类型 | 目录白名单 | 同 `server_type` |
| `chassis_form` | 机箱形态 | 目录白名单 | 同 `server_type` |
| `purchase_qty` | 数量 | 自由输入 | 默认 1 |
| `warranty_years` | 维保年限 | 自由输入 | 未提默认 |

部件行（权威 = `kp_categories` + `kp_slot_group_map`，每行）：`category`（大类）、`request_spec`（客户原话 / 规格，保留字面）、`qty`、`specified`（是否明确给具体型号）、`note`；GPU 行有 `allow_absent` / `absent_value_enum` / `required_by_type`。
写入者：仅 `agent_fill`。落定即冻结，任何下游只读、不回填。

### 2.3 `model_reason` → 方案配置表 L6 部分
- 行字段（来自真实方案配置表 L6）：`catalogue`（配置件）/ `description`（说明）/ `qty`（数量）；列定义读抽屉 `target.artifacts[0].columns`
- 行来源：`rows_from = template_eval`（选中机型 BOM 模板求值，基础机箱）
- 附带产出（同节点，非登记表）：锁定的整机基准 `baseline`（`server_model_id` / `series` / `form` / `bays` / `parts_count` / `total_price`）+ 候选池 `baselines_pool`
- 唯一写入者：`model_reason`；读者：`kp_reason`、`compose`

### 2.4 `kp_reason` → 方案配置表 KP 部分
- 行字段（来自真实方案配置表 KP）：`part_category`（Catalogue）/ `catalogue`（Configuration Description）/ `qty`（Quantity）
- 行来源：`rows_from = kp_landing`（按行锁定 / 推荐确认后的落地行；未落地不虚报）
- 节点私有工作状态（`engine.node_state.kp_reason`，**不在 ext**）：`picks` / `recommend` / `config` / `absent`
- 唯一写入者：`kp_reason`；读者：`compose`

### 2.5 `compose` → 完整方案配置表（plans）
每项 `plan` 字段：身份（`config_id` / `server_model_id` / `name` / `model` / `series` / `form` / `bays` / `bom_template_id`）、业务（`use` / `product_content` / `recommend_level` / `selling_points` / `chassis_signals` / `selection_alerts` / `unmatched`）、金额（`summary{parts_count, kp_count, unmatched_count, l6_cost, kp_cost, total_cost, currency, rates}`）、明细（`cfg{bom_excel_rows = l6_rows + kp_rows}`）。
行来源：`baseline × 该机型 kp` 确定性组装。唯一写入者：`compose`；读者：`output`。

### 2.6 `output` → 方案配置卡（bom_scheme）
- `output_kind = bom_scheme_draft`——交付去向由它决定（requirement / bom_scheme / conversation_reply）
- `target` = 目标层插头（与其他节点同形：`target.artifacts[0].slot = bom_scheme`）。历史配置把 `target`
  写成产物引用字符串，与插头同名不同义，本轮已收口：`finalize_output` 不再读那个字符串
- `payload_map`：`plans ← ctx.plans`、`ext ← ctx.ext`
- 落库：`persist_requirement_and_bom_from_ctx`（写入真实 requirement + bom_scheme）；无商机会话模式走 `build_preview_bom_scheme`
- 交付：商机详情页 / AI 办公室 / 聊天窗；唯一写入者：`output`

## 3. 节点隔离：状态放哪、产物怎么打包（2026-09-10 落地）

### 3.1 状态容器 `node_state`（已落地）
- 模块：`app/services/skill_node_state.py`
- 引擎/内存容器 `engine["node_state"]` ≡ 落盘 `mem["node_state"]`（**同一块对象**，回合内就地改、回合末回写）。
- `node_state(container, node_key)` 取该节点分区；`kp_state(container)` = `node_state(..., "kp_reason")`。
- `ext` 只保留「线索登记表」这份上游冻结文档；节点工作状态一律进各自分区。
- kp_reason 迁移：`ext.kp_picks/kp_recommend/kp_config/kp_absent` → `node_state.kp_reason.{picks,recommend,config,absent}`。
- 回归：`tests/test_node_state_isolation.py`（分区互不串扰 + 对象身份 + 跨轮往返 + 不回写 ext）。

### 3.2 产物槽只由抽屉声明（2026-09-10 收口）
- 模块：`app/services/skill_node_artifacts.py`；解释器注册表 `BUILDERS`（按**产物槽**分发）。
- 已注册产物槽（6 个）：`requirement_text`(input) / `requirement_slots`(agent_fill) /
  `l6_chassis`(model_reason) / `kp_table`(kp_reason) / `plans`(compose) / `bom_scheme`(output)。
- 插头两栏针脚，各司其职：**`slot` = 装什么**（产物槽，分发只认它，且**只在抽屉里声明**）；
  **`kind` = 怎么显示**（form / table / document，前端抽屉预览认它，不参与分发）。
- 代码里**没有**「节点 → 产物」兜底表（原 `DEFAULT_KIND_BY_NODE` 已删）：没声明 slot 的节点产物为空
  ——白盒不装懂，这是「换插头换得掉」的前提（回归：`tests/test_node_artifact_contract.py`）。
- `columns`（列契约：`key/label/from/fallback`）与 `rows_from`（行来源）是数据针脚：取值链只用于
  **行整形**，展示列只取 `key/label`——两栏分开，免得渲染列名被当成取值契约去校验。
- 组装节点（compose）产物 = 完整方案配置表行（`plans[].cfg.bom_excel_rows` 的 L6 + KP 求值行）；
  交付节点（output）同样带产物：「输出」节点下方也有输出物。
- 实时产物（边干边亮）同样是产物槽的属性：`LIVE_EMITTERS = {产物槽 → 发射器}`，主循环不认节点名。
- 登记契约（`requirement_slots`）也走同一条插头解释链路（`format_contract` 先认 slot 再认 kind），
  `kind=form` 特判已删；填写规则归抽屉 `description`（节点使命）与工具 schema，契约不二次复述。
- 迁移：`scripts/migrate_node_artifact_slots.py`（一次性把 slot 写进 `rules.reasoning_node_default`
  与各流增量；空库初始值见 `skill_config_bootstrap.NODE_PLUGS`）。

### 3.3 边沿一致性护栏（已落地）
- `skill_target_contract.validate_artifact(插头, 真实行)` → `{ok, broken_columns, unresolved_columns}`：
  列 `from/fallback` 链在真实产物行上取不出值即判红（列名对不上 / 上游改了字段名，不静默空列）。
- kp / 组装产物打包时对上游原始行做同一检查，不一致打 warning。
- 契约级检查用**上游原始行**（抽屉 `from/fallback` 指向的字段），展示行只用 `key/label`——
  两者混用会出现「列名当字段名」的假红/假绿。
- 回归：`tests/test_node_artifact_contract.py`（含「换 slot / 换列定义，主循环零改动」、
  「每个节点在真实抽屉里都声明了已注册产物槽」与「真实抽屉配置不得让打包抛错」）。

### 3.4 登记表冻结：属主打点 + 回合末判红（已落地）

- 属主节点（`agent_fill`）该步通过校验并标 done 的那一刻，对登记表打**内容快照**
  （`skill_node_state.mark_doc_frozen`，引擎/记忆容器里的 `frozen_docs.requirement_slots`）。
- 之后每一步结束时核对一次（`doc_freeze_violation`）：属主以外任何节点改动了登记表 →
  `logger.error` + 引擎 `contract_warnings`，让「下游回填上游」在运行时暴露，而不是靠约定。
- 引擎内部键（下划线开头）不计入登记内容，避免误报。

### 3.5 客户对某行的回答：进本节点分区，不碰上游文档（已落地）

- `kp_row_merge`（客户对某条配件行的追问回答）不再并进 `ext.kp_rows[].description`，
  而是按**登记行键**记进 `node_state.kp_reason.row_answers`。
- 行键始终取自登记原文 → 客户补一句话不会让该行已锁定的选型失配作废
  （旧实现改描述 = 改行键 = 丢选型）。
- 该回答在节点工作时叠加成该行的**检索文本**（`kp_rows_ctx[].answer`），
  登记表保持冻结。回归：`tests/test_node_contract_step45.py`。

### 3.6 指令唯一出处=左栏、完成摘要取产物（2026-09-12 收敛）

- 2026-09-12 起 `node_mission`（节点使命 = 抽屉 `description` + `goal` 注入每步 system）**退役**：
  指令唯一出处 = 左栏 `graph.manual_rules`；节点抽屉与 `rules.reasoning_node_default`
  的 prose 键（description / goal / final_contract）全清，原活指令增量并入左栏规则 13/14/15/24
  （迁移 `scripts/migrate_left_panel_single_home_20260912.py`）。主循环里的
  `if step_key == "kp_reason"` / `"agent_fill"` 节点专属文案早已全部删除。
- `skill_node_artifacts.done_summary(engine, key, artifact, vres)`：节点完成摘要由**产物**生成。
  产物为空就如实说空（`（产物为空）`），未注册产物说「本节点未注册产物」——
  不再按节点 key 硬编码文案（历史事故：`agent_fill` 完成时显示「配件选型完成」）。
- `skill_node_artifacts.emit_live_artifact`：节点回合内的实时产物广播（边干边亮）也改为
  注册表声明（`LIVE_EMITTERS = {产物槽 → 发射器}`），主循环不再认节点名。

### 3.7 取件工具的作用域真话（2026-09-10 落地）

机型锁定后候选池只剩「适配该机型平台」的料（`_SeriesScopedRepo` 在取数边界过滤）。这会带来一个
危险的误读：**「库里有、但不适配当前平台」被说成「库里没有」**——AI 于是拿着错误前提去问客户
（实测：兆芯 KH50000 只适配 Polaris，机型平台被推断成 Orion 后，每一轮都在问「要不要换成 AMD」，
10 轮不收敛、走不到交付）。

- `data_tools._scope_blocked`：作用域内零命中且库内确有匹配料时，回 `out_of_scope`（料名 + 各自
  适配平台）与 `scope_note`（「这不是『库里没有』，请客户在『改平台』和『换料』之间拍板」）。
- `part_query` 与 `part_recall` 两条检索通道都带这份真话；行批量召回的零命中 `reason` 也改成
  报真话（`_zero_reason` 优先用 `scope_note`），不再输出「库内无精确匹配」。
- `query_parts` 工具 schema 同步写明：收到 `scope_note` 必须如实告知客户，不许说库内无料、
  不许自行编替代型号。
- 回归：`tests/test_kp_scope_disclosure.py`。

## 4. 结构性差异收口（2026-09-10 完成）

1. ~~`ext` 仍是共享可变 dict~~ → **已拆（类型级只读）**：非属主节点拿到
   `skill_node_state.FrozenDocView`（写操作一律抛 `DocWriteForbidden`），属主 `agent_fill` 拿原始
   dict；读操作与 `isinstance(dict)` 判断保持兼容（否则会被替换成空 dict、登记内容丢失）。
2. ~~`make_agent_brain`（约 200 行）死代码~~ → **已删**，用例迁到 `run_brain_attempts`
   （大脑重试循环 + 收口）。
3. ~~`agent_fill` / `input` 未注册成插头~~ → **已注册**：六个节点都在抽屉里声明了产物槽，
   `kind=form` 特判与按节点兜底表都已删除。
4. 节点机制全部走插件钩子（`app/services/skill_node_plugins.py`）：编排壳里没有「按节点名的
   **分支**」（`if/elif node_key == "..."`）。仅剩两处按 step key 取展示 label 的查找
   （入口 / 交付节点），不是行为分支。回归：`tests/test_node_plugin_contract.py`。

## 5. 增量迁移顺序（已完成）

`agent_fill → model_reason → kp_reason → compose → output` 五个节点已全部迁完：
节点状态分区（`node_state`）、产物槽抽屉化（无代码兜底表）、节点使命取抽屉 `description`、
完成摘要取产物、`ext` 类型级只读、节点机制插件化。

## 6. 实测记录（2026-09-10，真实 HTTP + WebSocket + 真实 LLM + 真实库）

场景：`backend/scripts/e2e_scenario_zhaoxin.json`（兆芯需求原文，2 颗兆芯50000 / 768GB DDR5 /
2×480G + 1×1.92T SSD + 4×6T HDD / RAID 1GB 缓存超融合 RAID0-1-5-6+JBOD / 4 千兆 + 2 万兆 /
双电源 / 3 年 7x24）。驱动：`python -X utf8 scripts/e2e_skill.py --scenario ... --keep`。

### 6.1 三种需求都走到 output 终点（2026-09-10 复测，真实 HTTP + WS + 真实 LLM + 真实库）

同一套引擎，三种输入（越往下越模糊）。**模糊需求靠大脑自己推断 + 有选择地问**这条设计成立：

| 场景 | 输入 | 轮次 | 配件行 | 组装行 |
|---|---|---|---|---|
| 详细 | 兆芯 2 颗 50000 / 768GB DDR5 / 2×480G+1×1.92T+4×6T / RAID 1GB 超融合 / 4 千兆+2 万兆 / 双电源 / 3 年 7x24 | 3 轮 | 8 | 17 |
| 中等 | 2U 机架式通用计算，2 颗 CPU，内存 256G，万兆网卡，双电源 | 2 轮 | 3 | 12 |
| 模糊 | 「需要通用计算服务器，AMD平台的。」 | 3 轮 | 1 ⚠️ | 10 |

⚠️ 模糊场景**走到终点但只落了 1 行配件**：客户后续补了「内存 512G、系统盘 2×480G、RAID、网卡」，
大脑在登记表里只补了 CPU 一行，于是终检「登记的大类都落地了吗」自然全过 —— 交付了一张
只有 CPU 的整机单。**这是大脑登记质量问题，不是管道问题**（管道只能核对「登记 vs 落地」一致性，
不能用词表去猜客户原话里提过什么 —— 那正是被否掉的机械匹配）。已如实记录，待后续用提示词/示例收紧。

详细场景逐节点产物（模糊/中等同结构，行数不同）：

| 节点 | 产物槽 | 实测产物 |
|---|---|---|
| `input` | `requirement_text` | 需求原文透传 |
| `agent_fill` | `requirement_slots` | 线索登记表 · 6 项 + 8 行部件（类型/平台/形态都经客户选项卡确认） |
| `model_reason` | `l6_chassis` | 机箱表（L6 配置）· 机型「ZS22V2-P」/ 9 行 |
| `kp_reason` | `kp_table` | 配件表 · 8 行（首行 `KH50000 96C` ×2）|
| `compose` | `plans` | 方案配置表（L6 + KP 组装结果）· 17 行 / 1 个整机配置 |
| `output` | `bom_scheme` | 方案配置卡 · 已生成 |

8 行配件实际落地：兆芯 KH50000 96C ×2、64G DDR5 RDIMM ×12（768GB）、480G SATA SSD ×2、
1.92T SATA SSD ×1、6T SATA HDD ×4、LSI 9361-8i（1GB 缓存）、4 口千兆 ×1、2 口万兆（含光模块）×1。

### 6.2 本轮实测发现并修掉的缺陷

1. **「库里有、但不适配当前平台」被说成「库里没有」**（改造前 10 轮不收敛的根因，见 §3.7）：
   补上作用域真话（`out_of_scope` + `scope_note`）后，AI 不再自行编替代方案，而是走回
   「先跟客户确认平台」这条正路。
2. **列表增量会整条盖掉默认契约**：迁移脚本给「没声明 `target` 的流增量」凭空写 `target`，
   而合并语义里列表是整体替换 → 默认契约里的列契约被清空（kp_reason / compose 的三列）。
   迁移已改为只补「自己声明了 `target`」的增量，并把被盖掉的行修回。
3. **组装节点只报方案计数、没有表行**：`_plans` 现在按抽屉列契约整形
   `plans[].cfg.bom_excel_rows`（L6 + KP）——画布「方案组装 · BOM」节点下就是方案配置表本体。
4. **行整形把展示列当成了取值契约**：`part_category` 在 L6 行上不存在 → 假红。
   现在整形走带 `from/fallback` 的列契约、展示走 `key/label`（护栏用例当场抓出来的）。

5. **未完成的节点被落穿到组装/交付**（本轮最重）：大脑在 kp_reason 只旁白、没落地（回喂重试耗尽）时，
   编排壳从 `while pending` 直接 `break` 落穿到 compose/output，交付了一张**零配件行的「BOM 方案草稿」**
   并报「完成」。已收口成唯一的推进闸门 `step_gate_verdict`：本步没落定 → **如实暂停交客户**，
   绝不组装、绝不交付（回归：`test_shell_pauses_instead_of_delivering_a_half_done_step`）。
6. **`output` 抽屉的「交接目标」把产物槽写死成字符串**：`config.target` 同名不同义（旧=交接目标字符串，
   新=产物槽 `target.artifacts`）。在抽屉里保存一次输出节点，生效配置的 `target` 就变成字符串 →
   `resolve_kind` 找不到槽 → **该节点下产物凭空消失**（正是「只有登记节点还有输出物」那类事故的根因）。
   三层收口：抽屉不再写/不再展示该字段；保存时剔除非物件 `target`（自愈历史数据）；
   `reasoning_node_contract.effective_config` 合并时**物件 target 优先**，任何非物件覆盖一律忽略
   （回归：`test_a_string_target_cannot_clobber_the_drawer_plug`）。
7. **客户对大脑提问的回答在走引擎的入口被吞**：`click_note`（点选/口答）只在聊天兜底分支拼进文本，
   而试运行/续跑/点选快速路都是 `force_submit` 直进引擎 → 大脑看不见答案，**同一个问题一轮换一次措辞
   再问一遍**（实测连弹三轮 CPU 选项卡）。已把答案并进回合文本再进引擎
   （回归：`test_answers_to_brain_questions_reach_the_engine`）。

### 6.3 改造前实测（同场景）：⛔ 10 轮不收敛、走不到交付

登记段质量没问题（8 行部件全落地、无丢行），但配件选型段有两种死法：平台被推断成 Orion 后
CPU 行永远无料可锁（每轮换措辞重问一遍，客户怎么点都落不了地）；以及步校验失败时机制文案
直出成零选项死卡。前者见 §6.2-1 与 §3.7，后者由「校验失败回喂大脑」修掉。

### 6.4 「保持原需求」的终点状态：A + B 均已落地（2026-09-10）

`kp_absent` 的语义是「不配」（整行丢掉），装不下「客户已知悉库内无料、本行如实留白」。
两条路都做了：

- **A｜第三结局 `kp_waived`**：行级新结局 = **行保留 + 标注**（`waived=True` / `waived_note`，
  `request_spec` 原样保留客户原话），终检把 `waived` 类目视为了结，组装照跑。
  豁免只能来自客户拍板（点选带 `waived` 的选项 → `kp_waived` 行键），引擎不替客户认账。
- **B｜前提闸门**：`slot_contract.PREMISE_CATALOG_DIMENSIONS = ("series",)` +
  `unconfirmed_premise_fields()`——决定「库里有没有料」的目录字段（平台/系列）在进入配件选配
  **前**必须先经客户确认。确认只有两条留痕路（客户点选确认卡 / 大脑申报 `customer_stated`），
  值被改写即失效。实测兆芯场景现在依次弹 `server_type` → `platform_type` → `chassis_form`
  三张确认卡，客户点完才进选型。

实测 `e2e_scenario_waived.json`（客户点名 `NVIDIA B200 192G ×2`，库内确实无此料）：
4 轮走到 `output`，配件表 2 行、摘要「其中 1 行库内无料·客户已知悉」，compose 12 行。

### 6.5 复跑方式（三种场景已固化成脚本）

```powershell
cd backend
.\.venv\Scripts\python.exe -X utf8 scripts\e2e_skill.py --scenario scripts\e2e_scenario_zhaoxin.json --keep
# 另外两个： e2e_scenario_medium.json（中等）、e2e_scenario_vague.json（模糊）
```

报告落在 `backend/_e2e_report.md`，场景另各留了一份 `_e2e_report_{zhaoxin,medium,vague}.md`。
另有 `scripts/e2e_scenario_waived.json`（库内无料·保持原需求）与 `e2e_scenario_medium.json`（中等）。

**注意**：跑的时候不要改 `backend/` 下的 `.py`（包括临时查询脚本）—— `uvicorn --reload` 会重启，
把正在跑的 WebSocket 打断（`1012 service restart`，本轮踩过两次，报告会缺尾巴）。

### 6.6 第二次复跑发现并修掉的缺陷（2026-09-10 夜）

0. **点击通路静默失效（P0 事故）**：`skill_chat` 点击分支漏导入 `KP_NODE`，
   `apply_structured_slots(..., kp_state=node_state(mem, KP_NODE))` 在参数求值时就 `NameError`，
   被宽 `except` 吞掉 → **整条选项卡点击通路失效**：客户点了没反应、同一张卡反复弹、线程永远
   走不到交付。修法：补导入；并且**点击失败不再只写日志**——落 `mem["click_errors"]` 留痕
   （同类静默失效不许再藏）。两个新回归：
   `tests/test_click_signal_landing.py`（去掉修复就失败）、
   `tests/test_no_undefined_names.py`（`symtable` 全量扫「跑到了才炸」的未定义全局名，
   当前只剩 `__file__` 误报，已白名单）。
1. **节点卡住时只能把机制文案抛给客户**（本轮最重，`stuck_gap` 插座兜底）：
   大脑回喂耗尽后既没落地该行、也没升格提问 → 编排壳只能把 `_KpNode.validate` 的机制 hint
   （「登记的部件大类 […] 没有对应落地行——补选型或向客户如实说明」）交给同一颗大脑转述，
   客户**没有可点的卡**，机制文案还泄漏成了客户话术。
   修法不是话术兜底，而是给插座加一个新钩子 `stuck_gap(engine)`（`DefaultNodePlugin` 默认 `None`，
   只在编排壳确认该步**真的卡住**之后才调，不抢大脑自己提问；与 `delivery_gap` 的区别只在时机）：
   `_KpNode.stuck_gap` 把**第一条未落地行**做成行卡——库内候选取自大脑本轮 `query_parts`
   按需检索登记的接地索引（**不是**被否掉的预载候选池），客户点名型号库内无料时再补
   「保持原需求」（`waived`）；选项信号仍走唯一出口 `ask_option_signal`；
   **索引里没查过该类目就一张卡都不产**——引擎没查过，就没有资格替客户说「库里没有」。
   回归：`tests/test_kp_stuck_gap.py`（8 例）。
2. **兜底 slot 被当成登记表字段写进 ext**：`ask_option_signal` 对任何非空 `slot` 都照写
   `{slot: value}`，于是大脑提问卡（slot 兜底成 `brain_ask`）一点选就写出
   `ext["brain_ask"] = "…"` 这种登记表里根本不存在的键。
   现在只认登记表**真实字段**（`slot_spec()` 里 `src_type != "kp"` 的项），其余一律当客户的
   口头回答走对话。
3. **回答「无选项的卡」不算意图无歧义**：`click_fast_path` 只看 `click_labels`，
   客户答了卡（`ask_answers`）仍要多烧一轮聊天模型。现在两者都算
   （`bool(click_labels or ask_answers) and had_pending_card`）。

复跑结果（同夜，真实 HTTP + WS + 真实 LLM + 真实库）：

| 场景 | 结果 | 轮次（逐轮秒） | 配件行 | 组装行 |
|---|---|---|---|---|
| 详细（兆芯） | ✅ 走到 `output` | 4（60.3 / 51.2 / 57.7 / 48.4） | 8 | 17 |
| 库内无料·保持原需求（B200） | ✅ 走到 `output` | 4（59.6 / 85.5 / 67.4 / 15.4） | 2（1 行 waived） | 12 |
| 模糊（「AMD 平台的通用计算服务器」） | ⚠️ 未收口，逐行推进中（见 §6.7-1） | 8 轮 67~170s | — | — |

B 侧生效的实证：详细场景第 1~3 轮依次是 `server_type` / `platform_type` / `chassis_form`
三张前提确认卡（客户点选后 `confirmed_slots` 落值），第 4 轮一次性 8 行锁定。

### 6.7 仍在的问题（如实记录，未修）

1. **模糊场景一轮只问一行，行会越攒越多**：`kp_config` 每轮被大脑重新声明，同一类目会积累
   多份不同描述的行（如 `CPU|CPU AMD 9654` 与 `CPU|CPU 用 9654` 各算一行未落地），
   于是同一类目要一行一轮地点。根子在**行清单没有增量化**（已登记行不重报、不重跑），
   与「答案只追加不重 derive」同源。
2. **单轮墙钟 50~170s，瓶颈 100% 在 reasoning 模型的深思考**（检索工具全部秒回），
   单轮最多出现 3 次「思考超预算压缩重试」。这是模型/provider 侧的耗时，不是管道卡住。
