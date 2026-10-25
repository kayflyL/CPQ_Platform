---
name: portal-ai-shell-pluggable
description: 工作台/portal 形态演进：AI 壳(09-14定调)→09-28 改版为磁贴墙，聊天收拢到全局浮动助手
metadata: 
  node_type: memory
  type: project
  originSessionId: 63c2b4c8-8f11-4344-a520-5e0ea41a5453
  modified: 2026-09-28T05:53:24.178Z
---

`/portal` 工作台形态演进（碰门户/AI 入口前先看）：

1. **2026-08-14 定调（AI-first 壳）**：输入区为主角复用 useAssistant，不造意图识别/dispatch（走现有 AI 同事系统）。此形态 **2026-09-28 已退役**。
2. **2026-09-28 改版（磁贴墙，现行）**：页面=待办卡(左上)+角色 hero(右上)+方案助手磁贴(左下)+三张入口磁贴(底排)，单屏无滚动。**聊天入口收拢**：PortalAIInput/portalAssistant.ts 已删，点「方案助手」磁贴经 `useAssistantShell`（模块单例开关）唤起 DefaultLayout 持有的全局浮动助手；AssistantPanel 新增桌面全屏形态（`ap-fullscreen`，右栏按钮/Esc 切换，禁拖拽缩放）。待办数据=`GET /api/portal/todo-summary`（角色化口径，见 [[workbench-tile-wall-implementation]]）。
3. 仍然有效的原则：**门户/工作台零新 AI 逻辑**，聊天能力全部走全局助手（[[chat-session-runtime]] 保证换形态会话不丢）；入口按权限可见。

**Why:** 用户 09-27 定调参考奥迪 DDMP 经销平台：磁贴墙视觉 + 浮动助手全屏化；两态门户页退役，"AI 开场感"由磁贴墙上的方案助手入口承担。

**How to apply:** 改 /portal 先读 [docs/frontend-pages/portal/portal-home.md](../../docs/frontend-pages/portal/portal-home.md)；磁贴增删改 TILES 注册表（perm 与路由 meta 同套 page.* 键=权限联动物理同源）；别往工作台塞内嵌聊天。
