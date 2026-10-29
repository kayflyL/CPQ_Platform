---
name: cumora-agent-coordination-reference
description: "cumora(yetone开源AI队友聊天)的协调防线/防死循环/评测设计,对AI办公室审计P1(无run台账/无评测)直接对症;方法论与我们铁律互相印证"
metadata:
  node_type: memory
  type: reference
  originSessionId: fcb42c79-ac71-489d-802d-96912f5bcdc0
  modified: 2026-10-01T20:19:59.762Z
---

**cumora** = yetone(Avante.nvim作者)开源的「AI agent 是正式队友」的团队聊天,https://github.com/yetone/cumora 。与 [[chat-session-runtime]]+[[office-behavior-v2]]+[[dispatch-llm-judge]] 是同一命题的独立实现,2026-10-02 调研。

**可直接对症我们缺口的机制**(细节在仓库 docs/COORDINATION.md):
- llm_calls 成本台账+run 行(带 summary、基建故障只记 run 不进聊天)→ 我们 08-27 审计 P1「无 run 持久化/无观测」的现成设计
- ⚠️10-02 用户定调:系统 LLM 已官方直连,无中转 429 问题;它的限流防护对我们不再是痛点,协调防线类(t triage/新鲜度门/hold token)按边角参考处理
- benchmarks/ 真实 LLM 多 agent 回归(chain/counting/werewolf/kanban 四场景,debug+print 输出,pytest 跑)→ 审计 P1「无评测」的模板
- Triage gate: 小模型先判「这轮要不要醒」,纯门不做决策 → 我们转接判官的节流前置
- 新鲜度门: 回合发起时 seen_cursor 对比 live max(message_id),滞后即 HELD(带 reason 进上下文)同事务重读重决策;防撞车同时防过期回复
- 同事务原子 verbatim-dup HOLD: 防 Redis 与 inbox cursor 不同步双发 —— 教训:防重状态永远跟收件箱指针同一存储
- 确定性防循环地板: HARD_LOOP_CAP=20、lapping detection(消息数>在场agent数)、每8条强制查DM、triage floor≥90%允许被 LLM 否决 → 我们 TurnBreaker(现 observe-only)转执法的参考
- Stall pipeline + NX 认领 + 拒绝封顶: 谁停滞一个队友提醒一次;「队友缺席是团队常态」→ 补我们 mission 链「卡住谁接盘」缺口(PortalDispatchPanel.stuck 只管人机流程)
- Hold token: 任何 bypass 必须以 token 确认服务端展示过的事实,防软门被 agent 学会绕过
- 记忆是状态: 写失败要 all-or-nothing(静默失败曾引发卡死)、过拟合记忆要点名清除

**方法论印证**(我们已有同款,英文原版):
- "Never add a prompt rule when a code mechanism is the right fix" = 禁令不进黑盒代码
- prompt 只写形状规则、5 条天花板、~5KB = skill prompt 压缩(4314→1217字)
- 反模式对: 别只封一层(封两层+地板)、别用 prompt 修 infra、别加无超时 fetch、基线 diff 定位回归

**产品形态(10-02 看官方截图,对聊天窗/看板有参考)**:
- **10-02 已实施三件套**:①办公室右栏「团队群/同事」双域(OfficeRoomChat.vue 复用 group 渠道+AssistantComposer @点名;ColleaguePersonaCard.vue 名片=职责/presence/手头任务/工具白名单,**住 components/assistant/ 与浮动面板共用**);②思考流=AssistantMessageItem 升级可折叠思考块(计时+自动收起)+工具活动卡(后端 agent_react phase→runners 广播 tool_trace→assistantChatWs.toolTraces,行数预算 700 内);③@点名路由后端本就有(resolve_chat_target.find_mentioned_colleague)。构建+59 测试过;tool_trace 广播形状有专项守卫 tests/test_colleague_tool_trace.py(假循环钓出真 event_sink 闭包,拦库断言 start/done 保序+旧形状无 phase 不发卡)
- **10-02 晚第三轮(用户第三次发火「你到底做原型是为了哄我吗」后逐格对齐)**:浮动面板=消息中心——筛选签(全部/房间/同事/未读)+房间/同事分组(头像presence+时间+last_message预览+未读点);**多房间零迁移=有名字的群线程**(title即房间名,＋新建房间 threads.create,切换=setThread;默认名「全员大厅」;房间名是业务事实UI自建不种子);未读=localStorage lastSeen vs updated_at(首启存量点亮);presence=面板自持office WS;聊天头身份区(头像+房间/私聊chip+副标);消息meta(名字+时间,用户侧 你+时间);思考块+工具卡长进气泡内部;composer hint prop;后端 thread_kind=all(list_threads kind条件化,同事线程=office_colleague kind 默认list拿不到)。未读数字/房间种子/小声聊=不做(分别缺已读模型/业务事实/AI↔AI DM源)
- **10-02 晚「照原型做」第二轮(用户铁律:原型=规格书,不许自作主张砍范围)**:引用回复全链路已落=悬停↩(AssistantMessageItem)+composer 引用条+quote 快照存 assistant_messages.data JSON(零迁移,存快照不存 message_id 删后自洽)+LLM 回合输入附 [引用 X:…] 行(判官路由读 content 不受影响);办公室房间补齐历史抽屉/新建/全屏(Teleport 出逃 body——**backdrop-filter 祖先会吞 fixed**);名片两 bug 修复=暗色(曾写不存在的 --cpq-overlay-w9 假 token 恒白,教训:**用 token 前先 grep tokens.css 验存在**,正确浮层底色=--cpq-glass-3-bg)+关不掉(外点/Esc/滚动 capture/同锚点再点 toggle 四路关闭,taskAction prop 控制看任务按钮)
- **小声聊 whisper 定调=不做**:cumora 的 whisper 摘要的是「同事↔同事私聊」,本系统无 AI↔AI DM 通道(没有内容源可摘要);要落它得先建 agent 间私聊能力(谁发起/何时触发=产品决策),显示层不空转
- 未做=房间多线程/日程送达/小声聊(待 agent 私聊能力)
- 最大缺口对照:它=Slack 式「房间时间线」多人混排;我们原来办公室=点同事开 DM 面板一次一个角色,现在右栏有房间页签
- live 感三件套:typing 指示(会话列表预览里也有 "Atlas is typing...")+每颗头像 presence 点(绿在线/紫忙/灰离)+消息旁角色徽标(RESEARCHER/HUMAN 小徽章)
- @召唤经济:composer 提示 "Type @ to summon",agent 消息里 @同事 带内嵌小头像互相点名;@=显式人类意图可作转接硬指定
- 日程行为以同事消息送达:"Nova: 10:00 日历提醒已触发…" proactive 消息,非系统 toast —— 对我们 daily_plans/企微通知的「同事化送达」有借鉴
- 手机五 tab: Chats/Whispers(私聊)/Library/Agents/Me;皮肤是通用 Tailwind 灰白,勿抄(我们有 Glass Console+3D 身份);它的消息流是朴素长文本泡,无业务卡/任务胶囊——消息渲染我们领先
- cumora 源码可抄点(已读 Message.tsx/messages.ts):工具调用是一等消息(ToolCard)、流式即消息行(delta 追加、typing 首字节即消失+45s 过期兜底)、skipHtml 防注入、CJK 不用斜体、消息 #N 序号引用、同事私聊在房间留 WhisperLink 摘要行可偷看

**不适用/我们领先**: BYOA(Claude Code 守护进程)、K8s pod/FUSE/邮件集成;它没有权限模型(price_access/工具白名单我们更完善),它 agent 恒在线而我们有作息日程+3D办公室(产品维度它没有)。
