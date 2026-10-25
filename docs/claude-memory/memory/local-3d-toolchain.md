---
name: local-3d-toolchain
description: 3D 角色工作链工具迁至 D:\tools\cpq3d\（Blender 4.2.9 便携版/vrm-src 素材/fbx 工具/脚本，路径已改指新址）；仓库 tmp/ 已删除；用户另有桌面版 Blender 5.2（不在 PATH）
metadata:
  node_type: memory
  type: project
  originSessionId: babef718-9b52-47b1-8ff6-9ee23f732298
  modified: 2026-10-01T10:53:41.592Z
---

2026-10-01 上线清理时把仓库 `tmp/`（约 1GB）整体迁出，**仓库内已无 tmp/ 目录**。新址：

- `D:\tools\cpq3d\blender-4.2.9\` — Blender 4.2.9 便携版（974MB，09-29 Mixamo 绑骨工作链下载的，无头 bpy 脚本用；钉 4.2 LTS 因 5.x 有 API 变动）
- `D:\tools\cpq3d\vrm-src\` — 3D 角色素材（meshy/tripo 系列 glb、tripo-mixamo.glb 绑骨成品）
- `D:\tools\cpq3d\fbxconv\` — node 版 fbx 转换工具（node_modules 在内）
- `D:\tools\cpq3d\plan_crops\`、`plan_tiles\` — 办公室 3D 平面图素材；`samsy-main.js`、`plan_draft_check.mjs` 也在 cpq3d 根
- `D:\tools\cpq3d\scripts\` — convert_fbx.py（FBX→GLB）、bin_sink.py（:8772 模型上传接收）、png_sink.py（截图接收）——**三个脚本内的输出路径已全部改指 `D:/tools/cpq3d/vrm-src`**
- `D:\tools\live2d-models\` — live2d-widget-model-{haru,haruto,wanko}-1.0.5.tgz

**用户桌面另有 Blender 5.2**（7-20 装的，per-user 安装：不在 Program Files、不在 PATH，配置在 AppData/Roaming/Blender Foundation/Blender/5.2）。convert_fbx.py 用的 bpy 接口（import_scene.fbx/transform_apply/export_scene.gltf）理论上 5.x 兼容但**未实测**；要省 974MB 可先用 5.2 无头跑通一次转换再删便携版。

碰 Office3D/VRM/3D 形象工作前先看本条+[[office3d-refactor-plan]]。
