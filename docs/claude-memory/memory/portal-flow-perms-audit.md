---
name: portal-flow-perms-audit
description: 09-15权限审计两轮全落地+09-16工作台四子页统一商机线索表组件(tasks端点退役入/opps?node=)+商机状态门控action.opportunity.result(业务/报价可改,技术/成本403)+09-16五轮调度台v1+六轮v2+七轮无主改居中弹窗三列网格(人×节点看板替代49行矩阵/全token)；矩阵111断言；通知中心富popover+裁决条入QuoteWorkbench；存量11条卡死已放弃治理(2026-10-22定调)
metadata: 
  node_type: memory
  type: project
  originSessionId: adf95960-713e-4613-bf5a-f26a1427d84f
  modified: 2026-10-22T02:38:40.669Z
---

2026-09-15 商机详情页四步流程权限审计 → **P1-P5 修复已全部落地**（`backend/tests/perm_matrix_e2e.py`，隔离跑法 8001 无 reload + 项目 venv `backend/.venv/Scripts/python.exe`——裸 `python` 会命中 hermes venv 报缺 bcrypt）。

**已修清单**：
1. 成本附件泄露（高危）：`feed.py` 类别→权限映射 `_CATEGORY_VIEW_PERM`（requirement=field.flow.cost / technical=field.flow.bom / internal_quote 前向兼容），list/下载/版本/删除/改类别/消息内嵌附件全走 `_ensure_category_visible`；上传也校验（防无权者传成本桶）
2. 乱序提交（高危）：portal.py BOM三端点/成本四端点/需求五端点/convert 全部挂 `action.flow.submit.{requirement,boming,costing,quoting}`（新 key 已进 startup 权限目录+role 种子）+ `_ensure_stage_open`（流转卡 current_node 优先、全局 flow 兜底）+ 前置依赖校验（无 current 需求/方案 → 409）
3. 前端跟手：存档区受限列按权限隐藏（ArchiveSection CATEGORY_PERM）、看板工作台 readonly 化、转报价按钮 canSubmitQuote
4. 姓名即身份（中危，止血版）：create_user/update_name 撞名 409

**矩阵测试新发现并已修**：`deps.py user_can_access_opportunity` 的 `if owner_user_id: return owner==user` 早退使指派人分支成死码——**有 owner 的商机 te/cost/quote 被指派也 403 进不了详情页**（存量 bug，非本次改动引入）。修法=owner 命中放行、未命中落空到指派人判断；sales 回退保留在无 owner 分支。

**遗留清零（09-15 三轮，用户批准）**：assignees 已迁 user_id 存储。落地四件：
1. flow_repo 模块级转换器：`assignee_to_uid/assignee_to_name/match_assignee/render_flow_assignees`（用户表映射缓存 60s TTL）；`assign_task`/`apply_default_assignments` 写入统一 user_id（库中无此人的自由填写姓名原样保留，双格式兼容）
2. 出口渲染：`_svc`/submit 两处/assign/list_task_flows 返回前 assignees 值转姓名 → **前端零改动**
3. 匹配双格式：`user_can_access_opportunity`/`list_task_flows`（新增 assignee_user_id 参）按 user_id 或姓名命中
4. 迁移脚本 `scripts/migrate_assignees_to_user_id.py` 已跑：32 项迁 user_id、0 重名冲突、11 项无命中（全是 quoting「姓名，手机号」自由填写值，保留+兼容）；幂等可重跑

**用户拍板已修（09-15 二轮）**：阶段已过处理人失去访问权 = 存量设计缺陷非合理行为，用户定调「批完就要能回看」。`user_can_access_opportunity` 指派人判断改为**任一节点指派人（含历史/被退回上游）均放行**——顺带救活退回链路（return_portal_card 只移卡不动 assignees，原逻辑下被退回人 403 进不去改不了）。写侧不受影响（action key+阶段校验照挡），读侧裁剪照常（te 回看成本表仍为空）。

**优化轮（09-15 四轮，用户批准七步方案）全部落地，矩阵 74/74**：
- **P1 通知系统**：`opportunities.notifications` 表 + REST(/api/notifications*) + WS(/api/notifications/ws)；helper `notify_users` 落库+推送+去重+排除本人+永不抛错；同步端点→WS 走 `run_coroutine_threadsafe+bind_loop`；前端 `useNotifications`（模块级单例、指数退避重连）+ 全站顶栏 `NotificationBell`（DefaultLayout 一处挂载）。事件挂点：task_assigned/stage_advanced/card_returned/withdraw_*/quote_submitted/pricing_approval_*
- **P2 毛利审批门**：margin_alert 加 `approval_threshold`（存量部署缺省=警告门槛 7%，需编辑一次才分开）；发送端点（非导出）拦：综合毛利率(snapshot totals.marginPct，fallback profit_margin 列)<红线 → 409+自动建 `opportunity_pricing_approvals` 审批单+通知总监；approved 放行、rejected 重发建新单留痕；decide 端点 reject 必填意见 422；权限 key `action.flow.approve.pricing`（director 种子含，seed_missing_defaults 启动自动补存量）。**e2e 抓到并修的真 bug**：`latest_for_quotation` 用 scalar_one_or_none 撞驳回重发多行 → 500，改 `.limit(1)`
- **P3 门户角色板块 → 已退役（09-15 晚用户拍板「有小铃铛即可，门户干净点」）**：原 `PortalRoleSections` 五卡+组件删除；`GET /api/portal/flow-stats` 与全局 `GET /api/portal/pricing-approvals` 端点及 repo 方法（stage_counts/list_pending）一并删除；**裁决 UI 迁入商机详情页 QuoteWorkbench 审批裁决条**（有 `action.flow.approve.pricing` + pending 审批即显示琥珀条，批准/驳回），门户回归纯 AI 壳（欢迎语+磁贴+输入框）。信息去向：待我审批→审批通知直达详情页裁决；我的任务→工作台磁贴；阶段分布→驾驶舱
- **通知中心升级（同日第二轮）**：铃铛富 popover（未读/全部 tab+逐类型语义色图标 `notificationMeta.ts` SSOT+相对时间 `relativeTime.ts`+hover 标已读/删除+清空已读/查看全部）+ `/notifications` 全量页（按天分组+类型 chips+分页+批量已读）；后端新增 `DELETE /api/notifications/{id}`、`POST /api/notifications/clear-read`、list 加 types 过滤、unread-count 加 by_type 分组。**第三轮定调（用户嫌六分组太细+暗色不适配）**：筛选分组收敛 6→3 = 待办(任务/退回)/审批(撤回+毛利审批全周期)/动态(阶段/报价)，条目保留逐类型图标；通知色 SSOT = tokens.css `--cpq-notif-*`（双主题）+ `--cpq-warn-surface/-border`（审批条），通知组件禁硬编码色值（曾因 `#fff` 表面+浅色调图标色暗色翻车）
- **P4 指派角色校验**：`_validate_assignee_role`（非系统用户 409/角色不匹配 409），assign/transfer/initiate/提交带 assignee 全走；自由填写外部姓名退役
- **P5 公共池退役**：scope=pool→400、dispatch 页公共池块删、convert 无 assignee 时 resolve 兜底
- **P6 草稿乐观锁**：bom/cost draft `expected_updated_at`+`_ensure_not_stale` 409、报价 PUT expected_updated_at 409
- **P7 退回原因必填**：comment 空白 422；前端三工作台改 confirmWithReason
- **A1 总监可见性**：director 种子+存量补 `field.flow.bom/cost`——**总监现在能看方案/成本表/成本附件**（e2e 旧断言已翻转为新语义）
- A2 业务看已发报价/A3 复制改价重发：核实已有实现零开发

**09-16 admin 跨阶段自由提交（用户定调「admin 用户在各个节点都可以自由提交」）**：非 admin 的前置依赖校验保留，admin（`_portal_is_admin`=role admin 或 page.opportunities_all）三处放行——①submit_bom_scheme 跳过「需求单尚未提交」409；②submit_cost_sheet 跳过「方案配置尚未提交」409；③`_ensure_downstream_assignee` 加 user 参数对 admin 跳过（5 个调用点全过），下游节点可后续转交；convert_cost_to_quotation 的本人顶上 fallback 扩到 admin（报价节点不至于无主）。requirement 节点本就 admin 放行；submit_quote 发送无 admin 阻塞；毛利审批门是业务规则不豁免。全程 8000 实测：无需求提交方案→200、无方案提交成本→200、convert→admin 自动顶上 quoting。

**09-16 工作台四子页统一商机线索表（用户批准方案）**：我的商机/技术/成本/报价四页表格全部复用公共组件 `components/opportunity/OpportunityTable.vue`（从商机线索页右栏抽出；点客户名进商机详情页带 from 回跳）；后端 `GET /api/portal/tasks` 端点+`_task_item`/`_latest_prev_node` 已删除，任务队列并入 `/api/portal/opps?node=boming|costing|quoting&scope=mine|all`（卡片口径与商机模式一致=商机卡片+流程节点，summary 变 total/today/mine，更新时间取流程 updated_at，scope=all 仅管理员 403）。**商机状态权限定调（用户拍板：业务/报价可改，技术/成本不行）**：新 key `action.opportunity.result` 入 startup 权限目录+business/quote 角色种子，`PUT /api/opportunities/{id}/meta` 对 result 字段 403 门控（te/cost/director 无 key）；前端列表状态 tag 下拉与详情页状态下拉同 key 门控（无权限纯文本）；状态枚举 SSOT=`frontend/src/constants/opportunityResult.ts`。旧任务表的 BOM提交人/成本核算人来源列不留（用户拍板）。矩阵测试加 8 断言（te/cost 改状态 403、quote/biz 200、节点队列含 oppA+卡片口径、scope=all 越权 403）→ **89/89**。

**09-16 二轮（用户三点反馈）**：①多选+批量回收站浮条收进 OpportunityTable 组件本体（API+batch-trashed 事件，线索页与「我的商机」共用，一处加功能两边生效）；②搜索四页全开且与线索页同口径（客户/业务/商机号子串；节点模式后端 `_opp_search_hit` 内存过滤+重分页，SQL 版在 list_opportunities）；③slots 口径统一到 `opp_caliber_repo.current_slot_map`（current 优先、draft 回退）——原 `_opp_card` 用 `list_current_requirements_bulk` 只查 current 导致草稿期商机平台/数量为空（用户踩中）；该方法已删。矩阵 **96/96**。

**存量治理（⚠️2026-10-22 用户定调放弃，不再治理，留档防重复提议；09-15 扫描，只报告未动）**：非 ai 未完成流程 49 条中**当前节点无处理人卡死 11 条**（4 条卡 boming、7 条卡 quoting，公共池退役后无人接；09-16 admin 自由提交+本人顶上后 admin 可直接推走这些卡死流程）；**同商机多条活跃流程行 3 个**（OPP-20260814095342221994/OPP-20260812170627198213/OPP-20260814132537692128 各 2 条，疑脏数据需保留最新软删旧）；ai-* 隐藏商机 73 条 assignees 全空（AI 草稿，不治理）。

**09-16 三轮（隐患核对）**：扫 portal.py/opportunities.py/flow_repo/组件/视图/API 层，退役符号零残留，修三真隐患：①排序假交互（任务视图 sorter 箭头后端忽略→组件加 `sortable` prop 关掉；「我的商机」升序被硬编码 desc 吞→补 sortOrder，与线索页对齐升/降序）；②admin 全量视图 summary.mine 被覆盖成 total 冒充「分派给我」→删覆盖行显真实值；③批量回收站部分失败静默（后端逐项容错 200 返 success/failed）→组件按 failed 数分别提示。核对结论：slots/搜索/列表口径三处都汇 `current_slot_map`+`list_opportunities` 同源；`list_task_flows` 已排除软删/ai_office 商机；批量端点逐项 `ensure_opportunity_access`。（任务视图转交入口缺失 → 四轮已修）

**09-16 四轮（用户拍板转交归位）**：任务视图转交从右上角「转交第一行」按钮迁入行菜单——组件 `menu-mode` prop（owner=打开/重命名/回收站，task=打开/转交），顶栏按钮+`.ghost-btn` 死样式已删，openTransfer 必传行记录。

**09-16 五轮（任务调度页重设计 v1=四段式调度台）**：dispatch 分支独立成 `views/portal/PortalDispatchPanel.vue`（自管数据），四段=统计条→无主任务区→节点负载→规则矩阵（49 业务×3 节点 inline select）→转交记录。后端 `flow_repo.dispatch_snapshot()` 一次聚合 nodes/stuck/matrix；`POST /api/portal/dispatch/autofill`（body.opportunity_ids 可**定向**——e2e 生产共库必须定向只补测试商机，全量会连带改真实卡死流程+发真人通知）；autofill 的 suggest 过 `_validate_assignee_role`（legacy「姓名，手机号」值不落库计 unresolved）。**快照口径坑：排除软删/ai_office 之外还必须挡孤儿流程**（商机行已硬删的残留 flow，opportunity_id 形如 `ai-xxx`，实测 66 条；判定=opportunity_id 不在批量加载的 opp_map 里即跳过），否则调度台被幽灵任务刷屏（77 假无主 vs 真 11）。e2e 加 15 断言（含规则矩阵端点首次覆盖+自建 admin 测试用户）→ **111/111**。

**09-16 六轮（用户三点否决 v1 → v2 定稿，仅前端重写、后端零改动）**：①视觉违规（v1 硬编码 rgba/渐变/圆角）→ v2 全 token（notif 红/绿/琥珀 bg+前景、`--cpq-accent-gradient` 按钮、`--cpq-radius-sm/md/lg/xl`、`--cpq-overlay-w4/a10`、玻璃卡不嵌套=内层 chip 平铺半透明）；②规则矩阵信息密度太低（49×3=147 格仅 6 条规则，页面滚到底）+「任务分派该有更好呈现」→ **联网调研结论：GitHub code owners/review assignment 与任务管理工具全用按人分组**，v2 把节点负载+默认规则合并成**人×节点看板**（三列=节点；处理人卡=首字头像+在办徽标+默认承接业务 chips 带×删除；卡上＋=人选锁定的内联表单；列尾虚线＋尾卡=带处理人选择的表单；业务多选只列该节点未覆盖业务），147 格塌缩成 ~5 张人卡；③无主清单不占大区域 → 收进 a-drawer，入口两处：统计卡①（可点击按钮）+列头「无主 N」胶囊（带节点过滤），抽屉内=停留倒序清单（≥3 天红）+指派下拉（suggest 在候选内才预填，幽灵建议留空）+⚡一键补齐。幽灵处理人（legacy 自由填写姓名）在看板标琥珀头像（ghost=不在候选账号表）。浏览器实测：抽屉 10 行/列头过滤 3 行/6 规则 chips 全落位/表单人选锁定/computed style 全 token 解析正确；system-config 401 是登录前既有行为与面板无关。e2e 不受影响（后端零改动）仍 111/111。测试管理员账号：`权限测试-管理员`/PermTest#123（`opportunities.feed_users`，user_id 5acaa604…，浏览器验证前激活、验完停用；e2e 每轮 cleanup 也会全停）。

**09-16 七轮（用户追评两点 → 无主清单 v3）**：①抽屉→**居中 a-modal**（920px、centered、`wrap-class-name="portal-modal"` + body 走 `--cpq-bg-secondary`，与全站 modal 同皮肤）；②一行一卡信息密度低 → **三列密集卡片网格**（`.stuck-grid` repeat(3,minmax(0,1fr))，卡片=红底玻璃小卡：客户名 ellipsis+停 N 天+节点 pill+默认→建议+指派下拉/按钮，≤900px 退单列，max-height 62vh 内滚）。弹窗标题带数量+可关闭节点过滤 tag，工具行=口径说明+⚡一键补齐。**坑：隐藏标签页下 getBoundingClientRect/innerWidth 全 0、grid 读数失真**——验证布局前必须 preview_resize 强制视口（1280×800 下网格实测 3 列 272px×3）。浏览器已验证（10 卡三列、过滤器、computed style 全 token）；后端零改动 e2e 仍 111。

遗留（⚠️2026-10-22 用户定调放弃，不再治理）：孤儿流程 66 条仍在库（未清，调度台已不可见）；quoting 负载里 legacy 幽灵姓名（刘凯祥，15201755932 等）仍按原样渲染（v2 已标琥珀头像但未清理）。

**How to apply:** 碰 portal/feed 权限相关改动后跑 `perm_matrix_e2e.py` 回归（现 111 断言）；新阶段写端点必须 action key + `_ensure_stage_open` 双挂；改商机 meta 的 result 字段走 `action.opportunity.result` 门控别绕；门户商机卡片 slots/搜索必须与线索页同口径（current_slot_map / 客户·业务·商机号），别在 portal 另起一套；表格组件改交互先想任务模式是否后端支持（排序/筛选类后端忽略的要关 UI）；行菜单新动作进组件 `menuMode` 两形态之一，别在页面另造按钮；新附件类别必须进 `_CATEGORY_VIEW_PERM` 与前端 CATEGORY_PERM 两处同步；新流程事件记得挂 `notify_users` + `notificationMeta.ts` 登记类型；**任何聚合/列表新口径先想孤儿行**（父表已删子表残留是既有事实，查 opp_map 不命中即跳过）；**全局批量写端点必须带定向参数**（e2e 共库时只碰测试行）；e2e 跑法注意 Windows 临时端口耗尽（10048）——测试已改 per-token Session 连接池。关联 [[auth-rbac-system]] [[collab-flow-02-business-detail]] [[price-access-role-control]]。
