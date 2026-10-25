---
name: auth-rbac-system
description: 2026-08-09 新增的 JWT 认证 + 角色/权限 RBAC 系统（AUTH_ENABLED 灰度 + 价格字段级遮罩）
metadata: 
  node_type: memory
  type: project
  originSessionId: 9f14b11f-2b2f-4eb0-ad43-6270dd89f69c
  modified: 2026-09-16T10:12:38.686Z
---

2026-08-09 codex 一次性落地了完整认证授权体系（此前完全没有），碰任何 API/前端入口前先意识到它的存在：

- **JWT 认证**：`backend/app/api/auth.py` + `core/security.py` + `api/deps.py`；`AUTH_ENABLED`（config）是灰度开关，关闭时鉴权放行，前端 router/store 联动该开关；启动时引导首个管理员。
- **RBAC**：`models/role.py` + `repository/role_repo.py` + `api/roles.py`；后端业务端点用 `deps.require_perms("field.quote.price")` 等装饰器强制。quote/feed/assistant/compatibility_rules/system_config/requirement_rules 等端点已加保护。
- **价格字段级可见性**：`backend/app/utils/price_mask.py` —— 报价工作台(Workspace) + 商机详情(OpportunityDetail) 按权限遮罩价格字段（PriceTriple 配合）。这是 RBAC 落到业务字段粒度的关键。
- **前端**：`views/Login.vue` + `Forbidden.vue` + `store/auth.ts` + `api/auth.ts` + `api/rbac.ts`；路由守卫；`views/admin/UserRoleManagement.vue` 用户与角色管理页；`layouts/DefaultLayout.vue` 集成。

注意：认证这套没进 docs/CHANGELOG.md（CHANGELOG 从 0.1.53 起记的是需求分析改革）。加新 API 端点默认应挂 `require_perms`/`get_current_user_optional`。关联 [[assistant-skeleton]] [[opportunity-identity]]。

**权限目录对齐菜单（2026-09-16 刷新）**：目录 `system_config.auth.permissions` 曾与导航菜单严重脱节（page.opportunities 与 _all 共用「商机线索」名导致勾错、策略中心≠菜单「解决方案」、三个零 enforcement 死键、AI办公室无页面权限）。定调：**key 是契约，name/module 标签 canonical 跟菜单走**——`startup.ensure_permission_catalog` 对已知 key 强制对齐 `_DEFAULT_PERMISSIONS` 标签（菜单改名目录自愈），管理员自定义 key 只补缺不动，死键进 `_REMOVED_PERMISSION_KEYS` 回收。分组组序=菜单栏：工作台/AI 办公室/商机线索/服务器/配件/解决方案/设置（UserRoleManagement.moduleOrder+moduleOf 同步）。`page.office` 门控 AI办公室菜单+路由，**存量角色迁移时全部补授保现状**（admin=目录全量兜底无需处理）；工作台/门户与全局浮动助手有意恒开不挂权限（AI-first 壳层）。文档：docs/frontend-pages/settings/users-roles.md。

**同日两修**：①角色保存失败=RoleBody.role_key 必填而前端 PUT 不带 → 改 Optional（key 走路径参数）；②办公室访问权限清零某角色 AI 名单后浮动助手仍现「方案助手」兜底死面板 → `/api/auth/me|login` 增 `chat_roles_allowed`（office_access.allowed_chat_role_keys 空→False），DefaultLayout v-if 隐藏 FAB+面板；门户输入区有意不门控；策略改动随 /me 需重登/刷新生效。

**同日三次梳理（用户指摘目录对不上界面）**：module 用「商机线索 · 商机详情/报价工作台」层级串（「工作台」组撤销——门户恒开无权限，page.opportunities 归商机线索、field.quote.* 归报价工作台）；name 写界面真实文案（ai.office.manage=「AI 办公室管理·员工/团队/Skill Studio」，ai.office.admin=「·模型与接入/运行与权限」，对齐管理面左栏两段；field.flow.*=存档区方案/成本附件）。改目录标签=改 `_DEFAULT_PERMISSIONS` + 手动跑 ensure_permission_catalog()（DB 即时生效）+ 前端 moduleOrder/moduleOf 同步。**Manage Teams 按钮 v-if 任一权限可见**（用户指出只授 admin 进不去管理面=多此一举）；AiOfficeManagement.activeNav 用 watch 兜底到第一个可用左栏项。
