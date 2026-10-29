---
name: dispatch-llm-judge
description: "转接只在群里(2026-08-30定调):绑定会话含方案助手永不转接,私聊超能力由角色口头提议;群内LLM判官按名册判断"
metadata: 
  node_type: memory
  type: project
  originSessionId: 103415a3-4b46-42b1-a04c-db5d6194e356
  modified: 2026-08-29T20:44:40.937Z
---

**2026-08-30 定调（推翻旧「按 effective_role 判」做法）：转接只发生在团队群。** 绑定了 colleague_role_key 的会话（**含方案助手自己**）→ 锁定身份永不转接（`ai_colleague_service.resolve_chat_target`，post_message 调用；判别=「有无绑定」而非「是否 assistant」）；未绑定线程（group-resolve 的团队群）→ @点名确定性路由 / LLM 判官按名册转接（落 handoff 标记）。私聊里请求超出角色 skill/工具/数据范围时，由**角色口头建议**一位同事（`colleague_turn_service._handoff_hint` 注入三个 persona 装配点：名册摘要 `colleague_roster_digest` 与判官共用 `_dispatch_roster` 单源 + 规则=能覆盖的自己做/最多建议一位/客户决定）。前端浮动窗默认进方案助手 1:1（不再默认团队群），群从侧栏显式进。旧 bug 根因：绑定 assistant 私聊线程被旧条件 `effective_role != "assistant"` 送进判官分支 →「我想要一台服务器」被转给技术支持工程师。测试锚 test_dispatch_llm.py（bound_never_dispatches/group_dispatches/handoff_hint/capability_follows_skill_binding）。**skill 绑定=能力（2026-08-30 用户铁律）**：需求分析本职属技术支持工程师，assistant 绑定只是配置；**群内配置请求判给技术支持工程师是正确转接**（名册 skills 驱动）。解绑即失去能力（_has_workflow_skills 读 colleagues[].skills）；禁止代码里写死「角色↔技能」；DEFAULT_SKILL_BINDINGS 仅新库种子不覆盖已有配置。

**Why:** 用户拍板"只有在群里的时候才转接；私聊他自己会的不转接，除非他不具备 skill/工具/数据才提出转接"。唯一大脑：转不转（机制通道）在路由层代码定死；何时提议、提议谁=LLM 语义判断在提示词层。

智能转接已从关键词匹配改为 **LLM 判官**（2026-08-29 用户定调"硬编码关键词太落后"）：`resolve_assistant_message_target_async` 把员工名册（姓名 + 职责 = system_prompt/opening_message 前 120 字 + skills）+ 用户消息交给 chat_json（8s/1次/low 档/JSON schema），无合适人选或闲聊 → None（总助自己接），失败一律降级不阻塞。

**Why:** 关键词规则是宪法定性禁止的"数据表存话术"模式；自由表达穷举不完，LLM 一条判断全覆盖（实测 4 类消息全对：配置需求/成本/报价导出/闲聊不转）。

**How to apply:** ①新增 AI 员工必须写好 opening_message/system_prompt 职责描述——名册质量=转接质量；②要调整某员工是否可被转派用 colleague.dispatchable（团队页签面板即时开关）；③`dispatch_rules` 旧数据还在 config 里但代码已不再读，别复活；④dispatch-preview 契约=`{colleague, reason}`（matched_rule 已删）。**转接=群内专属（2026-08-30，见文首）**：转接可见化=用户消息后落 kind=handoff 标记（WS done 推送）+专家以自己身份回复；绑定会话（1:1）一律锁定身份。✅技能记忆已按「线程+角色」隔离（skill_chat:{role_key}，_load_mem/_save_mem 带 role_key）——专家接手是干净身份，不会复述别的角色的僵尸缺口问题（2026-08-29 用户截图实证后当天修复）。**P1 群聊 MVP（同日）**：@点名确定性路由（find_mentioned_colleague，用户自己路由无 handoff 标记，优先于 LLM 判官）；AssistantComposer 有 members prop + @ 补全浮层。**P1.5 两栏消息中心（同日，用户拍板）**：浮动窗 680px 两栏（左联系人 200px + 右会话），群聊（threads/group-resolve，未绑定总助线程）与 1:1 分窗，@ 只在群聊窗口；单权限账号无左栏无 @ 直接 1:1；新对话=归档软删+重建（历史抽屉与角色菜单已退役，会话历史抽屉 dead code 已删）。文档见 docs/frontend-pages/settings/ai-office-team.md。关联 [[agent-architecture-decision]] [[message-pipeline-silent-swallow]]。
