# AI 办公室 3D 视图 (AiOfficeView)

> 最后更新：2026-10-02（右栏升「团队群/同事」双域：房间聊天复用 group 渠道 + 同事名片浮层；思考流升级=可折叠思考块+工具活动卡。另见 09-28 记忆两级分域）

## 功能概述

AI 办公室主视图（`/ai-office`）：Three.js 3D 办公室现场（同事坐席/状态/区域），点同事对话，任务看板与团队管理入口。

## 桌面结构（>860px）

- **顶栏**：团队切换（room-picker，按房间 role_keys 过滤同事）+ LIVE 连接状态 + Manage Teams（`ai.office.manage`/`ai.office.admin`）+ 日志审批
- **三栏 workspace**：左 = 任务看板预览（stats + 最近任务 → 打开 TaskBoard 弹层）；中 = Office3DCanvas（3D 场景，`editable` 由 `ai.office.manage` 驱动）；右 = 检查器双域页签 **「团队群」/「同事」**（团队群=OfficeRoomChat 房间聊天；同事=头像/状态 + OfficeColleagueChatPanel）
- **弹层**：AiOfficeManagement（团队/员工管理全屏）、GovernancePanel（日志与审批）、TaskBoard（任务看板）

## 浮动面板=消息中心（2026-10-02 第三轮，逐格对齐原型 office-room-chat）

- **侧栏消息中心**：**房间/同事两组列表**（筛选签已删——用户定调多余）——行=头像(presence 点)+名字+时间+最新消息预览+未读红点，选中高亮。数据源=`threads.list({ withMeta, allKinds })`（后端 `thread_kind=all` 一次回群线程+员工线程，`last_message` 120 字预览随 `include_preview` 下发；skill_studio_preview 线程排除）。
- **多房间（零迁移）**：房间=有名字的群线程（无 `colleague_role_key` 的 assistant 线程，title 即房间名）；「＋ 新建房间」=内联输入回车 `threads.create(title)`；切换=`setThread` 换线程（同 openHistoryThread 链路）。默认房间显示名「**全员大厅**」（无 title 的群线程兜底名）；具体房间名是业务事实，UI 里自建、不做代码种子。
- **未读**：localStorage `ap-thread-seen-v2`（thread_id→本地时间戳），`updated_at > lastSeen` 即未读；打开会话/当前会话来新消息即记已读；首次启用按各自 `updated_at` 点亮。⚠️**v1 死于时钟坑**：存 `toISOString()` 是 UTC，后端 `now_iso()` 是本地时间 ISO，串比大小恒差 8 小时→红点清不掉；**戳必须与后端同格式同钟**。红点非数字——已读回执模型不存在，计数无事实源。
- **presence**：面板自持一条 office WS（`useOfficeSocket()` 实例，onMounted connect / 卸载 disconnect）；头像绿点=状态非 idle。侧栏头像、聊天头、消息头像、房头名册四处。
- **聊天头身份区**：头像+presence+名字+「房间/私聊」chip+副标（房间=N 位成员·可 @ 点名；私聊=同事职责一句话）。
- **消息 meta**：作者行=名字+时间（`fmtChatTime`：当天 HH:MM/昨天/MM-DD/跨年）；用户消息上方「你 · 时间」；**思考块+工具活动卡长进气泡内部**（原型消息卡形态，不再是气泡上方的独立暗块）。
- **composer**：`hint` prop（房间/群聊传「@ = 指定该同事接话 · Enter 发送 · 悬停消息可引用」，右对齐小字）。composer 左下的 +（工作流）和 @（点名）是真功能，原型位置的附件/emoji 装饰图标未加。
- **真人/AI 身份区分（2026-10-02 第四轮，第六轮修正）**：区分语言跟随系统既有惯例——AI 消息=同事名+「**AI 同事**」小牌+时间+头像 presence 点；人类消息=**登录账号真实姓名**+时间+右侧头像（曾有「你+人类」贴纸式标签，用户否决：系统里 AI 的标记就是「AI 同事」，真人名字即身份）。侧栏 280px；预览剥 markdown 符号；DM 里作者名常显。**多真人同房未做**：线程是 `created_by` 私有（读写+WS 都按属主过滤），多人房间要线程成员/共享模型（thread_members+跨用户广播+进房权限），属权限产品决策待拍板，别静默实现。
- **第五轮微调（2026-10-02 晚）**：默认窗口 680×680→**860×720**（`useAssistantFab.PANEL_WIDTH/PANEL_MAX_HEIGHT`，尺寸是常量即时计算不落 localStorage，改完即生效）；拆掉面板内的名册条 `.ap-room-head`（与聊天头身份区重复，两个头叠着=「中间被截断」观感；办公室页房间的 room-head 保留，那边只有这一个头）；**名片入口**=消息作者头像（聊天流里点谁的头像看谁的名片——主入口，`AssistantMessageItem` 发 `@persona` 由宿主解析成员档案；曾错挂到侧栏头像上，那里语义=切会话，用户纠偏）+ 聊天头头像（房间=Lead，私聊=当前同事）；侧栏 padding 右移（10px 14px）缓解贴边截断感。面板内名片看任务按钮仍 `taskAction=false`（无任务板可跳）。⚠️名片 `z-index` 必须 >2000——面板本体 1500/全屏 1600，曾用 1100 被面板整个吞掉（症状：上层头像的名片"半弹"、侧栏的"压根不弹"，实为全被盖住）。
- **不做**：未读数字（需已读回执模型）；房间名种子（业务事实）；小声聊（无 AI↔AI DM 内容源，待产品拍板）。

## 团队群房间 + 同事名片 + 思考流工具卡（2026-10-02）

对标 cumora 的产品形态三件套，全部复用现有渠道与状态源，零新后端表：

- **团队群房间（OfficeRoomChat.vue）**：右栏「团队群」页签进房间——房头名册头像串（presence 点，暗=离线/空闲、亮=有状态）+ live 副标（`s.statusText`「思考中…」），消息流复用 AssistantMessageItem（作者按 `message.colleague_role_key` 解析，群聊式头像/昵称）。渠道=productionRuntime `'group'` 会话，与浮动面板「团队群」**同一份会话状态**（thread 经 `threads/group-resolve` get-or-create，entry_point=ai_office）；发送走 `postMessage(roleKey='assistant')`，@点名=composer 传 `:members` 启用补全（后端 `resolve_chat_target` 的 `find_mentioned_colleague` 确定性路由，早已存在）。
- **同事名片（ColleaguePersonaCard.vue，住 components/assistant/，办公室页与浮动面板共用）**：点检查器头像/名字、房间名册头像、浮动面板房间头名册头像弹出——职责（`description→capabilities` 兜底链，同 AssistantPanel.colleagueDescription）、presence 徽标、手头任务（missions 里 owner/steps 命中的 running/queued 单）、工具白名单 chips（`tool_ids` 前 4 + 溢出数）、按钮 发私聊（切「同事」页签选中 TA / 面板内切 DM）/看任务（`taskAction` prop，默认关——聊天窗口里没有任务板，办公室页传 true 开）。Teleport 到 body + 触发元素锚定、越界翻转；**关闭四路**：外点、Esc、任意滚动（capture）、同一触发元素再点一次（toggle）。底色=`--cpq-glass-3-bg`（浮层专用玻璃，暗 rgba(18,24,38,.75)/浅白 .75 自动随主题）——曾误写不存在的 `--cpq-overlay-w9` 导致暗色下恒白，勿再发明 token。
- **思考流（AssistantMessageItem 升级）**：旧「Claude Code 式单行思考暗块」升级为**可折叠思考块**（头部=💡标签+秒计+箭头；流式期间展开直播尾部 1600 字，回合收尾自动折叠成「已深度思考 Ns」）+ **工具步骤行**（`traceRows` prop：同一工具 start→done 原地翻状态，行内带结果事实摘要+耗时右侧，转圈→✓，封顶 6）。数据源：后端 `agent_react` 工具发射带 `phase`+`detail`（`_tool_result_detail`：列表报条数/字典报键数/字符串报字数，确定性不发明）+`elapsed_ms`；`colleague_turn_runners.event_sink` 累积 `tool_steps` 广播 `tool_trace` 并**随消息落库**（`_persist_and_broadcast` 存 `data.tool_steps`）——历史消息常驻步骤行，不再回合即清。浮动面板与办公室 DM 面板同享。
- **不做**：人人聊天（人类间协作走门户/评论）；房间多线程（group 是单一团队群会话，房间×线程要后端线程模型扩展，未做）。
- **浮动面板房间头（2026-10-02 补齐，对齐原型的「整个聊天窗口」形态）**：AssistantPanel 群视图顶栏下加 `.ap-room-head`（群徽 + 团队群 + 房间 chip + live 副标「N 位成员 · 可 @ 点名」/回合中显示 statusText）+ 名册头像串（前 5 + 溢出数），头像点开同事名片（`taskAction=false`，发私聊直接切 DM）。窗口级能力（会话列表/历史抽屉/新建会话/全屏）面板本来就有，此处只补房间形态；数据与办公室页房间同一条 group 会话。
- **引用回复（2026-10-02，全链路）**：悬停消息浮现 ↩（`AssistantMessageItem` 触屏无 hover 不另做长按）→ composer 上方引用条（面板 `.ap-quote-bar` / 房间 `.room-quote-bar`，✕ 可撤）→ 随下一条用户消息发出。后端 `PostMessageBody.quote` 截断快照（名 40 / 文 120 字）存 `assistant_messages.data` JSON `{quote:{name,text}}`——**零迁移**（data 本就往返）；存快照不存 message_id，被引用消息删除后引用自洽。引用正文以 `[引用 X：…]` 一行附加给 LLM 回合输入（不影响 @点名路由——判官读的是落库前 content），用户消息本体保持干净展示。
- **房间历史/新建/全屏（2026-10-02，OfficeRoomChat 房头右侧三钮）**：↺ 历史（房间内右侧 240px 玻璃抽屉，群线程过滤口径=无 `colleague_role_key`，同 AssistantPanel.loadHistory；归档线程点选走 `threads.restore` 自动换位）、＋ 新建（归档当前群线程 + `group-resolve` 开新）、⛶ 全屏（Teleport 到 body 的 fixed 层——**房间祖先有 backdrop-filter 会吞 fixed，必须出逃**；Esc 退出）。与浮动面板共享同一条 group 渠道会话。
- **不做**：人人聊天（人类间协作走门户/评论）；房间多线程（group 是单一团队群会话，房间×线程要后端线程模型扩展，未做）；**小声聊摘要行**——cumora 的 whisper 是「同事↔同事私聊」的房间摘要，本系统没有 AI↔AI 私聊通道（同事不会互发 DM），没有可摘要的内容源；要落它得先建 agent 间私聊能力（谁发起/何时触发是产品决策），显示层不空转。

## 员工管理·长期记忆（2026-09-27 重构）

EmployeeManager.vue 记忆抽屉是记忆系统的治理面：

- **写入层换轨**：旧 fire-and-forget 抽取器已退役；`colleague_memory` 工具恒挂在同事工具轮（`_run_tool_turn` 注入，不占工具白名单）与 skill 聊天轮，对话中模型自决 write/retire。抽屉条目来源标签区分 `手动`/`对话记忆`/`整理归并`/`历史`（读 `provenance.via`）。
- **双时间轴**：删除/淘汰/矛盾取代都打 `retired_at` 戳不物理删（管理面「删除」=强制失效，仅「清空」仍物理删）。勾选「含已失效」可看历史，失效条目划线置灰并标注被谁取代（`superseded_by`）。
- **「整理」按钮**：触发 `POST /memories/consolidate`——同事用自己的 system_prompt 全量复查**公共域**活跃记忆提归并案（merge/retype/retire），确定性守卫（钉死集只读、未知 id 拦截）后落库；toast 报告生效数与被拦提案数。私有域不参与整理，靠容量封顶+对话内 retire 代谢。
- **注入层不变**：钉死集（置顶∪手工）恒注入 + 其余按相关性召回；命中刷新 `last_accessed_at` 供老化参考。容量 100/域（公共域与每个用户的私有域各自计），超出打戳淘汰最旧非置顶。

**两级分域（2026-09-28，多用户隔离）**：`colleague_memories.user_id` 定域——NULL=角色公共域（治理面维护，全员注入），非空=该用户私有域（对话写入归属 `TOOL_CTX.user_id`，仅本人注入/可 retire）。确定性规则，不靠 LLM 判断共享与否：工具 write 无用户上下文直接拒绝、公共域条目对话内无权失效；抽屉默认只列公共域（`GET /memories` 传 `user_id` 可查指定用户私有域排查）。

## TaskBoard 任务状态色（09-27）

- 色源：`behaviorConfig.mission.status_meta`（状态→label+color）——由后端 `_DEFAULT_BEHAVIOR.mission` 默认提供（queued/running/done/failed/cancelled），`_read_config` 对存量 DB 配置嵌套自愈补齐并回写；步骤枚举同住 `assignment_status_meta`。
- 渲染语法：日历事件 `.tc-cal-event` 与甘特条 `.tc-gantt-bar` 不再实色底+写死白字（夜间刺眼），改与 `.tc-status` chip 同款 `--status-color` tint：`color-mix(状态色 16~18%, var(--cpq-bg-card))` 底 + 状态色文字，明暗主题自适应。

## 可交互物件：点显示器看任务（2026-09-27）

- **交互**：点击同事桌的显示器屏幕 = 选中该同事（相机跟随）+ 打开任务板聚焦 TA 的任务。hover 命中同事任意部位时光标切 pointer 并显示名牌（空闲时限频 ~10Hz 的 raycast 探测，拖拽/按压中不跑）。
- **拾取关键**：`createDesk` 给显示器面板+屏幕两块 mesh 打 `userData.monitor`；`actorAtPointer` 返回 `{roleKey, mesh}`。**气泡/名牌 sprite 是 HUD，不参与命中判定**（否则俯视角会整片挡住桌面点不到屏），仅当射线只命中 sprite 时兜底选人（保留点气泡=选人）。
- **聚焦优先级**（AiOfficeView `onOpenMission`）：① `statusMap[roleKey].mission_id` 在 missions 里 → TaskBoard 直开该任务详情；② 无运行中但名下有任务（owner_role_key / steps[].role_key 匹配）→ 传 focusRoleKey，TaskBoard 用同事名预填搜索过滤；③ 都没有 → toast「TA 手头暂无任务」，**不开板**。`missionFocus` 随看板关闭清空（`closeTasksBoard`，左栏按钮打开为全局视图）。
- **TaskBoard 新增可选 props**：`focusMissionId` / `focusRoleKey`（全屏层 v-if 每次重挂，onMounted 应用一次，零结构改动）。
- **移动端**：tap 显示器 = 打开 `tasksOpen` 全屏任务层（同一 `open-mission` 事件，pointer 事件天然复用）。

## 移动端（≤860px，2026-09-19）

三栏取消，改为「主内容独占 + 旁路抽屉 + 拇指区动作」：

- **3D 全屏**：Office3DCanvas 独占视口剩余高度（`editable=false`，编辑空间仍走桌面）；状态图例浮右上。触摸交互依托 pointer 事件 + OrbitControls（点=raycast 选人 ≤5px 位移判定，拖=转视角，双指=缩放），组件零改动。
- **左侧同事竖栏**（09-19 晚从底部头像行改来）：62px 玻璃竖栏贴左缘（`position:absolute` 重定位，模板复用原头像行容器——`.m-workspace` 包裹层会触发 vue-tsc 推断塌陷，勿改回包裹结构），头像+姓名+状态点，点人 → 全屏聊天层；当前对话者蓝边高亮；3D 场景 margin-left 让位。
- **全屏聊天层**：底部滑入（m-chatup 过渡），头部 = 头像/名字/状态/正在做什么；OfficeColleagueChatPanel 以新增的 `defaultExpanded` prop 预展开（默认 false，桌面检查器不受影响）；✕ 收起回现场。
- **任务按钮 → 全屏任务层**：TaskBoard 整体复用，徽标 = running+queued 任务数。**弃用侧抽屉**：TaskBoard 甘特/清单 min-width 960、tc-root overflow hidden，330px 抽屉内头部竖炸 + 甘特被裁；全屏层（`.m-tasklayer`/`.m-taskscroll` 双向滚动）+ 宿主侧 :deep 让 tc-header/tc-actions 折行、tc-root 放开 overflow，TaskBoard 零改动。
- **任务入口在顶栏**（09-19 晚改）：手机端顶栏加「任务」按钮（徽标 = running+queued），原底部按钮弃用——底部只留头像行，场景不为按钮留空带也不怕遮挡。Manage Teams / 日志审批收纳 ⋯ 菜单（按权限显隐）；LIVE 保留顶栏。
- 原型：[docs/prototypes/ai-office-mobile.html](../prototypes/ai-office-mobile.html)

## 关键状态

- `selectedRoleKey`：3D 点选 / 头像行 / 任务卡跳转共享（同一 selectedColleague）
- `openLayer`/`chatLayerOpen`：手机端互斥层状态；`statusMap`（WS）驱动状态点与图例
