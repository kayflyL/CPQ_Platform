---
name: office3d-refactor-plan
description: 办公室3D绞杀式重构计划：权威文档docs/OFFICE_3D_REFACTOR_PLAN.md，R0基线→R1抽nav→…→R5薄壳，最终office3d/纯TS引擎，收益期=精细度/VRM/展厅
metadata: 
  node_type: memory
  type: project
  originSessionId: 664fb221-1fa1-46a2-bc1c-f12f6018e43c
  modified: 2026-09-29T07:32:27.844Z
---

AI 办公室 3D 前端重构分步计划（2026-09-28 定稿，用户拍板「慢慢一步一步改」）：

- **权威计划文档**：`docs/OFFICE_3D_REFACTOR_PLAN.md`（含每步搬哪些函数、行号锚点=2026-09-28 快照、验收清单、进度表）。进度表在文档里更新，不在本记忆里。
- **最终目标**：`frontend/src/office3d/` 纯 TS 引擎（core/assets/environment/characters/nav 六模块，零 Vue 依赖），Office3DCanvas.vue（4400 行）收到 ≤300 行薄壳。收益期三件事：F1 精细度（灯光/GLB家具）、F2 VRM 角色（@pixiv/three-vrm 按 CharacterAsset 接口接入）、F3 3D 展厅（复用 core+assets+nav）。
- **顺序**：R0 基线护栏 → R1 nav 纯函数+单测 → R2 资产缓存 → R3a 房间墙 → R3b 家具 → R4a 气泡标签 → R4b 角色系统（风险最高）→ R5 引擎核心+薄壳。
- **进度**：09-28 R0-R4b 完成（R4b 用户已目检放行）——office3d/{nav,assets,environment,characters} 全模块落地（actorSystem=createActorSystem(rt) 闭包工厂，模拟层零 Vue 可独立实例化），SFC 4400→2199 行（-50%），build+28 单测全过；房间组抽取随并行会话暂缓；**R5 形态重估**：不再抽 Engine 类（tick/拾取与 Vue 强耦），改为房间组+二次收口（详见计划文档 R5 重估节）；**F1 已开工**：IBL 环境光贴图落地（桌面档 0.45，移动档跳过；ACES/软阴影发现已在位），目检待确认，余项=家具 GLB 资产化+后处理；**F2 pilot 已落地并实机验证**：vrmLoader（rotateVRM0 归一+原始骨骼驱动，克隆+mixer 与 GLB 同路）+ vrmClips（T-pose 基烘焙 idle/walk/sit，世界轴摆动经父级世界四元数换算，坐姿降髋需除以 scale——单测抓过此 bug），样例 VRM 已进办公室（character_models 头部，DB 改前必备份），走/坐/待机全链路过，31/31 单测；**AI 生成 GLB 接入管线已通,两条路**:① 平台已绑骨(Meshy 直出/Tripo 付费)→ scripts/fix-ai-glb.mjs 修复(权重归一+IBM 对齐静止+躺平骨架站起,verify-glb.mjs 独立校验);② 静态导出 → Mixamo 免费绑骨(用户传 OBJ zip,下载 T-pose+Skin 的 FBX)→ **Blender 无头转换**(用户装了 D:\APP\Blender 5.2,-b --python 跑:应用变换+mixamorig: 冒号换下划线;别下载便携版,GitHub release CDN 不通、清华镜像快)→ glbSkeleton.ts 骨骼名映射(生成器名→canonical,含 mixamorig_)。注意:0.01 缩放系模型(Blender apply 后)包围盒=0.01,办公室按 1.42/height 缩放自动补偿 ✓,但 vrmClips 位移常量是世界米制,必须除以 s=1.42/height(hipsShiftedPos/hipsSeatedPos 已带 height 参数)（烘焙器已升级面向自测量，不假设面朝 +Z；frontRotation 用脚尖方向推导(L_ToeBase−L_Foot;手臂推导正反对称五五开曾推反 180°;idle/done 状态动画已改 working 坐工位)）→ 方案助手已穿 meshy-girl 实机坐岗；**配置配方=模型 URL 同时进 character_models 池 + 同事 model_url（缺一认领不生效）**；余项=VRMA/弹簧骨骼/正式授权模型。技术约定：office3d 模块运行时导入带 `.ts` 扩展名；>150 行文件写入用 heredoc/sed 拼，**.test.ts 即便小文件也掺杂质高发（本日两连坑），逐块 ≤15 行追加+每块 wc 验证最稳**；sed 区间锚先验证首尾；`from .` 类 sed 通配会吃引号（已三次踩坑，导入行改动用 Edit 不用 sed）；实机验证用 launch.json 的 backend-verify(8010 免认证)+frontend-verify(5174)，canvas 相机/actors 摸 `.office-3d-canvas.__vueParentComponent.setupState`，手动 updateActorStatus 后必须补 scheduleRouteRecompute() 才走路；GLB 二进制操作必须用 three 数学（Buffer 直接 fromArray 会把字节当浮点）+ 写后独立校验。
- **铁律**：绞杀式不重写；抽出的模块靠参数收上下文**绝不回读组件状态**；每步验收=build+node --test+officeDebug 手巡+用户目检视觉零回归；禁 git restore。
- **测试跑法**：`node --test frontend/src/xxx/yyy.test.ts`（Node 原生 TS 剥离，`.ts` 扩展导入，参照 `src/stores/selectionEngine.test.ts`），不引入 vitest。

**Why:** 后续三需求（精细度/VRM/展厅）都压在这套代码上，先拆再上功能；跨多会话推进，每次接续先看计划文档进度表。
**How to apply:** 碰 Office3DCanvas/办公室 3D 改动先读 `docs/OFFICE_3D_REFACTOR_PLAN.md`，改完刷新文档进度表+本文档描述；新功能若属于 F1/F2/F3 先确认对应 R 步已完成。关联 [[office-3d-layout-seed]]（布局种子与迁移）、[[small-batch-reads-avoid-stream-drop]]（拆解时小批量读）。
