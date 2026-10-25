---
name: write-tools-foundation
description: 方案助手写操作工具六件套+上传暂存+ai_read现场视图+分组;碰写工具/加价/确认/上传/视图先看
metadata:
  node_type: memory
  type: project
  originSessionId: d74ea112-16a7-4281-bdb8-ead4ebd3b831
  modified: 2026-10-17T19:03:12.300Z
---

方案助手"能办事"的两批落地(2026-10-16):**第一批**=六个写工具+两阶段确认+价格门;**第二批**=聊天框上传+暂存跟随+ai_read现场视图+自然标识+记忆闭环v1+分组+死机制清理。

**Why:** 架构定调=不做页面自动化,工具直调与页面同源;入口=方案助手聊天框([[portal-ai-shell-pluggable]] 延伸);不做每轮上下文注入(用户否决情景块)——现场靠按需查。

**How to apply:**
- **与页面同源范式**:写动作懒导入直调 API 路由函数本体(权限/阶段门/通知零漂移);别手拼 repo 绕过连带效应
- **两阶段确认**:`agent_write_confirm.py` 服务端待确认记录(TTL10分钟、单次、按 thread+tool+参数摘要匹配,数值归一)。**大脑重调时带同一参数+confirm=true,不靠凭据往返**——token 不跨回合存活(历史只有文本),跨回合确认必须服务端匹配。**别复活 `approval_required`**——死机制已删(guard=identity),先执行后拦截且批准无回路。方案助手提示词已升级为"办事型人格+先理解再行动"(同事级 system_prompt 覆盖,旧共享兜底未动,备份在 Temp)
- **自然标识**:写工具收 customer_name(口误叫法也行),`_resolve_target` 解析(id>名精确>名模糊>会话绑定),歧义回 candidates 由大脑转述用户选——别再逼大脑先查ID
- **先看后落(2026-10-17定调)**:import_cost_sheet 不带商机=仅解析预览(analysis_only,零落库零归档),大脑先转述识别结果+从文件名推断客户再问;带 customer_name/opportunity_id 才落草稿+归档。**别把业务参数挡在价值前面**——工具契约的参数顺序会绑架对话顺序
- **聊天上传**:`POST /api/assistant/threads/{id}/attachments` → `save_scoped("threads/{id}")` 暂存(opportunity_id=NULL);配额10个/100MB、TTL7天懒清;发送随 attachment_ids 绑消息+进 turn_text;暂存件只属于上传者
- **暂存跟随**:`import_cost_sheet` 认暂存件,成功即归档商机桶(改绑+移盘+删暂存);archive_only+category=「把附件放到某环节」动词(lead_requirement/technical/requirement/sent_quote)
- **ai_read 视图**(P0-2):加了 flows/flow_nodes/cost_sheets/attachments/pricing_approvals。**红线:cost_sheets 视图只有元数据列——configs 是JSON、内含价格,query_data 的列级脱敏管不住 JSON 内部**;暂存行(NULL商机)被 INNER JOIN 天然排除=隐私
- **记忆闭环 v1**:import 带 parse_overrides+sheet_id 原地重导,结果带 fixation_hint 提示写同事记忆;**确定性模板固化推迟**(overrides→模板规则翻译重),v1 靠同事记忆存参数+确认闸兜底
- **加价率口径**:set_quote_margin 是 store/quote.ts recalculateAll 的后端镜像——**双实现漂移点**,动定价公式必须两处同步(远期:重算迁后端单一权威)
- **分组**:specs category 四类 workflow/business/data/self(默认 workflow),前端 toolMeta.ts 标签;分组只管目录/批量启用,不碰运行时权限粒度
- **待办①→已解决(2026-10-18,走路径B)**:交付链独立轻执行器已接线并全链走通。**案台原则**:引擎状态通道=登记表slots,交付产物在那没座位→事务管道自己的案台=每轮从业务真实表现现算(delivery_executor.state_view),步骤指针=流节点序第一个产物未落者(_STEP_PROBES 按节点键);大脑带全案台+当步工具白名单干活,产物落了指针前移续跑(每回合≤4步),没落停本步等用户。内核/应用已分离(2026-10-18 Windows化):`transaction_engine.py`=内核(只认契约:TransactionApp=探针表+旗标表+事实行+flow_key,注册表resolve_app,状态槽/案台/指针/事实回写全通用);`delivery_app.py`=首个应用(import即注册,交付域探针/旗标,零编排);`transaction_turn.py`=轮壳+_dispatch(real_bound→注册表查应用,未安装→降级工具聊天绝不进需求分析机器,其余→引擎;fresh=True干净重开清状态槽)。**新事务工作流=种一个流+写核心函数+写一个App声明注册**。状态槽=reasoning_state key={state_slot}:{role_key}(只存加价/分享旗标,装填时清)。**E2E 实测 169.9s/4回合全链通**,每道闸机械生效。堵洞:set_quote_margin 的 confirm 分支原先不过闸(momentum 直呼 confirm 可绕预览)→已改与 submit 同形,先消费待确认记录才执行。布局守卫:transaction_turn 已登记 OWNERS;service 三处调用点统一走 dispatch_flow_turn(flow_key 参数,fresh 参数)。
**M3 目录改版已落地(2026-10-18)**:①型别徽标=/api/ai-colleagues/skills 列表载荷带 entity_binding(来源=active flow 图,与运行时分发同源,无新字段),CapabilityCard 按 type==='workflow' 渲染 事务型(geekblue)/推理型(cyan);②封面工具标签收敛为"N 个工具"小字(目录级 tool_ids 是生效授权:_effective_tool_ids 会并集进同事白名单,节点级 enabled_tools 是步骤白名单,两者用途不同非双源,不需迁移);③助手同事显式 tool_ids 与目录授权重复但无害(并集)。uvicorn --reload 在此机不可靠(实锤两次),后端大改后必须手动重启。E2E 内核化后复测 173.0s 零行为变化。需求分析零改动。

**多场景战役(2026-10-18,7场景全过)**:成本直通/中途提问(答状态不断链✓)/预览改参数(15→18%重预览✓)/方案表介入(=同一条成本链,M2库价推导分支确认不存在;大脑未谎称用库价)/挂已有商机(零新建✓)/裸表发问(纯预览零落库✓)/拒绝加价(0%原样报价优雅解✓)。全链 102-212s。
**战役揪出四连修**:①同事 system_prompt 里的反幻觉锚(机型)在引擎换掉后成负面指令大象→GLM 反复反驳不干活,已删+合并重复确认段(备份Temp);②SkillStudio 旧客户端整图保存剥 entity_binding→静默降级回需求分析引擎(ai-*载体死锁复现),upsert_graph 加保留闸+恢复 real_bound;③z.ai 半死连接 39min 挂死实锤→事务轮壳补 920s 硬闸(与skill同款);④重构引入 event_sink 越域引用 tool_steps(工具轨迹静默丢失)被 no_undefined_names 守卫逮住→外层盒子修。
**闸门摩擦根治**:确认摘要改用解析后值(submit=opp_id+sheet_id, margin=quotation_id+margin+apply_to),重放时 customer_name/opportunity_id 漂移不再失配;staged_args 上案台+随失配错误返回。残留:create_opportunity 偶发一次失配自愈。
**已知边界**:加价率缺失时大脑会自拟"行业默认15%"(闸门拦住但倾向在)→左栏规则已补"不得自拟";qty 解析 Lena 表显示 1 而实际 10 台(解析口径观察项)。
- **调试技法**:patch skill_turn_engine.run_stream_chat_loop 捕获每节点 LLM 输入到 jsonl——工作流"大脑为什么这么说"的实锤手段
- **交付流配置(DB 权威)**:reasoning_flow(key=delivery_to_quotation,6节点 input/identify/place/submit/margin/output,entity_binding=real_bound,graph 级 manual_rules=9条交付规则,节点挂工具白名单);执行器从 DB 流读步骤序/标签/白名单/规则(配置换起来不改代码);assistant 同事绑定 delivery_to_quotation+requirement_analysis 两个工作流
- **公共件已立桩**:slots_backfill.py(槽位回填器:契约校验/默认兜底/缺口清单,spec 可注入)+ workflow_ask.py(节点反问原语:服务端留底 30 分钟/按 run+node 匹配/自由文本原样带回)——消费者=交付工作流反问节点,需求分析后续绞杀迁移
- **核心层已拆**:delivery_core.py=业务唯一实现(解析/落草稿/提交转换/加价 preview+execute 分段/出件/商机定位/附件归档),skill_tools_write=聊天薄壳。**加业务规则只许改 core;行为指令也不许进工具结果(C1 2026-10-17修正):instruction/fixation_hint 类文案已剥,规则住助手提示词/工作流左栏,工具结果只摆事实**;margin 的 price_ok 为必传显式门;测试 patch 目标=dcore.financial_rates 等新位置;权威范式文档=docs/需求分析/01_架构与契约/(节点产物契约四原则:只写自己真实表/唯一份/schema权威/换插头=换AI填哪张表)
- **AskCard 已开放到聊天轮**(确认卡一键化,输入选项卡由处理层统一发射)

**启动表单+产物卡已实现(2026-10-18,原型=docs/prototypes/启动表单与产物卡-原型.html)**:
①launch_form:流配置 graph.launch_form(声明式 fields:key/type[label,text,number,select,file,textarea]/label/required/default/options),_normalize_graph 透传;/skills 载荷带 launch_form;LaunchFormPanel.vue=通用渲染底座(文件字段复用聊天附件通道,拖拽+点击),AssistantPanel 装填态渲染、提交拼装【开工单】结构化首条消息走现有 sendText(armed 消费+attachmentIds),可跳过=现状;编辑器=LaunchFormEditor.vue(管理卡片 ⋮ 菜单"编辑启动表单",字段增删改排序+实时预览,保存=读图改 launch_form 整图 PUT,清空=恢复自由对话)。
②产物卡:kind='artifact' 消息,data={artifact_type,title,summary,refs}——refs 只存 id,查看器按 ref 拉活数据(权限在拉取时);TransactionApp 契约加 cards_from_facts(facts,view),delivery_app 声明四规则(import ok→cost_sheet_parse(仅落库才发)/submit+margin ok→quotation(同单去重最新胜出)/share ok→share_link),轮壳在 apply_facts 后逐卡 _persist_artifact 落库广播;前端 ArtifactCard.vue=壳+查看器:**cost_sheet_parse→CostSheetEditor(readonly 切编辑,保存走 saveCostSheetDraft 同人工接口)**,**quotation→QuoteWorkbench(quotePriceVisible=现成价格开关,auth.can('field.opportunity.quote_price') 初始化,面板折叠+动作 emits 深链详情页)**——查看器零新表格,与人工操作同组件。需求分析引擎的产物广播未动(零破坏)。

**形态定案(用户拍板)**:产物卡与开工单一律"聊天内收起卡 + 点击居中弹窗"(a-modal:PC min(1080px,94vw)/640,手机 100vw 全屏 wrap-class);**不用抽屉**(PC 也不好用)、**不内联展开**(QuoteWorkbench 内联进聊天气泡手机端挤压变形+撑破聊天流,实测图为证)。产物卡 refs 必须**步后案台**装配(步前视图没有本步刚绑的商机——实测踩坑,解析卡 refs 空导致查看器"未找到")。CostSheet 列表 API 返回字段是 `id` 非 `sheet_id`。

**launch_form 已迁独立列(2026-10-19,结构性修复)**:第二次被剥后弃了"graph 内寄存+防剥闸"方案——launch_form 迁到 rules.reasoning_flow 独立 JSONB 列(migrations/add_reasoning_flow_launch_form.sql),画布保存物理碰不到。读写:repo.set_launch_form(skill_key, schema) + to_dict 带出;API=PUT /api/reasoning-flow/launch-form?skill_key=;编辑器(LaunchFormEditor)保存走该端点;upsert_graph 防剥闸只留 entity_binding。graph 内残留的旧键无害(读取以列为准)。**教训:多写者文档(graph)里寄存单写者配置=结构性剥键,防剥闸只是补丁;分存储才是修**。另:同线程第二单劫持已修(装填入口优先于续跑分支+fresh 解绑线程商机),真实验证过。

**节点契约字段级 schema + 缺口驱动反问已实现(2026-10-19,并行会话接手完成,本会话验收)**:
交付流节点契约下沉到字段级——node_configs target.artifacts[].fields[{key,label,ask,hint}]:identify=customer_name/sales_person(ask),place=attachment(ask),margin=margin_pct(ask+不得自拟默认值);place_bom/derive_cost/submit/output 无字段(闸门/推导节点)。运行时:`format_step_contract(step)`(transaction_engine)把目标层+必填清单+逐字段 hint 注入本步提示词,纪律=「缺哪个先要哪个,一次问齐,全齐直接办,不重复反问」;runner 已接线。**反问时机由契约 fields[].ask 开关驱动,配置者改开关下一轮反问行为同步变**——替代散落的硬编码/规则文字(create 壳的 sales_person needs_input 保留为机械兜底)。编辑器 LaunchFormEditor 新增「从节点契约同步」:identify 目标层字段契约一键带入表单——**一份 schema 三处消费:画布契约/开工单表单/运行时反问**。
验收:60 关键测试+全量 966 绿(2 个他人既有红),前端构建 ✓,后端已重启。

**节点契约完整性守卫+条件边(2026-10-19)**:test_contract_completeness.py 遍历事务引擎工作流(real_bound)校验:①字段级 schema 的 ask=true 字段必须有 label+hint;②每个挂工具节点必须有 completion 声明(仅校验 real_bound,推理管道不在范围)。画布条件边:graph.edges[].condition 透传,place_bom→place 边标"成本表入口",place_bom→derive_cost 标"方案表入口"。format_step_contract 注入工具 one_liner(从 agent_tool_display 取)。manual_rules 行动映射文字已删(从契约生成)。
