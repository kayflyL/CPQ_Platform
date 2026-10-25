# 商机详情页 (OpportunityDetail · 统一审批流看板)

> 最后更新：2026-10-15（产出物分享上线：方案/成本表/报价单行操作新增「分享」——网盘式链接（token 免登录下载，可过期/撤销/提取码）+ 视角化导出（方案=无价格/成本=只显成本/内部=留位清值，客户视角一期锁定）；ShareDialog 公共组件。同日：报价外发审批门 M1 + 发送撞闸原地弹发起窗。需求单分享 fast-follow）

## 功能概述

单个商机的**统一审批流详情页**——四步协作流程（需求→方案配置→成本核算→报价单）的主战场。同一页面按角色后端裁剪出不同视图（business/te/cost/quote 四角色各管一步，director 只读，admin 全量）。

页面 = `OpportunityDetail.vue`（壳，处理加载态/骨架屏）+ `OpportunityProcessBoard.vue`（主体看板）。旧版"证据链 + 生成报价推理面板"主线已下线；旧业务轻量视图 `/portal/:oppId`（BusinessOpportunityDetail）已下线。

## 路由

| 路由 | 组件 | 权限 |
|------|------|------|
| `/opportunities/:opportunityId` | `views/opportunity/OpportunityDetail.vue` | `page.opportunities`（进入后再过商机访问层） |

## 访问层（谁能进，后端 `user_can_access_opportunity`）

- 商机 owner（`owner_user_id`）恒可进
- `page.opportunities_all`（admin/director）全商机可进
- 流程**任一节点的指派人**（含历史——自己阶段提交后仍可回看，被退回时能进来改）
- 其余 403。指派存储 user_id（迁移完毕），API 出口渲染姓名。

## 组件

| 组件 | 用途 |
|------|------|
| `OpportunityProcessRail.vue` | 左侧四步流程轨道（当前阶段高亮/完成态） |
| `RequirementForm.vue` | 需求单：基本信息 + 结构化部件清单（桌面表格/手机卡片）+ 需求原文（autoSize 4~16 行自增高）；RequirementSlots 契约 |
| `RequirementAttachmentChips.vue` | 需求附件徽标条（2026-10-13，宿主=需求单弹窗）：上传/预览/删除随单完成，附件钉到需求单版本（`opportunity_attachments.requirement_version`，提交后随版本快照留档）。过滤=lead_requirement 且 version 匹配或 NULL（存量散件降级合并显示）。溢出=换行不滑动；手机无 hover，点徽标开预览看全名；编辑态 ✕ 删除（Popconfirm）、拖拽/「＋上传」/原文 Ctrl+V 粘贴截图直传；只读态仅预览。新建草稿未落库时上传落为未归版散件；删草稿时后端解绑回 NULL。原型：prototypes/需求单-内嵌附件区-原型.html |
| `ShareDialog.vue` | 产出物分享（2026-10-15，公共组件）：方案卡/成本表行/报价单行「分享」→ 网盘式弹窗（视角选择+模板选择+大预览 56vh+有效期/提取码+生成链接/下载）。**三视角全走导出模板管线**：scheme（无价格列）/cost（只显成本价，需 field.quote.export_internal）/customer（完整报价；quote 来源创建/预览/下载须持有效外发许可——与导出/发送同闸；cost/scheme 来源属内部传阅不闸）。方案/成本数据经 `quasi_source_from_configs` 投影成 Quotation 同构喂模板装载器（preview_data_loader 新增 source/source_items 入口）；服务端 snapshot→openpyxl 出 xlsx。后端：`services/artifact_share.py` + `api/artifact_share.py`（含免登录 `/api/share/{token}` 下载——部署层若有统一鉴权需放行 /api/share/*），share_tokens 表 `opportunities.artifact_share_tokens`；生成即归档附件桶（kind=export）+ 下载计数留痕。需求单分享 fast-follow（表单形状需自己的版式）。原型：prototypes/产出物分享-原型.html |
| `BomSchemeWorkbench.vue`（内嵌 `SchemeEditor.vue`） | BOM 方案工作台：多方案/多配置，配置=L6 整机 + KP 行；`readonly` 由 `canWriteBom` 驱动。编辑/查看方案弹窗为左右布局：左侧=上游需求单只读参考（与需求节点同构复用 `RequirementForm`，含多配置 tab 与部件清单，打开弹窗时从 current 需求单快照回填），右侧=方案编辑。旧 `RequirementContextPanel` 摘要面板已删（2026-09-18） |
| `CostSheetWorkbench.vue`（内嵌 `CostSheetEditor.vue`） | 成本核算工作台：成本 Excel 上传自动解析 / 手建草稿，毛利调价；`readonly` 由 `canWriteCost` 驱动 |
| `QuoteWorkbench.vue` | 报价单工作台：工作底表 → 「转为报价草稿」（`canSubmitQuote`）→ 发送/导出定稿；**报价外发审批门**（2026-09-15 低毛利单闸 → 2026-10-15 升级三口一闸）：客户版导出/平台内发送/分享报价视角出门均须有效外发许可（批准绑定内容指纹，改价失效重批），报价单挂「外发审批中/被驳回」徽标；**审批裁决条**：存在 pending 审批时，报价表上方显示琥珀色裁决条（批准/驳回，驳回必填意见）——审批通知直达本页裁决 |
| `ApprovalFlowPanel.vue` | 审批流时间线（节点事件/处理人/退回/撤回操作） |
| `ArchiveSection.vue` | 存档区四桶（见下），受限桶按权限隐藏列 |
| `AssigneePickerModal.vue` | 下游处理人选择（提交时指派/转交） |
| Feed 协作流 | 商机内消息 + 附件，WS 实时 |

## 角色视图矩阵（后端强制，前端按钮跟手）

| 区块 | business | te | cost | quote | director | admin |
|---|---|---|---|---|---|---|
| 商机信息卡 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 需求单 | **可编辑** | 只读 | 只读 | 只读 | 只读 | 可写 |
| BOM 方案 | 🔒 空 | **可编辑** | 只读 | 只读 | 🔒 空 | 全量 |
| 成本表 | 🔒 空 | 🔒 空 | **可编辑** | 只读 | 🔒 空 | 全量 |
| 报价单 | 定稿后+价格遮罩 | 定稿后遮罩 | 底表+价格可见 | **全量+可转/发** | 价格可见 | 全量 |
| 存档区 | 我的+报价附件 | +方案附件 | +成本+方案附件 | +成本+方案附件 | 我的+报价 | 全部 |

- 裁剪 key：BOM=`field.flow.bom`，成本=`field.flow.cost`，报价价格=`field.opportunity.quote_price`/`field.quote.price`
- 写 key：`action.flow.submit.{requirement,boming,costing,quoting}`（各角色一个）+ 退回 key `action.flow.return.{boming,costing,quoting}`
- 报价外发审批权 key：`action.flow.approve.pricing`（名为“低毛利报价审批”的时代遗留，2026-10-15 目录名已改“报价外发审批（裁决外发许可）”——M1 后低毛利仅是审批卡警示，此权限决定谁是审批人：被指派总监或广播单先到先批；director/admin 种子已带，可再勾给其他角色）
- 存档区桶门控：成本附件=`field.flow.cost`，方案附件=`field.flow.bom`；挪桶校验源+目标双类别（防洗白）

## 四步审批流程

```
①需求(业务) → ②方案配置(技术) → ③成本核算(成本) → ④报价单(报价) → done
```

1. **需求**：业务「发起」一步到位（商机信息+slots vN+推到 boming+指派技术，下游人选必填否则 409）；「更新需求再提交」=新版本拉回重跑（仅阶段开放时）。需求单弹窗内嵌附件区（2026-10-13）：需求单工作台卡头不再有「上传附件」按钮（只留「我的附件」归档），上传/预览/删除收进弹窗随单完成，附件钉版本随快照留档
2. **方案配置**：技术存多方案草稿 → 提交（转 current、其余归档、推到 costing+指派成本）；前置：需求已有 current 版本
3. **成本核算**：上传成本 Excel（自动解析草稿表+文件归档成本附件）/手建 → 编辑毛利 → 提交自动生成报价工作底表草稿、推到 quoting；前置：方案已有 current。**上传解析弹窗（2026-09-26 上线；09-27 模板归属改使用位置绑定+布局三栏化）**：用哪套解析模板由 设置→解析模板 的「使用位置：成本核算 · 上传解析」绑定决定，弹窗顶部只读显示当前模板（绑定错模板解析全空时给警示条，指引去设置页换绑）。布局：左=格子档案+字段映射（列绑定点选），中=交互网格（点格档案/行号拖选→浮动工具条：跳过行/收口区域，区域着色），右=解析结果（动态区域行数+数据表、静态字段）。修正以补丁 chips 呈现可逐条撤销，**落点只有一个：确认生成**（session overrides 仅对本文件本次生效；原「存回模板/另存新模板」已退役——上传页不承担规则维护）。上传仅收 `.xlsx`（旧版 `.xls` 请先另存）
4. **报价单**：报价员 convert（worktable→manual 报价草稿）→ 工作台编辑 → 发送/导出 `exported_at` 定稿 → 业务侧最终报价卡出现、流程 done。**报价外发审批门（2026-10-15）**：客户版导出冻结、平台内发送出门前须持有效许可（approved 且内容指纹一致，改价失效重批）；**发送撞闸 409 时原地弹审批发起窗**（与工作台导出口共用公共组件 OutboundApprovalModal，不再让用户另找入口）；审批单由调度面板「报价审批」列规则按业务路由到唯一总监（无规则降级广播先到先批），`action.flow.approve.pricing` 决裁；裁决条升级为外发审批条（责任人/已等待/转交）；调度页新增待审批队列（等待时长+催办，懒超时提醒 remind_hours 可配于 margin_alert 策略）

**写侧三重防线**（每提交端点）：商机访问 → 角色 action key（403）→ 阶段校验（流转卡优先/全局 flow 兜底，409）+ 下游依赖校验（409）。

**流转机制**：流转卡（flow_cards）每交付物一张，退回只移卡不动全局节点、被退回阶段向原角色重开；撤回=上游申请+下游审批；指派/转交= admin 或当前处理人，默认规则（FAE→boming、报价人→quoting、FlowAssignmentRule 业务默认）。

## API 端点（board 一次取齐）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/portal/opp/{oppId}/board` | 三栏看板聚合：商机/需求/方案(裁)/成本(裁)/报价/流转卡/审批状态 |
| POST | `/api/portal/opp/{oppId}/initiate` | 业务发起（一步到位） |
| POST | `/api/portal/opp/{oppId}/requirements` | 更新需求再提交（新版本） |
| POST | `/api/portal/opp/{oppId}/bom-schemes/draft` / `{id}/submit` | 方案草稿/提交 |
| POST | `/api/portal/opp/{oppId}/cost-sheets/upload` / `draft` / `{id}/submit` | 成本表上传/草稿/提交 |
| POST | `/api/portal/opp/{oppId}/convert-to-quotation` | 工作底表转报价草稿 |
| GET/POST | `/api/portal/opp/{oppId}/cards/...`（return/withdraw/approve/reject） | 卡退回/撤回链路 |
| POST | `/api/portal/opp/{oppId}/assign` / `transfer` | 指派/转交 |
| POST | `/api/portal/opp/{oppId}/quotes/{quotationId}/submit` | 报价单发送定稿（低于审批红线 → 409 + 自动建审批单） |
| GET | `/api/portal/opp/{oppId}/pricing-approvals` | 商机内外发审批单列表（徽标数据源） |
| POST | `/api/portal/opp/{oppId}/pricing-approvals/{id}/decide` | 总监裁决（approve 放行 / reject 必填意见 422）；权限 `action.flow.approve.pricing` |
| GET/POST/... | `/api/feed/{oppId}/messages|attachments` | 协作流 + 存档区（类别门控） |
| GET/POST | `/api/notifications/...` | 站内通知（铃铛/门户板块，见 [portal/notifications.md](../portal/notifications.md)） |

回归：`backend/tests/perm_matrix_e2e.py`（**80 断言**角色矩阵 + 指派角色校验 + 乐观锁 + 退回必填 + 审批门全链路 + 通知中心，隔离 8001 跑法见脚本头注释）。

## 数据库表（opportunities schema）

| 表 | 用途 |
|----|----|
| `opportunity_flows` | 一商机一流程（current_node + assignees{node→user_id}） |
| `opportunity_flow_nodes` | 时间线事件（submit/assign/complete/return/draft + artifacts） |
| `opportunity_flow_cards` | 流转卡（交付物↔节点，可见性/退回） |
| `opportunity_requirements` | 需求单版本（slots JSON，current/archived） |
| `opportunity_bom_schemes` | BOM 方案（draft/current/archived，configs JSON） |
| `opportunity_cost_sheets` | 成本表（draft/current，configs + quotation_id 关联） |
| `flow_assignment_rules` | 业务级默认指派规则（存姓名语义，指派生效时转 user_id） |
| `opportunity_pricing_approvals` | 报价外发审批单（margin/threshold/status/assigned_to/content_hash/requested_by/decided_by，驳回重发建新单留痕） |
| `notifications` | 站内通知（user_id/type/title/body/opportunity_id/payload/read_at） |

设计文档：[docs/协作流程方案/02-business-detail.md](../../协作流程方案/02-business-detail.md)（历史）；权限体系见 memory: portal-flow-perms-audit / auth-rbac-system。

## 移动端双抽屉（≤768px，2026-09-19）

桌面三栏映射为「中间工作台独占全屏 + 双抽屉」，改动集中在 `OpportunityProcessBoard.vue` 手机分支，桌面三栏零改动：

- **阶段工具条** `.stagebar`（新，仅手机渲染）：`☰流程` → 左抽屉；①-④ 迷你进度（done/current 判定与 Rail 同源：`approvals.state` + `flow.current_node`，点击同开左抽屉）；`动态` → 右抽屉，红点 = 该商机未读通知数（`GET /api/notifications?unread_only=true` 后按 `opportunity_id` 过滤，只读统计不代标记已读，开抽屉时刷新）。
- **左抽屉**（placement=left，宽 82%）：`OpportunityProcessRail` 整体复用（collapsed=false）；`@select/@select-substep` → 收抽屉 + 现有 `scrollToNode/scrollToSubstep` 定位链路。原「窄屏 rail 占满整行」特例退役。
- **右抽屉**（placement=right，宽 88%）：`ApprovalFlowPanel` 整体复用；桌面 `board-aside`（v-if !isMobile）与抽屉实例（v-if isMobile）互斥，单实例运行。pending 外发审批的裁决入口仍在报价卡上方（面板内），未做置顶重排（原型 C 的置顶裁决卡为 P3 打磨项，如实测面板排序可后续在面板内调）。
- **两抽屉互斥**：共享 `openDrawer: null | 'rail' | 'dyn'` 单状态。
- **sticky 动作条避让**：`bottom` 从 0 改为 `var(--cpq-tabbar-inset)`（全局底栏 58px + 安全区，见 DefaultLayout 全局变量）。
- **外壳样式**：`.opp-detail-drawer` 玻璃化覆盖走组件内全局 style 块（portal 够不到 scoped）。

## 移动端二次整改（2026-10-21，进行中）

双抽屉骨架之上，内容层系统性适配（设计定调沉淀在 [前端设计/布局与用法规范.md](../../前端设计/布局与用法规范.md) §4/§5）：

- **页头紧凑化**：`⋯` 菜单（右上角 fixed）收纳回收站/删除商机（危险操作不常驻页头，删除走 Modal.confirm）；标题 17px、状态/创建日期第二行。
- **工作卡统一沟槽**：≤768 `.board-body` 统一 12px 页边距，`opp-info-panel` 取消自带 margin——所有工作卡（商机信息/需求单/方案/成本/报价）同一宽度，不再一大一小。
- **卡头防挤压**：eyebrow/h3 加 nowrap+ellipsis；标题容器 `min-width:120px`，按钮组 `flex-wrap` 放不下换行——不再把「商机信息/需求单工作台」压成逐字竖排。
- **弹窗全屏化**：需求单/归档/编辑方案/编辑成本表/配置明细/分享/附件预览全部改走 `ResponsiveModal`（tier 档位），≤768 转全屏页 + 返回按钮 + 返回手势同步；编辑方案弹窗「上游需求单」手机端默认折叠（卡头可点开合）；解析预览手机端降级提示去电脑端。
- **表格卡片化**：`RecordTable` ≤768 自动转卡片列表（td `data-label` 显示字段名）；需求单/方案/成本/报价四张表已全部挂 label。
- **悬浮层**：提交需求单吸底条改 `fixed` 于 `--cpq-tabbar-inset` 上方（原 sticky 依赖的滚动宿主在窄屏换层吸不住）；AI 悬浮球拖拽夹取与全屏弹窗隐藏走 `body.cpq-fs-modal-open`。
- **异步组件防白板**：看板内全部 `defineAsyncComponent` 换 `lazyWithRetry`（chunk 加载失败自动重试 2 次，dev 热编译窗口不再出现"新建需求弹窗空白"）。
- 遗留打磨项：动态抽屉（ApprovalFlowPanel）内部仍是桌面布局；stagebar/桌面端不受影响。

## 状态变更弹窗（2026-10-12）

状态变更唯一路径 = 头部下拉选中目标后弹 `ResultChangeModal`（`components/opportunity/`），确认走 `POST /opportunities/{id}/result-change`，一次原子完成：

- **归因落库**：`result` + `extra_fields` 的 `loss_reason_keys（多选）/ loss_note / result_changed_at`（改回进行中/中标时清空归因）；丢标至少勾一项（调研表式勾选，非下拉），过期选填，任何变更必填一句话。
- **审计即跟进**：自动向协作动态发一条 kind=comment 的评论，首行 `【状态变更】旧状态 → 新状态 · 原因1/原因2`，第二行=填的一句话；跟进记录=右栏评论栏，不建独立表。
- **原因字典**：`system_config` key `opportunity.loss_reasons`（`[{key,label,enabled}]`），种子 10 项源自 FAE 进度表真实归因值；弹窗内「管理原因字典」入口（`page.settings.users` 门控）可增/改名/禁用/删除，历史 key 删除后回退显示 key。头部状态旁的红色 tag 显示当前归因，tooltip 带说明与变更日期。
- **te 角色修复**：`action.opportunity.result` 已加入 te 角色种子（role_repo `_DEFAULT_ROLES`），启动 `seed_missing_defaults` 自动补种到现有库。

## 中栏滚动修复（2026-10-13）

症状：中部内容再长也无法滚动（部分宽度下被裁切）。两条断链，均已修：

- **≤1080px**：页面壳 deep 选择器 overflow:hidden（两类名，特异性高于组件内单类名媒体查询的 overflow-y:auto）把单列整页内滚压死 → 壳内显式补同特异性媒体查询放行。
- **全宽度**：a-spin 的自定义 class（.board-spin）不会落到 antdv 的 .ant-spin-nested-loading 根节点，高度链钩子全部失配 → 容器无界；且中栏卡片 overflow:hidden 在 flex 里自动最小尺寸归零，内容一长卡片被压扁裁切、滚动容器永不溢出。改为按真实类名挂高度链 + .process-workbench 子项 flex-shrink:0。滚动职责：process-workbench（>1080）/ bod-page（≤1080）/ main-scroll（≤768）。

三档宽度已用隔离后端（AUTH_ENABLED=false + 8010 端口）+ 注入探针实测滚动通过。

**卡壳融合修复（同日）**：方案配置/成本核算的卡壳 `.rich-card.card-collapsible` 原本只有 box-shadow（无底/边/圆角），卡头自刷灰底成方角通条，与内层自带 14px 圆角壳的 .bom-workbench/.cost-workbench 割裂成两块。修法：外层 `.card-collapsible` 补全 opp-info-panel 同款玻璃卡配方，`.card-shell-head` 改透明头+柔化分隔线，内层两工作台去自带壳——头与展开抽屉融合为一张圆角卡。报价单节点成本表行的操作钮（转为报价草稿/退回成本表/删除）包进 .qw-sheet-actions 成组右聚，修掉 space-between 散放导致的"一个居中一个靠右"。
