---
name: office-3d-layout-seed
description: AI办公室3D布局改法：种子在ai_colleagues.py _DEFAULT_OFFICE，DB是权威，改种子必须配旧坐标精确匹配的迁移才会生效
metadata: 
  node_type: memory
  type: project
  originSessionId: 574460d1-0de8-4a9c-b6cb-5fdc11556e7e
  modified: 2026-09-16T12:41:28.888Z
---

AI 办公室 3D 布局链路（2026-09-16 白板搬家+补门扇时摸清）：

- **种子**：`backend/app/api/ai_colleagues.py` 的 `_DEFAULT_OFFICE`（zones+furniture）。
- **权威在 DB**：`rules.system_config` key=`ai_colleagues` 的 `layout.office`。`_read_config` 只补缺失键、
  只有 `furniture_catalog` 每次强制刷新 —— **光改种子对已有 DB 无效**，必须配迁移（`_migrate_office_whiteboards`
  模式：旧坐标精确匹配才搬，幂等，返回 bool 接 `config_changed` 持久化）。
- 前端渲染：[Office3DCanvas.vue] 非会议室房间 `buildRoomShell` **只有 zone 带 `door` 配置才建墙+门洞**
  （`createRoomWalls`）；墙不参与寻路（`meetingWallBlocked` 只挡会议室），门扇半开 1.2rad 纯装饰。
- 坐标系：zones x 左负右正；办公室人坐桌子 +z 侧面朝 -z；贴墙挂件中心 = 墙内表面 ∓ 0.09
  （墙厚 0.12 中心在边界线上）；rotation_y=0 时白板书写面朝 +z，转 π 朝 -z。
- 工位朝向：`slotForward(0)=(0,0,1)`，座位锚点 = 桌位 + forward×0.95。

**Why:** 用户在持续打磨 AI 办公室场景，改布局时曾以为改种子就生效。
**How to apply:** 碰办公室布局：种子+迁移一起改；查现网实际布局先查 DB（postgres `rules.system_config`）。
关联 [[app-startup]]（后端 venv：`D:/CPQ_Platform_V1/backend/.venv/Scripts/python.exe`）。
