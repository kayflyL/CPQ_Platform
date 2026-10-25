---
name: office3d-elastic-head-anchor
description: AI办公室3D头顶名牌/气泡/状态球的Y必须用模型实测包围盒锚定+坐姿偏移，禁止魔法数常量（模型一换就飘）
metadata:
  node_type: memory
  type: project
  originSessionId: 11ac8fc6-c7ce-4016-aad1-4416a558e39f
  modified: 2026-10-08T03:10:58.612Z
---

AI 办公室 3D 场景中，角色头顶三件套（名牌 label / 状态气泡 bubble / 状态球 indicator）的 Y 定位**禁止写死常量**（旧值名牌 2.42/气泡 1.58/状态球 1.62，换模型或坐姿就悬空/穿头）。

**正确做法（actorSystem.ts + Office3DCanvas.vue）**：
1. 模型加载后**实测包围盒**：`Box3.setFromObject(model)` 取 max.y = headY；并用实测高度二次校正归一化缩放（登记元数据 template.height 可能缺失/不准，勿信）；
2. 三件套 Y 全部由 headY 推导：名牌 headY+0.42、气泡 headY+0.10、状态球 headY+0.16（actor 上存 labelY/bubbleY/headY）；
3. **坐姿动态偏移**：坐姿时角色 group 下沉 seatY 且 sit 动画压低头部，每帧 `label/bubble/indicator.y = 锚定Y - 0.34`（sitting 时），站姿归零。

**10-03 深夜回归+终修**：第一版弹性锚定里的"整模型二次缩放"（Box3 普通包围盒实测→乘系数）被**远端节点污染**（骨骼绑定位/远处网格撑大包围盒→实测虚大→系数把模型缩到不可见）——用户报"角色全消失"。终修四件：①撤销二次缩放，归一化回归元数据 scale；②改名/实测一律用 **precise**：`Box3.setFromObject(root, true)`（r151+ 逐顶点世界坐标含蒙皮——蒙皮 GLB 普通包围盒是绑定位姿塌缩值，data-analyst.glb 实测 0.01 vs 真实 ~1.8，差 142 倍）；③headY 钳制 [0.9, 2.4]；④每帧挂载加 Number.isFinite 防护。**vite 长跑实例 HMR 腐坏**也是本案例一环：几十次热更新后模块图半新半旧，症状=three-vrm uncaught promise + scene 不初始化，重启 dev server 即愈；gltfCache 同名 import+re-export 会加剧 HMR 重复声明报错（改只 export 导入绑定）。环境光 0.18 非我改，已还原 0.45。

**10-08 数据分析师球悬空【已修复】**:用户报"数据分析师状态圆点比谁都高"。根因=data-analyst.glb(Mixamo 绑骨 AI 生成)绑定位姿顶点云塌缩到 ~0.01(142 倍缩放由此来)且骨架云悬空,旧代码用**绑定位姿**包围盒测 headY → 测出 201 → 钳到上限 2.4 → 球站姿 2.56(其他角色 1.06~1.50)。修法(actorSystem.ts createCharacterFromTemplate):mixer/clips 创建提前,先 `idleAction.play()+mixer.update(0.5)` 让骨骼摆出真实姿态,再 precise 测 box → data-analyst 实测 **1.414**(脚踏实地,与 Node 严格复刻/调查复现三方吻合);钳制 [0.9, 2.4]→[0.9, 2.0]。**同时删了 updateOverheads 的死码段**(1.62 魔法数+waiting 缩放脉冲——每帧被 Office3DCanvas.vue tick 弹性锚定覆盖,缩放脉冲 tick 里 animation 分支另有一份活的);updateOverheads 现在只管气泡淡出。回归:assistant headY 1.002 与修前 0.999 一致。**踩坑记录:临时脚本复刻时 bakeProceduralClipsIfMissing 必须在 scale 之前调(生产在 load 时烘焙)——scale 后烘焙会产出把骨架抬到悬空 0.4 的坏 clip,测出 1.81/假象;对照实验时先核对烘焙时机**。data-analyst.glb 文件本身的绑定位姿缺陷没修(换模型才是根治)。

**Why:** 2026-10-03 用户报"方案助手名牌/绿点/已完成提示离角色太远、像硬编码，换模型就很怪"——三层根因即上述魔法数+元数据信任+坐姿不跟随。

**How to apply:** 动 office3d 角色悬挂件时，一切 Y 从实测 headY 推导；新增悬挂元素同理；勿信资产登记的 height 字段。相关：[[office3d-refactor-plan]]。

**三条过程铁律（今晚两次返工换来的）：**
1. 主链零新雷：任何实测/探针/测量代码进主链必须 try/catch + 明确回退值，失败绝不中断角色构建链；
2. 每完成一个语义完整的修改，立即在完整环境整页刷新走一遍主流程——不攒批、不在坏中间态上继续叠（HMR 失败会把坏模块钉死在用户页面）；
3. 用户报异常时，第一个动作是让用户把 console 红字**完整展开**抓来，而不是自己翻旧记忆猜——10-03 全消失事故的真因（VRM 碰撞体 updateWorldMatrix 抛错）一秒钟就能从红字里读出来，我却挖了两个小时旧档案。
