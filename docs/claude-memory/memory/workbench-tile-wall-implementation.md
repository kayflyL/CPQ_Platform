---
name: workbench-tile-wall-implementation
description: 09-28 工作台磁贴墙实装落点：Portal.vue TILES 注册表/todo-summary 端点/AssistantPanel 全屏形态/useAssistantShell
metadata: 
  node_type: memory
  type: project
  originSessionId: 14c1c9bd-5e8c-43c0-aefe-24deb15b1f73
  modified: 2026-09-28T05:53:44.913Z
---

工作台磁贴墙 2026-09-28 实装（原型 docs/prototypes/工作台磁贴墙原型.html）：

- `Portal.vue` 重写：`TILES` 注册表（12 张磁贴带 perm/roles/scene）→ `visibleTiles` 动态槽位（第 1 张=hero，后 3 张底排 flex，隐藏前移不留空洞）；插画 `SCENES`（currentColor+透明度分层主题自适应，`.al`=accent 线、`.pulse`=SMIL 替代的 CSS 脉冲）；待办格图标 `GLYPHS`+`TODO_ICONS` 按后端 key 映射。
- 后端 `GET /api/portal/todo-summary`（portal.py 末尾）：按 role 分支——business=本人商机按流程节点分布(6格)/te·cost·quote=list_task_flows 本人节点任务+今日到达/admin=dispatch_snapshot.stuck+在办+今日新增；**坑：角色→节点映射表 `_TODO_ROLE_NODE`，别拿节点键当角色键匹配**（首版 bug）。
- `AssistantPanel.vue` 第四形态：`apFullscreen` ref + `canToggleFullscreen`（仅浮动面板、非手机）；panelStyle 全屏分支与手机共用 100vw/100vh；Esc 监听挂 window，open=false 时复位；全屏禁 startDrag/startResize。
- `useAssistantShell.ts`：open 模块单例，DefaultLayout 与 Portal 磁贴共享（跨路由唤起浮动助手）。
- 报价工作台磁贴 roles 限 business/cost/quote，任务调度限 admin——否则管理员 hero 会被报价工作台抢占。
- SkillStudio 内嵌试运行聊天、办公室 3D 角色聊天**不动**；workstation 子页无独立聊天面。

相关：[[portal-ai-shell-pluggable]]（形态演进）、[[solution-platforms-bind-real-models]] 同页权限联动手法。
