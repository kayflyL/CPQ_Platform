# AI 办公室 · 团队管理（TeamManager / EmployeeManager / ColleagueAccessPanel）

> 最后更新：2026-10-15（工作流发起两入口：「+」装填模式 + suggest_workflow 确认卡；占位消息路径已删）

## 行为配置页二轮打磨（2026-09-17，用户五条反馈）

- **重复标题清理**：子页签内的面板不再自带页级大标题——OfficeBehaviorEditor 的「行为配置」toolbar 删除、capability 子页签 Skills/Workflows 的同名 h3 删除（aom-hint 保留）；员工/访问权限面板本就无页头
- **重复保存清理**：行为页的「保存行为配置」按钮删除，统一走管理页页头「保存当前」（saveCurrent → behaviorEditorRef.save()，defineExpose 曾在重写时丢失导致断线，已补回）
- **泳道时间轴**：单轨+左侧同事栏改为**全员泳道**（每同事一行 38px 轨道，标签列 116px），角色变多纵向增长且每行都有内容；「现在」红线只画当前选中泳道；「＋新增」每行尾部各自有，写入该同事个人段；选中段编辑器仍在下方（跨泳道 key=`${role}:${planId}:${idx}`）
- **行为日志迁出**：新组件 [OfficeEventLogPanel.vue](../../src/views/office/OfficeEventLogPanel.vue)（a-radio-group 筛选 + a-tag 徽标 + 20s 轮询）；挂进 [GovernancePanel.vue](../../src/views/office/GovernancePanel.vue) 的 a-tabs（治理审批 / 行为日志），3D 办公区入口按钮「治理审批」→「日志审批」，浮层标题「日志与审批」；行为页不再有日志卡
- **antd 化**：生效星期改 a-select multiple、删段/批量按钮全 antd、徽标 a-tag color
- **暗色适配**：组件内全部颜色收敛为局部调色板变量（--be-*/--seg-*/--bd-*），`[data-theme='dark'] .behavior-editor` 整体覆盖（段块/徽标改浅色前景 + 低透 tint），玻璃面走 --cpq-glass-* token + backdrop blur + glass-card-shadow
- 教训：脚本化 marker 切片改模板时 cut 的 keep_end 语义要复核，本轮曾产生双 `<div class="be-section">` 与重复注释（已修）

## 行为配置页 V2 重构（2026-09-16）

组件：[OfficeBehaviorEditor.vue](../../src/views/office/OfficeBehaviorEditor.vue)（整体重写，原型 docs/AI_OFFICE_BEHAVIOR_EDITOR_PROTOTYPE.html）。挂在两处：员工页签「行为配置」、TeamManager 的 behavior 编辑窗——两处均已传 `:colleagues`。

- **页面结构**（六段裸表单 → 三块 + 折叠）：全局条（自主时钟开关/心跳/时区下拉 + 自主活动/LLM 措辞开关/预算滑条）→ **一日作息时间轴**（左列同事卡切换，09:00–19:00 横向色块段；拖边缘调时长、拖中间整体挪、5 分钟吸附、自动避让相邻段；点色块下方编辑器改活动文案/状态/意图/区域/起止/生效星期；尾部「＋新增」排个人段空档）→ 智能层卡（会议智能/会议模型/同事互动/协作联动/任务引擎）+ **行为日志**（`GET /api/office/events` 20s 轮询，来源徽标：日程 autonomous / 任务 pipeline / 对话 chat / 系统 system）→ 折叠外观层（status_meta 状态样式 + 状态→区域映射）
- **数据模型**：`behavior.autonomous.daily_plans = [{id,label,roles[],weekdays[],segments[{start,end,status,intent,zone,activity}]}]`；roles=[] 为全员段，个人段 roles=[role_key]；段文案支持 `{name}/{role}/{zone}` 变量。旧 `schedule_rules`/`idle`/`life.fallback_actions` 已退役：后端 `_migrate_behavior_daily_plans` 读侧迁移（schedule_rules 逐条转「旧定时规则（迁移）」计划的段，其余直接删键），前端 normalize 显式组装不再回流旧键
- **引擎**（[office_clock.py](../../backend/app/services/office_clock.py)）：`_tick_plans` 段开始时刻（HH:MM 命中）向角色群发事件、每天每段一次（fire_key 去重）；`_tick_life` 按当前时刻命中段出动作（`_current_segment` 多计划取开始最晚段=个人段覆盖全员段），**无段时段保持安静不再编造活动**；LLM 开时只贡献措辞与聊天对象，status/intent/zone 由段锁定（确定性包裹 LLM）；确定性同事互动保留（冷却桶哈希低频触发）；[office_brain.py](../../backend/app/services/office_brain.py) 删除 `_DEFAULT_FALLBACK_ACTIONS` 四条全局台词池及 `_autonomous_rule_action`/`_profile_fallback_action` 死路径
- **与任务看板的关系**（定调）：优先级 任务 > 日程段 > 空闲；派单随时打断作息（assignment_action_map 不变），段为任务提供语境；行为日志把任务/作息/对话合流为统一时间线
- 验证：DB 真实配置迁移烟测（7 段基线 + 2 条旧规则迁移、幂等）、`npm run build`、backend AST+import 全过

## 员工档案页整页审计修复（2026-09-15）

用户报「宽度不自适应 + 开场白贴胶囊 + 输入框底色显眼 + 参数区无排版」，整页审计后一次修复：

- **宽度**：编辑弹窗 760 封顶 → `min(94vw, 1000px)`（原 760 是简历纸初版设计上限，≥810px 屏幕恒宽显得「不自适应」）；其余 modal（记忆 720 / 会话 880 / 消息 640 / 新建与重命名 520）统一 `min(94vw, Npx)` 兜底小屏
- **开场白底色显眼·真根因**：`a-textarea(auto-size)`/无前后缀 `a-input` 的**根元素就是 input.ant-input**（无包裹层），自定义类落在元素自身——旧代码 `.em-quote :deep(textarea)` 等**后代**选择器从未命中，虚线样式与 `!important` 夺回全部失效，全局 `#app .ant-input` 玻璃底透出。修复=自选择器（`.em-quote.ant-input`）+后代选择器双保险（大名字/填空行/开场白三处同修）；开场白与胶囊间补 `margin-top: 14px`
- **封面色带对齐**：`.em-cover` 负 margin 由 `-24px -24px` 修正为 antd 实际 body padding `-20px -24px`（原顶部多拉 4px）
- **参数三件套同构**（温度滑杆 / 推理档位胶囊 / 模型覆盖输入框）：统一「标题行(label+蓝读数+重置钮) / 控件 / 提示」结构，`grid auto-fit minmax(250px,1fr)` 自适应分列；模型覆盖从封面填空线迁入并改标准输入框；「恢复跟随全局」从提示行内小链接改为标题行正规 pill 按钮（温度与模型覆盖各一个，仅自定义时出现）；删除竞争 margin（.em-slider-field 14px vs 8px）
- **权限面板迁出**：ColleagueAccessPanel（页面级配置）移出员工档案弹窗（原来排在删除/保存按钮之后），独立为「员工 → 访问权限」第三页签（员工配置 / 行为配置 / 访问权限）；封面「价格可见」chip tooltip 同步改指该页签；该页签下页头「保存当前」隐藏（面板自带「保存权限」）；em-root 撤销 height:100% 改自然流
- **清理**：死样式 ~90 行（.em-list/.em-member/.em-dot/.em-name/.em-role，旧列表布局遗骸）；保存按钮去 letter-spacing 6px hack（min-width 168→132）；动作区改两端对齐（删除极左、保存极右）；会话消息/记忆条目/权限面板卡硬编码 `rgba(255,255,255,x)` → cpq token（--cpq-overlay-w3 / --cpq-border-secondary / --cpq-overlay-w4）

## 员工编辑弹窗·简历式版式（2026-09-13）

EmployeeManager 编辑弹窗按「简历纸」重排（原型 docs/prototypes/employee-profile-cv.html，羡辙 zhangwenli.com/cv 版式语言 × CPQ token）：

- **封面**（蓝调 a5 色带通栏）：圆形头像环（头像 URL 优先，否则 Live2D 形象）→ **大名字即输入框**（28px/800，双层错位阴影 `1px 2px a30 + 3px 5px a10`）→ role_key mono 胶囊 → 状态 chips（在职/可被总助分派可点切换，价格可见只读带 tooltip）→ 开场白引述（居中斜体虚线下划）→ 填空行（主题色/形象/头像 URL，下划横线填空式，focus 蓝边）
- **基本信息 section 取消**：名称/主题色/头像URL/形象全部融入封面；role_key 只读展示一次
- **分节居中标题**（人格与指令/能力/记忆，17px+轻阴影+副题一行），替代原 01-04 编号左对齐头
- **动作居中**：删除=弱化文字按钮，保存=渐变主按钮 letter-spacing 6px min-width 168px
- 纸宽 `min(94vw, 760px)`，高度自然生长、超 92vh 内部滚动（scrollbar-gutter stable）；ColleagueAccessPanel 仍在纸底（※ 2026-09-15 起纸宽已放宽至 `min(94vw, 1000px)`，权限面板已独立为「访问权限」页签，见上文审计修复节）
- 所有交互逻辑（chips 切换/滑杆/档位/记忆面板/3D 折叠）零改动，纯版式重排
- **控件语言 pill 化（同日二轮，对齐原型截图差异）**：回复风格/推理档位=胶囊按钮组（.em-pill，选中 a10 底+蓝字）；温度滑杆去 marks 粗轨 6px+行头蓝字读数「0.7 · 适中」；模型覆盖改填空横线行；能力三 select 改 pill 云样式（.em-cloud，已选项=蓝胶囊，输入框透明虚线）；记忆=单行 switch+标签+右侧统计 tag（.em-mem-row，修掉 flex 拉伸全宽开关）+文字链接入口；编辑功能不减（pill 点选即原绑定，云 select 仍可增删）
- **穿透全局样式**：`#app .ant-input/.ant-select-selector` 玻璃化 ID 优先级压过 scoped :deep()，弹窗内下划线填空/透明云选择器用 `!important`（沿用 portal-sheet-modal 先例）；Live2dPreview 在 148px 圆环内需 `min-height:0` 覆盖 + `bg-color="transparent"` 让父级蓝调透出；纸面改实色（去 backdrop-filter）+ 弹窗标题弱化居中

## 团队页签砍掉旧同事编辑器（2026-08-30）

- 左栏「同事配置」view/edit 面板整体删除：与员工页签（EmployeeManager）完全重复，且其「回复风格」绑定顶层 `response_style`，被后端 `response_profile.style` 优先级覆盖（改了不生效的样子货）；编辑/新增/删除统一收敛到员工页签
- 团队页签瘦身后的形态：结构画布（拖节点调布局 / 拖线建协作，点节点不再有响应）+ 右栏总览（团队卡 / Lead / 成员列表**仅展示** / 房间 / 团队信息编辑 / 智能转接）；「新增同事」按钮跳员工页签的新增弹窗
- 随删死码：永不弹出的「新增 AI 同事」modal（`createColleagueOpen` 从未置 true）、`tools`/`scopeOptions` 加载（只为旧编辑器服务）、`saveTeamTab` 旧 `updateColleague` 块（含失效 `response_style` 写入）、accessPolicy 死 prop 链（AiOfficeView → AiOfficeManagement → TeamManager 全链清除，权限面板 ColleagueAccessPanel 本就自包含）、孤儿 CSS（tm-access-view / tm-policy-* / tm-user-exceptions / tm-dispatch-rule-card / tm-left 系等）

## 员工页重构（2026-08-30）

### 表单结构（6 卡 → 身份/指令/能力/记忆 + 高级折叠）

1. **身份**：名称 / 角色标识（只读）/ 头像 / 主题色 / 启用 / 允许总助分派 / 开场白
2. **指令（大脑）**：System Prompt 人格提示词 + 回复风格三选一（**简洁 / 详细 / 自定义** radio，选中态存 `response_profile.style_mode`；选「自定义」展开 `style_prompt` 文案框，即原「详细度提示词」；保存时自定义+空文案会拦截）+ **模型参数**紧凑区（标题行内嵌「模型覆盖」输入框 + **温度滑杆** 0~1.5 与 **最大 Tokens 滑杆** 4000~16000 双列并排）
   - 滑杆交互：滑杆**常驻可拖**（无启用开关）；默认跟随全局（温度 0.7 / Tokens 8000，档位 tag 显示「跟随全局」）；一旦拖动即自定义，标题行出现「跟随全局」链接，点击回 null 走全局；档位提示 tag+文案随值实时变化（温度：稳定 ≤0.3 / 适中 ≤0.8 / 发散；Tokens：常规 ≤6000 / 长文 ≤10000 / 超长）；数据写 `response_profile.temperature/max_tokens`
   - 生效范围（2026-08-30 审计）：plain 闲聊与 react 工具两条路径真实消费；**skill_chat 业务问答路径固定低温 0.2 不读滑杆**（业务流确定性优先，滑杆下方有灰字说明）；`model_override` 五条 LLM 路径全部消费
3. **能力**：Skill / 工作流 / 可用工具——**数据来源与数据边界已退役（2026-09-13 工具即权限）**：能力面 = tool_ids（绑定 Skill 自动并入其工具），价格可见性 = 同事级 `price_access` 布尔（权限面板直改），query_data 可读表 = 工具自有白名单 `system_config.query_data_tables_allow`（默认 8 张业务表）；`DATA_SOURCE_CATALOG`/`scope-options` 端点/节点抽屉数据源派生展示全删，`normalize_colleague` 读侧静默剥离存量 `data_boundary`/`data_sources` 键（DB 无需刷库；存量一次性迁移脚本 `scripts/retire_colleague_data_permissions.py`）
4. **记忆**：启用长期记忆 + 对话后自动学习两个开关 + 按类型统计 tag + 「管理记忆」「会话管理」入口
5. **高级（a-collapse 默认收起，仅一栏）**：3D 办公室行为（wander / 空闲秒数 / 偏好区域 / 空闲动作）——模型参数已并入指令卡，不再放折叠区
- **整卡删除**：情绪 / 日程 / 关系卡（mood / schedule / relations.peers / preferences 后端零消费点）
- 死配置清理：`ColleagueUpdate` / `_default_colleague` 删除 memory / mood / schedule / preferences / relations.default+peers 字段；`normalize_colleague`（data_boundary.py）读时静默剥离存量死键，DB 无需刷库；relations 只保留 team_role / reports_to（有消费点）
- 孤儿组件 CharacterEditor.vue（零引用）已删除
- 温度 / 最大Tokens 补齐消费：react 工具路径（run_react_loop 新增 `llm_max_tokens` 参数全链路贯通）与 plain 闲聊路径行为一致；skill_chat 路径不动
- **方案助手已预填自定义风格**（`assistant.response_profile.style_prompt`）：活泼带表情文案（一段最多1~2个表情、先结论后展开、严肃话题收表情）；改/清在员工页「指令」卡

### 结构化长期记忆（Claude 式分型 + Mem0 式抽取归并）

- **存储**：新表 `rules.colleague_memories`（id / role_key / type / content / source(auto|manual) / pinned / created_by / 时间戳），按同事隔离，上限 100 条/同事（超限淘汰最旧非置顶）
- **四类记忆**：`user_profile` 用户画像 / `preference` 偏好反馈 / `business_fact` 业务事实 / `guide` 行为指引
- **自动学习**：每轮回复完成后 fire-and-forget 后台任务（`colleague_memory_service.extract_and_reconcile`）——便宜 LLM（reasoning_effort=low, 30s 超时, max_attempts=1）从本轮对话抽候选事实，对存量做 ADD/UPDATE/DELETE/NOOP 归并；失败静默（记忆是增强不是依赖）；开关 = memory_policy.auto_memory
- **注入**：`memory_block(role_key)` 按类型分组注入 system prompt（置顶优先，上限 30 条），替换旧的聊天快照罗列
- **管理面板**（「管理记忆」Modal）：类型彩色 chip + 内容 + 来源（自动学习/手动）+ 置顶星标（行内切换）+ 搜索 + 新建/编辑/删除/清空——像 Claude Settings→Memory 一样可查看可编辑
- **旧路径全删**：每条消息/回复写 `office_events(event_type='memory')` 聊天快照的读写管道、`/api/office/memories` 五端点、`office_memory.remember*` / `retrieve_memories` / `memory_prompt`、`office_event_repo.prune_memories`；startup 幂等清理存量 memory 事件行；office_memory 仅保留 3D 可观测态（events/facts/relations）
- **新端点**（挂 ai_colleagues，ai.office.manage 权限）：`GET/POST /api/ai-colleagues/{role_key}/memories`、`PUT/DELETE …/memories/{id}`、`DELETE …/memories`（清空）；前端 client 见 office.ts `listColleagueMemories` 等

## 工作流发起：装填模式 + 确认卡（2026-10-15）

工作流（如需求分析）从此前「只有输入框旁『+』显式发起」扩成两个入口，后端同一分支（`run_colleague_turn` 的 `workflow_launcher`，force_submit 直进引擎，首回合拿到的都是真需求）：

1. **「+」装填模式**：选工作流不再发「请开始【xx】工作流。」占位消息（旧路径会拿占位话当需求原文、白烧一整个引擎回合反问需求）。composer 亮装填条，下一条发送携带 `entry_point=workflow_launcher` + 需求原文直进引擎；群聊发送钉住技能归属同事（`ownerRoleKey` → `role_key`），防 LLM 判官把 launcher 消息路由给别人；换会话自动卸装填。
2. **suggest_workflow 确认卡**：绑定 workflow 的同事在普通聊天态自动获得 `suggest_workflow` 工具（可发起清单=其 workflow 绑定，经 TOOL_CTX.workflow_offers 下发）。对话里出现完整需求时模型整理需求原文发起建议，建议随消息 `data.workflow_suggestion` 落库+广播；前端渲染一键发起卡，点击即以需求原文 `workflow_launcher` 发起。补上了 skill_types 契约里「模型建议+用户确认」这半条路线（此前只有「+」半条）。

实现：`colleague_prompt._workflow_offers`/`_first_workflow_skill`（能力域归 prompt 层）、`agent_tool_handlers._tool_suggest_workflow`、`colleague_turn_io._workflow_suggestion_of`/`_persist_and_broadcast(workflow_suggestion=…)`、`useAssistant.armedWorkflow/armWorkflow/launchWorkflowNow`（旧 `launchWorkflow` 占位消息版已删）。测试：`tests/test_agent_tools.py` suggest_workflow 三例。

## 回合终态兜底 turn_active（2026-09-13，修复「所有 AI 角色卡模型思考中」）

- **病灶链**（当日实测复盘）：done 终态事件落在 WS 重连空窗（一个线程 15 分钟重连 7 次）→ 看门狗 resync 以「有未见消息」判终态，但卡片消息已经 WS 先到本地 → 永远判不出「已结束」→ 全局 `waiting/running` 卡死 → 切到哪个角色都显示同一颗「模型思考中」泡 + composer 全员禁言（零 POST）；用户硬删当前线程自救 → resync 404 死循环，锁得更死
- **修法 = 服务端事实替代客户端猜测**：`colleague_turn_service` 维护 `_THREAD_TURN_ACTIVE`（排队不算在跑，drain 续跑重新标记），`GET /threads/{id}/messages` 返回 `turn_active`；前端两个 resync（useAssistant.resyncThreadState / useEmployeeChat.resyncStateMessages）改为「有未见消息 ∨ turn_active=false ∨ 404」都判终态采纳解锁
- 长回合（skill 引擎数分钟）期间 turn_active=true 持续等，不会误采纳；实测：执行中 True→结束后 False+回复落库
- WS 频繁重连（~2 分钟一次）疑似 vite proxy 空闲断开，未根治但已被本兜底覆盖；停步按钮（stop）也补广播 `queue_state depth=0` 清排队徽标

## 会话运行时 ChatSessionRuntime（2026-09-13，根治「多窗口各养一套聊天状态」）

- **病灶**：useAssistant 是「单当前线程 + 一组全局瞬态 ref」，浮动窗/门户/工作流画布预览各持独立实例，办公室侧 useEmployeeChat 再平行实现一套（states[roleKey]+全局单 socket+独立看门狗）；同一条服务端线程在多个窗口各有一份互不相通的客户端状态，瞬态全局单例 → 一处卡死全体假死（见上节 turn_active 事件）
- **架构**（[chatRuntime.ts](../../src/composables/chatRuntime.ts)）：会话=渠道键 `dm:{role_key}` | `group` | `preview:{entry_point}` → 唯一 reactive 状态对象（AssistantChatWsState 超集）。服务端本就「每角色一个活跃会话」，渠道键即会话身份 → 浮动窗/门户/办公室传同一 `productionRuntime` 单例，**同角色=同一份消息/流式/瞬态/WS**；工作流画布预览传独立 runtime（`preview: true`）
- **职责切分**：useAssistant/useEmployeeChat 退化为门面（对外 public API 一字未改，UI 组件零改动）——实例只剩「激活指针 + 线程列表 + 表单态」，会话级状态（messages/streaming/waiting/running/nodeTraces/queuedCount…）全在 runtime 会话对象里，门面用 computed 代理激活会话
- **每会话独立**：WS（引用计数，最后一个窗口解持才关；断线 2s 重连）+ 看门狗（waiting 且 45s 无事件才 resync，空闲零开销）+ 重连即对账（`resync`：未见消息 ∨ turn_active=false ∨ 404 = 终态采纳）。LRU 上限 8 会话，只驱逐「无窗口持有 + 空闲」的
- **FIPA-lite 信封**：`AssistantHub.broadcast` 每帧注入 `thread_id`（显式带的以调用方为准），客户端按会话线程校验，迟帧/错帧丢弃——单点改在 assistant_hub 覆盖全部 ~25 个广播点。**需后端重启生效；客户端对无信封旧帧兼容**
- **切换语义**：`runtime.setThread` 换线程即清瞬态（上一回合的流式/等待态绝不带进新线程）；面板关闭=解持冻结（状态保留，重开 loadThreads 补 attach，onopen 对账）；回合服务端继续跑，回来靠 resync 采纳
- **群聊路由**：群线程不带 colleague_role_key，AssistantPanel 的 openGroup/历史恢复显式传 `selectThread(id, { kind: 'group' })`；dm 历史恢复传 `{ kind: 'dm', roleKey }`
- **布局分组**：同一 useAssistant 实例只在窗口内部共享指针——门户和浮动窗各自激活各自看的会话，但底层数据同源（两窗开同角色=实时同屏）

## 输出体验（2026-08-29）

- **真流式协议 v2**（agent_react.run_stream_chat_loop）：正文由 LLM 生成期间经 `chunk` 通道逐字直推（首字即所见），工具调用走 ```tool 围栏块永不外泄；**不变量**：推给用户的全部 chunk 拼接 == 落库 answer（done 换泡内容逐字一致）。断流降级：中转断死时已流出正文保留为终答，两连空手失败才报错。旧的「回复完成后 8 字符假打字机回放」已删除。前端 `chunk`/`done` 契约零改动
- **状态显示重构**（AssistantMessageItem）：思考过程默认收起为一行「▸ 思考过程」（有思考文本才出现，点开看全程）；实时气泡永远单行——流式正文 > 状态行（呼吸点+文字，如"正在调用 catalog_search…"）> 三连呼吸点；不再出现竖排文字/空气泡
- 旧"发送前转接确认"死脚手架（pendingDispatch 卡片，浮动窗与门户两处，从未被触发）已删除

## 会话记录与上下文水位（2026-08-29，用户反馈补全）

- **会话记录浮层**（头部 🕘 按钮）：当前联系人/群的**全部会话**（进行中 + 已归档），点归档项 → `POST /threads/{id}/restore` **换位恢复**（同角色当前活跃会话自动归档，满足每角色一个活跃的唯一约束）；行内 ✕ → `purge` **硬删**（软删=再归档，用户感知不到，故删除一律硬删连消息物理清；删当前会话自动开新会话补位）
- **上下文水位**（头部徽标）：`GET messages` 返回 `context_usage`（按历史字符数 ×0.6 估算 token，上限按 64k 显示）；<70% 蓝 / ≥70% 黄 / ≥90% 红，提示何时该开新对话；**自动压缩（compaction）未做**，超限前请手动新对话
- 前端：AssistantPanel 会话记录浮层（historyItems/openHistoryThread/removeHistoryThread）；useAssistant.selectThread 用 `threads.messagesFull` 并导出 `contextUsage`
- 旧"发送前转接确认"死脚手架（pendingDispatch 卡片，浮动窗与门户两处，从未被触发）已删除

## 两栏消息中心（2026-08-29 浮动窗重构，用户拍板）

- **布局**：面板加宽 390→680px；左栏联系人（团队群置顶 + 各角色，200px，窄屏缩成 64px 图标栏），右侧会话区。仅当账号可访问 **≥2 个角色**时显示左栏；**单权限账号无左栏无 @**，直接进唯一角色的 1:1
- **群聊与 1:1 是两个窗口**：群聊（未绑定同事的总助线程，`POST /threads/group-resolve` get-or-create）= @ 点名 + leader 智能转接场所；1:1（office_colleague 绑定线程）= 锁定身份，无 @ 按钮。数据层二者按 thread_kind / colleague_role_key 区分
- **新对话**：头部 `+` 按钮 = 归档当前会话（软删，DB 保留）+ get-or-create 全新会话；群与 1:1 均可。会话历史抽屉与角色切换菜单已退役（联系人制下冗余）
- 实现：AssistantPanel（view=group|dm、showContacts、startNewConversation）；AssistantComposer `members` prop 控制输入区 @ 按钮与补全浮层是否出现
- **排队可见化**（2026-09-13）：回合执行中再发的消息由后端串行排队（`_THREAD_TURN_QUEUE` 续跑）；入队/drain/停止时广播 `queue_state {depth}` → 前端 `queuedCount` → AssistantComposer `queued` prop 在输入框上方显示「已排队 ×N，当前任务完成后自动处理」蓝点徽标
- 旧"发送前转接确认"死脚手架（pendingDispatch 卡片，从未被触发）已删除

## 群聊 MVP（2026-08-29 P1）

- **@ 点名确定性路由**（最高优先级）：消息含 `@名字/@role_key` → `find_mentioned_colleague`（[ai_colleague_service.py](../../backend/app/services/ai_colleague_service.py)）直接分派，不走 LLM 判官、不落 handoff 标记（用户自己路由）；名字包含匹配，停用/不可转派不可被点名，@ 不匹配任何同事按普通文本处理
- **输入区 @ 补全**（AssistantComposer）：`members` 名册 prop；键入 `@片段` 或点 `@` 按钮弹出候选浮层（头像+名字+职责），选中插入 `@名字 `
- **通讯录**（面板角色菜单升级）：「配置团队 · N 位成员」+ 说明行；每成员显示职责一句话，行内 `@` 按钮把点名插入输入框，点行切换 1:1 私聊
- 转接仍为 leader 专属（见下节）；@ 路由不受 leader 门控限制？——受：@ 路由只在总助（群）会话生效，专业同事 1:1 会话维持锁定不换人

## 转接规则（2026-08-29 P0 定案）

- **leader 专属调度权**：`get_team_lead_role_key()`（layout.team_graph.lead_role_key，默认 assistant）。只有总助（=leader）会话才允许 AI 判断转接；leader 改为别人后总助丧失调度权
- **专业同事会话永不转接**：线程绑定同事或显式点名非 assistant 角色时锁定身份，跨域问题只口头建议
- **转接可见化**：post_message 在用户消息后落一条 `kind=handoff` 标记（leader 名义，含 LLM 判断理由），经 WS `done` 事件实时推送；浮动窗渲染为分隔线样式（.ap-handoff），专家回复带自己的头像/名字（消息级 colleague_role_key 渲染）
- **语义坑**：浮动窗线程是绑定 colleague_role_key='assistant' 的（不是空）——门控必须按「effective_role 是否 assistant」判断，不能按「是否有绑定」判断
- **技能记忆按「线程+角色」隔离**（2026-08-29 修复）：`skill_chat:{role_key}`（skill_chat.py `_mem_key`）——专家接手时是干净身份，不会复述别的角色没走完的流程（此前线程共享导致三个角色连问同一个 kp_mode 缺口，用户截图实证）；旧 `skill_chat` 裸键的存量记忆被忽略

## 智能转接（2026-08-29 起：LLM 判官，关键词规则已删除）

- 机制：总助收到未指定角色的消息时，`resolve_assistant_message_target_async`（[ai_colleague_service.py](../../backend/app/services/ai_colleague_service.py)）把**员工名册**（姓名 + 职责 = system_prompt/opening_message 前 120 字 + 技能清单）+ 用户消息交给 LLM 判断该谁接手；无合适人选/闲聊 → 总助自己回复
- 已删除：`dispatch_rules` 关键词匹配、`_rule_matches`、团队拓扑点名兜底、前端关键词规则编辑器（旧数据留在 config 中但不再被读取）
- 判断契约：`_DISPATCH_SCHEMA`（colleague_role_key/reason）；失败/超时（8s, max_attempts=1, low 档）一律降级为总助自己接，绝不阻塞消息
- 团队页签面板 = 「启用智能转接」开关 + 每员工「可被转派」开关（dispatchable，即时保存）
- **名册质量决定转接质量**：新增员工时必须写清楚 opening_message/system_prompt 里的职责描述
- 契约：`POST /threads/{id}/dispatch-preview` 返回 `{colleague, reason}`（原 matched_rule 已删）

## 页面定位

路由 `/ai-office` → 「Manage Teams」打开团队编辑抽屉（TeamManager），四个页签：**团队 / 空间 / 行为 / 员工**。团队页签自 2026-08-30 起不再提供同事编辑（成员列表仅展示，无删除入口），同事的编辑/新增/删除全在员工页签；员工页签即 EmployeeManager（员工卡网格 + 档案编辑弹窗）；「AI 角色访问权限」面板（ColleagueAccessPanel）自 2026-09-15 起独立为「员工 → 访问权限」页签。

## AI 角色访问权限面板（2026-08-29 起，自团队页签迁入员工页签）

组件：[ColleagueAccessPanel.vue](../../src/views/office/ColleagueAccessPanel.vue)（自包含：自行加载角色/用户/策略，独立「保存权限」按钮）。

### 价格可见性（按 AI 角色开关）

- 数据：`system_config.ai_colleagues.colleagues[].price_access`（bool，**默认关闭**；价格机密，须显式开启；2026-09-13 起唯一事实源，直存不再由 data_boundary 派生）
- 初始白名单：方案助手（assistant）、成本核算（cost_analyst）= 开；其余角色 = 关
- 关闭后该角色的**全链路无价格**：
  - 对话脑工具 `catalog_search` 返回数据**不含 price 字段**（模型物理上拿不到价格，无法口误泄露）
  - `query_data` 工具边界按 `price_ok` 脱敏价格列（`tool_boundary()`，execute_read 物理执行）
  - 引擎选型选项卡（model_options）不带 ¥ 金额；LLM 选型候选清单同样剥价
- 接线点：`skill_chat.handle_skill_chat_turn` 读 `colleague_price_ok(colleague)` → `_TOOL_CTX.price_ok`（工具层）+ `requirement_prompt(price_ok)`（提示词层）+ `engine_ctx.price_access`（引擎层）

### 角色访问控制（原功能迁移，存储不变）

- 数据：`system_config.ai_colleagues.access_policy`（`enabled` / `role_chat_role_keys` / `user_chat_role_keys` / `default_chat_role_keys`），解析逻辑在 [office_access.py](../../backend/app/services/office_access.py)，语义未动
- 团队页签的旧访问权限折叠面板已删除（含全部关联死代码）；「智能转接规则」面板仍在团队页签（复用 `tm-access-collapse` 样式类，注意区分）
- **清零即隐藏浮动助手（2026-09-16）**：某账号解析出的可聊 AI 角色为空时，`/api/auth/me|login` 返回 `chat_roles_allowed: false`，前端（auth store → DefaultLayout `v-if`）隐藏全局浮动「方案助手」按钮与面板——否则零角色账号仍会看到以「方案助手」兜底名渲染的死面板（发送必 403）。策略改动需重新登录或刷新后生效（随 `/me` 下发）。门户输入区（Portal AI 壳主角）**有意不**受此门控，仍恒开。

## 相关 API

- `GET /api/ai-colleagues/admin-config`（策略+配置）、`GET /manage-roles`、`GET /manage-users`
- `PUT /api/ai-colleagues/access-policy`（策略）
- `PUT /api/ai-colleagues/{role_key}`（含新字段 `price_access`，[ColleagueUpdate](../../backend/app/api/ai_colleagues.py)）

## 验证记录（2026-08-29）

- support_engineer（无价权）E2E：问在售机型 → 只报名型不报价；追问价格 → 「没有查看权限，建议联系成本核算或方案助手」
- `_TOOL_CTX.price_ok` 开/关单测：有权限含 price 字段、无权限无
- UI 保存回路：开关报价专员 → 保存 → config 落库 → 还原
- 277 backend tests / `npm run build` 通过
