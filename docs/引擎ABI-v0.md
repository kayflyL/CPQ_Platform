# 引擎 ABI v0（引擎与宿主的接口契约白皮书）

> 版本：v0（基线固化，方案第 1 步"立规矩"产出）｜ 定稿：2026-10-30
> 地位：本文是契约的**文档载体**，执法载体是两套测试（事件快照 `tests/test_event_contracts.py`、
> 流发布闸 `tests/test_flow_validation.py` + `FLOW_VALIDATION_MODE` 闸）。改契约必须三处同步：
> 文档 → 测试 → 实现。规范的长效载体是校验器和测试，本文只做导航和 why。

---

## 分册一：事件协议（引擎 → 前端的广播契约）

前端画布/任务条/聊天流只认这些事件与键。**加删键必须三处同步（本文 + 快照测试 + 前端）。**

### 事件类型

| 事件 | 发起方 | 语义 |
|---|---|---|
| `pipeline_start` | 事务轮壳 | 一次开工单的骨架广播：标题 + 步骤清单，画布据此建骨架 |
| `node_trace` | 两台运行时 | 节点级状态与产物（running/done/skipped），画布亮灯与输出物展示 |
| `pipeline_paused` | 推理引擎 | 推理管道暂停（反问/等确认） |
| `pipeline_waiting` | 推理引擎 | 等待用户输入的暂停事实 |
| `pipeline_done` | 推理引擎 | 全链完成 |
| `error` | 两台运行时 | 出错事实 |

### 载荷键集（快照锁定，键集变更=破坏契约）

| 构造器（唯一出处） | 键集 | 备注 |
|---|---|---|
| `transaction_turn._pipeline_start_payload` | `{type, title, steps[{key,label}], thread_id}` | title 空时回退流 label |
| `transaction_turn._step_running_payload` | `{type, step, label, status, summary, thread_id}` | status=running |
| `transaction_turn._step_done_payload` | `{type, step, label, status, duration_ms, output, summary, input, artifact, thread_id}` | 无产物卡时 artifact=null |
| `transaction_engine.state_events` | `{type, step, label, status, summary, thread_id}` | 状态语义只在引擎算一次，壳只搬运 |
| `skill_node_artifacts.node_payload` | `{type, step, label, status, input, output, summary, artifact} ` | skill 运行时节点产物广播 |
| `skill_plan_runtime`（node_trace 组装处） | `{type, step, label, status, …}` | 惰性演进：下一步抽取为具名构造器后入快照 |

`artifact` 引用形状（两台运行时通用）：`{kind, title, data}`；`kind=artifact_card` 时
`data.card` 挂产物卡；skill 运行时 kind ∈ 产物槽注册表（BUILDERS：requirement_text /
l6_chassis / kp_table / plans / bom_scheme / requirement_slots / data_report）。

### 输出物种类（kind 分册）

唯一注册表 = `app/services/output_kinds.py`：bom_scheme_draft / requirement_draft /
plans / data_answer / generic。前端经 `GET /api/reasoning-flow/output-kinds` 拉取，
**前端不再硬编码清单**（抽屉保留内置清单仅作拉取失败时的兜底）。

---

## 分册二：节点契约（一条流必须带什么，发布闸执法）

校验器 = `app/services/flow_validation.py`，模式 = 环境变量 `FLOW_VALIDATION_MODE`
（`report` 默认 / `enforce`）。执法点：`PUT /api/reasoning-flow/graph`、
`PUT /api/reasoning-flow/nodes/{node_key}`；报告入口 `GET /api/reasoning-flow/validation-report`。

| 条款 | 级别 | 内容 | 修法 |
|---|---|---|---|
| E1 | error | 图非空；必须有 input 与 output 节点 | 补节点 |
| E2 | error | 每个图节点必须有画布标签 label | 补标签 |
| E3 | error | 已声明的产物插头 slot 必须在产物槽注册表（BUILDERS） | 改为注册过的 slot 或先注册新槽 |
| E4 | error | 边不得引用不存在的节点 | 修边 |
| E6 | error | 决策点声明（decisions）缺 slot/match_category/question 任一 | 画布抽屉补决策点声明——闸按它发卡停轮 |
| W1 | warning | 干活节点（agent/agent_fill/model_reason/kp_reason/compose）未声明产物插头（target.artifacts） | 画布抽屉配置目标层 |
| W2 | warning | 大脑干活节点（agent/agent_fill）未声明工具白名单（enabled_tools） | 抽屉勾选工具 |
| W3 | warning | 流级左栏规则（manual_rules）为空——大脑行为纪律没有唯一出处 | 左栏写规则 |

条款演进规则：存量流补齐后，warning 逐条升级为 error（改 severity + 同步测试）。
**新条款先加进校验器与本文，再考虑前端提示。**

条款适用范围：**W1/E3 仅约束 skill 运行时流**（产物槽分发）。事务内核已注册的流
（`resolve_app` 命中，如 delivery_to_quotation）的产物窗口 = artifact_card（工具规格
默认 + 节点配置覆盖），不受 W1/E3 约束——2026-10-30 恢复交付流后实测误报修正。

**决策点声明（P1.5，2026-10-31）**：节点配置 `decisions[] = {slot, match_category,
question, min_candidates, allow_other}` 声明"该节点有需用户拍板的类目"。决策闸
（`skill_decision_gate.py`）机械保证：锁定/写路径上声明类目候选 ≥ min_candidates 且
无用户信号（`human_query.user_signal_for` 按 slot 查已回答问询，AI 自填不产生记录）
→ 发 choice 卡（复用问答协议）并停轮，AI 只执行不代答。设计：docs/决策闸设计-P1.5.md。

### 节点类型清单（ABI 的身份分册）

通用：input / agent / ask / rule / transform / branch / assemble / output / orchestrator /
condition；需求分析白盒：agent_fill / model_reason / kp_reason / compose。
（来源：`app/api/reasoning_flow.py:_VALID_NODE_KEYS`——注册表唯一出处。）

---

## 分册三：工具契约（已落地，2026-10-31）

唯一注册表 = `_TOOL_SPECS`（`app/services/agent_tool_specs.py`）+ 契约字典 `_TOOL_CONTRACTS`
（写语义工具逐个声明，构建时合并进 `spec["contract"]`；未登记默认 read+不弹卡）。
字段（命名对齐 MCP 注解，保守默认）：

| 字段 | 值域 | 说明 |
|---|---|---|
| effects | read / write | 副作用方向 |
| confirm_policy | none / stage / stage+consent | 确认分级（写工具缺省 stage+consent） |
| idempotent_hint / destructive_hint | bool | 幂等/破坏性 |
| target_entity | str | 目标实体（审计/回读定位） |
| verify | "模块.函数" | 写后回读函数（registry 惰性解析，不符=error 事实） |

暴露与消费：`tool_catalog()` 与 `GET /api/assistant/tools` 每条带 `contract`；
`_confirm_gate` 闸内按 confirm_policy 分诊（none 档不落待确认不弹卡）；
`agent_tool_registry.write_finish` 写路径统一收尾（回读 + 审计落账 `rules.agent_audit_log`，
查询 `GET /api/assistant/admin/write-audit`）。
完整性测试：tests/test_tool_contracts.py（写工具登记快照——新增写工具必须显式登记契约）。

> 保守默认哲学（对齐 MCP）：**没声明确认策略的写工具按最高档处理**——升级字段落地时，
> 缺省 = `stage+consent`，绝不满世界假设工具无害。

---

## 分册四：宿主接口（业务系统接入引擎的声明面）

| 接口 | 形状 | 现状 |
|---|---|---|
| 应用声明 `TransactionApp` | `flow_key / state_slot / context_fn / digest_lines / flags_from_facts`（探针/旗标/案台事实行） | 已有（delivery_app 唯一样本） |
| 流定义 | DB reasoning_flow：graph（nodes/edges/flag_rules/entity_binding/manual_rules/launch_form）+ node_configs | 已有 |
| 产物槽注册表 | `skill_node_artifacts.BUILDERS`（slot→builder） | 已有，新槽=注册 builder |
| 输出 kind 注册表 | `output_kinds.py` | v0 新增 |
| 发布校验 | `flow_validation.validate_flow / validate_node` | v0 新增 |
| 事件广播 | 分册一的构造器族 | v0 起键集快照锁定 |

宿主接入步骤（新系统七步清单的工程版）：跑脚手架（第 2 步交付）→ 填声明（I1）→
过发布校验器 → 试运行冒烟 → 上线。
