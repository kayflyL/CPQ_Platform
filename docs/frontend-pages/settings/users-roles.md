# 用户与权限（设置 → 用户与权限）

> 最后更新：2026-10-02（界面 10-01 大改版同步：抽屉化/底版+增量编辑器/分页排序；补充 10-02 分页与弹窗搜索）

设置子菜单「用户与权限」（`/settings/users`，`UserRoleManagement.vue`）。仅 `page.settings.users` 权限可见。

## 页面结构（2026-10-01 改版后）

**Tab 用户管理**（默认）：
- 工具行 = 状态过滤器（全部/已启用/已停用，带计数）+ 搜索（姓名/企微ID）+「＋新建用户」
- 成员表：头像+姓名（企微ID 副文本）/ 角色色点徽标 / 最近活跃（`last_login_at` 相对时间，>30 天或未登录灰显；**仅新登录起有数据**）/ 状态徽标 / 行尾 ⋯ 菜单（查看详情/重置密码/停用·启用/删除——admin 角色与本人禁删）
- **分页 20/页**（`hideOnSinglePage`），用户列按姓名排序、最近活跃列可排序；筛选/搜索后不足一页自动隐藏页码
- 行点击 → **用户详情抽屉**：账号信息（企微 ID 行内编辑）+ 角色下拉（带职责说明，改角色即时生效）+ 操作（重置密码/停启）+ **危险区**（删除 → 引用清单+转接人确认流，`DELETE /api/admin/users/{id}`，参考 [[perm-gap-audit-2026-10]]）

**Tab 角色管理**：
- 角色表：角色名（内置/超管徽标）+ 描述 / **成员数**（蓝链，前端从用户表现算）/ 权限 dot 条+计数 / ⋯（编辑权限/查看成员/**复制此角色**/删除——内置角色禁删，有成员时后端 400）
- 行点击 → **角色抽屉**（1080 双栏，权限配置 / 已授权成员 双 Tab）
  - **权限配置（V2 编辑器）**：底版机制——新建先进底版选择卡（空白+5 内置角色），编辑已有角色自动选重叠率 ≥50% 的底版；Diff 汇总条「基于『X』· 基础 N 项 ＋x −y = 当前」+ 增/减 chips（✕ 撤销）；权限树按三类语义分组（页面/字段/操作）×模块二级，每项带 基础/＋增量/底版划掉 徽标；**列表/网格双视图**（网格=模块×五类动作矩阵，短标签映射 `SHORT_LABELS`）；换底版且已有调整时弹「重置为其集合 / 仅换对比基准」。保存的永远是最终权限集合，底版只是编辑参照
  - **已授权成员**：成员列表+移除（转 member）+添加成员弹窗（带搜索）
  - 侧栏：角色信息表单 + 保存前预览（权限总数/等价于/覆盖模块/敏感权限）
- admin 角色特判：权限面板显示「默认全部」说明，禁删

## 权限体系三层

- **权限目录**：`system_config.auth.permissions`（DB JSON，`GET/PUT /api/auth/permissions`）。条目 = `{key, name, group: page|field|action, module}`。key 是契约（前后端 enforcement 引用），name/module 纯显示。
- **角色**：`rules.roles` 表，每角色一个 permissions key 列表。`admin` 角色特判 = 目录全量兜底（`role_repo.permissions_of`），普通角色显式列 key。
- **判定**：后端 `user_has_permission` / `require_perms` / `field_visible`（`app/api/deps.py`，AUTH_ENABLED=false 灰度期恒放行）；前端路由守卫 `meta.perm`（router/index.ts:263）+ 菜单 `v-if="auth.can(...)"`（DefaultLayout）+ 组件内 `auth.can`。

## 目录分组对齐真实页面（2026-09-16 二次梳理）

抽屉里权限勾选按 module 分组，组序 = 页面真实层级：**商机线索（菜单）/ 商机线索 · 商机详情 / 商机线索 · 报价工作台 / AI 办公室 / 服务器 / 配件 / 解决方案 / 设置**。名称写页面里的真实文案（按钮/栏/字段），层级用「·」表达。无「工作台」组——门户工作台（/portal）恒开不挂权限，原混在「工作台」组的 key 已各归其位。

| key | 名称 | 门控对象 |
|---|---|---|
| page.opportunities_all | 商机线索菜单（数据范围 = 全部销售的商机） | 商机线索菜单本体；无 = 只看自己的商机 |
| page.opportunities | 商机子页面：商机详情 / 报价工作台 / AI 线索 / 回收站 / 门户任务页 | 商机域全部子路由（含 /portal/workstation 任务页） |
| field.opportunity.quote_price | 报价金额可见 | 商机详情/列表的报价单价格（quotations/portal 遮罩） |
| field.flow.bom / field.flow.cost | 存档区 · 方案/成本附件可见 | 商机详情流程看板的存档区两分类（ArchiveSection） |
| action.flow.submit.* / return.* / approve.pricing | 发起·编辑·提交·退回·审批 | 商机详情流程操作按钮（portal.py 全量二次校验） |
| field.quote.price / field.quote.export_internal | 价格字段可见 / 导出对内版 | 报价工作台价格列与导出 |
| action.flow.submit.quoting / return.quoting / action.quote.unfreeze | 发送报价单 / 退回市场报价 / 解冻已导出报价单 | 报价工作台（QuoteWorkbench + 成本抽屉 + 详情解冻入口） |
| page.office | AI 办公室菜单与页面 | `/ai-office` 菜单+路由 |
| ai.office.manage | AI 办公室管理 · 员工 / 团队 / 工作流 | 管理面（Manage Teams 打开）左栏前半：员工/团队/工作流/工具目录编辑 |
| ai.office.admin | AI 办公室管理 · 模型与接入 / 运行与权限 | 管理面左栏后半：模型与接入/运行与权限 + 跨账号会话管理/审计/trace 清理。**Manage Teams 按钮任一权限即可见**（只授本权限也能进管理面，左栏仅显示后半两段） |
| page.servers / page.parts / page.strategies | 服务器 / 配件 / 解决方案（策略中心全部子页） | 各菜单+子路由 |
| field.parts.price | 配件价格可见（库价/价格历史） | KP库/料号库/价格历史/异动/比价/L6整机价的读面 + `/api/kp/parts` 选件价（admin.py/parts.py/kp_config.py/bom_cases.py 遮罩）；无键=配件页「查型号模式」 |
| action.parts.price.manage | 配件价格维护（录价/改价/价格导入导出） | 价格记录增删改、KP/料号价格导入导出、配件编辑载荷里的价格键（2026-10-16 起价格写从 page.parts 拆出） |

**价格 fail-closed（2026-10-17 定调）**：`field.quote.price` / `field.opportunity.quote_price` / `field.parts.price` 三键为机密级——**AUTH_ENABLED=false 灰度期也不豁免**，匿名/无授权一律不可见（deps 的 field_visible/user_has_permission 与前端 store can() 三处同源收口，AI 链路 effective_price_ok 经 user_has_permission 自动跟随）。其余权限键灰度期仍恒放行（灰度语义不变）。
| page.settings.* | 用户与权限 / 解析规则 / 导出模板 / 服务器管理 | 设置子菜单四项 |

已删死键（零 enforcement，曾被误当可用开关）：`page.portal`（工作台恒开）、`page.settings.ai`（AI 设置已并入办公室，由 ai.office.manage 管）、`field.server.price`。`field.parts.price` 曾因从未接线被回收，**2026-10-16 复活并全链路接线**（防复发网见 `backend/tests/test_parts_price_gate.py` 的路由源码扫描）；持有角色：quote（2026-10-16 补授）/cost/director，business/te 有意不给。

角色种子速查：business/te 无任何价格键；quote 持 `field.quote.price`+`field.parts.price`（报价拼 KP 行价靠库价）；cost/director 另持 `action.parts.price.manage`。

## 角色权限编辑器（2026-10-17 三带层改版）

编辑器按「层优先」组织，替代旧列表/网格双视图（均已删除，不留并列模式）：

- **第一带 · 页面权限（进哪里）**：一个域一张磁贴（page.\* 聚合），单页面域=磁贴头大开关，商机线索/设置多页面域=贴内逐行开关。关了 = 导航不出现、路由进不去。
- **第二带 · 字段可见（看什么）**：全系统 6 个字段键的清单行（域前缀 + 名称 + 说明 + 开关）；价格三键带「机密」徽。
- **第三带 · 操作权限（能做什么）**：按域折叠组（默认收起、首组展开），组头 = 已开 N/M + 整组批量开关，展开逐项开关；增量绿字、底版划掉删除线。
- **机密键确认**：勾开价格四键（field.quote.price / field.opportunity.quote_price / field.parts.price / action.parts.price.manage）弹二次确认，写明影响成员数。
- **生效语义**：抽屉保存按钮旁与保存成功提示均写明「N 名成员需刷新页面生效」（替代旧「即时生效」的错误文案）。
- **两 Tab 打通**：角色表成员列 = 头像堆叠（点开成员管理）；用户表角色徽章可点击直达该角色编辑。
- 保留未动：底版+增量三步（diff 压成上下文条一行）、已授权成员 Tab、⋯菜单、用户详情抽屉、危险区。规格样张：docs/prototypes/权限磁贴墙-原型.html。

## 种子语义（startup.ensure_permission_catalog）

幂等：**已知 key 的 name/module/group 强制对齐 `_DEFAULT_PERMISSIONS`**（菜单改名后目录自动跟随，标签是 canonical）；管理员新增的自定义 key 只补缺不动；`_REMOVED_PERMISSION_KEYS` 死键回收。目录条目顺序 = 种子顺序，与分组展示无关。

相关迁移：`scripts/refresh_permission_catalog_20260916.py`（目录刷新 + 存量角色补 page.office + 角色死键清理）。
