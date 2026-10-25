---
name: chat-session-runtime
description: "2026-09-13 ChatSessionRuntime落地+用户实测三bug修复：会话=渠道键dm:{role}/group/preview→唯一reactive对象共享productionRuntime；交付后收口(flow_delivered)+task_state服务端任务态对账+llm_client <think>流式过滤；碰聊天/助手/WS代码前先看"
metadata: 
  node_type: memory
  type: project
  originSessionId: eba9e191-91a0-40d3-99bc-5b91569c0fd6
  modified: 2026-09-27T15:59:34.950Z
---

2026-09-13 ChatSessionRuntime 落地（用户批准的5步方案，munder-difflin 调研成果首次结构性落地）。

**架构**：[chatRuntime.ts](frontend/src/composables/chatRuntime.ts) 把会话提为一等公民——渠道键 `dm:{role_key}` | `group` | `preview:{entry_point}` → 唯一 reactive 会话对象（AssistantChatWsState 超集）。服务端本就「每角色一个活跃会话」，所以渠道键即会话身份：浮动窗/门户/AI办公室传同一 `productionRuntime` 单例，**同角色=同一份消息/流式/瞬态/WS**（两窗开同角色实时同屏）；Skill Studio 预览用独立 runtime。

**Why:** 旧世界 useAssistant=「单当前线程+全局瞬态 ref」×3 实例 + useEmployeeChat 平行第四套，同一条服务端线程在多窗口各有一份互不相通的客户端状态，瞬态全局单例一处卡死全体假死（[[message-pipeline-silent-swallow]] 09-13 事件的土壤）。

**How to apply:**
- useAssistant/useEmployeeChat 已退化为门面，**对外 public API 一字未改**，UI 组件零改动（仅 AssistantPanel 三处 selectThread 传 `{kind:'group'}` 渠道提示，群线程不带 colleague_role_key 必须显式声明）。改聊天逻辑去 chatRuntime.ts，别往门面里加状态。
- 每会话独立 WS（**引用计数**，最后一个窗口解持才关）+ 独立看门狗 + resync 对账（未见消息∨turn_active=false∨404=终态）；LRU 8 会话只驱逐「无持有+空闲」；`setThread` 换线程即清瞬态。
- FIPA-lite 信封：`AssistantHub.broadcast` 每帧注入 `thread_id`（单点覆盖全部广播点），客户端按会话线程校验丢错帧。**信封需后端重启才生效；客户端对无信封旧帧兼容**。
- 守卫测试：colleague_turn_service 薄壳白名单已登记 `turn_active`（test_colleague_turn_layout.py）。
- 新增聊天入口（第四个窗口）= 自持 useAssistant 指针即可，禁止再造状态机。

**用户实测三 bug 修复（2026-09-13 晚，后端 669 测试+前端 build 绿）：**
1. **任务胶囊消失**（pipeline 事件只发一次不重放，刷新/重连/切会话后骨架丢）→ messages 端点新增服务端事实 `task_state`（skill_memory.task_state_for_thread：steps/done/pause/phase，turn_active 才下发），前端 `applyTaskState` 在 selectThread/resync/useEmployeeChat 两载入路径对账重建。
2. **方案交付后每条消息都复活任务条且 AI 永远用流程语气**（`kind=="done"` 后会话仍存回 ACTIVE + ACTIVE 优先路由 → 每条消息重进引擎）→ 交付时存 `SKILL_SESSION_DONE`（colleague_turn_runners）+ `flow_delivered()` 读时自愈存量（compose∈steps_done 即交付）+ 路由加守卫；gaps 仍保持 ACTIVE 续跑。显式重新发起工作流走 `reset_flow_memory` 整份清空防旧状态串场。
3. **`<think>` 标签漏进气泡**（中转把推理内联在 content 而非 delta.reasoning_content）→ llm_client 三 chokepoint：stream_agent_chat 用 `_ThinkStreamFilter` 状态机把 think 内容改道 reasoning 事件（前端「思考过程」折叠展示，chunk拼接==落库 answer 不变量保持）、stream_chat 丢弃、chat_json 用 `_strip_think_blocks` 剥除。
- 注意：用户自己 21:59 起的 dev 后端带 `--reload`（uv 全局 python，非 launch.json 的 .venv 无 reload 版），改代码自动热载，预览托管的 backend 起不来（端口被占）属正常——验证生效用「messages 响应含 task_state 键」判别。

**2026-09-27 团队群渠道事实块**：用户在群里问「有多少人」被总助否认群的存在（提示词只有可转派名册、无渠道事实）。修法=api/assistant.py post_message 判定 `thread.colleague_role_key` 为空 → `channel_kind="group"` 透传到 run_colleague_turn → `_group_channel_note`（colleague_prompt.py）注入「群内人类成员=发起人；AI 同事成员=在册启用全员 N 位（含你）」到 system prompt。**人数必须用 `get_ai_colleagues(include_disabled=False)`（含组长 assistant）**——`colleague_roster_digest` 是可转派名册（`_dispatch_roster` 滤掉 `dispatchable=False`），拿它数人头会漏组长（5≠6）。用户定调：群人数=人类成员+全部虚拟 AI 角色。e2e 实测答「7 位成员=你+6 位 AI 同事」。

关联 [[munder-difflin-borrow-list]] [[skill-tree-trunk-architecture]] [[agent-architecture-decision]] [[dispatch-llm-judge]]。
