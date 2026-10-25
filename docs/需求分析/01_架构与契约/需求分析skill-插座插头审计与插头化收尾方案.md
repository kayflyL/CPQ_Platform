# 需求分析 skill 插座插头审计与插头化收尾方案

> 最后更新：2026-09-14

2026-09-14 对「节点是否符合插座插头理念 / 换目标输出物与工具是否还能工作 / AI 办公室能否独立」三问做过一轮代码级审计（结论见 §1），本文把审计结论存档，并给出两个未达标面（三个角落 + 两个断口）的收敛方案。配套权威架构文档见《需求分析skill-技术架构.md》，铁律出处见 2026-09-02 定调（五插槽契约、树干-枝叶模型）。

---

## 1. 审计结论速览

### 1.1 现在的节点是否符合插座插头理念——骨架符合，两个角落未清

**已插座化（树干层，代码可证）**：

| 插座针脚 | 实现 | 锚点 |
|---|---|---|
| 产物插头 | `target.artifacts[]`，`slot`=装什么 / `kind`=怎么显示双针脚；`resolve_kind` 完全由抽屉声明，代码里没有「节点→产物」硬编码表，未声明白盒留空不装懂 | `skill_node_artifacts.py` `declared_slot` / `resolve_kind` |
| 新插头类型 | 注册即用：产物 builder 注册表 `BUILDERS`；契约解释器对 `_CONTRACT_FORMATTERS` / `_ROW_SHAPERS`；机制零改动 | `skill_node_artifacts.py` `BUILDERS`；`skill_target_contract.py` |
| 节点插件 | `_PLUGINS` + `register()` 唯一扩展点；未注册节点走 `DefaultNodePlugin` 声明式空实现，编排壳零改动 | `skill_node_plugins.py`（`test_register_is_the_only_extension_point` 守护） |
| 工具插座 | `effective_node_tools = DB enabled_tools ∪ 机制保底`，唯一真源 = `capability_spec.SPECS`（Capability-as-Data，三处派生 + 启动自检 `validate_specs`） | `skill_plan_runtime.py`；`capability_spec.py` |
| AI 层指令 | 唯一出处 = 左栏 manual_rules（09-13 A 段收口：node_mission 退役、宪法测试防回流） | 宪法测试 `PROSE_MARKERS` |
| 实时亮灯 | 按产物槽不按节点名，换插头→实时行为跟着换 | `skill_node_artifacts.py` `emit_live_artifact` / `LIVE_EMITTERS` |

**未达标的三个角落**：

1. **四个内建插件的针脚还长在代码里**——接线逻辑通用，但接线配置是类属性写死：`_ModelNode.result_tool="choose_model"`、`result_pool_key`、`lock_func_path`、`progress_func_path`（`skill_node_plugins.py` `_ModelNode` 类属性）。半声明式：改一行类属性能换，但不是「改 DB 生效」。
2. **引擎残留**（09-02 已知违背项③，未盘点）：kp_mode 门控、`_default_qty`、组装钳制、场景推荐 top-N、`_DEFAULT_REQUIREMENT_SLOTS`（恢复默认按钮）等「伪装成机制的规则」仍在代码里。
3. ~~**执行序未图驱动**~~（2026-09-14 实施时复核纠正）：大脑步执行序**本就**由 `steps_payload` 图拓扑驱动（`_prepare` → topo → `_brain_steps`）；真正滞后的是 pipeline_start 步骤骨架/输出标签与「提议话术」视图仍走 `PHASE_TABLE` 固定序，且新节点拿不到大脑回合（`_brain_steps` 按插件注册表过滤）。已随批 4 阶段 A 收平，见 §4.1 修正。

另：output 交付节点的 `target` 是下游产物引用字符串（如 `'bom_scheme'`）而非插头字典，`target_artifacts` 返回空表——这是**有意设计**（交付语义非产物语义），不算违背。

### 1.2 换目标输出物、工具还能不能工作——声明层能，机制层不能

- **换 DB 声明（生效）**：产物槽/kind 换→产物发射、完成摘要、实时亮灯、大脑 sys_prompt 契约文本全部跟随（`_verify_target_plug.py` 33/33 锚过）；换到未注册 slot/kind→白盒降级（`format_generic_contract` 通用契约 + 前端 raw JSON），不崩但没有结构化契约；工具增删即配即生效（原生 FC 每轮拿新 schema）。
- **换机制层（不跟）**：机制工具摘不掉（保底补回+告警）；职责工具换名字会断收口（`wire_result` 只认 `result_tool`，落锁不发生→`validate` 失败回喂→死循环）；fill 的写回目的地（商机需求草稿）、前提闸门、kp_required 门钉着 CPQ 状态机。

### 1.3 AI 办公室独立——外壳能独立，workflow 跟不走，但不拆穿外壳

外壳（ChatSessionRuntime / assistant_hub / 同事体系 / 记忆 / llm_client）纯对话回合零 CPQ 依赖。要剪的六条缝：

1. workflow 挂钩：`colleague_turn_runners / colleague_turn_service / colleague_prompt` 经 `is_workflow_skill` 同进程直连 skill 引擎——独立后「+」发起与 TaskStepper 消失，除非引擎 API 化；
2. 商机实体：`_ensure_ai_office_opportunity` 自动建商机；`business_artifact` 卡渲染 bom_scheme 等 CPQ 实体；
3. 数据边界：data_boundary / price_access 指向 CPQ 表——独立后无表可读，未接数据的 query_data 类工具必须摘（否则编造查询结果）；
4. 认证：`ai.office.manage` 权限 + JWT + 用户系统挂在平台；
5. 前端共享层：useAssistant / useEmployeeChat / AssistantPanel / AssistantComposer 三处共用，须先切出；
6. 内部旧账：ai_colleagues 域服务层反依赖 API 层 3 处。

需求分析 workflow 的 9 工具 / 目录 / KP 库 / CRE 规则 / 目标层组件全是 CPQ 插头，独立后=插座上没插头（白名单空、目标表无落点）。迁移路径现成：工具即权限白名单机制平移，CPQ 侧把工具/数据源做成跨进程接口（MCP 式）。

---

## 2. 方案一：接线针脚 DB 化（wiring 插头）

**针对角落 1（内建插件针脚写死在代码里）。**

### 2.1 现状

`_ModelNode.wire_result` 的接线是通用的（按「哪个工具、结果哪个字段、落到哪个池」查找并落锁），但这份声明以类属性住在代码里：

```python
result_tool = "choose_model"
result_selected_key = "selected"
result_id_key = "model_id"
result_pool_key = "baselines_pool"
lock_func_path = "app.services.skill_phases:_lock_baseline"
progress_func_path = "app.services.portal_flow_adapter:save_scheme_progress_from_ctx"
```

### 2.2 方案

1. **node config 新增 `wiring` 段**（与 `target` / `enabled_tools` 平级）：

   ```json
   "wiring": {
     "result_tool": "choose_model",
     "result_selected_key": "selected",
     "result_id_key": "model_id",
     "result_name_key": "name",
     "result_pool_key": "baselines_pool",
     "pool_id_keys": ["server_model_id", "id"],
     "pool_name_key": "name",
     "default_reason": "AI 按需求在候选池内选定",
     "lock_handler": "lock_baseline",
     "progress_handler": "save_scheme_progress"
   }
   ```

2. **handler 注册表（代码=机制实现，DB=引用名）**。DB 严禁存函数路径（任意路径=代码执行面+与代码内部耦合），改为代码侧注册表，DB 只写名字：

   ```python
   LOCK_HANDLERS = {"lock_baseline": _lock_baseline}          # skill_phases
   PROGRESS_HANDLERS = {"save_scheme_progress": save_scheme_progress_from_ctx}
   ```

   `DefaultNodePlugin.wire_result` 升级为读 `cfg["wiring"]` 的通用接线实现；`_ModelNode` 类属性退役（迁完后删除，不留「DB 空则代码兜底」第三层）。

3. **迁移脚本**（仿 `migrate_kp_target_contract.py` 先例）：把现类属性值写进流 125 `node_configs.model_reason.wiring`，零行为变化；带 guard（已有 wiring 的流跳过）。

4. **fill / kp 的定位声明（明确不动）**：`_FillNode.validate`（前提闸门）与 `_KpNode.bridge_ctx`（KP 行状态机）是**目标域的确定性协议=树干**，不是针脚，不搬 DB。理由：前提面已数据驱动（`PREMISE_CATALOG_DIMENSIONS=("series",)` 只钉维度名，字段与取值全在字段契约里，`slot_contract.py` 注释明示「要加宽/收窄前提面，改字段配置而不是改这个元组」）；KP 必登记开关已是 target 层策略位（`kp_required`）。协议开关继续走 target 层，协议本体留代码。

### 2.3 验收

- 改 DB `wiring.result_tool`（注册一个别名工具并绑定到节点）→ e2e 落锁仍发生，不碰代码；
- 换 `lock_handler` 名 → 落锁行为跟着换；
- 新增 wiring 契约测试（与 `test_register_is_the_only_extension_point` 并列）。

---

## 3. 方案二：引擎残留三类归位（先盘点，拍板后再动）

**针对角落 2（伪装成机制的规则）。** 按铁律三类归位：业务规则→策略中心（CRE requirement 域）、默认值/词表→DB（表单定义/登记策略）、数据完整性守卫→留机制。

| 残留项 | 来源 | 建议归属 | 动作 |
|---|---|---|---|
| `_default_qty` 数量默认 1 | 代码核实（`skill_node_plugins.py`） | 表单定义 `requirement_sheet_form` 字段 `default_value`（契约已支持、validate 已读） | 迁 DB；顺带了结「有默认值的 L0 策略」旧悬念 |
| `_DEFAULT_REQUIREMENT_SLOTS`（恢复默认按钮） | 代码核实（已知待办④） | 表单定义 + 登记策略的 DB 种子 | 按钮改读 DB 快照；与「init_defaults 已删、DB 备份是唯一保险」口径对齐 |
| kp_mode 门控语义 / `KP_MODE_OPTIONS` 业务值 | 记忆源，待盘点 | 业务值→策略中心/DB；门控语义若属机制则留 | 先出盘点报告，用户拍板 |
| 组装钳制（compose 数量/行钳制） | 记忆源，待盘点 | 数据完整性守卫→留机制；业务上限→CRE 规则 | 先出盘点报告 |
| 场景推荐 top-N | 记忆源，待盘点 | 业务值→DB/规则 | 先出盘点报告 |
| `PHASE_TABLE` 固定链 | 代码核实 | — | 归方案三 |

**铁律提醒**：新增任何默认值/词表/规则到代码前必须停下问用户；盘点报告先交拍板再动手，不并入其他批次偷跑。

---

## 4. 方案三：执行序图驱动（两阶段，B 另立项）

**针对角落 3（PHASE_TABLE 固定链）。**

### 4.1 现状（2026-09-14 实施时复核修正）

大脑步执行序本就 = `steps_payload` 图拓扑序（compose/output 是引擎确定性尾段）。阶段 A 实际收平的是三处滞后：① pipeline_start 骨架与输出标签走 `skill_steps_view`（PHASE_TABLE 固定序）→ 现传 `flow` 走同一份 `_topo_order`；② `_brain_steps` 成员按插件注册表过滤 → 现改为「steps_payload 全量」（无工具节点已被剔除，凡挂工具的节点自动获得大脑回合，新节点绑工具即插即用）；③ 排序逻辑两份 → 抽出 `_topo_order` 单源共用。迁移 guard 按批 1/4 实际形态落为：`_topo_order` 天然排除 extract、环成员补尾；无 graph 老流自动回退 PHASE_TABLE（skill_steps_view 的 fallback 分支，skill_memory 的 manifest 无 graph 也走此兜底）。

### 4.2 阶段 A：线性图驱动（本轮做）

1. **执行序 = flow graph 拓扑序**（复用 `_graph_maps`；`input` 仍特判首步、`extract` 仍排除——两者 `_graph_maps` 已内置）；
2. **PHASE_TABLE 降级为**：无 graph 的老流兜底 + label 权威（`skill_steps_view` 继续消费）；
3. **骨架同源**：pipeline_start 骨架、大脑任务卡、执行序三处必须同一份 topo 结果，杜绝两套顺序（别在补丁上打补丁）；
4. **迁移 guard**（仿 reasoning-flow-migrate-gate 铁律）：graph 节点集覆盖当前插件注册表键（含 output）才启用图驱动，否则回退固定链+告警；
5. **配套**：`done_steps` 跨回合恢复按新序重放；新增 harness「调换 graph 顺序→执行序跟随」；全量 pytest + zhaoxin/A1 e2e 基线对比。

### 4.3 阶段 B：条件分支（另立项，先不批）

条件边/分支执行涉及 `step_gate_verdict`（advance/pause/deliver）语义扩展与 pause 恢复语义，复杂度独立成档。触发条件：真实出现「按需求特征跳过某节点」的场景再立项。

### 4.4 验收（五插槽验收场景完全体）

画布上拖一个 `DefaultNodePlugin` 新节点（声明已注册 slot + DB 绑 enabled_tools）插入链中，不碰代码跑通 e2e。

---

## 5. 方案四：机制工具边界显性化（「摘不掉」→看得懂）

**针对「机制工具摘不掉」。** 先定调：**这不是缺陷，是树干边界**。`capability_spec.py` 已是 Capability-as-Data 唯一真源（default_tools=初值可增删，mechanism_tools=节点协议动词），三处派生（空库播种 / 运行时保底 / 前端抽屉）+ 启动自检。机制工具是节点**协议的手**：

| 节点 | 机制工具 | 承载的协议 |
|---|---|---|
| agent_fill | fill_requirement、ask_user | 登记协议 + 缺口反问协议 |
| model_reason | choose_model | 落锁协议（wire_result 的落锁入口） |
| kp_reason | query_parts、select_parts、ask_user | 找料 + 落料 + 行反问协议 |

摘掉 = 缺口协议/落料协议失效（比如没有 ask_user 的 fill 节点无法反问，只能死循环或静默缺字段）。保底补回正是防 DB 漂移的自愈。

### 5.1 改进三件（无行为变更）

1. **补回事件可见化**：运行时保底补回从 `logger.warning` 升级为 node_trace 事件——试运行面板能看到「配置漂移：机制工具 X 已保底补回」，不再只进日志；
2. **抽屉锁因文案**：机制锁 tooltip 说明锁因（「缺口协议依赖，不可摘」），数据取自 capability spec（`as_dict` 已下发清单，补一个锁因字段）;
3. **扩展正路文档化**（写进本节，落抽屉帮助）：要「不反问的 kp 变体 / 轻量机型节点」→ 正路是新增节点 key + 自建 CapabilitySpec + DefaultNodePlugin（或 register 覆写），不是摘机制。

### 5.2 备选（不推荐，记录理由）

取消保底、纯 DB 权威 + 运行时 fail-fast。不推荐理由：与「init_defaults 已删、DB 备份是唯一保险」叠加后，一次 DB 漂移 = 节点瘫痪且无自愈；保底的代价仅一行日志。除非将来出现「确实要永久关掉某协议动词」的真实需求——届时改 spec（代码+测试同步），不开运行时开关。

---

## 6. 方案五：职责工具改名不断收口（改名走查单 + 三道闸）

**针对「职责工具换名字会断收口」。** 依赖方案一（wiring DB 化后，model_reason 的职责工具名改一处 DB 即可）。

### 6.1 现状断点

`wire_result` 按 `result_tool` 名在 tool_calls_log 里找结果；改名后找不到→warning+break 静默忽略→落锁永不发生→`validate`（"机型尚未锁定"）失败回喂→大脑反复调、流程卡死。整个链条没有任何一处提前报错。

### 6.2 三道闸

1. **启动期**：扩展 `validate_specs` / 新增 wiring 契约校验——所有流 `node_configs.*.wiring.result_tool` 必须 ∈ 注册工具（`registered_tool_ids`）且 ∈ 该节点 `effective_tools`；不满足→启动告警清单（不改行为，只报白盒）；
2. **保存期**：Skill Studio 保存节点时校验 wiring 引用，不在注册表→400 白盒错误（把断口掐在配置保存时，不是聊到一半）；
3. **运行期**：`wire_result` 的「结果不在候选池/找不到工具调用」从 warning+break 升级为白盒 node_trace（大脑落锁失败可见），配合现有大脑重试守卫。

### 6.3 两类名字，两种改法（走查单）

| 类别 | 例子 | 改名方式 |
|---|---|---|
| 职责工具（wiring 引用） | choose_model→pick_model | 改 DB wiring 一处 + 工具 spec 注册改名 + 节点 enabled_tools 同步；代码零改 |
| 协议动词（机制工具） | fill_requirement / ask_user / select_parts | 代码+capability_spec+宪法测试三处同步变更——这是机制变更不是配置变更，走查单里明示「动前先问用户」 |

### 6.4 验收

`_verify_target_plug.py` 增两例：改 wiring 工具名→落锁仍发生；DB 删机制工具→补回 + node_trace 可见。

---

## 7. 实施顺序建议（依赖关系，每批独立可回退）

| 批次 | 内容 | 性质 | 验证 | 状态（2026-09-14） |
|---|---|---|---|---|
| 1 | 方案四（可见化三件） | 纯增强，无行为变更 | 全量 pytest + 试运行肉眼验 trace | ✅ 落地（mechanism_reason + node_tool_drift + 运行期 node_trace/contract_warnings + 抽屉锁因文案） |
| 2 | 方案二盘点报告 | 只读盘点，交拍板 | — | ✅ 报告已交《引擎残留盘点-伪装成机制的规则.md》，归属待拍板 |
| 3 | 方案一 wiring DB 化 + 方案五三道闸 | 迁移脚本 + 契约测试（同批做，闸依赖 wiring 存在） | 迁移零行为对比 + 验收例 + e2e 基线（zhaoxin ≈227.9s/5轮 量级） | ✅ 落地（683 pytest 绿 + DB 回填生效 + 启动/保存/运行三闸；e2e 因 LLM 上游 402 余额不足暂缓，见下） |
| 4 | 方案三阶段 A（图驱动执行序） | 编排变更，最后做 | 全量 pytest + 新 harness + e2e 全量回归 | ✅ 落地（_topo_order 单源 + 骨架同源 + 大脑步=有工具节点；执行序复核纠正见 §4.1） |

**实施备注（与原方案的差异）**：
- 方案二的 handler 注册表落地为「名字 → module:func 字符串 + importlib 懒加载」（非直接函数引用）——skill_node_plugins 有意延后导入避免模块环，字符串表保持这一机制；
- `_verify_target_plug.py` harness 已在此前清理中删除，方案五两验收例并入 pytest：`test_select_model_tool.py::test_model_wire_miss_pool_whitelists_as_contract_warning`、`test_node_plugin_contract.py` §5（wiring 契约三例 + 未注册新节点通用接线例）；
- e2e 基线复跑被环境挡住：LLM 上游 cloudprime 返回 402 Insufficient Balance（日志证据 `_e2e_uvicorn_8001.log`），引擎行为正确（零产出→如实失败暂停，未编造）。余额恢复/换通道后重跑 zhaoxin 对表即可，代码侧无待办。

**待拍板项**：① 方案一是否本轮含抽屉 UI（建议先 DB/脚本，UI 后补）；② 方案三阶段 B 条件分支是否立项；③ 方案二各项归属（kp_mode / 组装钳制 / top-N）。

---

## 8. 执行后的预期效果

**一句话**：配置面（DB / 画布）成为唯一可动面，代码只剩机制；三个断口从「聊到一半才炸、只进日志」变成「保存时 / 启动时就报」。

**改一件东西要动几处（before → after）**：

| 想做的事 | 今天 | 执行后 |
|---|---|---|
| 换 model_reason 职责工具名 | 改插件类属性 + 发版 + 重启 | 改 DB wiring 一处 |
| 调执行顺序 / 插新节点 | 改 PHASE_TABLE + 发版 | 画布拖线，guard 校验 |
| 改数量默认值 | 改 `_default_qty` + 发版 | 表单定义改 `default_value` |
| 增删增强工具 | 改 enabled_tools 即生效 | 不变 |
| 摘机制工具 | 摘不掉（设计如此，但看不出来） | 依旧摘不掉，但抽屉写明锁因、漂移自愈在试运行面板可见 |
| 工具改名漏改接线 | 客户对话卡死，日志一行 warning | 保存时 400 白盒错 / 启动期告警清单 / 运行期落锁失败 trace |

**分批效果**：

- 批 1（方案四）：配置漂移从「翻日志才知道」变「跑一次就看见」；「摘不掉机制工具」从隐性规则变显性契约。行为零变化。
- 批 2（盘点后执行）：引擎代码里业务值清零——kp_mode / 数量默认 / 钳制改配置即生效，新环境部署不再吃代码里散落的业务常量。
- 批 3（wiring + 三道闸）：换职责工具 / 落锁器 = 改一处 DB；断口提前到配置保存与启动期。「choose_model 改名 pick_model」从一次发版变成一次 DB 编辑 + e2e 仍绿。
- 批 4（图驱动）：画布调序 / 插 DefaultNodePlugin 新节点不碰代码跑通——**五插槽验收场景完全体**（「录一条规则 / 换一张目标表 / 换接线 / 调顺序，不碰代码生效」）；骨架 / 任务卡 / 执行序单一来源，永不再出现两套顺序。

**对三问终态的升级**：① 三角落清零，节点=纯插座（接口），插头（target / tools / wiring / 规则 / 指令）全 DB；② 「换目标输出物、工具」从「声明层能、机制层断」变「声明层全链路能」，未注册新物仍有白盒降级兜底；③ AI 办公室独立的地基更干净——workflow 侧只剩「工具 / 数据源跨进程接口化」一件物理活，语义缝（接线 / 顺序 / 断口）已先收平。

**明确不在射程内（诚实边界）**：单轮推理耗时（reasoning 模型思考，50~200s）、AI 话术质量、P1 平台冲突调解 / P3 旁白复读等未修项——本方案全是「配置边界 / 机制纯度」工程，不碰 AI 质量。性能与回归基线不退化：e2e zhaoxin ≈227.9s/5轮、A1 3轮2卡量级保持，全量 pytest 666+ 绿。AI 办公室独立部署本身不在本方案内，只是把缝收窄。

---

## 9. 关联文档

- 权威架构：《需求分析skill-技术架构.md》（§0-25 全景）
- 产物契约：《需求分析skill-节点产物契约.md》
- 引擎残留盘点：《引擎残留盘点-伪装成机制的规则.md》（批 2 产出，归属待拍板）
- 铁律出处：2026-09-02 树干-枝叶定调（五插槽契约、单一权威源、agent_fill 样板验收）
- 迁移先例：`scripts/migrate_kp_target_contract.py`（columns 补 from/fallback 零行为变化）；本轮 wiring 迁移 = `skill_config_bootstrap.ensure_node_wiring_backfill`（幂等带 guard，启动时执行）
- 验收例：原 `_verify_target_plug.py` harness 已删，wiring/接线验收例并入 `tests/test_node_plugin_contract.py` §5 与 `tests/test_select_model_tool.py`
