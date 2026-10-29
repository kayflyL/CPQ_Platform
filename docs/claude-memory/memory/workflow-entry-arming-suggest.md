---
name: workflow-entry-arming-suggest
description: 工作流发起两入口(2026-10-15)——「+」装填模式(不发占位消息)+suggest_workflow一键确认卡;碰工作流入口/同事聊天/launcher先看
metadata:
  node_type: memory
  type: project
  originSessionId: 1b626d52-5a43-436d-bdb8-cf89b7bb25e4
  modified: 2026-10-15T07:43:53.008Z
---

**2026-10-15 定调+落地：工作流发起两入口，后端收敛同一分支**（`run_colleague_turn` 的 `workflow_launcher`，force_submit 直进引擎）。背景病灶：用户把需求贴进同事聊天 → 走的是普通 ReAct 工具回合（`_run_tool_turn`，同事只有 choose_model/search_cases），工作流只认「+」显式发起 → 聊天态同事口头承诺"落料号出配置"但根本没那能力（fill_requirement 被 task_active=False 硬闸），对话死胡同。skill_types 契约写的「模型建议+用户确认」半条路线一直没实现。

**两个入口**：
1. **「+」装填模式**：选工作流不再发「请开始【xx】工作流。」占位消息（旧 `launchWorkflow` 已删——占位话当需求原文进引擎，白烧一整个引擎回合反问需求）。前端 `armedWorkflow` 装填态（composer 装填条+placeholder 变化），下一条发送自动带 `entry_point='workflow_launcher'`+真需求原文；群聊记录技能归属 `ownerRoleKey` 发送钉角色防判官改道；换会话自动卸装填。
2. **suggest_workflow 确认卡**：绑定 workflow 的同事聊天态自动挂该工具（`_workflow_offers` 经 TOOL_CTX.workflow_offers 下发合法取值域）→ handler 校验后写 `TOOL_CTX.workflow_suggestion` → `_persist_and_broadcast(workflow_suggestion=…)` 随消息 data 落库+广播 → 前端 `kind='workflow_suggestion'` 渲染一键发起卡，点击=`launchWorkflowNow` 以需求原文 launcher 发起，已点置灰。

**How to apply:** ①名字住址：`colleague_prompt._workflow_offers/_first_workflow_skill`（能力域归 prompt 层）、`agent_tool_handlers._tool_suggest_workflow`、`colleague_turn_io._workflow_suggestion_of`；②工具挂载在 `_run_tool_turn`（colleague_turn_runners），非白名单配置；③测试 test_agent_tools.py 三例；④引擎侧 full_text 会拼线程 prior user 消息（skill_chat.py），确认卡发起不丢聊天里的分析。

**三个坑**：①宪法 PROSE_MARKERS 连「建议」二字都拦（agent_tool_specs/colleague_prompt/colleague_turn_* 全在扫描面），措辞用「发起确认卡/向用户发起」；②colleague_turn_runners 有 700 行硬预算（test_colleague_turn_layout），加东西先想搬 prompt/io 层（依赖方向 prompt←io←runners←service 不许反向）；③AssistantPanel 模板里裸 `preview` 是靠 Vue 渲染代理回落到 props（脚本里没有这个绑定），脚本代码必须写 `props.preview` 否则 ReferenceError。

**存量未修（与本改动无关）**：test_report_pdf::test_finalize_output_renders_pdf_artifact（files 空）、test_select_model_tool（DB 候选池漂移缺 es22v3-p）。关联 [[dispatch-llm-judge]] [[skill-current-state-2026-09-12]] [[inferred-slots-must-confirm]]。
