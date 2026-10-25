# 门户工作台子页（Portal Workstation）

> 最后更新：2026-10-14（调度台处理人卡新增「移除」：在办任务转无主+默认规则连带删除+`remove-handler` 端点；规则 PUT 校验处理人必须是该节点有效角色账号——幽灵兜底规则被 409 拦截；te/cost/quote 改单一「我经手的商机」列表——mode=involved 全集+流程节点列标注环节，双视角切换已废；新增节点兜底规则「承接全部业务」；list_task_flows 排除硬删孤儿流 + status≠done 对齐调度台）

## 功能概述

`/portal/workstation/:view` 下五个角色工作台（`PortalWorkstationView.vue` 单组件按路由参数分view）。2026-09-16 起四个列表页**统一复用商机线索表公共组件**（点客户名进商机详情页，`from` 参数回跳对应工作台），表格口径=商机卡片，不再用旧的任务条目表（`/api/portal/tasks` 已删除）。

| view | 页面 | 数据源 | 商机状态列 | 特有能力 |
|------|------|--------|-----------|---------|
| `business` | 我的商机 | `/api/portal/opps`（本人商机；管理员全量） | 可改（需 `action.opportunity.result`） | 搜索/排序、行菜单（重命名/移至回收站）、新建商机 |
| `te` | 技术支持工作台 | `/opps?node=boming&scope=mine\|all` | 只读 | 行菜单·转交 |
| `cost` | 成本核算工作台 | `/opps?node=costing&scope=…` | 只读 | 行菜单·转交 |
| `quote` | 报价专员工作台 | `/opps?node=quoting&scope=…` | 可改（同上权限键） | 行菜单·转交 |
| `dispatch` | 任务调度页 | `/api/portal/dispatch` | — | 调度台 v2（无主弹窗/人员×节点看板/转交记录，管理员） |

- `scope`：非管理员恒 `mine`；`all` 需管理员（后端 403 校验）。
- **排序全视图一致（2026-10-12）**：involved 接口支持 `sort_by=updated_at|created_at × asc/desc`（updated_at 以流程更新时间为准，缺失回退商机更新时间），与线索页同一套排序语义；「我的商机」走 SQL 排序不变。任务视图排序箭头已恢复（旧队列接口写死倒序时代的「箭头已关」限制随 involved 化一并解除）。
- **商机状态列全视图按权限键门控（2026-10-12）**：`statusEditable = can('action.opportunity.result')`——角色管理里配了键就能改（te 已配），视图不再额外设限（旧规则「仅 business/quote 视图可改」随权限放开同步作废）；未持键角色依旧纯文本只读。
- **搜索四页全开**（含节点模式），口径与商机线索页完全一致：客户名 / 业务 / 商机号子串（`_opp_search_hit` ↔ `list_opportunities` 同字段）。节点模式后端内存过滤后重分页。
- **slots 口径与线索页同一份**：`opp_caliber_repo.current_slot_map`（current 优先、缺失回退最新 draft）——平台/形态/数量在需求单还是草稿时也有值，不再只查 current。
- 四页统计条：business＝**待办事项**（returned，需求退回待修改）/ 流转中（in_progress）/ 已定稿（done）/ **全部商机**（全集收尾，不做前导伞卡）；节点页**全个人口径、四卡互不重合**（2026-10-12 定稿；「队列总数」全公司口径、「任务范围」元信息卡、「今日处理中」〔待办的子集〕均已废）＝**待办事项**（mine，分派给我的存量）/ **今日完成**（done_today，节点还挂我名下但流程已推进且今日有更新）/ **配置数**（我经手商机的配置份数，与线索页「总配置数」同词汇）/ **经手商机**（involved 全集）——summary 由 `mode=involved&node=` 一次性给出。
- **te/cost/quote 单一列表（2026-10-12，取代初版「待我处理/我经手的」双视角切换——分页切换与其他页面不一致，流程节点列已能标注环节）**：节点工作台直接展示「我经手的商机」=`GET /opps?mode=involved&node=<节点>`——**任一节点指派含我**（user_id/姓名双格式，复用 `match_assignee`）**或商机 fae 角色字段=我**，节点无关（BOM 已提交流转到核价/报价的历史商机仍可见）、只含活商机；按流程更新时间倒序，search 同口径。待我处理的商机就是列表中环节=自己节点的行。summary 带 `mine/today/queue_total`（节点队列口径，统计条前 3 卡）+ `total`（经手全集，第 4 卡）。此前的纯队列口径会让流程一推进商机就从技术支持视野消失（fae 归属商更是无处可见）。
- 「经手商机」角标同口径进 todo-summary（items.involved，dim 不计入今日待办）——工作台首页非 admin 角色的第 2 枚 hero 角标即读它。
- **详情闸门同口径（2026-10-12）**：`deps.user_can_access_opportunity` 增加 fae 支（owner/销售姓名/流程任一节点指派人之外，fae=本人姓名也放行）——「我经手的」能列出就必须能点进详情页，否则出现列表可见、点击 403 的断链；进详情后字段级可见性照旧各自管（价格遮罩、成本附件按 field.flow.cost 裁剪）。
- **多选 + 批量移至回收站**：收在 `OpportunityTable` 组件内（浮条+API+`batch-trashed` 事件），线索页与「我的商机」共用；任务视图（te/cost/quote）不开多选（非数据归属者）。后端逐项校验权限，部分失败仍 200，组件按 `success/failed` 分别提示。
- 任务 summary 的 `mine` 恒为「真实分派给我数」（admin 全量视图不再用 total 冒充）。
- **转交在行菜单**（`menu-mode="task"`：打开/转交；原右上角「转交第一行」按钮已删）。owner 菜单=打开/重命名/移至回收站，task 菜单=打开/转交。

## 任务调度页（调度台 v2，2026-09-16 重设计）

`view=dispatch` 分支渲染独立组件 `views/portal/PortalDispatchPanel.vue`（自管数据加载；admin 门控保留在 PortalWorkstationView.guardView）。v2 设计三原则（用户三点反馈驱动）：**无主清单不占主页面**（收进居中弹窗）、**规则呈现按人分组而非业务×节点大矩阵**（参考 GitHub code owners / review assignment 的按人分组口径，49 行矩阵塌缩成 ~5 张处理人卡）、**全站 Glass token 合规**（notif 色/accent 渐变/圆角 token，零硬编码 rgba）。

三块 + 一弹窗：

1. **统计条**：🔥无主任务 N（**可点击卡片**，红边框，点开无主弹窗；0 时绿色「全部有主」）| 活跃任务 N | 今日转交 N | 规则覆盖 M/N（已设规则格 / 业务数×3，暴露规则缺口）
2. **人员 × 节点看板**（在办负载与默认规则合并成同一视图，三列=方案配置/成本核算/报价单）：
   - 列头：节点名 + 合计在办 + 「无主 N」红胶囊（可点击 → 弹窗过滤到该节点）
   - 处理人卡：首字头像（幽灵处理人=琥珀头像，legacy「姓名，手机号」自由填写值匹配不到候选账号）+ 姓名 + 在办 N 徽标 + 默认承接业务 chips（chip 内 × 删规则）+ **「移除」按钮**（2026-10-14：确认弹窗明示代价后一键移除该处理人——其在办任务全部转无主（逐条留「转交给 未指派」审计，进转交记录）、默认规则连带删除；卡片随 load 消失，任务在无主清单手动指派或一键补齐再分配。人卡的来源=在办任务∪规则，所以**只删规则芯片删不掉人**，移除走卡级按钮）
   - 卡上「＋」= 列级内联表单（人选锁定）；列尾虚线「＋ 添加默认规则」尾卡 = 表单带处理人选择（全站新增入口范式）；业务多选只列该节点未设规则的业务（一业务一节点一规则），「全选未分配」一键填满候选。**勾「承接全部业务」= 节点兜底规则**（`business_user_id='*'`，卡片渲染为虚线「全部业务」芯片，× 可删）：默认解析优先级 = **商机角色字段（fae/报价人）> 业务专属规则 > 节点兜底**——核价节点无角色字段，兜底即全部；方案配置 fae 有值仍归 fae 本人，兜底只接 fae 为空的商机（含未来新增业务账号）。
   - 处理人卡芯片**折叠**：超过 5 个只显前 5 + 「+N 项」虚线芯片，点击弹层看全量（弹层内同样可 × 移除）——批量承接后卡片不再被业务名撑爆。
3. **转交记录**：a-collapse 默认收起，近 30 条 assign 事件反解「由 X 转交给 Y」
4. **无主任务弹窗**（a-modal 居中 920px，统计卡与列头「无主 N」两个入口，列头入口带节点过滤）：**三列密集卡片网格**（≤900px 退单列，卡片=红底玻璃小卡而非一行一条）按停留天数倒序（≥3 天标红）+ 每卡指派下拉（预填 suggest，仅当建议人选在候选内；幽灵建议不预填）+ 指派按钮（走 `/opp/{id}/assign` 留审计事件）+ 工具行「⚡一键按规则补齐」；空态=绿色条「全部任务都有主」

后端口径（调度台 `flow_repo.dispatch_snapshot()` 与节点队列 `flow_repo.list_task_flows` 同一套，2026-10-12 对齐）：活跃=命中节点且 `status != done` 的流程；**只认活商机**——排除软删/ai_office 商机**且商机行必须仍存在**（`in_(alive_subq)` 取代 `~in_(excluded)`：商机物理删除后残留的孤儿流此前会混进 te 队列成死任务，2026-10-12 实测排除 63 条、boming 队列 66→3）。stuck 的 suggest=`resolve_node_assignee`（商机角色字段优先，否则业务默认规则）；matrix 仅统计有 owner 的商机（v2 UI 不再展示 matrix，接口保留）。
⚠️ `list_task_flows` 的按人过滤以 `assignee_name` 非空为开关（`match_assignee(cur, uid, name)`）——调用方只传 `assignee_user_id` 会被**短路成全节点口径**（todo-summary 曾因此把「我的待办」算成全公司存量 66）。传就两个都传。

autofill 安全设计：body 可传 `opportunity_ids` 定向补齐（默认全量）；suggest 过 `_validate_assignee_role`（legacy「姓名，手机号」自由填写值不落 assignees，计 unresolved）——与 `/assign` 端点同校验。

## 商机状态权限（action.opportunity.result）与新建权限（action.opportunity.create）

后端 `PUT /api/opportunities/{id}/meta` 对 `result` 字段加权限门控（[opportunities.py](../../../backend/app/api/opportunities.py)）：**管理员/业务/报价员**可改，技术/成本/总监 403「无权修改商机状态」。权限键入 `_DEFAULT_PERMISSIONS`（startup 播种）+ business/quote 角色默认权限（role_repo）；前端 `OpportunityDetail` 详情页状态下拉同权限键门控（无权限显示纯文本）。状态枚举 SSOT：`constants/opportunityResult.ts`（pending 进行中/won 已中标/lost 已丢标/expired 已过期）。

**新建商机同键门控（2026-10-13）**：`POST /api/opportunities/` 此前只挡未登录（界面无入口但 API 裸奔），现挂 `action.opportunity.create`（业务/总监默认持有，管理员全量兜底；技术/成本/报价/总监以下 403「无权新建商机」）；**各工作台视图右上「+ 新建商机」按钮与线索页按钮均按 `canCreate`（同键）显隐**——角色勾选该键即在自己工作台出现按钮，创建归属自己、计入「我经手的商机」（involved 口径含 owner 匹配）。键入 `_DEFAULT_PERMISSIONS` + role_repo `_DEFAULT_ROLES`（`seed_missing_defaults` 幂等补授）。
**建档归属语义（2026-10-14 定稿）**：业务角色建档=业务字段自动归属自己（只读）；**其他持键角色（技术支持/管理员/总监）建档=必填指定归属业务**（业务名搜索框，后端 400「请填写归属业务」），命中在册业务账号则商机归属该账号（进该业务的工作台）、**技术支持建档 FAE 自动记创建者**（弹窗只读行「FAE（自动记录为创建者）」明示）。管理员/总监（view_all）代建档逻辑不变（此前就允许留空业务，现统一必填）。

## API

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/portal/opps?page=&page_size=&search=&sort_by=&sort_order=&node=&scope=&mode=` | 商机卡片列表；`node+scope` 为节点任务队列（summary=total/today/mine/involved）；`mode=involved` 为「我经手的商机」（任一节点经手/fae 归属，含历史），再带 `node` 时 summary 附 mine/today/queue_total 队列口径（工作台单一列表用） |
| GET | `/api/portal/dispatch` | 调度页：业务列表 + 分派规则 + 转交记录 + 调度快照（nodes/stuck/matrix） |
| POST | `/api/portal/dispatch/autofill` | 一键补齐无主任务（admin；body.opportunity_ids 可定向，默认全量） |
| POST | `/api/portal/dispatch/remove-handler` | 移除处理人（admin；body.node_key+handler）：在办任务转无主（留审计）+ 该节点其默认规则连带删除，返回 cleared/rules_removed |
| GET | `/api/portal/assign-options` | 各节点候选人（转交/规则表单） |
| PUT | `/api/portal/assignment-rules`、DELETE 同路径 | 分派规则增删；PUT 校验处理人必须是该节点有效角色账号（幽灵串/错角色 409） |
| POST | `/api/portal/opp/{opp_id}/transfer` | 任务转交 |
| PUT | `/api/opportunities/{opp_id}/meta` | 状态/重命名（result 受权限门控） |
| POST | `/api/opportunities/{opp_id}/trash` | 移至回收站（business 行菜单） |

已退役：`GET /api/portal/tasks`（404；2026-09-16 并入 `/opps?node=`）。

## 组件

| 组件 | 位置 | 用途 |
|------|------|------|
| `PortalWorkstationView.vue` | `views/portal/` | 五 view 壳：统计条 + 卡片容器（四列表页共用搜索/分页状态）+ 转交/重命名 modal；dispatch 分支只挂 `<PortalDispatchPanel />`（admin 门控在此） |
| `PortalDispatchPanel.vue` | `views/portal/` | 任务调度台面板 v2：统计条（无主卡可点开弹窗）+ 人员×节点看板（在办+默认承接 chips+内联加规则/尾卡）+ 转交记录收起面板 + 无主任务弹窗（三列卡片网格，指派/一键补齐），自管数据加载 |
| `OpportunityTable.vue` | `components/opportunity/` | 商机线索表公共组件（商机线索页同款）：状态 tag（可下拉改）、流程节点 pill、行菜单、多选+批量回收站浮条、分页自适应 |

回归：`backend/tests/perm_matrix_e2e.py`（状态门控 403/200 + 节点队列口径 + 节点搜索 + 草稿 slots 回退 + scope=all 越权 + 调度台快照/无主/规则矩阵 PUT+DELETE/定向 autofill/移除处理人（403 门禁、幽灵规则 409、在办转无主+规则连带删），118 断言；隔离跑法见文件头——独立 8001 实例，测试商机自建硬清）。

## 移动端（≤768px，2026-09-19）

页面 padding 12px、hero 折行、统计 2×2（≤900 已有）；卡头折行后搜索框占满整行（宽度自适应），OpportunityTable 内部横向滚动（scroll.x 1024/964）不变；新建商机按钮保留 hero 右侧。桌面四子页布局零改动。
