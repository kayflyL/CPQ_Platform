# 更新日志

> 最后更新：2026-10-22
>
> 定位：**轻量变更索引**（接手导航）——每条 = 变更 + 根因一句 + 涉及面；细节与 why 以代码注释为准。
> 图例：🔄 撤回/纠正 · ⚠️ 破坏性/严重 · 💡 认知定论（最值得看）。

---

## [未发布] - 2026-10-23 — 问答协议（human-as-tool）：一个契约、两种发起者、三种类型、id 路由

- **背景**（用户架构裁定）：对照 Claude 的 AskUserQuestion，判定"卡"命名编码了错误的本体——发卡不是目的，**反问才是**；且系统里"向人要信息"散落四套机制（确认卡/表单卡/option_slot/开工单表单），答案路由靠 `user_text in ("确认执行","确认","取消")` 全局字符串比对。用户定调：好好设计、不敷衍、不硬编码黑盒、考虑清理/更新/重写与架构调整。
- **变更**：**问答协议 HumanQuery/HumanAnswer**（新 `human_query.py`，状态在 reasoning_state `human_query` 槽）：一个契约（载荷形状即类型——options→choice、fields→form、consent 绑定 action.tool，大脑不选模板）、两个发起者（ask_user 工具=大脑发起 choice/form；调和器=系统发起 consent，R0-R4 不变量原样）、**每线程至多一个开放问题**（任务规则 12"一回合一卡"从行为规则降维成协议不变量，第二问=契约错误）、答案按 **query_id** 结构化路由（文本"确认/取消"降为兜底，匹配范围被开放问询收窄，全局串比对废除）。新 `ask_user` 工具（options 2~4 个含 recommended 机械置首/fields 1~8 个，系统自动追加 Other）；consent 问询带 action 绑定直达执行；答案结构化注入大脑（【问题已回答】带完整问题上下文——跨回合断层由协议补偿）。
- **清理**：删 `ask_user_card` 工具（规格/handler/display，tool_names 改名轨道 ask_user_card→ask_user）、删 `persist_confirm_card`/`persist_user_card`（被协议发射口取代）、删事务壳文本路由块；`_with_confirm_card`→`_with_consent_query`、carded→`query_opened`（兼容读旧字段）；defer_confirm_card→`defer_user_emission`。**前端收敛**：新 HumanQueryCard（schema 驱动单渲染器：consent 按钮/choice 单选+Other+推荐标记/form 表单），接 AssistantMessageItem 与两块聊天面板；新 POST /answers 端点（id 路由+展示副本落消息流）；旧 input_options/input_form 消息由旧组件重放（数据不迁移）。左栏：flow 规则工具名改口；宪法棘轮基线复测（transaction_turn 8、agent_tool_specs 1）。
- **验证**：全量 1021 过（2 失败均为并行会话既有）；新增协议测试（单开槽不变量/形状校验/consent 发射与幂等/ask_user 形状与校验）+ 跨步重放契约改走 hq 断言；vite 五文件编译 200；后端重启 stale:false。
- **涉及面**：`backend/app/services/{human_query 新,transaction_turn,agent_write_confirm,agent_tool_handlers,agent_tool_specs,agent_tool_display,skill_tools_write,colleague_turn_io,tool_names}.py`、`backend/app/api/assistant.py`（/answers 端点）、`frontend/src/components/assistant/{HumanQueryCard 新,AssistantMessageItem,AssistantPanel}.vue`、`frontend/src/{api/assistant.ts,views/office/OfficeColleagueChatPanel.vue}`、`backend/tests/{test_agent_write_tools,test_transaction_engine,test_constitution}.py`、DB flow 127 规则改口。
- 💡 **定论**：① 命名编码本体论——"卡"立物上、"问"立行为上；问的形式可以变介质（语音/推送），授权必须持久——**问（ask）和准（consent）是两个言语行为，一个协议两种语义，不混谱系**；② human-as-tool 的可取处是契约化（结构化问、结构化答、id 路由），不可取处是阻塞式回合（对面是程序员不是客户——异步+持久化才是业务聊天正解，只抄契约不抄同步）；③ 行为规则能降维成协议不变量时就降维（一回合一问），机制保证的不再靠大脑自觉。

## [未发布] - 2026-10-23(凌晨) — 确认闸调和器：四守卫收敛为一个状态机 + 一条定理

- **背景**（用户实测 21:57 + 架构裁定）：①大脑说"请在卡片点确认"但卡根本没人发——识别步的 import 被分流纪律降级为仅解析预览（analysis_only），create 成功后指针**静默推进**到落位步，大脑对推进零感知、拿旧结果承诺没人发的卡（库里实锤：零 input_options 消息、全库零待确认记录）；②用户裁定：四个机械守卫散落各处=逐层打补丁，要整体设计；prompt 注入方案被否（服从是概率的）。
- **变更**：**卡的存在性不依赖大脑纪律——一条定理四条不变量，一个调和器执行**。R1 投影幂等：一份待确认记录至多一张卡（carded 标记，昨日已落）；R2 投影完备：有记录必有卡、必在本轮答案后（吸收"facts 循环落卡"+"回合末兜底网"两个散点，`_emit_ready_cards` 幂等发射）；R3 记录完备：(a) 跨步——工具降级带 `deferred_by_step` 声明 → 轮壳推迟账本记账（write_confirm 桶新 deferred 键，跨回合存活）→ 指针推进后**原参数重放**，工具在所属步自己走确认闸出卡，重放一次即清账（吸收原"闸步补推"管不了的跨步断层）；(b) 停闸——闸步无记录时合法反问（needs_input/user_card）不逼重调，其余强制重调一轮，仍无 → 壳发机械话术"确认操作没有生成成功"（假承诺→真报错）；R0 记录产生只在工具闸内（写语义归工具，生命周期归调和器）。R4 时序：卡必在本轮答案后（defer_confirm_card 闸口不变）。
- **清理（三净：代码删净/测试改写/文案清除）**：删 `consume_if_confirmed`（app 零调用的遗留兼容口）及其测试；删 facts 循环落卡块、回合末兜底网块、`confirm_box` 计数、【待确认就绪】指令（措辞纪律迁左栏：flow 127 规则新增【确认卡就绪】）；`persist_confirm_card` 的 tool 改必填（删无工具兼容分支）。**治理**：事务家族 7 个文件（transaction_turn/engine、agent_write_confirm、skill_tools_write、delivery_app/core、skill_memory）补进宪法棘轮 MECHANISM_FILES（实测基线 7/0/0/1/0/1/0 封顶）——此前整族游离在扫描外，指令文案在代码里攒了一路没人拦。
- **验证**：新增契约测试×4（跨步重放→卡在答案后落库、重放失败清账、闸步强制重调→机械话术、needs_input 合法反问不逼重调）+ 账本/过期/漂移重写×6；全量 1021 过（2 失败均为并行会话既有：data_range_follow、report_pdf）；后端重启 stale:false；flow 规则在线确认。
- **涉及面**：`backend/app/services/{transaction_turn,agent_write_confirm,colleague_turn_io,agent_tool_handlers,skill_tools_write}.py`、`backend/tests/{test_transaction_engine,test_agent_write_tools,test_constitution}.py`、DB rules.reasoning_flow v160（manual_rules +【确认卡就绪】）。
- 💡 **定论**：① 卡片这类 UI 事实的存在性必须由机制保证，大脑只读事实写判断，从不做"触发投影"的开关——prompt 是概率组件，关键路径一环都不押；② 同一族故障的多个补丁是没写出定理的信号：先收敛成状态机+不变量，新故障映射条款修条款，不再长第五个散点；③ 跨步语义（识别步只解析）必须配跨步交接机制（推迟账本+重放），否则纪律本身制造断层。

## [未发布] - 2026-10-22(晚) — 确认卡投影去重 + 报价工作台内嵌弹窗宿主层级

- **背景**（用户实测）：①同一轮连出两张一模一样的"提交成本表并转报价"确认卡（库里实锤连着两条 input_options）②产物卡里报价工作台的「更多→分享」弹窗开了看不见（被产物卡弹窗压住）。
- **变更**：① **卡=待确认记录的投影**：`stage()` 记录加 `carded` 标记（同参重发沿用、参数漂移归零重发）；`persist_confirm_card` 带 tool 查 `card_already_out` 去重、落卡成功 `mark_carded`；三个调用点全透传工具名（回合壳事实循环/兜底网补卡/工具聊天路径 `_with_confirm_card`）。兜底网的跨回合重复补卡（旧卡还在屏上又补一张）一并堵住；记录存在但卡真丢（carded=false）时兜底网照常自愈。② **QuoteWorkbench 加 `hostZIndex` prop**：内嵌 5 个模态（分享 ShareDialog/外发审批 OutboundApprovalModal/转交/发送/配置明细 ResponsiveModal）统一接 `:z-index="hostZIndex"`（前两类经单根 attr 透传到内部 a-modal）；ArtifactCard 承载处传 2100。与既有 popup-container 同构：一个 prop 修一类，原生平宿主（报价工作台页）不传=行为不变。
- **验证**：新增单测×2（投影语义/落卡去重含旧语义兜底）；写工具+事务引擎+轮壳+交付公共 5 套件 110 过；工作台页实机冒烟（workbench 正常渲染）；后端重启后 `/build-stale` stale:false。
- **涉及面**：`backend/app/services/{agent_write_confirm,colleague_turn_io,transaction_turn,agent_tool_handlers}.py`、`backend/tests/test_agent_write_tools.py`、`frontend/src/components/opportunity/QuoteWorkbench.vue`、`frontend/src/components/assistant/ArtifactCard.vue`。
- 💡 **定论**：① 卡片这类 UI 事实和状态一样必须"在库投影"——大脑重复调用是常态不是异常，发卡口的幂等性要机制保证，"调用方自去重"等于没人去重；② 高层级宿主复用生产组件时，组件内嵌弹窗的层级和下拉挂载点是一类问题，一个 prop 一次修完，别等用户逐个发现。

## [未发布] - 2026-10-22(傍晚) — 实测四问题批次：L6 配置级口径 + 重导护栏 + 会话输入卡 + 闸步纪律

- **背景**（用户实测，已确认打在新代码上）：①确认卡迟到+同段话陈述两遍 ②缺价只出文字没输入卡 ③大脑不知道 L6=整机一口价，要 8 行逐行价 ④"我填好了"被理解成重导→新草稿抹掉人工补价→死循环。
- **变更**：① **L6 配置级口径对齐页面**（用户定："L6 是整体价格，8 行只是明细展示"；页面存储=配置级 `l6_cost`，portal 成本核算/报价提交均读它）：缺价探针 `_missing_prices` 的 L6 改按配置数（l6_cost 缺=该配置缺），不再逐行数；`set_cost_prices` 支持 `[{config_name, l6_price}]` 写配置级；案台缺价文案改"L6 整价 N 个配置"；set_cost_prices 规格/展示文案同步。② **重导三层护栏**（`tool_import_cost_sheet`）：同商机已有未归档草稿 + 不带 sheet_id → 已有补价则拒（reimport_guard，错误带 sheet_id/reset 指引），无补价自动原地更新（不再起 -v2 挤掉探针在读的草稿）；显式 sheet_id 原地更新若比现存草稿少填价 → 拒（wipe_guard，需 reset=true）。新增 `delivery_core.latest_cost_sheet/filled_price_count/get_cost_sheet`。③ **会话输入卡 `ask_user_card`**（用户定调"AI 调模板发卡"）：大脑定时机与内容（type=input_fields，1~8 个字段），系统机械弹出与渲染（`persist_user_card`，kind=input_form）；用户提交以「label」=值 文本回流对话。后端 spec/handler/display/工具全链 + 前端 `InputFormCard.vue`（提交后塌已答行）接入 AssistantMessageItem 与两块聊天面板（interactive/answered 判定纳入 input_form）。flow 127：place/derive_cost 白名单 + ask_user_card，规则追加【缺价补价】（L6 按配置一个数）与【重导纪律】（补过价禁重导）。④ **闸步纪律**（治"说了点确认卡但卡没出"）：指针停在 gated 步、无待确认记录、本回合没落过卡 → 机械补推一轮（注入【确认闸纪律】指令，最多一次）；**待确认去重**（卡已弹出后大脑再被唤醒时注入【待确认就绪】勿重复陈述）。⑤ **应用日志落文件** `backend/logs/app.log`（5MB×3 轮转）——bat/cmd 启动的服务排障不再依赖窗口现场。
- **验证**：两套件 78 过（新增：reimport 拒绝/自动原地、L6 配置级回写、缺价探针配置级、ask_user_card 校验、闸步 nudged 契约×2）；既有 price_ready 测试按新口径更新；vite 编译新组件 200。后端整体重启后 `build-stale` 自检通过。
- **涉及面**：`backend/app/services/{delivery_core,delivery_app,skill_tools_write,transaction_turn,agent_tool_specs,agent_tool_handlers,agent_tool_display,colleague_turn_io}.py`、`backend/app/main.py`、`frontend/src/components/assistant/{InputFormCard.vue 新,AssistantMessageItem.vue,AssistantPanel.vue}`、`frontend/src/views/office/OfficeColleagueChatPanel.vue`、DB rules.reasoning_flow v159、`一键启动.bat`（[1.5/3] 源一致性体检步）、`.scratch/{flow_update_20261022b,fix_bat}.py`。
- 💡 **定论**：① 卡分两类定终身——写动作的影子卡（确认/产物）永远工具机械发，大脑只许在工具结果里看到"卡已就绪"才陈述；会话输入卡走 `ask_user_card`（大脑调、系统保底）——"AI 调模板"与"卡不靠自觉"不矛盾，边界在有没有写动作语义；② 价格口径必须与页面同源同粒度（L6=配置级 l6_cost），探针粒度错配会让大脑理直气壮地问错问题；③ 覆盖人工输入的写操作必须显式声明（reset=true），"帮用户刷新一下"式的重导是死循环发动机。


- **背景**：用户实测 ①传成本表后方案落位仍绿（skip_if 命中但没配文案→回合壳拿文案真假当判定广播成 done）②点确认后只出预览不落草稿、四连卡（resolve 先销记录后执行，任一步失败即永远只出预览；--reload 静默失效又把内存里的待确认记录抹掉）。用户定调"从根子上解决，别装样子修补表层"。
- **变更**：① **状态单一事实源**：`transaction_engine.node_states()/state_events()` 唯一计算口（skipped 按 skip_if 条件本身、与 skip_note 文案无关；steps 带 `skip_note` 顶层字段），回合壳广播/画布渲染/`skill_memory.task_state` 全部只搬运；前端 `applyTaskState` 吃 `statuses` 权威载荷、TaskStepper 加 skipped 样式；契约单测锁广播载荷（`test_turn_broadcasts_skipped_not_green`）。② **确认三连**：待确认记录落库（reasoning_state `write_confirm:assistant` 槽，活过 --reload/重启；`_STORAGE="memory"` 供测试）、`resolve_confirmed` 不再销记录 + 成功才 `consume`（失败重试直达）、**确认卡直达执行**（轮壳 `_execute_pending` 按 staged 记录直调工具 handler，结果并入本迭代 facts 走与大脑调用同一份记账，大脑只陈述；不适配时回退带 confirm 重调）。③ **分支一等公民**：守卫上边（`edge.guard {flag,equals}`）、`branch_reach` 图遍历（可达=经过/不可达=skipped/守卫未定=undecided 不提前灰）、指针与 node_states 走图（菱形汇聚天然正确）、旗标声明化（`graph.flag_rules` + `$result.x` 引用，delivery_app 手写 `_flags_from_facts` 删除）、`_normalize_graph` 透传 guard/flag_rules + upsert 防老客户端剥键（沿 entity_binding 先例）。DB v155：identify→双落位边上守卫、flag_rules 五条、节点 skip_if 补丁摘除。④ SkillStudio 画布边显示 `lane=cost` 标签 + 节点抽屉「出边分流条件」可视化编辑（`outgoingEdges` prop + `set-guard` 事件）。⑤ 顺带修 `delivery_core` 缺 logger（自动绑定路径 NameError）+ 尾部不可达重复块。
- **验证**：全量 1008 过 / 3 失败均非本轮（constitution=并行会话 04:04 的 data_range_follow、select_model 候选池、report_pdf 渲染——均属并行会话领域）；新增 skipped 契约×2、直达执行契约、branch_reach/node_states/声明旗标×3；DB 双分流场景复核（成本链：place_bom/derive_cost=skipped，方案链对称，submit 双路汇聚 done）；实机画布 8 节点 + 边标签 lane=scheme/lane=cost + 抽屉守卫编辑区带值渲染。⚠️ 排障实锤：8000/8010 两个 --reload worker 自 13:28/13:34 起未随任何存盘重启（代码改到 15:12+）——reload 静默失效已升级为**常态假设**；8010 被提权隐藏进程占答（进程表不可见、taskkill 无效），已弃用 8010，唯一服务口=8000。
- **涉及面**：`backend/app/services/{transaction_engine,transaction_turn,agent_write_confirm,skill_tools_write,delivery_app,delivery_core,skill_memory}.py`、`backend/app/repository/reasoning_flow_repo.py`、`frontend/src/{composables/assistantChatWs.ts,components/assistant/TaskStepper.vue,views/admin/reasoning/{SkillStudio,ReasoningNodeDrawer}.vue}`、`backend/tests/{test_transaction_engine,test_agent_write_tools}.py`、DB rules.reasoning_flow v155、`.scratch/migrate_branch_20261022.py`。
- 💡 **定论**：① 状态语义全链只允许一处定义（引擎），广播/画布搬运不推导——单测锁的必须是"层间契约"（广播载荷）而不是层内函数，否则测对了函数、病从层缝漏过去；② 用户意图的通路不该经过概率组件——确认=服务端按存证直执，参数转述/摘要匹配/抢跑自愈那套复杂度全是为"经大脑转述"这个原始设计擦屁股；③ 分支的合法形态升级：条件上边+图遍历，不可达=跳过，旗标映射进流程配置——**建新分支流零代码，画出来即所得**；④ 状态在库不是口号：任何活过回合的东西（含确认存证）放进程内存=给 --reload 和并行会话递刀。


## [未发布] - 2026-10-22(上午) — 案台跟随绑定 + 会话续跑 + 确认直执引导 + 跳过态灰色（部分验证未收口）

- **变更**：① **案台跟随绑定（设计总纲落地）**：`delivery_core.resolve_opportunity` 命中即把会话绑定跟随过去——工作流是在操作商机详情页，工具摸到哪个商机案台就是哪个商机；此前案台身份只认 create_opportunity 写的绑定副通道，大脑按页面语义按名解析/归档就死锁在识别步（step_key 护栏把每次落位降级成预览，用户看到"始终仅解析预览"）。② 事务回合开头持久化 SKILL_SESSION_ACTIVE（防续跑回退需求分析）+ 确认卡直执引导（用户点确认/取消时轮壳把 staged 参数直接塞给大脑重调/机械清记录，执行不再押在大脑自觉）+ 分流跳过节点广播 `status:"skipped"`（画布灰虚线，不再冒充完成绿）。③ `_eval_completion` 新增 all_of/skip_if 算子（见上条）。④ 修复 SkillStudio.applyNodeState 的 `??` 残影（事件明确 null 也保留旧产物——芯片永远删不掉的实底）。
- **⚠️ 未收口**：真路径全链验证（直驱 API+真附件）到第 2 轮起**仍漂进需求分析引擎**（agent_fill/线索登记问答；skill_chat 槽被 requirement_analysis 占用）。已落的事务回合会话持久化未生效（skill_session=null、日志零痕迹——**应用日志不落 stderr，排障盲飞**），根因未钉死：疑点=会话保存代码已确认在文件且服务已重载，但 turn-1 未产生预期写入；下一会话第一件事：给 app 日志接可见 handler 后复跑 verify_chain.py（.scratch），钉死续跑分发。另：并行会话/用户侧多次与我在 8000 端口互踩（10:07 又见第三方起的进程），改后端后务必核对 worker mtime。
- **涉及面**：`backend/app/services/{delivery_core,transaction_turn,agent_write_confirm,skill_tools_write}.py`、`frontend/src/views/admin/reasoning/{SkillStudio,ReasoningNodeVf}.vue`、`backend/tests/`。
- 💡 **定论**：交互可靠性三支柱全部要机制化——卡的存在（兜底网）、确认的执行（直执引导/参数直塞）、画面的真实（键存在即覆盖）；"大脑应该会这么做"不是设计。

## [未发布] - 2026-10-22(凌晨·再续) — ⚠️ 确认卡三类失效机制性封死 + 画布产物残影根除

- **变更**（用户实测"说了请在下方卡片确认但卡不来"+"芯片挂在识别节点删不掉"）：① **画布产物残影根除**：`SkillStudio.applyNodeState` 的 `state.artifact ?? n.data?.artifact`——事件明确带 `artifact: null`（本次无产物）时 `??` 保留旧产物，**任何一次运行的产物一旦挂上就永远删不掉**，后端改对用户也看不见（"说了好多遍不改"的实底：不是没改，是清除被前端吞了）。改为键存在即覆盖（null=明确清除）。② **确认门抢跑自愈**：大脑在上一段节点就把"请在卡片确认"说完（陈述跑在闸前面），轮到落位步直接带 `confirm=true` 首调——原闸报"未找到待确认记录"了事=没 stage、没卡、用户等一张永远不来的卡。改为 `confirm=true` 无待确认记录时**原地降级为出预览+出卡**（stage 带预览存证），绝不执行；执行仍要求 stage 后有真实用户消息——安全性不变，抢跑路径收敛到卡。③ **回合级兜底网**：回合结束时还有待确认记录而本回合一张确认卡都没落过 → 从 stage 记录取存好的 preview 机械补卡——卡的存在从此不依赖大脑的叙述纪律。④ **回合不再无声死亡**：`_drive_steps` 未捕获异常原先直接吞掉任务（文本已落、卡没落、无暂停态——用户面对一段"请在下方确认"的孤儿陈述），现在落一条可见消息后照常走兜底网+暂停态。⑤ `agent_write_confirm.stage()` 增加 preview 存证（记录第 5 位），新增 `pending_previews()` 只读取回。
- **验证**：后端全量 1003 过 / 2 失败均为既有问题（select_model 候选池数据、report_pdf 渲染，目标文件 git 零改动）；新增抢跑自愈测试×2（import/margin confirm 首调降级+重调执行）；真文件真脑 E2E 复现全链（见下轮报告）。⚠️ 并行会话 04:04 改了 `data_range_follow.py` 引入 `_EXTRACT_PROMPT` 触发宪法红灯（test_no_code_side_fallback_prompts）——非本会话改动，留给该会话处理。
- **涉及面**：`backend/app/services/{agent_write_confirm,skill_tools_write,transaction_turn}.py`、`frontend/src/views/admin/reasoning/SkillStudio.vue`、`backend/tests/test_agent_write_tools.py`。
- 💡 **定论**：交互可靠性不能依赖大脑的叙述纪律——卡要由机制保证存在（自愈+兜底网），画面要由事件保证真实（键存在即覆盖，`??` 兜底=残影永生）。另：`uvicorn --reload` 本次排障期间累计第 4/5 次静默失效，且一次内联 PowerShell 杀进程失败造成过 4 分钟双活——改后端后核对 worker mtime 是铁律，杀进程用脚本文件不用内联命令。

## [未发布] - 2026-10-22(凌晨·续) — 🔄 拆回双落位节点：分流旗标 + skip_if 短路（分支在执行层成立）

- **变更**：用户否定合并方案（"成本和方案节点合起来不合理"）+ 点破"即使画了分支也是假分支"。内核 `_eval_completion` 增加 `all_of`（双条件）与 `skip_if`（旗标短路）两个纯配置算子 + `skip_note`（短路节点的如实说明）；`flags_from_facts` 写**分流旗标 lane**（import_cost_sheet→cost、import_bom_scheme/derive_cost_from_scheme→scheme，解析预览与落位都算判定）；两个落位工具加识别步护栏（step_key=identify 强制只预览/拒调——机制保下限，大脑越不过）。DB v141：拆回 方案落位（any_of [scheme] + skip_if lane=cost）/ 成本落位（slot sheet.price_ready + skip_if lane=scheme）；识别步完成条件={"all_of": ["opp", "flags.lane"]}（没做分流判定指针不前进——旗标在库里，不靠大脑自觉）；**边恢复真分支**：identify→双落位、方案落位→库价推导、成本落位→提交直连。执行序仍是节点序列（指针），但错误链路节点被配置短路并显示 skip_note（"本链为xx链，不经过xx落位"）——分支从画布装饰变成执行事实。
- **验证**：全量 981 过 / 2 个既有失败（test_select_model_tool 候选池、test_report_pdf 渲染，均与本轮无关，目标文件 git 零改动）；新增 `test_eval_completion_all_of_and_skip_if`。⚠️ `uvicorn --reload` **第四次**静默失效——已整体重启（3:49:20 起，HTTP 200）。
- **涉及面**：`backend/app/services/{transaction_engine,transaction_turn,delivery_app,skill_tools_write}.py`、`backend/tests/test_transaction_engine.py`、DB rules.reasoning_flow v141。
- 💡 **定论**：内核执行=节点序列上的指针（案台原则不变），"分支"的合法形态=**旗标 + skip_if 短路**：判定落在库（lane 旗标），节点配置声明"本链不经过我"，画布边与执行行为第一次一致。识别步的完成条件挂 `flags.lane` 是关键——分流判定从"大脑的自觉"变成"过不去的闸"。

## [未发布] - 2026-10-22(凌晨) — 交付流八项实测修复：落位合流、先看后落、缺价闸、卡内弹层治理

- **变更**（用户实测 8 问题逐项）：① **方案落位+成本落位合并为「落位」节点**（DB 图 v128：identify 摘掉两个落位工具只管判定+建档+解析预览；place=双工具双卡 import_cost_sheet/import_bom_scheme，完成 any_of [scheme, sheet]；边改 identify→place→derive_cost 单链，方案表链在 derive_cost 落成本、成本链自动跳过）——解析卡从此必然落在落位节点。② 画布产物查看去嵌套：NodeArtifactModal 不再内嵌 ArtifactCard auto-open（双层弹窗、外层空壳的实底），产物卡类由 ArtifactCard 自带 z-2000 弹窗顶层直挂（`:key` 按卡引用重建）。③ **节点摘要各自持久化**：状态槽保留键 `node_notes`（step→本步事实摘要），回合开头各节点各念各的、没存过的显示「本步未单独执行」；`_desk_summary` 整桌复述删除（三节点一个模样的实底）。④ **先陈述后弹卡**：产物卡装配与落库分离，落库统一在本步答案广播之后（确认卡随后）；**import_cost_sheet 两阶段化**（落库段过 _confirm_gate：首调=解析预览+确认卡，confirm=true 才落草稿，先看后落）。⑤ **缺价闸（目标层字段策略驱动）**：place/derive_cost 目标层 artifact.fields 增列级字段 `l6_price/kp_price`（ask=true，画布可改可关）；案台探针按策略现算 `kp_missing/l6_missing/price_ready`（delivery_app._latest_cost_sheet+_missing_prices）；完成条件 place→any_of [scheme, sheet.price_ready]、derive_cost→sheet.price_ready（DB v129）；案台事实行显示缺价明细；新工具 **set_cost_prices**（聊天回价→按 配置名+Catalogue 回写 base_price，页面同源保存、保留 bom_scheme_id 挂接；spec+display+handler+白名单齐）。⑥ 报价单卡只留最终一张：submit 规格卡删除，margin 卡改名「最终报价单」。⑦ 卡内弹层治理：ShareDialog 抬 z-2100；QuoteWorkbench 新增可选 `popupContainer` prop（a-dropdown 挂载容器，详情页不传=零变化），ArtifactCard 传 closest('.ant-modal-content')；上游成本改 v-model 真双向（原传死值 false 点开没反应）；点报价行=先关卡片弹窗再跳报价工作台（与详情页点草稿行同语义；原跳转发生在弹窗底下看似没反应）。
- **验证**：后端全量 979 过（3 个既有失败与本次无关：test_select_model_tool 候选池数据、test_report_pdf×2 渲染产物，目标文件 git 零改动）；宪法棘轮合规（新 spec 描述按词表重写）；vite 转译三组件 200（修了一处删头导致的 v-else-if 孤儿）。⚠️ `uvicorn --reload` 第三次静默失效（worker 2:17 未随 6 次保存重启）——杀 worker 后父进程未重生，改用 Start-Process 后台整体重启（reloader 63988/worker 64564，3:27 起）。
- **涉及面**：`backend/app/services/{transaction_turn,skill_tools_write,delivery_core,delivery_app,agent_tool_specs,agent_tool_handlers,agent_tool_display}.py`、`frontend/src/components/assistant/ArtifactCard.vue`、`frontend/src/components/opportunity/{QuoteWorkbench,ShareDialog 无改动}.vue`（QuoteWorkbench+ArtifactCard+NodeArtifactModal）、`backend/tests/test_agent_write_tools.py`、DB rules.reasoning_flow v129（备份 `.scratch/delivery_flow_backup_20261022_premerge.json`）。
- 💡 **定论**：①「哪些列必填」是目标层字段策略的事（fields[].ask 三档），缺价闸=策略驱动的完成探针（sheet.price_ready 现算），代码里不出现第二套"缺价"配置；② 卡片是工具的属性但**弹出时机是轮壳的纪律**——先陈述后弹卡、确认贴输入框；③ 高层级宿主弹窗（z-2000 产物卡）必须给内部生产组件传 popupContainer，否则 dropdown 默认 z-1050 全部"开了看不见"。

## [未发布] - 2026-10-22(凌晨·前段) — 确认重放宽容匹配 + 节点输出摘要显示 + 等待态胶囊

- **变更**：① `agent_write_confirm` 消费匹配升级：严格摘要之外退化**宽容匹配**（staged 的键在重放中都在且归一相等；staged 空值键缺失=等价；字符串/数值形态互换认等价），模型确认后重放参数漂移不再假性失配——治"用户点了确认、系统又要求确认一遍"（用户实测确认后重复预览+重复出卡的实底）。失配**不再销毁记录**（staged_args 保留自纠），过期才清。② 画布节点卡输出块显示条件 `runtimeOutput` → `runtimeOutput || runtimeSummary`——连带过关步骤的 done 只有案台摘要没有 output 值，原先整块连摘要一起被藏（用户实测中间三节点无输出物的实底）。③ `pipeline_waiting` 前端 phase 'running'→'paused'：带 pause 事实=在等人的事实，胶囊显示「中断在 xx · 等待你」，不再无限计时假跑（用户实测"卡在第 6 步"的实底；语义变更：需求分析等反问时同样显示暂停态）。④ 案台报价单 version 去 'v' 前缀（治确认卡里 "vv1"）。
- **验证**：后端 69 测试绿（新增 `test_confirm_loose_match_tolerates_drift`：漂移命中/值变仍拒且记录保留）；vue-tsc 0 错误；真脑 E2E（真实成本表）：产物卡×3 + 确认按钮卡×1 落库可见。
- **涉及面**：`backend/app/services/agent_write_confirm.py`、`backend/app/services/{delivery_app,transaction_turn}.py`、`frontend/src/composables/assistantChatWs.ts`、`frontend/src/views/admin/reasoning/ReasoningNodeVf.vue`、`backend/tests/test_agent_write_tools.py`。
- 💡 **定论**：确认闸的信任边界在「staged 的关键值没变」，不在「大脑逐字节重放」——按值等价匹配既保安全（换参数仍拒）又消灭假性失配的重复确认循环；失配时保留记录是自纠的前提。

## [未发布] - 2026-10-21(晚) — 交付链成果卡落地 + 行为纪律（真实成本表真脑验证通过）

- **变更**：① DB 配置（原配置已备份 `.scratch/delivery_flow_backup_20261021.json`）：6 节点 artifact_card（成本落位/方案落位/库价推导→成本表卡、提交/加价→报价单卡、出件→分享卡；**identify 也挂 import_cost_sheet 卡**——大脑常在识别步就把表落了，卡必须挂在工具实际跑的节点）；identify 目标层 fields 补 ask 开关（customer_name/sales_person）；**output.view ask=false**（分享视角反问是这条配置驱动的，按口径改默认 internal 不问）；左栏规则重写（收尾禁「需要我帮你…吗」、开工单参数=已确认口径直接执行、确认卡由系统弹不手抄文本、解析如实转述）。② ⚠️ 修 `load_flow_rules` 只认 dict 形态 artifact_card——**列表（多卡合法形态）被丢成 None 导致永不发卡**（此前"做过又看不到"的实底之一）+ 回归测试。③ 连带过关步骤的 node_trace done 带案台事实摘要（`_desk_summary`，治"节点只有完成勾没有输出内容"）。④ 步骤发过产物卡 → node_trace.artifact 挂卡，画布「输出物」经 NodeArtifactModal 复用 **ArtifactCard**（新增 bom_scheme 分支=SchemeEditor 可编辑保存；autoOpen 供宿主直开弹窗）。⑤ 核实确认按钮卡机制一直正常（input_options 落库/渲染/点选全通），用户实测未见是大脑手抄文本卡+旧规则混淆——规则已治。
- **验证**：后端 38 测试绿；vue-tsc 干净；真脑 E2E（真实成本表×多轮，`e2e_skill.py --scenario` 带附件/应答队列）：产物卡×2 + 确认按钮卡×1 落库可见，重复提交被"已办过"拦住，权限拦截如实转述。
- ⚠️ **教训**：`uvicorn --reload` 会**静默失效**（worker 自 19:45 未重启，晚间代码改动全部没加载）——改后端代码后必须核对 worker 进程启动时间与文件 mtime，必要时杀 worker 让父进程重生或整体重启。
- **涉及面**：`backend/app/services/{transaction_engine,transaction_turn}.py`、`frontend/src/components/assistant/ArtifactCard.vue`、`frontend/src/views/admin/reasoning/NodeArtifactModal.vue`、`backend/scripts/e2e_skill.py`、`backend/tests/test_transaction_engine.py`、DB rules.reasoning_flow/reasoning_node_config（交付流）。
- 💡 **定论**：产物卡三件套=「节点配置 artifact_card（哪个工具→哪张卡，dict/list 皆合法）× 工具事实（refs 只存 id）× 生产组件查看器（ArtifactCard 容器）」——前两件纯配置、第三件已通用；"看不到卡"先查配置是否真进生效集、再查 worker 是否真加载了新代码。

## [未发布] - 2026-10-21 — 前端设计文档归组更名（docs/前端设计/）

- **变更**：`docs/Frontend_Style_Guide.md` → `docs/前端设计/视觉风格指南.md`；`docs/设计规范.md` → `docs/前端设计/布局与用法规范.md`；活样张 `docs/prototypes/设计规范.html` → `docs/prototypes/布局与用法规范.html`。两文档分工不变（前者=材质层：颜色/玻璃/投影/动效；后者=用法与理由：间距/字阶/布局/组件决策），归组到一个目录 + 文件名按层自述。同步更新全部引用：CLAUDE.md 权威顺序链与设置卡条目、frontend-pages/README 规范指针、Principles.md ⑩、商机详情页文档、tokens.css 两处注释、两文档互链、样张标题与 tokens.css 相对路径。
- **根因**：两文档分居 docs 根目录且一英一中，文件名看不出"材质 vs 用法"分工，检索时必须点开才知道看哪个；"设计规范"一名还与样张 html 撞名。
- **涉及面**：仅文档/注释路径，零代码行为。

## [未发布] - 2026-10-21 — 交付事务流接入需求分析同款过程事件（试运行实时输出物/进度）+ 试运行放开附件上传 + 试运行开工单

- **变更**：① `transaction_turn._run_transaction_turn` 补发三段过程事件，词汇与需求分析引擎完全同形——turn 开头 `pipeline_start`（全步骤骨架+标题=技能名，随后按案台补发已过关步骤的 `node_trace done`）；每步入口 `node_trace running`、步后 `done`（指针前移=完成，携带 `_fact_bits` 工具事实摘要；一步工具连带过关的后续探针由 `_emit_done_if_passed` 补发 done，防任务条漏标）；停在本步等用户（反问/答疑/确认闸/920s 超时）发 `pipeline_waiting`+pause 事实（approval/brain_ask/turn_timeout）。dispatch 透传技能名做任务条标题。**前端零改动**：SkillStudio 画布节点高亮/输出物、聊天任务条计步、中断点胶囊全部复用既有事件消费。② `AssistantPanel` 输入框 `allow-attach` 不再禁预览模式（原 `:allow-attach="!preview"`）——试运行线程是真线程，上传（`POST /threads/{id}/attachments` 落会话暂存）与 `attachment_ids` 随消息绑定本就与入口无关；交付工作流试运行靠它传成本表/方案表。③ **试运行开工单**：预览面板按画布当前工作流常驻同款「待发起」装填条（与正式聊天同一操作逻辑：**不自动弹表单**，点条上「填写开工单」才弹 `launch_form` schema 的表单；跳过直接打字发送同义，首条发送后隐条，重置测试恢复）；提交=【开工单】结构化首条+附件走既有通道（preview 入口）；后端 `transaction_engine.desk_complete`（纯探针）+ `dispatch_flow_turn` 边界判定——案台交割完毕（全探针通过）时同线程再发自动干净重开（fresh 同义），链中绝不重开。新增回归 `test_turn_broadcasts_pipeline_events`、`test_desk_complete_boundary`。
- **根因**：交付转报价与需求分析共用 SkillStudio/抽屉/节点卡组件，但事务轮壳只广播 thinking/chunk/tool_trace，从不发 node_trace 系事件——试运行时画布全灰、无输出物无进度（用户观察"失去了本该有的特性"的实底：不是组件重写，是事件协议没接）。附件闸是 2026-09 预览只为需求分析文本输入设计的遗留；开工单缺口同源——交付流的正式入口是「+」装填（启动表单+fresh 干净重开），试运行面板只有裸输入框，既没表单也没 fresh 语义（同一预览线程跑完一链后再发会停在 complete 空转）。
- **验证**：后端 78 测试绿；浏览器实测：工作室打开交付转报价 → 📎 出现 → 页内注入真实 xlsx → chip 上传完成 + `POST .../attachments 200`；打开仅显示「待发起」装填条不弹窗，点「填写开工单」弹出同张表单（成本表/方案表*、客户名称*、归属业务*、加价率%），× 关闭后装填条仍在、可直接发送，控制台零报错。
- **涉及面**：`backend/app/services/transaction_turn.py`、`backend/app/services/transaction_engine.py(desk_complete)`、`frontend/src/components/assistant/AssistantPanel.vue`、`backend/tests/test_transaction_engine.py`。
- 💡 **定论**：两台运行时（推理管道/事务内核）要共用一套前端表现，对齐点在**事件协议**而非组件——`pipeline_start/node_trace/pipeline_waiting` 是画布与任务条的通用词汇，新运行时接入=补发这三个事件，零前端改动；开工单语义对齐点在**案台边界**（complete=交割完毕，再发即新单），不依赖入口标记，预览与正式装填自然同义。

## [未发布] - 2026-10-21 — 需求原文图片识别（图→文字）设计方案（仅文档，未落地）

- **变更**：新增 `docs/需求分析/01_架构与契约/需求原文图片识别-设计方案.md`（二稿）：补「图片→文字」一环——`POST /api/feed/attachments/{id}/ocr`（鉴权/存储复用 feed 端点族）+ `services/vision_ocr.py`（双协议视觉调用收口，**直接用 llm_config 主模型，AI 设置页模型连接配置零改动**，llm_client 仅加 `supports_vision` 能力档）+ 能力档案新增「多模态」探测档（乐观默认 + 实测修正，复用现有 probe 机制）+ 识别结果确认弹层（可编辑草稿追加/替换进需求原文，绝不自动提交）；结构化抽取继续走既有文字管线。无 DB 迁移、无新依赖（不引 Pillow）。
- **根因**：业务需求以邮件贴图高频到达，纯图附件对文字抽取/规则词表/AI 分析不可见，且手敲截图数字易错；现状粘贴截图进附件的管道与文字→slots 管线均已存在，缺的只有一环。选型定论：多模态大模型而非传统 OCR（中文截图效果 + 界面噪音过滤，且平台已有双协议接入框架）；用户拍板现配模型已支持识图，不加第二模型配置。
- **涉及面**：本期仅文档；落地时涉及 `api/feed.py`、`services/vision_ocr.py(新)`、`services/llm_client.py`(能力档+探测)、`api/system_config.py`(probe 扩展)、`views/office/AiSettingsPanel.vue`(能力档案加一行展示)、`components/opportunity/{RequirementAttachmentChips,OpportunityProcessBoard}.vue`。

## [v0.1.68] - 2026-10-18 — AI 办公室三渲二轻风格化 + 专用光位（?officeStyle=pbr 可整体关闭）

- **变更**：① 新增 `office3d/environment/toonStyle.ts`：toon 孪生材质（冷调阴影 ramp——暗部偏蓝紫，赛璐璐阴影是设计过的颜色；**polygonOffset 系照抄**，否则 actorSystem 认不出显示器材质会退化成双份桌）；描边外壳（候选网格 clone 后沿法线外扩，`mergeGeometries` 并成**单个** style-outline 网格，raycast 禁用）；`applyToonLightRig`（压环境光 Hemi×0.35/Ambient×0.28、主光 ×2.0 挪侧低位 (-14,11,3) 出赛璐璐长影，WeakMap 基准快照防重复调用漂移）；窗口光柱（三片渐变透明平面，raycast 禁用）；`toonifyStandardMaterials`（角色树非 MToon 材质换孪生，按材质 uuid 缓存跨克隆共享）。② `Office3DCanvas.buildEnvironment` 在 `mergeStaticGroup` 之后应用：合并体上**换材质引用**（零额外 draw call）+ 单网格描边（+1）+ 光柱（+3）。③ `actorSystem` 模板角色挂载前 toonify（VRM 的 MToon 本就是三渲二，不动）。默认开；`?officeStyle=pbr` 整体回退；编辑态 rebuild 跳过（与合并策略一致），退出编辑重建恢复。
- **根因**：风格对比页（style-test.html）实验结论：本场景 PBR 本就近乎平色块，仅换着色模型差异微弱（用户实测反馈"没区别"）；色阶要可读必须配套**压环境光 + 侧低位主光**——光的构图才是三渲二表现力的主要来源，故材质与光位一起进产品。
- **验证**：vue-tsc 全项目通过；toonStyle 过 esbuild+tsc 双查；三个改动文件 vite 转译 200。draw call 预算 ~152→~155。
- **涉及面**：`frontend/src/office3d/environment/toonStyle.ts(新增)`、`frontend/src/views/office/Office3DCanvas.vue`、`frontend/src/office3d/characters/actorSystem.ts`；临时试验页 `frontend/{style-test.html, src/styleTest.ts}`（仅供风格对比，可删）。
- 💡 **定论**：三渲二的差距主要不在着色器（一晚就能换），在光的构图与色彩设计；toon 孪生必须照抄 polygonOffset 系（actorSystem 靠 `mat.polygonOffset` 识别显示器材质并挂接现有桌）。

## [v0.1.67] - 2026-10-18 — AI 办公室 3D 性能修复：draw call 1459→152，帧耗时 56ms→3.6ms

- **变更**：五项修复，全在 office3d 渲染链路。① **去双份桌**：`rebuildActors` 不再为每个同事 `createDesk` 一张同位叠放的桌（曾致每工位两张桌：双倍 draw call + 桌面 z-fighting 闪烁），改为挂接 buildProps 已渲染的 `furniture-${slot.id}`——只挂接显示器材质（polygonOffset 判别）/名牌改染同事色（`userData.nameplate` 标记）/屏幕网格收集，异常配置兜底回自建桌；② **静态几何合并**：新增 `office3d/environment/mergeStatic.ts`，`buildEnvironment` 末尾把千级小网格按「材质 uuid+阴影开关」分桶合并成几十个大网格；原件就地隐藏保留作拾取代理（three 对不可见对象仍做射线求交，编辑器 `hitTestAt` 的 `userData.edit` 链不受影响），合并体禁用 raycast；编辑态 rebuild 传 `mergeStatic=false` 跳过合并（拖拽频繁重建），退出编辑的 save-config 重建再合并；③ **dpr 上限 2→1.5**（init + onResize 两处）；④ **阴影降频**：`shadowMap.autoUpdate=false`，tick 每 0.25s 置一次 `needsUpdate`（场景静态仅角色动），布局重建后立即补一帧防开场无影；⑤ **轻量拾取**：悬停/点击不再递归打整只角色（蒙皮网格逐顶点求交贵），改为代理胶囊+头顶 HUD 精灵+显示器膜的目标集合（actorSystem 新增 `pickTargets`/`monitorTargets`，显示器膜写入 `userData.roleKey` 保持悬停语义）。顺带：书架书材质共享化（每架 28 个独立材质→全局 6 个）。
- **根因**：本机复刻线上渲染配置实测：瓶颈不在三角形（全场仅 16.3 万）而在 **draw call**——小零件各自成 Mesh 无合并，8 工位场景 1459 draw call/帧 + dpr2 填充率 = 56.4ms/帧（≈18 FPS）；关阴影几乎不变快，证明阴影非主因。
- **实测**：修复后同场景 **152 draw call/帧**：dpr1.5 3.62ms、dpr2 6.23ms（9~15×提升）；渲染像素抽样完好（地面/家具着色正常、背景透明正确）。
- **涉及面**：`frontend/src/office3d/characters/actorSystem.ts`、`frontend/src/office3d/environment/{furniture.ts, mergeStatic.ts(新增)}`、`frontend/src/views/office/Office3DCanvas.vue`。现场诊断用内置浮层：URL 加 `?officeDebug=1` 看 fps/draws/meshes 实时读数。
- 💡 **定论**：浏览器 3D 的第一瓶颈是 draw call 数量，不是三角形数也不是阴影；「隐藏原件当拾取代理 + 合并体禁 raycast」可以在不侵入编辑器拾取链的前提下做全场景几何合并。VRM/GLB 角色与角色重建（colleagues deep-watch 触发 rebuildActors）是下一档优化空间，本次未动。


## [v0.1.66] - 2026-09-13 — 商机详情页：左栏可折叠 + 中栏工作卡默认折叠

- **变更**：商机详情三栏里，**左栏**新增折叠态——宽度 230px ↔ 64px（过渡走 `--cpq-dur-2`），折叠后渲染竖向图标条（已完成=成功色勾 / 进行中=主色序号 / 未开始=灰序号，带 title），折叠按钮贴左栏右缘垂直居中（48×24 右圆角、箭头旋转），状态记在 `localStorage:cpq:opportunity:rail-collapsed`；进度头新增 **Stage Progress**（当前阶段子步骤 x/y + 百分比），底部新增信息区（业务 / FAE / 报价人 + 最后更新，取 `opportunity.updated_at`）；子步骤完成标记按真实数据判定（商机信息=已填客户名，需求单=已发起，其余阶段跟随节点状态）。**中栏**把 `reqInfoOpen/requirementOpen/bomingOpen/costingOpen` 四个 `ref(true)` 合并为 `cardOpen` 映射，**默认只展开「当前待办」那张卡**（商机信息未填→展开商机信息；已填未发起需求单→展开需求单；其余节点按节点状态），用户手动折叠过的卡不再被默认值重置。右栏不动。
- **⚠️ 修复**：折叠卡残影——`.card-collapse.collapsed > .card-collapse-inner` 需清零上下 padding。原来 `.card-collapse` 用 `grid-template-rows: 1fr↔0fr` 折叠，内层 `padding: 0 16px 16px` 会顶起 `0fr` 行的**最小行高**（实测残留 16px，露出首行内容残影）；默认展开时看不见，改默认折叠后必现。
- **根因**：对齐参考 CPQ Workflow 页的评审结论——左栏完全采纳、中栏仅采纳默认折叠、右栏保留现状；折叠后仍需「知道走到哪一步、谁负责、何时更新过」。
- **涉及面**：`frontend/src/components/opportunity/{OpportunityProcessRail.vue(折叠态+图标条+阶段进度+底部信息区), OpportunityProcessBoard.vue(cardOpen 默认值/列宽变量/折叠按钮)}`、`frontend/src/views/opportunity/OpportunityDetail.vue`（透传 `updated_at`）。方案与原型：`docs/frontend-pages/opportunities/detail-workflow-redesign.md`、`detail-workflow-redesign-mock.html`。
- 💡 **定论**：`min-height:0 + overflow:hidden` 只能压掉内容的**最小尺寸**，压不掉 **padding**——所以「折叠到 0 高」必须连 padding 一起清零；另外左栏节点状态值只有 `pending/current/done`（**没有 `active`**），写状态样式别按 `active` 写。
## [v0.1.65] - 2026-09-09 — 配件选配（kp_reason）检索工具形态：定向 / 分页 / 高信号

- **变更**：`choose_parts` 检索侧升级为「定向检索/浏览」面——`series` 自动继承锁定机箱、`keywords`/`spec_filters` 定向收窄、`limit` 默认有界 + `truncated` 标记、新增 `offset` 翻页、`response_format=concise/detailed` 控制返回体量（默认 concise，裁剪 specs）；`part_query` 支持 `offset` 并回传 `total`/`next_offset`。选定侧不变：`picks` 只认服务端接地索引，价格/政策由引擎算，库外料号拒绝；`specified=false` 必填行只登记推荐并调 `ask_user`。
- **根因**：旧 `choose_parts` 是薄检索原语（一次一类目、limit=8、无翻页/无高信号排序），AI 被迫逐类全库检索 + 叙述，烧光 10 轮预算仍落不完（“边搜边废话/一轮跑不完”）；且行驱动候选池只挂在确认卡 `/card-pick`，没接到大脑工具面。按 Anthropic“多次小范围目标搜索好过一次性宽泛大搜索”“分页/过滤/截断+默认值”定调。
- **涉及面**：`backend/app/services/{data_tools,skill_chat,agent_tool_specs}.py`、`backend/tests/{test_skill_phases,test_select_kp_parts_tool}.py`、docs 新增 `kp选型-工具设计-搜料与选定.md`。
- 💡 **定论**：保留“AI 驱动检索/浏览”工具面，但每次检索做成定向+可收窄+可翻页+高信号；把检索真相/价格/政策/白名单锁在引擎，AI 只提议，不确定交客户确认。
## [v0.1.64] - 2026-09-09 — 配件选配（kp_reason）「必填 ↔ 反问」语义修正

- **变更**：`select_kp_parts` 不再对必填类目一刀切"永不落地锁定"；改为**按行**判定——`specified=true`（线索登记表已登记该行具体型号）→ 可直接锁定（命中=锁定，近替代=`substitute` 白盒）；`specified=false`（未登记/仅类目名）且属必填 → 只登记推荐并必须调 `ask_user` 交客户确认。新增 `part_selector.kp_registered_specified` 判据，基源=线索登记表 `kp_rows`。
- **根因**：旧实现把「必填」与「必须反问」焊成一件事（ask=true = AI 永不代选），导致客户已明确写清 CPU/内存/硬盘/RAID/网卡规格时，AI 查到真实料号仍只写 `kp_recommend` 不写 `kp_picks`——AI 误报"已选定"，引擎 end 校验/终检看到 5 大类全部 unmatched 即拦截（死锁）。
- **涉及面**：`backend/app/services/{part_selector,skill_chat,agent_tool_specs,skill_plan_runtime}.py`、`frontend/src/views/admin/reasoning/{TargetLayerModal,TargetTwoPane}.vue`、DB `rules.reasoning_node_default`/`reasoning_node_config` 的 `kp_reason` description 与字段 hint；docs 新增 `kp选型-必填与反问语义.md`。
- 💡 **语义定论**：必填=该行必须落在最终方案（不能跳/不能静默丢）；反问=AI 自己拍板或替代时才需客户确认。二者不是同一开关。用户写了→填，没写/模糊→推荐并问。
## [0.1.63] - 2026-08-16 — 报价策略模块补全：形态维度 / BOM 分项毛利 / 海外固定费 / 分档红线 / order_mult 断裂修复

- **变更**：加法引擎 7→**8 维**（新增 `form_adj` 机箱形态 ±百分点，数据走需求单 slots.chassis_form）；新增独立策略 `part_margin`（BOM 分项毛利：deal 目标之上按 KP 品类 ±，`computePartMargins` 每个 clamp，未来 AI 出价 per-line 直接消费）；region 海外档支持 **每台固定费**（`{pct,fixed_fee}` 对象形态，纯数字兼容，`suggestPrice=(成本+固定费)×(1+目标%)` 只入售价不进毛利）；guardrail 支持 **按订单类型分档红线**（`tiers` 首命中，渠道 5~25/集采 5~20，默认 7~30）。
- **⚠️ 修复①**：`order_mult` 枚举断裂——引擎 ctx 读 `order_type` 自由文本列（直销/渠道/集成商/最终用户），而系数表 key 是 `customer_type` 枚举（直签大客户/渠道分销/集采项目/零散项目），**值域不相交导致真实链路永不命中静默 ×1**；快照 ctx 改读 `extra_fields.customer_type ?? order_type`（业务拍板用 customer_type 枚举）。
- **⚠️ 修复②**：`DimensionDrawer.enumConfig` 对 region/cost_tier/qty_mult/guardrail 返回非空，模板首个 v-if 枚举表分支**遮蔽四个专门编辑分支**（打开区域抽屉显示的是订单系数表）；非枚举表维度改返回 null。
- **根因**：调研定调「模块先做完整、消费端(AI 转草稿/人工路径)不动、接入=纯 import」；引擎是纯 TS，`computeTargetMargin/suggestPrice/computePartMargins` 供未来方案助手直接调用。
- **涉及面**：`frontend/src/{stores/pricingEngine.ts(+单测 21 例), stores/pricingRules.ts, constants/pricingMeta.ts, views/admin/pricing/{PricingFlowCanvas,DimensionDrawer}.vue}`、`views/quote/Workspace.vue`（快照 ctx 两行）、`backend/scripts/seed_pricing_strategies.py`（+form_adj/part_margin/海外对象/分档，修滞后文案）；演算器加形态下拉+固定费标注+分项建议毛利表，画布下方加分项毛利摘要卡。
- 💡 商机 `order_type`（自由文本列）≠ `customer_type`（BusinessField 枚举存 extra_fields）——两套订单语义并存，定价维度认 customer_type。

## [未发布] - 2026-08-14b — 门户首页补商机卡片入口

- **变更**：门户空闲态磁贴下方新增「我的商机」卡片网格（客户名/摘要/流程节点，点进 `/portal/:oppId`）+ 后端 `GET /api/portal/opps` 批量端点（流程+当前需求单 IN 查询，无 N+1）。
- **根因**：02 详情页无入口可达，门户卡片是设计稿定义的主入口。

## [未发布] - 2026-08-14 — 协作报价流程 02：业务商机详情页（审批式视图 + 需求单结构化）

- **变更**：新建 `/portal/:oppId` 业务商机详情页（双栏/手机单栏）+ 流程三表（`opportunity_flows/flow_nodes/requirements`，opportunities schema）+ `/api/portal/opp/*` 六端点。
- **根因**：业务员需要「提需求/看进度/拿报价单」的受限视图，需求单从自由文本改为结构化部件清单（RequirementSlots 契约，后端直接消费）。
- **涉及面**：`backend/app/{models/flow.py, repository/flow_repo.py, api/portal.py}`、`frontend/src/{api/portal.ts, components/flow/*, views/portal/BusinessOpportunityDetail.vue}`、权限目录新增 `field.flow.bom/cost`。

## [0.1.62] - 2026-08-12 — 规则绑定工作台「好玩层」：拖放投放 / 粒子流 / 覆盖度 HUD / 首进引导（P1）

- 🎯 拖放投放绑定：左栏规则卡片可拖拽，拖到地图区域松手即显式绑定（真图纸 Viewer 与示意解剖图 Map 均支持）；拖过区域时亮蓝虚线高亮投放目标，绑定成功区域脉冲 + 爆开粒子
- ✨ 规则→区域粒子流：悬停/定位规则卡片时，粒子从卡片位置飞向命中区域（显式绑定 ∪ 字段推断）；手写轻量粒子层（不引依赖），单 Graphics 每帧重绘
- 📊 覆盖度 HUD：地图角落进度环显示已绑定区域/总数与规则绑定率，区域绑齐时撒花庆祝（首次评估不触发）
- 🎮 首进引导：一次性扫描线 + 「点击区域/拖卡片绑定」提示浮层（sessionStorage 记录，可关闭）；跨视图自动定位与点击区域均触发高亮脉冲
- 实现面：ServerAnatomyViewer（pulseId prop、drop-rule 事件、defineExpose playStream/burstAtRegion）、ServerAnatomyMap（拖放+脉冲 CSS）、CompatibilityRuleEditor（拖拽/流/HUD/引导）

## [0.1.61] - 2026-08-12 — 兼容性规则 ↔ 服务器图区域：显式绑定闭环（P0）

- 💡 绑定从「字段猜」变「显式」：后端 compatibility_rules 新增 regions TEXT（JSON 数组：料号库大类 id），startup 幂等 ALTER 自动补列，create/update 落库、to_dict 回传；规则 body 字段推断降级为「建议」
- 规则编辑器：编辑弹窗新增「绑定到区域」多选（料号库大类，机型无关）；卡片新增已绑定/建议徽章；右栏情报拆分「已绑定 / 推断可采纳」，支持单条/全部采纳；顶部「自动绑定」批量将推断转显式
- PixiJS 可视化：未绑定但有推断建议的区域显示琥珀色流动虚线 + 「+N」徽标（真图纸 ServerAnatomyViewer 与示意解剖图 ServerAnatomyMap 同步）；示意图区域改为显式 majorNames 映射（不再靠字段猜）
- 图纸配置页：区域列表红/黄/绿绑定状态徽章 + 汇总条（已绑定/可采纳/未绑定）

## [0.1.60] - 2026-08-12 — LLM 工具整合为唯一注册表：统计工具升级为数据工具，AI 设置页内嵌工具目录

- 💡 **全系统 LLM 工具唯一注册表** `services/agent_tools.py`：`_TOOL_SPECS` 统一声明 name/description/parameters/category/default_enabled，需求分析 ReAct 与方案助手共用同一份元数据，拒绝双写；新增 `tool_catalog()` + `GET /api/assistant/tools` 供前端渲染
- **统计工具更名升级为数据工具 `query_cpq_data`**（不止统计：KPI/平台/机箱/排行/逐期趋势/重点商机 × 本周/上周/本月/近半年/今年/自定义区间）；方案助手提参 schema/system prompt 改为从注册表派生，枚举/描述不再双写；趋势指令走确定性拆参（4 条固定查询）
- **前端落点按用户指示**：AI 工具目录并入 AI 设置「方案助手」tab 底部只读表格（不单独开 tab）；docs 工具说明并入 `ai-settings.md`（不单独占文件）
- 清理：`query_cpq_statistics`、`chat_with_tools`、旧「统计工具」表述全部替换为 `query_cpq_data`/「数据工具」（docs + 注释）

## [0.1.59] - 2026-08-12 — 方案助手接统计查询链路，清退 trend-overview 富上下文注入

- 💡 方案助手新增统计查询链路 `query_cpq_statistics`（本周/上周/本月/近半年/今年/自定义区间 × KPI/平台/机箱/销售排行/逐期趋势/重点商机）：追问「上周怎么样」等任意周期问题自动查数作答，告别「一口气塞数据、再问就哑火」
- 实现：LLM 提参（chat_json JSON mode 把消息解析成 0..N 条查询）→ 服务端 `_exec_query_stat` 查库 → 结果注入消息后流式作答；趋势分析指令走确定性拆参（本周/本月/近半年/重点商机 4 条固定查询）。注：CC Switch 代理端点只认 web_search 工具变体、拒绝标准 function 调用（400 unknown variant），故未走原生 function calling
- 删 `/api/dashboard/trend-overview` 路由（查询逻辑抽为 `get_highlights` 供链路复用）；前端 `assistantProviders.ts` 删 `formatPeriod`/`formatHighlights`/`buildTrendContext`，快捷指令不再注入富上下文

## [0.1.58] - 2026-08-10 — 执行路径统一 + 旧 handler/线性兜底删除（-604 行，结构性除旧）

### 核心改革：三套执行路径 → 统一为 orchestrator 唯一引擎
- **画布试运行改走 `run_orchestrator`**（此前走 `run_graph_executor`，与正式方案助手执行逻辑不一致）
  - reasoning_flow.py test_run/_stream_test_run 从 graph_executor 切到 orchestrator
  - 前端 useTestRun.ts 新增 `plan_progress` 消费：LLM 决策间隙显示"智能体规划中…剩余 N 步"
  - **节点高亮 + 卡片特性完整保留**（step_start/step_done 格式相同，前端事件驱动不认后端引擎）
- **`_run_linear_fallback` 删除**（-173 行）：orchestrator 异常 → 诚实降级（广播"引擎不可用"），不再跑旧 5 步规则链假装出方案
- **`_dispatch` 删 9 个 v9 handler**（-296 行）：normalize_input/llm_agent/slot_validate/scene_analysis/select_baseline/match_kp/clarity_check/ask_user/confirm_series + extract — orchestrator 只 dispatch V11 能力链类型，这些 handler 确认无人调用
- **`PIPELINE_STEPS` 常量删除**（v9 线性链步骤定义，-8 行）
- **`build_domain_knowledge` 死函数删除**（0 引用，-5 行）
- **6 个 v9 测试删除**（-116 行）：test_executor_select_baseline/clarity_check×4/ask_user — 测的 handler 已删

### 验证
- 后端 365 passed（-6 个废弃测试）+ 前端 vue-tsc 0err/npm test 60 绿
- 净节省 **-604 行**（649 删 / 45 插入）
- reasoning_executor.py 843→547 行（-35%）；requirement_intel_service.py 删 linear fallback 后大幅精简

### 保留（评估后决定不动）
- `run_graph_executor`（90 行）：仅测试/脚本用（test_scene_analyzer 图级回归），生产代码已全走 orchestrator
- `_default_node_configs`（214 行）：v9 配置生成器，但其中 extract/select_baseline/match_kp 三段词表数据仍是 V11 种子的默认值来源（动它有破坏 seed 默认值风险）
- `_run_understand_legacy`：split_steps=false 降级路径，有测试覆盖

---

## [0.1.57] - 2026-08-10 — 历史遗留清理（双路图/逐节点开关/migrate代码/extract前端残留，净 -936 行）

### 三批清理（每批后跑测试确认）
- **批次1·死注释/死引用**（7 文件）：capabilities.py/requirement_intel_service.py 删 requirement_parser 悬空引用；models/reasoning_flow.py 旧 5 步描述改 AI-first 单路链；llm_extract_enhance/llm_client/reasoning_intel 删双路旧描述。
- **批次2·逐节点开关**：删 `ai_mode`(4处死字段) + `enable_llm`(llm_audit 只认全局开关 + 删 orchestrator `audit_llm` 预算字段) + `proposal_mode`(kp_reason 固定 llm_propose，删 react/rule 分支 + 死符号 `_KP_REASON_PROMPT`/`_collect_kp_from_react`)。测试：删 `test_disabled_skips_llm`(节点级开关已不存在)。
- **批次3·结构性删除**：
  - `DEFAULT_GRAPH`(v9 双路种子图) 删除 + `seed_default_if_empty` 改 seed V11（新环境直接建单路链）
  - `active_is_current` 删 v9 死检查（understand 提前返回已覆盖）
  - **21 个 migrate/upgrade 方法**删除（reasoning_flow_repo -815 行）+ **startup.py 19 个 migrate 调用**删除（只留 seed + active_is_current 检查）
  - `_VALID_NODE_KEYS` 收敛 + 补全 orchestrator/result_check（修保存 400 潜在 bug）
  - extract dispatch 改静默跳过（返回 None）；`understand_fallback` 死信号删除
  - 前端 extract meta/IO/stepCopy/抽屉 buildConfig/form 全清理；NodeIndexOutlined 未用导入删

### 验证
- 后端 371 passed（原 372，删 1 个废弃测试 test_disabled_skips_llm）
- 前端 vue-tsc 0 error + npm test 60/60 全绿
- 净节省 **-936 行**（1011 删 / 75 插入），reasoning_flow_repo.py 从 ~1393 行降到 ~605 行

---

## [0.1.56] - 2026-08-10 — 正则解析路径物理删除（requirement_parser 包移除，约 -2600 行）

### 删除清单（AI-first 后死代码物理清除）
- **整个 `requirement_parser/` 包**（signals 1266 行 + knowledge 109 + tokens 9 + __init__ ~90 ≈ **-1474 行**）：`extract_keywords` 正则理解自由文本 + 全部字段级正则提取器（`_extract_budget/_extract_mem_signal/_extract_cpu_signal/_extract_psu_signal/_extract_drive_groups/_extract_gpu_groups/_extract_raid_groups/_nic_line_filters/_split_requirement_fields/_mem_group_from_each/_normalize_table_rows` 等）——均已无生产调用
- `capabilities.run_rule_understand`（extract 节点 handler，~-40 行）
- `reasoning_flow_repo._v11_node_configs` 的 extract 默认配置 + 过时注释（~-15 行）
- 测试：`test_nic_qty_binding.py`（全测已删正则，~-245 行）+ `test_requirement_intel.py` 死块（~-900 行，90+ 个死正则测试）
- **净节省 ≈ -2650 行**（迁入 requirement_intel_service 的 `_load_series_values`/`_CN_STOPWORDS` 仅 +25 行）

### 保留
- `_load_series_values`（系列白名单权威源）+ `_CN_STOPWORDS` → 迁入 requirement_intel_service（调用方 llm_extract_enhance/reasoning_executor/reasoning_flow_repo 导入路径不变）
- 其余共享能力（CATEGORY 词表经配置、MODEL_TOKEN_PATTERN 在 clarity_evaluator 本地）不受影响

### 验证
- 后端全量 pytest **372 passed**（删 94 个死测试后）+ 前端 vue-tsc ✓；导入健康检查通过
- 职责边界：AI-first 后节点职责 = 理解(LLM)/机型(规则+放宽)/配件(LLM提议+库校验)/组装(确定)/校对(judge)/反问；extract/规则正则理解已彻底退出历史舞台

---
## [0.1.55] - 2026-08-10 — 正则理解路径（extract_keywords）生产调用全摘除

### 背景
用户问"AI 失效走手动配置，后端为什么还保留正则解析"。核查发现：AI 失效（关 AI）确实走目录手动选型、不碰正则；但正则解析还挂在**两条边缘路径**：① 线性兜底（整个图/orchestrator 异常时第 1 步还在跑 run_rule_understand）；② 旧图兼容（画布显式放 extract 节点）。

### 改动
- `_run_linear_fallback` 第 1 步：正则解析 → **诚实降级**（广播"⚠️ AI 推理不可用，请手动选择机型与配件"+ 空 ext），不再产出可能错误的 BOM
- `_dispatch("extract")`：返回 `{deprecated: true, ...}` 占位，不再调 requirement_parser
- **保留**：`extract_keywords` 函数本体 + `requirement_parser.signals` 字段正则（`_extract_raid_groups`/`MODEL_TOKEN_PATTERN` 等仍被 merge/清晰度评估/测试使用，不可整删）；生产路径已不再调用

### 验证
- 后端全量 pytest **466 passed**（+ 前端 60，vue-tsc 绿）
- AI 失效路径不变（目录手动选型）；图/orchestrator 异常路径从"假智能正则"改为"诚实降级提示"

---
## [0.1.54] - 2026-08-10 — AI 路线清理：画布/抽屉/旧开关全面瘦身（用户主导）

### ① 画布收敛
- active flow 从 10 节点 → **9 节点全连通**：移除 extract（正则理解已废弃）；llm_ask（反问配置）、spec_compliance（合规红线）、audit_fix（自纠）**连线保留**（此前孤立）
- 新边：understand→llm_ask、kp_reason→spec_compliance→compose、llm_audit→audit_fix→review
- palette 移除 extract / gap_analyze / scene_decide（已并入理解；meta 保留供旧图渲染）

### ② 右上角「LLM 节点」按钮移除（旧版逐节点开关 LLM）
- ReasoningFlowCanvas：按钮 + LLM 节点总览抽屉 + openLlmNodes/toggleLlmNode/setAllLlm 全删
- 后端 `GET /api/reasoning-flow/llm-nodes` + `list_llm_nodes` 删除；前端 api `llmNodes()` 删除

### ③ 抽屉旧开关清理（AI-first，后端默认行为保留）
- **ai_mode（智能实现）**：4 处单选全删；`_ai_enabled` 简化=只认全局 AI 开关（规则只作失败兜底）
- **proposal_mode（提议方式）**：ReAct/纯规则选项删除；后端默认 llm_propose + 失败自动降级规则
- **deterministic（确定性红线）开关**：删 UI；后端默认红线集合（compose/llm_audit/review/audit_fix/spec_compliance/result_check）照旧
- **llm_audit「启用 LLM 方案校对」**开关删（默认走 judge，由编排预算控制）
- 清理 DEFAULT_DETERMINISTIC 常量 / toggleLlm / isCapabilityNode 等死代码

### ④ 剩余项：专家分析 issues 前端渲染
- `_dispatch` understand 返回透出 `issues`；试运行步骤里渲染「专家分析」问题清单（标题+依据+建议），像方案助手一样先给建议再进选配
- requirement_parser 收敛为纯结构化工具：保留为 dormant（画布兼容），不在主线使用

### 验证
- 后端全量 pytest **466 passed** + 前端 vue-tsc + 60 tests ✓
- 8 卡需求真实 flow：KP 全对（8×32G/9361-8i/双口网卡/2700W）、spec_compliance 无重跑循环
- 说明：本轮 e2e 慢是模型当前坏期（understand 91s/kp 79s），非功能回归；链路顺序与清理前一致

---
## [0.1.53] - 2026-08-10 — 需求分析智能化改革 · Phase3：诚实降级 + 清理规则路径残留

### ① 删 ai_mode: rule（纯规则模式）
- `_ai_enabled` 删除 rule 分支（rule 不再作为独立模式，规则只作失败兜底）；前端 4 处「纯规则」单选项移除
- 遗留配置 ai_mode="rule" 自动按 auto 处理（跟随全局）

### ② AI 不可用 → 明确告知 + 目录手动选型（诚实降级）
- orchestrator ai_off 路径广播「⚠️ AI 引擎暂不可用（网络/额度），以下按手动选型引导，选项均来自在售目录」
- 不再用正则假装理解自由文本；extract 仅当用户显式连入画布图才执行

### ③ 画布试运行（run_graph_executor）同步去 extract 自动兜底
- 与方案助手一致：extract 不再因 understand_fallback 自动执行（旧正则理解路径全链路下线）

### 验证
- 后端全量 pytest **466 passed**（1 deselected：既有数据依赖）；前端 vue-tsc + 60 tests ✓
- test_scene_analyzer 改 hermetic（注入 ext + 关 LLM，不依赖已删的 ai_mode=rule）；套件从 ~7min 降到 ~17s（测试不再碰真实 LLM）

---
## [0.1.52] - 2026-08-10 — 需求分析智能化改革 · Phase2：理解升级「专家分析」+ 默认链收敛

### ① 理解节点「专家分析」（第 5 个子任务，并行）
- `UNDERSTAND_STEPS_DEFAULT` 新增 `analysis` 步：LLM 像资深售前一样输出**硬问题清单 issues[]**（issue/evidence/suggestion，最多 5 条）——检查电源/内存通道/RAID 存储/网卡/散热
- 8 卡需求实测 5 条：电源需 4×2700W、内存 256GB 通道不匹配、数据盘容量不足、10GE 瓶颈、缺专用 GPU 机箱 —— 与方案助手分析同级
- issues 进 `ctx.analysis_issues` + understand 步 payload（step_done 带 issues，前端可展示）

### ② 理解节点自带「场景/缺口」（为去 gap/scene 做准备）
- run_understand 现在同时产出 `ctx.scene`（由类型/系列/形态确定性给出，与 scene_decide 同构）+ `ctx.clarity`（充分→explicit / 不足→partial）+ missing_fields
- 默认链不再依赖 gap_analyze/scene_decide；_needs_llm_decision 反问门控照常工作

### ③ 默认链收敛
- `DEFAULT_GRAPH_V11` 收敛为 6 节点：understand(专家分析) → model_reason(多级放宽) → kp_reason(提议+库校验) → compose → llm_audit(judge) → review（llm_ask 反问侧枝）
- active flow 已更新；迁移框架（migrate_v12_spec_audit 等）幂等补回 spec_compliance/audit_fix/extract 三个**确定性安全门**（0s；GPU 必配/自纠/兜底，不碎片化 LLM 智能）——gap/scene/budget 等 LLM 碎片节点已移除
- 旧节点保留在 palette 可拖回（图=能力注册表，回退=画布改图）

### ④ 实测（真实 active flow，8 卡需求）
- 155.6s | plans=1（ESA24V3-P Orion-Switch）| 专家分析 5 条
- KP 全对：9354×2 / R9700×8 / 32G×8 / 480G×2+960G×2 / 双口1G+双口10G(光) / 9361-8i×1 / PSU 2700W
- 模糊需求（6 节点链）：18s 反问"主要用途？"（真实选项）

### 验证
- 后端全量 pytest **466 passed**（1 deselected：既有数据依赖）；前端 vue-tsc + 60 tests ✓
- 测试更新：ready_deps/线性链/retry 链/derive 均收敛到 6 节点；retry 测试 hermetic（mock _decide_retry_targets）

---
## [0.1.51] - 2026-08-10 — 需求分析智能化改革 · Phase1：KP「LLM 提议 + 库校验」+ 删 extract 理解路径

### 背景
8 卡需求实测：方案助手（纯 LLM）又快又准，需求分析（规则匹配）又慢又错（内存 16G×1 / RAID 缺失 / 网卡 400G / 电源 2000W）。根因=LLM 整体推理被"字面抽取+死规则匹配"丢弃（正式方案见《需求分析智能化改革-执行方案.md》）。

### ① KP「LLM 提议 + 库校验」（kp_reason 改革·核心）
- 新 `_kp_llm_propose`：LLM 读需求+理解摘要+机型通道 → 确认需领域知识的项（内存条数/RAID 型号/网卡口数/电源）→ `pick_kp_parts` 库校验执行（真实料号/价格，防幻觉）
- `proposal_mode` 可配：llm_propose(默认) / react(旧 ReAct) / rule(纯规则)；失败自动降级规则
- 8 卡需求实测：内存 16G×1→**32G×8**、RAID 缺失→**LSI 9361-8i×1**、网卡 400G→**双口1G i350 + 双口10G+光模块**、电源 2000W→**2700W×4**（确定性 TDP 计算）

### ② 配套子修复
- memory 槽位加 `total_gb`：只给总量（256GB DDR5-4800）不丢，LLM 提议按通道拆条（8×32G）
- RAID：S4 允许按规格推断型号（2GB缓存+8口→9361-8i）；修复 stage-1 关键词 + raid_groups 双路径双计 qty（×2→×1）
- 网卡：S4 "N×speed" 解释为 N 口双口卡（2x 1GE→ports:2,qty:1）
- PSU：`_kp_signals` 改按 GPU 实际 TDP（配件库 specs.tdp 优先 → `gpu_tdp_by_model` 配置表 → 词表兜底），删对硬编码清单的强依赖；`high_tdp_threshold_w` 可配

### ③ 删 extract 理解路径（AI 失效第二套智能）
- orchestrator 不再路由 `understand_fallback` → extract 正则理解（诚实降级：理解失败→缺口反问）；extract 仅画布兼容保留
- 遗留：ai_mode=rule 抽屉选项、requirement_parser 收敛到结构化解析（Phase3 清理）

### 验证
- 8 卡需求 KP 对标技术员方案（CPU/内存/RAID/网卡/盘/GPU/电源 全部对齐）；PSU 确定性推断 2700W
- 后端全量 pytest **466 passed**（1 deselected：既有数据依赖 test_raid_applicable_orion_default_9540）；前端 vue-tsc ✓
- kp_reason 抽屉新增 proposal_mode（LLM 提议+库校验 / ReAct / 纯规则）

### ⚠️ 误删恢复说明
Phase1 实施中替换区间误删 capabilities 的 run_llm_ask/run_llm_confirm/白名单辅助（_catalog_whitelist/_filter_catalog_options/_catalog_fallback_options/_FORM_WHITELIST 等），已按 tests/test_llm_ask_catalog.py 契约 + 原实现语义重建并全绿。

---
## [0.1.50] - 2026-08-10 — 需求分析 agent 化：理解拆步子任务 + 选型多级放宽 + 混合脊柱编排 + judge 校对（全部可配，白盒）

### 背景（💡 根因实测定论）
用户反馈"AI 智能体像假的、5 分钟跑不完、不出方案"。逐层实测定位：
1. **理解节点空回**：deepseek-v4-flash（reasoning 模型）对"10+ 字段一次性大填表"过度思考，把 max_tokens=8000 烧在思考阶段（finish_reason=length）→ 正文空回（40-60% 失败、慢 42-64s）。**轻 prompt 只缓解不根治**，拆成聚焦小子任务 reasoning 骤降（228~1414 字）→ ~100% 成功。
2. **plans=0 根因**：需求点名 Intel 平台 AI 机型，目录里 AI 机型全是 Orion（AMD）→ select_models 按 series 硬过滤返 0 → 白等 4 分钟没方案。
3. **编排层浪费**：每步都调一次 LLM 决策"下一步跑哪个节点"（~10 次 × ~8s），拓扑已确定时纯属重复劳动。

### ① 理解节点 agent 化（分步子任务，可配）
- `UNDERSTAND_STEPS_DEFAULT` 4 个子任务：类型/系列/形态 · CPU/内存 · 硬盘/GPU · 网卡/电源/RAID，每步 3-5 字段、prompt 聚焦、领域知识按 kind 注入（`build_domain_knowledge_map` 按需检索）
- 并行执行（`parallel_sub_steps` 默认开）→ understand 从 78s+空回降到 **~9s 稳定**；子任务失败单独便宜重试（`sub_step_retries`），仍失败只丢该子字段、交反问，不再整表失败
- 开关：`split_steps` 总开关 / `steps.{key}.enabled` / `parallel_sub_steps` / `sub_step_retries`（understand 节点抽屉全可配）；`split_steps=false` 走 legacy 单次填表
- 实测：8-GPU 需求 4/4 子任务成功，正确抽出 类型/GPU×8/内存×16/盘3

### ② 选型多级放宽（A 方案，非硬编码）
- 接上 model_reason 抽屉里**早已存在但未实现的 `fallback_order`**（exact→same_series→same_form→all，用户可配）：严格条件无货时按配置逐级放宽
- `select_models` 每条候选带 `match_stage` + `fallback_note` 白盒说明（数据驱动：如"库内无 Intel 平台 4U 全匹配机型，已放宽【平台系列】，按最接近给出候选"）
- 规则路径（run_select_baseline_rule）与 LLM 工具路径（_tool_select_models）同源生效

### ③ model_reason 短路（可配）
- `skip_react_when_model_missing`（默认开）：需求点名了不在在售目录的具体机型（机型代码特征检测，`model_missing_token_pattern` 可配）→ 跳过注定失败的 ReAct，直走规则降级 + 白盒说明（实测 model_reason 15.9s→0s）

### ④ 混合脊柱编排（LLM 只做决策，规则跑腿）
- `_needs_llm_decision` 门控：信息明确（clarity=explicit）且无异常 → 按拓扑序确定性跑，不为"下一步"反复调 LLM；只在 信息不足/选型落空/收尾总结 这些真正需要判断的点让 LLM 介入
- 编排 LLM 决策 ~10 次 → 0-2 次；保留反问（llm_ask）、重跑选子集（_decide_retry_targets）、终局总结

### ⑤ llm_audit 升级独立 judge（防同模型自批判塌缩）
- 独立裁判人设 + 规则硬校验结果（audit_plan）作为事实喂入 + 每条要求引用需求依据 + confidence（0-1）
- 规则判通过但 judge 认为有意图级问题必须明确指出；judge 与规则冲突可采样人工评级（llm_trace）

### ⑥ 执行预算（0.1.49 补充）
- orchestrator `budgets`：墙钟/步数/工具调用/反问轮数，抽屉可配；超限自动停止反问与 LLM 决策、按确定性链收敛（实测 240s 耗尽后正确线性收敛）
- 每步广播 `plan_progress`（剩余计划 + 预算用量），plan_preview 可配

### 实测（8-GPU 需求：WA5480 G3/2×Intel 6530/8×RTX 5090/16×64G/盘/25G/4×2700W/RAID）
| 阶段 | 基线 | 现在 |
|---|---|---|
| understand | 78s + 空回 | ~9s，4/4 子任务 |
| model_reason | count=0（series 硬过滤） | count=4（多级放宽 + 白盒说明） |
| 方案 | plans=0 | plans=4（Orion/Polaris 4U） |
| 总耗时 | 258.5s 无方案 | **70-95s 出方案** |
| 模糊需求「我要一台服务器」 | — | 20.5s 反问"工作负载？"（真实选项+why） |
| 中等需求「2U 通用 EPYC 64G*16 2*960G 预算20万」 | — | 51.4s 直接出方案 ES22V3-P |

### 验证
- 后端全量 pytest **464 passed**（1 deselected：既有数据依赖 test_raid_applicable_orion_default_9540，配件库无 9540，与本次无关）；前端 vue-tsc ✓
- 编排测试改为 hermetic（stub `_dispatch`，不再碰真实 LLM，20 tests 17s）
- 新增单测：分步/限长/few-shot 限量/预算/judge 事实注入/select_models 多级放宽/model_reason 短路（+32）
- ⚠️ 未提交（历阶段累积，用户未让 commit）

---

## [0.1.49] - 2026-08-09 — 需求分析编排优化：编排配置节点 + 方案自检节点 + 结构化记忆 + 延迟优化（全部可配，不黑盒）

### 背景
对照主流 agent 架构评估（ReAct / Orchestrator-Workers / Graph / Reflection / HITL）：架构方向达标；短板在「编排行为是黑盒、无显式计划、多轮记忆靠文本、端到端延迟高」。用户拍板：P1-2（结构化记忆）+ P1-3（延迟优化）+ P2-4（执行中自检），且全部做成画布可见可配置。

### ① 画布新增「编排配置」节点（orchestrator，不执行，只提供配置）
- **AI 增强预算**：省时间(快=ReAct 3 轮+校对纯规则) / 均衡(默认=4 轮+LLM 校对) / 最优(6 轮+LLM 校对)——控制 model/kp 的 ReAct 轮数与 llm_audit 是否走 LLM，预算优先于节点种子默认
- **结构化记忆**：跨轮续接把「已确认槽位/缺口/场景/候选/已完成」摘要喂回编排 agent（`_state_summary` + 会话持久化 `orchestrator_memory_summary`），对话文本只作补充；摘要开关/字段/对话保留轮数可配——解决"多轮反问后忘记早期确认"
- **推进策略**：确定性能力并行（默认关；链式图一次只就绪一个、无收益，分叉图才有；DAG 保证并行能力互不依赖，无竞态）
- 未画该节点时用默认值（均衡），零配置即可用

### ② 画布新增「方案自检」节点（result_check，确定性，画布可见）
- 与「规格合规校验」分工：spec_compliance 查配置是否符合目录/兼容规则；result_check 查方案有没有缺漏/自洽
- 检查项可勾选：方案非空 / 核心件齐全（CPU/内存/盘）/ 数量合理性（配 GPU 有供电线、有内存条）
- 失败处理：仅标记需修改 / 自动触发确定性重跑（compose→预算→自检，重建脊梁强制保留，LLM 不可跳过）
- `_dispatch` 支持 + orchestrator 派发，两条执行路径（方案助手/画布试运行）通用

### ③ 延迟优化实测
- 同需求「2U 通用 32G 2×1T」：**quality(6 轮≈原默认) 246s vs balanced(4 轮·默认) 126s，约快 49%**（含审计重跑差异，样本级）
- 三项核心逻辑均有自检：模拟对话 3 场景（模糊→反问→续接出方案 / 详细一键出方案含自纠重跑 / 闲聊引导）全部通过，result_check 集成 passed

### 验证
- 前端 vue-tsc + 60 测试 ✓；后端全量 pytest 421 ✓（orchestrator/agent/audit/spec 相关 52 先跑）
- 浏览器实测：palette 出现「编排配置」「方案自检」，抽屉表单可配
- 未改 active flow（13 节点/13 边不动），新节点从 palette 拖入即生效

 - 2026-08-09 — BOM 模板配置说明：拒绝黑盒，行/规则/模板分类三处可查

### 背景
用户反馈 BOM 模板"只有配置没有说明"：每一行要填什么、根据什么配件填充、内容来自哪里完全靠猜；不同服务器（2U/4U、直连/Switch）模板格式不同，但没人解释为什么。

### ① 基准配置页文档入口（BomTemplateManager.vue）—— 单一数据源
- 「新建模板」旁新增「📖 模板说明」按钮 → 抽屉，**实时拉取文档库《BOM 模板配置指南》（module=selection）用 MarkdownView 渲染**；每次打开同步最新，用户在文档库编辑后此处自动变化
- **不维护第二份拷贝**：删掉上一版硬编码的行类型/模板分类/规则 kind 常量（约 130 行）；文档被改名/删除时抽屉给兜底提示

### ② 文档库完整指南（唯一内容源，用户可编辑，v2）
- `docs/策略中心/02-选型配置域/BOM模板配置指南.md` → 已发布至「策略中心 → 选型配置 → 📄 文档库」（操作指南）
- 含行类型速查（11 种）/ 模板分类差异 / 规则 kind 速查 / 常见问题；kind 中文名随界面术语同步（模板拼接/取料号字段/按结构自动生成…）

### ③ BOM 模板编辑大改版：降门槛 + 表格化 + 实时预览（用户主导，BomTemplateManager.vue / BomRuleSourceEditor.vue）
- **从现有模板复制**：新建时可选择已有模板（2U12标准/4U8-GPU直连/4U8-Switch），整份行骨架+规则带入，改名即用
- **新行默认规则自动填充**：按行类型带推荐规则（heatsink→取料号/料号数量、cable→配置 cable_desc/固定 1…），保存即合理，⚙ 从"必做"变"进阶微调"
- **行列表表格化 + 列头**（# 行类型 左栏标签 槽位/形态 解析规则 操作）；规则列显示摘要（不开 ⚙ 也懂：`料号 heatsink.name / 料号数量 heatsink`），点摘要展开精细编辑
- **实时预览**：编辑弹窗底部用演示数据跑求值引擎，随编辑刷新每行"规则解读 + 效果示意"（标注演示数据）
- **控件自解释，去掉小字**（BomRuleSourceEditor 重写）：
  - kind 下拉大白话：固定文字/取料号字段/模板拼接/按结构自动生成/取配置参数/手动填写（存储值不变）
  - 料号品类 category 从下拉选（heatsink/fan/rail/backplane/psu/cable），不再自由输入
  - 模板拼接：点选「插入变量」下拉（中文标注）自动插入，输入框下实时渲染预览（`${bays}*3.5 ${bp_type_desc}` → `24*3.5 SATA/SAS/NVMe`）
  - 结构计数 scope 按行类型限定（io_slot 行只给 riser 选项、rear_summary 行只给汇总选项）
- 行类型下拉分「系统自动计算 / 需人工填写」两组，选项带中文说明
- **修复**：行类型下拉选项为空（`a-select-optgroup` 组件名写错 → 改为 `a-select-opt-group`，下拉分组+选项正常显示）
- **布局**：编辑弹窗改左右两栏（modal 860→1120px）——左栏行骨架表格、右栏实时预览，顶部对齐、预览独立滚动
- **预览可读性**：右栏预览从三列挤排改为卡片式——每项「行标签 + 效果示意」同一行（space-between）、规则解读在下方一行，窄栏下不再挤压
- **预览对齐工作台左栏**：实时预览改为与工作台 BomTable 一致的 L6 配置单表格（Catalogue/Description/Qty 三列 30/58/12%、表头 sticky、空值显示 [空]、空行隐藏）——视觉统一，宽度按工作台左栏同等列宽分配
- 联网核实差异依据：2U=通用平衡（≤4 张 L40S 级风冷 GPU）；4U=全高 PCIe+多 GPU+大风道；Direct=点对点直连（省线缆）vs Switch=NVSwitch 全互联（训练场景，需背板/更多线缆/常配 RAID）

### 验证
- 前端 vue-tsc -b ✓、node --test 60/60 ✓；后端 pytest 421 全量 ✓

 - 2026-08-09 — 需求分析「配置体验优化」：装修减负 + 数据自愈 + 试运行交互

### 蓝图落地（`docs/策略中心/02-选型配置域/需求分析配置体验优化-蓝图.md`）
- **P0 信息架构**：节点元数据统一到 `utils/reasoningNodeMeta.ts`（中文名/职能/来源/图标/分组，palette/节点卡/抽屉共用真源）——修复 10 个新节点在画布上职能说明为空的旧问题；palette 搜索/拖拽添加/已用角标/空态引导；节点 label 去英文后缀（时间线/弹窗用中文名）
- **P1 画布交互**：网格吸附（snap-to-grid）、自动布局（按边拓扑分层，零依赖手写）
- **P2a 抽屉减负**：4 处 JSON 文本框 → 可视化表格编辑器（char_fixes / noise_patterns / cpu_mem_type_rules / category_aliases），业务用户不再手写 JSON
- **P2b 该删的删掉**：清理 8 个 palette 已无法添加的旧节点分支（normalize_input / slot_validate / confirm / llm / llm_understand / llm_agent / 独立 ask_user / 独立 clarity_check / scene_analysis）——模板 + buildConfig + 相关 refs 全删，抽屉 1374 → 1117 行
- **P2c 试运行交互式反问**：暂停反问时给选项按钮 + 回复输入 + 继续，模拟客户回复拼进需求文本重跑（forceComplete=false 保持可继续反问），页面内走完完整对话流；加快速样例下拉（模糊/中等/详细/闲聊）

### 设置-AI设置「会话记录」管理（回收站 + 历史数据清理）
- **背景（用户反馈）**：方案助手会话删除是软删除，消息/推理状态/反馈样本/调用痕迹只增不减，数据越堆越多
- **功能**：AI 设置新增「会话记录」tab——统计（总会话/回收站/消息总数）、会话表格（全部/正常/回收站筛选，标题/创建人/消息数/最后活跃/状态）、操作：查看（只读消息）/ 删除（进回收站）/ 恢复 / 彻底清除（物理删消息+状态）
- **历史数据清理**：LLM 调用记录（保留最近 N 天）+ 需求反馈样本（保留最近 N 条/清空），删除不可恢复
- **后端**：`GET /threads?scope=all`（管理员含回收站+消息数）、`POST /threads/{id}/restore`、`DELETE /threads/{id}?hard=1`（物理删）、`POST /admin/cleanup/trace|samples`（rules schema 走 Rules_SessionLocal 遵守 schema 隔离）
- 验证：前端 vue-tsc/测试/构建 ✓；后端全量 421 ✓；端点冒烟（清理 365 天/10000 条=0 无害、恢复/硬删不存在会话=404）

### AI-first 容量匹配：理解交给 AI、规则可配置（盘/内存/GPU 显存）
- **根因（用户实测）**："1T以上的硬盘" → LLM 照抄 capacity="1T以上" → 归一函数不认 → 盘需求被静默跳过 → 方案零硬盘 + 审计误报
- **契约反转（AI 干理解的活）**：drives/memory/gpu 槽位新增 `capacity_gb`/`per_stick_gb`/`capacity_gb`（数值）+ `comparison`（gte=以上/至少，lte=以下/最多）；两个理解 prompt 加示例（"1T以上"→1024+gte、"一tb/一t/1tb"→1024、"48G以上显存"→48+gte）。AI 把千变万化的自然语言归一成数值，不再靠正则枚举词
- **规则可配置（kp_reason 抽屉·匹配参数）**：新增「容量匹配策略」（容差近似/严格下限≥需求）+「容量容差 %」（默认 10）；AI 识别出 gte/lte 时自动按严格语义执行，不受默认策略影响
- **匹配器消费**：`_drive_spec_substitute`（盘）支持 comparison/strategy/tolerance；`_pick_mem_groups`（内存）按单条容量过滤；`_pick_gpu_groups`（GPU 显存）支持纯显存组（无型号）+ comparison/策略过滤——"48G以上显存"→ 选 ≥48G 件
- **实测**：①"兆芯+1T以上硬盘"→ comparison gte → 配出 1T NVMe（1024G），不再 960G；②"AI 服务器+2张48G以上显存"→ 配出 2× NVIDIA L20 48G；审计均 ok
- 测试：新增 ~12 个（盘 gte/strict_min/lte/容差、merge comparison 透传、GPU 显存过滤/纯显存组），后端全量 **421 通过**（412→421）；前端 vue-tsc + 60 测试 ✓

### 方案A：画布试运行改流式（完成一步显示一步）
- **根因**：试运行原为「同步 HTTP 一次性跑完 + 前端 setTimeout 快速回放」——后端含 LLM 单步 20~40s、13 步总耗时 1~3 分钟，期间前端干等，跑完才 3 秒内一口气列完所有步骤（用户反馈「等好久突然一口气列出」）
- **改法**（复用方案助手 WS 基建，不另起炉灶）：后端新增 `POST /test-run/start`（只注册 run_id，**首个 WS 订阅者连上后才启动后台任务**，杜绝漏掉首个 step_start）+ `WS /test-run-ws/{run_id}`（复用 `assistant_hub` 房间）；前端 `useTestRun` 从 HTTP 回放改为 WS 实时驱动——`pipeline_start` 预置全部步骤 pending → `step_start/step_done` 逐个亮起 → 终态带 ext/kp_by_model/plans/awaiting_input
- **实测**：真机跑通——`pipeline_start`(0s) → 需求理解 running → 29.7s 完成 → gap/llm_ask/scene/model(37.5s)/kp(123s)/…/review → pipeline_done，步骤逐步到达；`need_input`/`candidates_ready` 照常（P2C 交互反问不受影响）；旧 `/test-run` 端点保留兼容
- 验证：前端 60 测试 + build ✓；后端 412 全量 ✓

### 修复（真 bug，非装修）
- **💡 连线全损坏 + 弹窗风暴根因**：VueFlow 的 `isValidConnection` 会对**加载的每条边**也跑校验（`createGraphEdges`），查重函数用 `edges.value.some(...)` 时边还在列表里 → 每条边把自己判成「重复」→ 全部丢弃 + 刷「已存在相同连线」。修复：校验移到 `onConnect`（只在手动连线时），加载的边原样渲染
- **💡 active 流丢边自愈**：v12/v13 图重建时旧边引用旧节点 id 被过滤、新边未回填 → active 流 13 节点 0 连线（画布全节点「孤立」、编排器退化为无依赖平坦链）。新增 `migrate_v14_restore_default_edges`（幂等，启动自愈：默认节点集 + 0 边 → 恢复 v11 链），已修复线上数据
- 抽屉保存修复：extract / spec_compliance / audit_fix 三个节点之前不在 CONFIGURABLE → 保存按钮不出现（表单能编辑但存不进去），已补
- scene_decide 抽屉里「场景映射 JSON」是死配置（buildConfig 不保存）→ 删
- `ReasoningNodeKey` 类型补全 extract/spec_compliance/audit_fix；model_reason 也加载推荐策略（原只在 select_baseline 时加载 → 下拉为空）
- 非 condition 边的 source_handle（缺口/足够/答完回理解）VueFlow 找不到 Handle 不渲染 → 加载时归一到默认出口

### 🔄 撤回/纠正（去「屎山」层）
- 移除 persist 防误擦/防污染守卫全套（lastLoadedGraph / edgeDeleteIntent / lastReloadToast / applyFlow / 弹窗限频）——层层补丁产物，persist 回到「编辑即保存」；数据保护交给后端幂等迁移
- 移除「孤立未连线」黄色警告条、连线校验弹窗（其引入的 bug 已修复，校验不再需要）

---


### B：反问选项锚定产品目录（根治「问塔式但我们没有塔式」）
- **形态白名单从目录派生**（`capabilities._catalog_whitelist`）：forms 取目录机型的 `form` 字段（真实在售形态，去重），目录空才回退常量——系统里有什么形态就问什么
- **空选项兜底**（`_catalog_fallback_options`）：LLM 选项全被白名单过滤（如只给塔式）→ 按缺失项从目录给合法选项（形态→forms / 类型→types / 系列→series），反问永远带真实在售选项
- **委托选项放行**：不确定/你推荐/随便 这类选项保留（AI 开与 AI 关目录引导一致，客户随时可把决定权交回系统）
- **删死配置 `use_catalog_options`**：后端逻辑从不读它（白名单过滤是硬保证不是可选开关），误导性配置按「该删的删掉」移除（默认配置 + 画布抽屉 + 存量 DB 键）；`_LLM_ASK_PROMPT` 去掉硬编码形态表（形态由 user 消息动态给）
- 验证：`tests/test_llm_ask_catalog.py` 9 用例（塔式过滤 / 空选项兜底 / 委托保留 / 形态派生 / 回退）
- **形态来源修正（2026-08-09 追问「目录加形态 AI 会自动加吗」发现）**：机型自身无 `form` 列，真实来源是 `l6.base_configs.form`（当前目录实际只有 2U/4U）。此前 `_catalog_whitelist` 读 `m["form"]`（空）→ 回退硬编码常量 `1U/2U/4U/5U/6U/8U`——**反过来会反问目录里没有的 1U/5U/6U/8U**。已改为读 `base_config.form`（顶层 form 兜底），目录加形态（如新增 3U 基准配置）→ 白名单/AI 反问自动出现（已实测）

### C：审计意见喂回编排 agent（自纠有 LLM 参与，仍受确定性红线约束）
- 新增 `_decide_retry_targets`：audit_fix 检出问题后，把审计意见（llm_audits/spec_issues）作为 observation 喂给编排 agent，由它决定**可选重跑项**（llm_audit 再审 / audit_fix 再自纠 要不要）
- **重建脊梁强制保留**（kp_reason→spec_compliance→compose→budget_check，retry_scope 子集配置驱动）：修复的确定性后果，LLM 不能跳过、不能改数据、不能提前 final
- `_retry_mode` 重跑链改为**只跑目标能力**，跑完退出恢复正常 LLM 编排（不越跑、不提前 final）；AI 关/LLM 失败 → 全量重跑（现状兜底）
- 修复真实调用问题：prompt 缺 "json" 字样导致 json_object 格式被 API 拒（400），已补
- 验证：orchestrator 新增 4 用例（脊梁保留/越界丢弃/失败兜底/重跑模式只跑目标后恢复）；真实 LLM 实测——AI 服务器缺 GPU 场景，LLM 决策只重跑脊梁、不再重复审计（符合预期）

---

## [0.1.45] - 2026-08-09 — 编排器读画布拓扑（A 方案）：能力链不再硬编码

- **背景**：Graph Orchestrator 的能力清单/依赖是代码硬编码（`CAPABILITIES` 11 步链），执行只读 `node_configs`，**不读画布图的 nodes/edges** —— 用户在画布上改图对执行无感（「画布改了没反应」根因）
- **图 → 编排器**（`reasoning_orchestrator._derive_capabilities`）：从 active 流画布图实时派生能力链（拓扑序）
  - 节点分类：能力节点（type 有后端 handler）/ `llm_ask`（反问动作）/ `extract`（AI 失效兜底）/ `condition`（透明桥，入边源→出边目标直连）
  - deps = 过滤后的直接前驱能力节点；边 handle/condition 不参与（能力池全执行、LLM 选顺序）
  - 图缺失 / 能力 DAG 成环 → 兜底默认链（由 DEFAULT_GRAPH_V11 种子图经同一套推导函数算出，非第二份硬编码拓扑）
- **确定性红线去硬编码**：`deterministic` 移到节点配置（画布抽屉开关），默认 = 原硬编码集合（spec_compliance/compose/budget_check/audit_fix/review）；编排 prompt 的动态红线清单从配置读
- **按 type 派发**：`_dispatch` 传节点 type 而非 id（用户加第二个同类型节点如 `model_reason_2` 也能真正执行）
- **配套修复**：`_VALID_NODE_KEYS` 补齐 v12 key（此前 understand/model_reason/… 抽屉保存会 400）；新增 `migrate_v13_cleanup_orphan_configs` 清理图里已不存在的孤儿配置（cond_gap/ask_user 残留）
- **验证**：新增 6 个图派生单测（v12 图=兜底链逐节点一致 / 改图跟随 / condition 透明桥 / 成环兜底 / 空图兜底 / 确定性配置驱动）；实验：model_reason 拆两个节点 → 编排器按新图执行且真正出结果；后端全量 399 通过、vue-tsc ✓、npm test 60 ✓

---

## [0.1.44] - 2026-08-08 — 智能体 search_cases 案例检索升级：字符 2+3-gram + TF-IDF 加权（A 方案）

- **背景**：CBR 案例检索原为裸字符 2-gram 集合重合——英文词（GPU/NAS）被拆成噪声 2-gram、长需求因字多天然得分高（长度偏差）、每条都有的「服务器/机箱」淹没「深度学习/训练」等有区分度的词
- **方案**（`case_provider.py`，零依赖，不引 jieba / rank_bm25 / Whoosh / 向量库）：查询与案例需求先归一化（小写、去空白标点，只留 CJK+字母数字），取字符 2+3-gram；IDF=log((N+1)/(df+1))+1 平滑加权，案例/查询向量=(1+log tf)×idf，TF-IDF 余弦相似
- **行为**：3-gram 保英文词与中文短语；罕见有区分度的词由 IDF 放大；余弦消掉文档长度偏差；标签命中仍各 +0.3 加权（tags_keyword 默认模式，tags / keyword 两种旧模式保留）；案例库长大再走 ExternalRagProvider（向量检索）
- **验证**：新增 `tests/test_case_provider.py` 9 用例（归一化 / gram 计数 / TF-IDF 排序 / retrieve 排序含 mock session）；真实案例库 6 条对比——AI/GPU 查询命中 AI·8卡GPU 案例、不再被长文本通用 2U 案例压过；`test_nic_qty_binding` 端到端 3 个改为注入假 baseline（不再依赖 select_models 从文本猜机型，与 extract 收窄新语义对齐）；后端全量 393 通过

---

## [0.1.43] - 2026-08-08 — 基准配置「机箱能力约束」可配置化（PSU 档位 / CPU·内存上限 / 每路通道数）

- **背景**：对照 ES22V3-P 用户手册（AMD 9004/9005、24 DIMM DDR5、PSU 仅 1300/1600/2000W），发现 PSU 推断可能产出机型不支持的 2700W、CPU TDP 表缺 9005 500W、内存/CPU 数量无上限校验、内存选型按 Intel 8 通道启发式（EPYC 应为 12ch/路）——均为硬编码/黑盒
- **基准配置新增 4 个可配能力字段**（`l6.base_configs`，机箱能力卡可配、缺省走全局兜底，拒绝硬编码）：
  - `psu_wattages`（JSONB）：允许的 PSU 瓦数档位，如 ES22V3-P=[1300,1600,2000]；空=不限沿用全局
  - `max_cpu`（默认 2）、`max_dimm`（默认 24）、`mem_channels`（默认 12，EPYC 12ch/路）
- **推理链路消费**（`candidate_search.py`）：
  - `_infer_psu_wattage` 结果收敛到机型档位（`_clamp_psu_wattage`：取 ≥ 推断值的最小档，超上限取最大档）
  - CPU TDP 优先读配件库 `specs.tdp`（9005 等新 SKU 在配件库配即可，不再改代码），型号表仅兜底
  - `_pick_memory_part` 目标条数按 `mem_channels × CPU 路数`、上限按 `max_dimm`（未配保持旧行为）
- **校验规则**（`compatibility_rule_repo` 默认规则 +2）：CPU 颗数超 `max_cpu`、内存条数超 `max_dimm` → `selection_alerts` warning（规则引擎 WHEN 支持 `config.max_cpu` 交叉寻址）
- **前端**：基准配置页机箱能力卡新增 PSU 档位（tags 多选）/ CPU 上限 / 内存上限 / 每路通道数输入；`chassisMeta.PSU_WATTAGE_OPTIONS` SSOT
- 验证：pytest 新增 7 用例（PSU 收敛/TDP 数据驱动/内存目标条数/超上限规则）全过；vue-tsc ✓；npm test 56 ✓；test_scene_analyzer 3 个图级失败为既有环境问题（stash 验证与本次改动无关）

---

## [0.1.42] - 2026-08-05 — 配件管理：分类移到顶部胶囊条，侧栏只留规格筛选

- **左侧栏瘦身**：分类列表（全部 + 各分类 + 计数）从 `category-sidebar` 上移到页头下方的分类胶囊条（`category-nav-bar`）；「管理分类」入口移到胶囊条右侧齿轮按钮
- **侧栏只留筛选**：侧栏 `v-if="hasSelectedCategory"`，仅渲染 Brand + 规格维度折叠组；未选分类时侧栏隐藏、内容区全宽；选中分类但无筛选维度时显示提示
- 复用此前预留的 `cat-chip` 胶囊样式，修正其 hover 依赖的未定义 token（`--cpq-overlay-a6` → `--cpq-overlay-a8`）
- **筛选交互改列表勾选**：左侧筛选从胶囊 chips 改为「勾选框 + 名称 + 计数」列表（勾选框在左）；点行文字 = 单选切换（该维度只看这一个值，再点一次取消），点勾选框 = 多选累加/取消，不再点一下误选；「已选」横条（搜索栏下方）整条删除，清空入口移到侧栏「筛选」标题行右侧
- **筛选列表不再重排**：去掉「已选优先显」排序，勾选/点选后列表保持原有顺序、选中项原地高亮，不再跳到首行
- 验证：vue-tsc ✓


## [0.1.42] - 2026-08-05 — 配件管理：分类移到顶部胶囊条，侧栏只留规格筛选

- **左侧栏瘦身**：分类列表（全部 + 各分类 + 计数）从 `category-sidebar` 上移到页头下方的分类胶囊条（`category-nav-bar`）；「管理分类」入口移到胶囊条右侧齿轮按钮
- **侧栏只留筛选**：侧栏 `v-if="hasSelectedCategory"`，仅渲染 Brand + 规格维度折叠组；未选分类时侧栏隐藏、内容区全宽；选中分类但无筛选维度时显示提示
- 复用此前预留的 `cat-chip` 胶囊样式，修正其 hover 依赖的未定义 token（`--cpq-overlay-a6` → `--cpq-overlay-a8`）
- **筛选交互改列表勾选**：左侧筛选从胶囊 chips 改为「勾选框 + 名称 + 计数」列表（勾选框在左）；点行文字 = 单选切换（该维度只看这一个值，再点一次取消），点勾选框 = 多选累加/取消，不再点一下误选；「已选」横条（搜索栏下方）整条删除，清空入口移到侧栏「筛选」标题行右侧
- **筛选列表不再重排**：去掉「已选优先显」排序，勾选/点选后列表保持原有顺序、选中项原地高亮，不再跳到首行
- 验证：vue-tsc ✓

## [0.1.41] - 2026-08-04 — IO/Riser 数据补齐 + 基准配置编辑器补 UI + 防简介保存清字段

- **IO 空根因**：ZS22V2-P 基准配置（bc 20）`config_content` 只有测试残留（`{"spec_diff":"22222","description":"123123"}`），没配 `standard_riser`/`riser_x16` → 模板 eval 走"未配置留空手填" → IO1/IO2 空
- **bc 20 数据补齐**（Polaris 2U12 三模版）：`standard_riser={"IO1":"1*X16+1*X8 FHFL","IO2":"1*X16+1*X8 FHFL"}`、`riser_x16="1*X16+1*X8 FHFL"`、`standard_mem_speed="4800"`（技术员单口径；顺带清掉 UI 会显示的测试残留文案）
- **基准配置编辑器补 UI**：原页面只有 rear_slots（IO1-4 + 容量），`config_content` 无编辑入口（文档超前于 UI）→ 新增「IO/Riser 与内存速率」编辑区：各 IO 槽 `standard_riser`（按槽位 dict）+ `riser_x16` 升级规格 + `standard_mem_speed`；留空的槽不落库=手填；`ConfigContent` 类型同步扩展
- **修 clobber 坑**：ModelEditorPage 保存"简介"原来整体替换 `config_content`（只带 description/spec_diff）→ 会把 standard_riser 等字段清掉 → 改为合并保存（保留 riser/内存字段）
- 实测验证：该需求重跑 → IO1/IO2 = 1*X16+1*X8 FHFL、Memory = 32GB DDR5 4800（对齐技术员单）；pytest 282 · vue-tsc ✓ · npm test 56 ✓

## [0.1.40] - 2026-08-04 — 代码瘦身第一轮：删一次性脚本/死代码/死依赖（-4k+ 行）

- **一次性脚本 36 个（~3100 行）**：`backend/scripts` 45→9。删 migrate_*/seed_*/drop_*/clean_*/diag_*/update_bom_template_* 等已执行完的脚本；保留 6 个长期工具（replay_cases/simulate_requirement/online_verify/audit_reasoning_batch/strategy_insights/analyze_kp_data）+ 3 个被前端注释当同步契约的脚本（seed_pricing_strategies/seed_strategy_fields/migrate_base_config_capability）
- **requirement_check 死代码整段拆除**：0.1.36 已从流程删节点，本轮把残留全清——executor handler、linear fallback 调用、PIPELINE_STEPS 条目、`_VALID_NODE_KEYS`、默认节点配置、v6 迁移方法 + startup 调用、`check_plan` 全家桶（DEFAULT_CHECK_CONFIG/load_check_config/helper）+ 9 个对应测试、前端 RequirementCheck 类型/字段/IO 定义/步骤文案/节点抽屉表单；DB 清 30 条孤儿 node_config；`audit_plan`（review 校对）保留
- **死文件/死依赖**：`bom_similar.py`+test（experience_alerts 引擎，0.1.38 已下线，零引用）、前端 3 个零引用组件（ActivityStream/ShowcasePreviewModal/SelectionNode）、`selectionConfig.ts`（已删画布的配置）、`dagre.d.ts`+package.json 移除未用 `dagre` 依赖、旧 `scripts/_backup/` 6 个 BOM 模板备份
- **死常量**：`requirement_checker._PLATFORM_SERIES`（只定义未引用）
- **过期注释 3 处**：startup.py / ruleMeta.ts / bomRuleEngine.l6.test.ts 里指向已删脚本的引用
- **llm 占位节点拆除**：通用 `llm` 节点（role=extract_enhance）从未被任何流程图连接（34 个 flow 全无），其能力已被 extract 节点自带 enable_llm 增强取代 → 删 executor handler/默认配置/_VALID_NODE_KEYS/前端 palette/抽屉表单/IO 定义 + 2 个 dispatch 测试 + DB 32 条孤儿 node_config；extract/scene/review 三节点自己的 enable_llm 开关保留
- 验证：pytest 284（-18 测试：9 check_plan + 5 bom_similar + 4 其他）· vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归（BI 0 差异）

## [0.1.39] - 2026-08-04 — 国产 CPU 厂商分家：Polaris=兆芯，KH-50000 不再标"海光"

- **根因**：系统只有"系列"维度没有"芯片厂商"维度，Polaris 被当成"信创大杂烩"桶（兆芯+海光+飞腾+鲲鹏混装），"海光"又被当成 Polaris 代称 → 用户需求 `KH-50000`（兆芯开胜）被整条链路当成海光
- **口径定论（用户确认）**：Polaris 只配兆芯、Orion 只配 AMD；海光/飞腾/鲲鹏/龙芯不是 Polaris
- **改动（代码 + 配置双修）**：
  - 系列词表摘除海光/hygon：extract 节点 lex_series（默认 + active 流配置）+ scene_mapping series_hints（默认 + system_config）→ `KH-50000/兆芯/zhaoxin/开胜/开先` 独属 Polaris
  - CPU 平台过滤按厂商分家（candidate_search）：需求点名厂商 → 只留该厂商家族（海光需求绝不落兆芯 KH/KX）；只写"信创/国产"或平台=Polaris → 留兆芯家族；`_XINCHUANG_RE` 补"国产"；修中文前缀 `KH` 词边界不匹配问题
  - review 校对厂商感知（requirement_checker）：海光/飞腾/鲲鹏/龙芯需求不再提示"应为 Polaris"，海光需求配 Polaris（兆芯）也 blocked
  - 系列确认别名（requirement_intel_service）："海光"→Polaris 别名删除，只留兆芯/开胜/信创/国产
  - 前端 chassisMeta 常量 `REAR_SLOTS_2U_HAIGUANG` → `REAR_SLOTS_2U_POLARIS`（Polaris=兆芯）
- **验证**：pytest 298 · vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归；`KH-50000` 需求实测 → ZS22V2-P（Polaris）CPU=KH50000×2、事件零"海光"、audit ok；`海光` 需求实测 → 系列 None + 校对 blocked（Polaris 是兆芯不能替代海光）

## [0.1.38] - 2026-08-04 — experience_alerts 在线展示下线（案例库防偏差误报噪音）

- **用户实测**：ZS22V2-P（兆芯 KH-50000）需求被 `attach_experience_alerts` 拿 ES22V3-P（AMD）案例做规格级对照 → 跨平台满屏差异（CPU platform/HDD cap/iface/Memory speed/NIC/数量…）
- **处理**：review 节点不再挂 `experience_alerts`（案例库对照只保留在训练 bom_compare/重放），PlanCard 撤掉 experience_alerts 展示；在线"重大偏差"由 audit_plan 硬校验兜底（缺件/平台冲突/严重超预算）
- 方案卡最终只剩「校对通过 ✓ / 需修改：…」，零噪音警告
- 验证：pytest 290 · vue-tsc ✓；海光需求实测：requirement_check 不存在、experience_alerts=0、selection_alerts=[]、audit ok

## [0.1.37] - 2026-08-04 — 阶段 2：LLM 接入（extract/scene/review 三节点增强 + 节点级开关 + 槽位清单可视化）

- **LLM 三节点接入（每个节点抽屉独立开关 enable_llm && 全局「设置-AI 设置-启用 AI」双重约束）**：
  - extract：LLM 结构化抽取并入 extract 节点（`run_extract_enhance`，schema 收口 + merge 只补缺、规则赢、能力声明不产配置）；失败降级规则结果
  - scene_analysis：`run_scene_infer` 规则推不出系列时 LLM 从语义补推断（如 A800 8卡→Orion），明说/已定不动
  - review：`run_llm_audit` 语义校对（方案是否真满足需求意图），规则硬校验兜底；LLM 存疑 → status=review（需人工确认）
- **节点抽屉 UI**：extract/review/scene_analysis 抽屉顶部加「启用 LLM 增强」开关；llm 节点保留（通用）
- **槽位清单可视化**：新增 `SlotListEditor.vue` 放 clarity_check 抽屉（编辑全局 `requirement_slots`：L0/L1/L2 层级 + label + default_ok + 反问阈值），替换已弃用的信号规则编辑
- **降级验证**：extract enable_llm=True 但 LLM 未配置 → chat_json 失败 → 静默降级规则，不阻塞主流程
- 验证：pytest 290 · 前端 vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归

## [0.1.36] - 2026-08-04 — 需求分析流程重构（R29）：槽位覆盖度 + 系列确认 + AI 统一开关 + 删差异报告

- **删 requirement_check**：在线「需求核对差异报告」实测警告泛滥（把库缺口/替代/措辞全当警告）→ active flow 移除节点 + PlanCard 撤警告行；`bom_compare`/重放（训练对照）保留
- **明确度=槽位覆盖度**：`requirement_slots` 期望清单可配置（L0 底线[场景/系列/CPU/内存]/L1 重要[形态/GPU/网卡]/L2 推导[RAID/电源]），`evaluate_slot_coverage` 按已填槽位差距判 explicit/partial；存储 default_ok（缺了给默认盘），AI 场景缺 GPU 反问
- **系列确认 confirm_series（新节点）**：scene_analysis 输出 `series_source`（explicit=需求明说 / inferred=系统推断）+ `scene_determined`；cond_scene 判据改 `scene_determined`；推断系列→问「是否 XX 系列？」，推不出→列在售系列选，明说/已确认→直接选型；答复（是/不是/系列名/平台别名）解析持久化 `requirement_confirmed_series`
- **review 改校对**：`audit_plan` 阻塞式 通过/不通过 + 必改项≤2（缺 CPU/内存、信创需求配非信创、严重超预算），挂 plan.audit，PlanCard 展示「校对通过 ✓ / 需修改：…」
- **AI 统一设置**：`llm_config.enabled` 全局开关（设置-AI 设置-API 设置「启用 AI」），`llm_client.stream_chat/chat_json` 统一 gate + `is_llm_enabled()`；关闭后所有 AI 能力走规则/不调 LLM，llm 节点双重开关（节点 enable_llm && 全局）
- 验证：pytest 290 · 前端 vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归（BI 0 ✓）

## [0.1.35] - 2026-08-04 — ESA24V3-P（4U）首测：RAID 显式型号分组 + NIC SKU 归一 + PSU 冗余数量

- **RAID 显式型号分组（R28）**：需求逐行给阵列卡型号（`RAID卡：LSI 9560 16i 8G缓存 *1`）→ `_extract_raid_groups` 归一 `9560-16i` 按组精确出件（不再泛配 9540-8i）；stage-1 跳过 RAID 组 token（含完整型号串，修 BI/LLW 回归），无型号（RAID 0,1,10）交回 I22 applicable 兼容选件
- **NIC 型号归一**：`X710DA2BLK` 去 BLK 后缀 → 命中库件 `Intel X710-DA2` 含光模块（原选国产无光模块件）；连字符归一放匹配侧（保留 ConnectX-6 形态）；`光口含模块/含模块` 识别为光模块信号
- **PSU 冗余数量（R28）**：`2700W 2+2/3+1冗余` → 4 个（N+M 求和；原按「冗余=双电源」出 2）；4U 8 卡机电源 2700W×4 对齐技术员单
- **噪音过滤**：`TDP360W`（CPU TDP 连写）不再当型号 token 报 unmatched
- **新案例入库**：ESA24V3-P · HK-2026-0707（4U8-Switch，model_id=16 / bc25 / tpl3），校对 BOM 以技术员单为准；待确认：GPU A800 需求 ×2 vs 技术员 ×8、Switch 行 `3*X16` 口径、L6 文案 KH50000 vs AMD 实配
- 验证：pytest 283 · 重放 5 案例（BI 0 差异 ✓ / ESA24 3 [GPU业务+2库缺口] / YLL 1 / YC 1 / LLW 3 已知）

## [0.1.34] - 2026-08-04 — IO/Riser 配置经验沉淀 + 对照引擎 riser 内容级比对

- **riser 数据驱动落地（R25/R26/R27）**：`config_content.standard_riser`（默认，per-slot dict、大小写不敏感）+ `riser_x16`（GPU/100G 升级）；未配置留空手填，零硬编码。ES22V3-P 三连版=满配 `1*X16+1*X8 FHFL`、直连版=预算 `1*X8 FHFL`（对上 LLW/BI/YLL 技术员单）
- **对照引擎新增 riser 内容级比对**：行数一致时比槽位规格（`_riser_signature` 归一，`2*X8` vs `1*X16+1*X8` 报 l6 差异；FHFL 形态词/槽位顺序不算）→ 重放立即抓出 YC IO2=2*X8 缺口（待更多样本定 per-slot 覆盖）
- **经验与规则入系统**：文档写入「策略中心-选型配置-📄文档库」（`rules.policy_docs` module=selection，操作指南「IO 与 Riser：配置经验与填充规则」）——联网调研 + 4 案例实证 + 填充规则 + 改哪里
- **Riser 配置优先级文档**：文档库新增操作指南「Riser 配置优先级：系统自动填充规则」（sort_order=4）——系统自动填充 IO1/IO2 的可执行优先级（GPU→全槽 riser_x16 / 100G+ 网卡→IO1 riser_x16 / 否则 standard_riser / 未配置留空手填）+ 实测输出表 + 数据改哪里
- 验证：pytest 277 · npm test 56 ✓

## [0.1.33] - 2026-08-03 — 需求分析收尾：意图感知开场白 + 完整清单直接出 BOM + 推理 BOM 完整性

- **对话更聪明**：意图感知开场白（你好→问候 / 我要服务器→问用途 / 贴规格→识别）；"你帮我推荐/你定"= 全局授权直接出方案（区别于"还没定"只跳当前字段）；负载原型按原文匹配（最近补充 > 全文 > usage），修"数据库/OLTP"被 server_type 词表折叠后错配"通用/Web 业务"；删开场白"现成配置清单"引导（已贴清单还问清单=荒谬）
- 💡 **完整配置清单直接出 BOM**：clarity 新增 4 规则（品类≥4+内存/型号→明确、型号token≥3→明确、品类≥3+内存+用途→明确）；无规则命中兜底改按信号推导缺口（修"请补充需求描述不够具体"假死循环）
- **推理 BOM 完整性**：`buildPlanCfg` 接料号库后面板数据——IO1/IO2=1×X16+1×X8、OCP=X8、按 KP 盘型推线缆（SATA/SAS÷8、NVMe÷2，镜像 CRE）、NVMe→背板 tri；模板 Cable 行 manual→推导（改动已备份 `backend/scripts/_backup/bom_template_1_20260803.json`）
- **内存解析**：`DDR564G*8`=DDR5-64G×8=512G（原把代际"5"算进容量→564G→9 条）；`_extract_mem_signal` 加代际剥离 + 单条×条数
- 验证：pytest 92 · `npm run build` ✓ · `npm test` 48 ✓

## [0.1.32] - 2026-08-02~03 — 需求分析对话机制（反问修复+负载引导+会话重置）

> 合并原 0.1.39 / 0.1.40 / 0.1.41 / 0.1.42 / 0.1.43 / 0.1.44 六条。
- **反问三连修**：① cond_clarity 阈值写反（只对 unclear 反问、partial 放行）→ 改非 explicit 都反问；② 补充不累积"没记性"→ `requirement_clarity_base/supplements` 跨轮持久化；③ round 跨会话不重置→重新生成报价=新对话重置 round=0（清理 3 存量卡死商机）
- `model_token_in_category` 原失效（"EPYC9354"不含"CPU"）→ 型号→品类关键词表；extract 加 `usage_inferred` 区分"用户明说/系统兜底"
- 死循环防护：轮次上限 3→6；修 R-22 编辑事故（赋值行丢失→NameError→假死循环）+ 防回归测试
- **Spec Assistant 式引导**：新规则类型 `workload`（6 负载原型 + drill_down 追问树，策略中心 ask_user 节点可 CRUD）；首轮抛负载菜单、选 AI→问 GPU；`_field_satisfied` 防跨轮重复问
- **M1 会话语义**：`_merge_clarify_text` 新对话清空旧补充（修"重复上一轮"）；一次一问 take=1；"不确定/你推荐/还没定"=已答只跳当前字段；推理面板「🔄 重新开始」按钮
- LLM 预留（不接，离线可跑）：llm 节点 passthrough + `chat_json()` 桩（extract_enhance / question_gen / best_fit 三 role）

## [0.1.31] - 2026-08-02 — 需求→BOM 引擎校正（训练循环）

> 合并原 0.1.33 / 0.1.34 / 0.1.35 / 0.1.36 / 0.1.37 / 0.1.38 六条。
- 🔄 **BOM 填充层位纠正**：PSU/后面板填充从 `build_plan.bom_excel_rows` 回退（那是无模板 excel 兜底路径，模板模式不读）→ 改 `chassis_signals.psu_wattage` + 前端模板渲染；修 `deriveVars` gpu_qty/drive_count/psu_qty 全 0 bug（GPU/盘不在机箱件里）
- 🔄 OCP 不再自动填（2 轮真实样本：网络走 PCIe 网卡 KP 件、从不占 OCP，推翻 Dell 行业假设）；IO1/IO2 有 GPU 才填 X16 Riser
- PSU 瓦数按 GPU 分档：≥8 高功耗→2700W / 有 GPU→2000W / 无→1600W（修 R9700 误估 2700）
- KP 数量串台(R-6) + 过匹配(R-8)：数量解析改位置绑定+方向感知（修 SSD 盗内存 16、GPU 漏 ×1、NIC 串 8）；stage-1 跳纯容量碎片、Memory 交容量反推
- 型号正则修 H100/A100 漏匹配(R-15)：加 `[A-Za-z][0-9]{3,}` 分支；非 AI 需求 abort 修复（规格清单无用途词→usage 兜底"通用计算"）
- 🔄 撤回 4U 补件：4U=整机箱 lump 是有意的（未拆件，L6 行偏粗是预期）；GPU电源线属按 GPU 数人工加、不属机箱标配层；风扇占位件 `S.E.M.0000501` 挂 2U ×6（价 0 待补）
- R-17 Cable 调研（未实现）：SAS→Mini-SAS 线、NVMe→PCIe/MCIO；模板 `struct_count(front_cables)`+`frontCableQty` 机制已备、仅推理喂 0

## [0.1.29] - 2026-08-02 — 机箱能力主数据对齐

> 合并原 0.1.31 / 0.1.32 两条。
- 15 份真实配置校准 5 类底座（AMD/海光 × 2U/4U × 直连/Switch）；4U GPU 槽恒 8；OCP 是 AMD 平台特性（海光 2U 无、4U 有）
- 后面板槽位标准化：`chassisMeta` `REAR_SLOTS_2U_AMD/HAIGUANG/4U` + `rearSlotsFor(form,series)`；「恢复标准布局」按 form+series 取模板
- 能力档案回填 `backfill_chassis_capability.py`（4U→psu=4/gpu=8、2U→psu=2、2U 海光去 OCP），10 条校正（不覆盖已填值）
- 🔄 4U 后面板纠正：`REAR_SLOTS_4U` 从误克隆 IO1-4+OCP → 仅 OCP（GPU 槽与 IO 槽物理分区）；4U GPU 走 gpu_slots=8 + gpu_arch(direct/switch)
- 待确认：ZSA24V2-P gpu_arch 建议 switch；id=21/24/26 数据不一致；内存速率分档待权威 MT/s

## [0.1.28] - 2026-08-01~02 — 选型配置重构（L0/L1/L2 架构）

> 合并原 0.1.28 / 0.1.29 / 0.1.30 三条。
- 💡 **两层兼容架构**：L0 机箱能力档案（base_config psu_bays/rear_slots/gpu_slots/max_tdp）+ L1 配件适配（料号库 specs 声明，`partFit.ts`）+ L2 跨件规则 CRE（require/exclude/derive/recommend）
- CRE 双端：`selection_engine.py`（Python 移植 selectionEngine.ts），DB 规则 SSOT 双端共用；补 3 条 exclude 互斥（同型号不混搭）；`seed_missing_defaults` 按名补种
- 硬编码清零：`chassisMeta.ts` SSOT、L6ChassisConfig 清 5 处硬编码、GPU 架构读 `gpu_arch_default`
- 兼容规则加"业务分类"维度（category 列，仅组织用；编辑器分类过滤条+主题分组；API `?category=`）
- 机箱能力并入 `BaseConfigEditorPage`（修 save payload 写死 gpu_arch_default='none' 的 clobber bug）；删冗余 ChassisCapabilityEditor；选型配置瘦身两标签；PartFitMatrix 迁服务器管理（L0/L1 目录主数据归服务器管理、仅 L2 CRE 归选型配置）

## [0.1.27] - 2026-08-01 — 推理流编排可解释性

- 节点 IO 元数据（`reasoningNodeIo.ts` consumes/produces）+ 试运行步骤显示输入/输出；方案卡「回溯路径」高亮生成链；palette 三环节分组；condition 分支必连校验（防路由死路）
- 明确不做：全改显式变量系统、单节点调试、LLM 节点化（二期）

## [0.1.26] - 2026-08-01 — 需求分析试运行 + 两个潜伏 bug

- 画布加试运行 playground：`POST /api/reasoning-flow/test-run` 复用线上 `run_graph_executor`（force_complete 跳反问），节点逐步高亮+IO 明细+候选方案；抽 PlanCard/useTestRun 共享
- ⚠️ simpleeval 从未进 requirements（缺它 `_eval_condition` 永远 True → cond_clarity 永远反问）；build_plan 货币混算（USD 件当 RMB 混加，按 `store/quote.ts` 口径折算成含税 RMB）

## [0.1.25] - 2026-07-31 — 策略文档库

- 报价策略加左目录（定价策略/策略文档）；文档复用 `rules.strategies`（domain=policy，零新表）；marked+dompurify Markdown 渲染；5 篇定价手册种子（空表才灌，绝不覆盖用户改动）
- 推迟：版本快照/回滚（改动直接覆盖）

## [0.1.24] - 2026-07-30 — 报价策略重构：查表→加法定价引擎

- 💡 定价模型：查表三档 → 六维加法叠加（平台+行业+区域）×订单×成本×台数，夹 [保底,封顶]；7 条维度策略、零新增列
- 纯 TS 引擎 `pricingEngine.ts`+单测；`pricingMeta.ts` 维度元数据 SSOT；VueFlow 固定流水线画布+维度抽屉+演算器；工作台告警 floor 改 guardrail（仍只警告不锁价）
- 移除旧 scope→三档模型（PricingStrategyCanvas、MarginTier、seed）；L3 溯源输出 pricing_additive

## [0.1.23] - 2026-07-30 — 选型配置大整理：清退 DerivationEngine

- 💡 线缆/背板规则收敛进 CRE 唯一真相源：删 `derivation_engine.py`、`/api/derive`、DerivationRulesPanel；SATA/SAS÷8、NVMe÷2、GPU 供电线、背板 tri（含 NVMe→tri）迁入 CRE；删整机功耗/PSU/Switch 三条规则
- `ruleMeta.ts` 元数据 SSOT（规则类型标签/语义色/算子符号/ctx 字段）；选型配置页重做（紧凑卡片+弹窗编辑+三列因果流拓扑）
- 修 NVMe 线缆恒 0（`"NVME".includes("NVMe")` 恒 false）→ 引擎层 `normalizeDriveKind` 大小写无关 + 优先读 KP specs
- 移除"按商机平台过滤候选机型"filter 规则（只过滤候选机型、与基准配置下拉表现不一致）

## [0.1.22] - 2026-07-30 — 回退 Excel 表头自适应列定位

- 🔄 移除 0.1.20 引入的 `header_labels` 自适应列定位：频繁定位错列（子串匹配误命中）、扫描窗口难覆盖所有排版、与显式 `col` 双真相冲突 → 回归固定列字母 `source_config.col`（所见即所取）；存量 header_labels 自动忽略无需迁移

## [0.1.21] - 2026-07-30 — 趋势洞察下沉为方案助手快捷指令

- 删商机线索页趋势洞察卡片、`/api/dashboard/ai-insights`、`ai_insights_config` → 并入助手「📈 分析本期趋势」快捷指令
- 快捷指令 prompt/context 支持函数；AI 设置可配 prompt 模板；新增 `/api/dashboard/trend-overview`（周/月/近半年聚合+重点商机，LLM 输出 8 段报告）
- 修 `get_trend_overview` 裸调路由函数 500（Query 默认对象被 strptime）——带 Query 默认值的路由函数不能当普通函数裸调

## [0.1.20] - 2026-07-29 — 清理 pricing_engine 历史包袱

- 💡 `pricing_engine` 1094→425 行（-61%）：拆纯算法引擎 + 业务服务（QuoteService，商机 CRUD 迁入）+ 解析器（ExcelParser）；删 7 个遗留解析方法、Excel 导出样式块、死导入；parse_file 统一走规则驱动（异常直接暴露而非旧实现掩盖）；`_safe_eval_math` 移入 excel_parser（替换 eval()）
- 删 l6/kp_region_config 残留（rules_repo/models/api 共 -263 行）+ 物理删表脚本 `drop_l6_kp_region_config.py`
- 商机详情页报价单解析预览弹窗（热力图+区域/字段规则可调）；Excel 表头自适应列定位（0.1.22 回退）
- 修报价单列表价格/利润不显示（回退误加的按 items 重算逻辑，直接读 quotation 表存量值）

## [0.1.19] - 2026-07-28 — 商机存储文件夹可读命名 + 附件清理

- 文件夹 `OPP-xxx` → `客户名_OPP-xxx`（客户名变更自动重命名+同步路径）；迁移脚本 `migrate_opportunity_folders.py`（--dry-run）
- 修附件物理文件残留：存档区删除、永久删除报价单 Feed 附件时同步清磁盘文件

## [0.1.18] - 2026-07-28 — 料号库体验

- 分页（50/页）、批量导入/导出（解析预览标注新增/更新/无效）、响应式（侧栏可折叠/移动端覆盖层）、卡片去圆角
- 修卡片泛白（玻璃层嵌套叠加近纯白）；PN 可编辑（此前不可编辑是误判）

## [0.1.17] - 2026-07-27 — 工作台规格书 + 行级货币 + 推理流增强

- 工作台规格书预览（SpecSheet+打印 PDF，后端零改动）；KP 行级 RMB/USD（QuotationItem.currency，按币种联动重算）
- ⚠️ 修 USD 计价放大 ~9 倍（税率/汇率是字符串，`1+"0.13"="10.13"`，源头统一 Number()）
- 推理流：结构化 BOM 解析（`3.84T×4+960G×2` 按件独立计数）、per-机型 KP 套餐、预算驱动选件、underspend/超预算双向标注
- 料号库 description 拆 `spec_text`/`description`；系列枚举统一 `system_config.server_series` SSOT；推理流硬编码挪前端抽屉可配（机型套餐/数量格式/型号正则/underspend/select 策略）

## [0.1.16] - 2026-07-23 — 料号库/驾驶舱/主题

- 料号库机型系列筛选；背板回归普通配件（不再走 bp_tri_pn/bp_dc_pn 特殊字段）；驾驶舱自定义时间区间+图表粒度自适应；列表排序
- 修主题切换被浏览器扩展篡改（MutationObserver 守护+首屏预写主题）、L6 价格历史快照丢失（l6_repo 写错 schema）、序列未同步（`sync_sequences.py`）、料号编辑 500
- 服务器管理面接入玻璃视觉系统；文档：Frontend_Style_Guide 重写（Soft Glassmorphism）

## [0.1.15] - 2026-07-17 — 清理

- 修预览数据不完整（preview 接口缺 quotationId）；移除冗余 `confirmed_price`（统一 base_price+final_price）、item 冗余 model_name/server_model

## [0.1.14] - 2026-07-16 — 修导出模板编辑器边缘发灰（Dark 主题暗角装饰罩住全屏编辑器，z-index 提升）

## [0.1.13] - 2026-07-16 — 修导出模板 L6/KP 保修字段预览错位（动态绑定插行未同步静态绑定行号，改用行偏移表累加）

## [0.1.12] - 2026-07-16

> ⚠️ 破坏性：SQLite 四库 → 单一 PostgreSQL（schema 隔离 opportunities/kp/l6/rules/l6_history/public），必须跑迁移脚本，旧 SQLite 不再兼容；`DATABASE_URL` 环境变量替代硬编码路径。

## [0.1.11] - 2026-07-11 — 导出模板 + 文档

- 动态绑定自动保存（bindingForm 深度 watcher，修切 tab 绑定丢失）；新增 CLAUDE.md / Pricing_Engine.md / Excel_Parsing.md / Engineering_Guide.md + API 路由文档补全 119 端点

## [0.1.10] - 2026-07-09 — 硬编码清理

- 后端路径 `DATA_PATH` 环境变量；前端 14 组件 100+ 处色值改 `--cpq-*` CSS 变量；CORS 读环境变量；新增 docs/README.md、Deployment.md

## [0.1.9] - 2026-07-04 — 项目文件管理

- 拖拽多文件上传、新建项目自动建标准文件夹；修详情页路由白屏、文件列表加载失败（filename vs file_name 字段名不匹配）

## [0.1.8] - 2026-07-04 — L6 三栏对比 + 导出模板引擎

- L6 三栏对比（需求/匹配/定价）；导出模板引擎（`${xxx}` 变量 + `#for` 循环块）+ 卡片 CRUD + 所见即所得编辑器；配置页预览复刻 Excel 结构
- L6 匹配：主板降级、机箱模糊匹配；修匹配引擎空指针、导出合并单元格错位、Excel 空行渲染横线

## [0.1.7] - 2026-07-03 — 文件归档/评论

- 文件按项目自动归档+实时扫描+重命名/删除/上传/打开；项目评论（@提及/回复）；工作台侧边栏（文件列表+评论流）双栏
- ⚠️ 修文件下载路径穿越（路径白名单校验，拒绝 ../）

## [0.1.6] - 2026-07-03 — 质保独立计算

- 质保服务费 L6/KP 独立计算；质保年限自动识别（"质保3年"→3 年）；质保卡片重构

## [0.1.5] - 2026-07-03 — 质保可编辑 + 修复

- CPU 价格 0 警告；质保可编辑（年限/费率）；L6 匹配状态显示；价格失焦重算；修前端税率多乘 13%、综合毛利率口径不一致

## [0.1.4] - 2026-07-03 — 导出规则 + 评论

- 导出描述引擎：循环块、动态分类（按配件类别自动分组）、拖拽排序、智能展开（空行自动跳过）；工作台侧边栏评论流

## [0.1.3] - 2026-07-02 — L6 价格库

- 五维规格匹配筛选（机箱/机型/盘位/PSU/主板）；卡片网格重构；抽 `L6SpecFilter` 公共组件

## [0.1.2] - 2026-07-02 — L6 匹配规则可视化

- 规则可视化配置页（拖拽排序/降级开关/模糊规则/多结果手选）；L6 匹配引擎增强（主板降级、机箱模糊）；"基准价格"更名"KP价格库"

## [0.1.1] - 2026-07-01 — 四库分离 + 规则在线化

- kp/l6/rules/cpq_platform 四库分离；规则在线化（Excel 锚点/L6 维度/KP 映射/主板映射）；KP/L6 在线 CRUD+价格历史趋势图；回收站软删除；项目管理看板

## [0.1.0] - 2026-06-29

> ⚠️ 破坏性：从旧系统（Streamlit 单体）全面重写为 Vue3+FastAPI 前后端分离，数据不兼容。

- 智能上传（Excel 拖拽→自动解析→多配置拆分→入库）；报价工作台（实时精算/独立调价/财务三维联动）；五维匹配引擎；质保按需；WYSIWYG 导出
- 技术栈：Vue3+TS+Vite+AntD+Pinia / FastAPI+SQLAlchemy / SQLite×4（0.1.12 迁 PostgreSQL）
