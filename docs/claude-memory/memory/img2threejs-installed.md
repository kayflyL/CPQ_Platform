---
name: img2threejs-installed
description: img2threejs skill 已装到 ~/.claude/skills/img2threejs（v1.4.1），图片→程序化 Three.js 模型；纯 Python 3.10+ 零依赖；客户端实时识别
metadata: 
  node_type: memory
  type: reference
  originSessionId: 12ddfd66-c961-4387-b062-1713aabc8dc9
  modified: 2026-07-27T02:15:29.227Z
---

2026-07-27 装 **img2threejs**（Apache-2.0，v1.4.1）到 `~/.claude/skills/img2threejs/`，客户端下一次 system-reminder 立刻列出，`Skill(img2threejs)` / `/img2threejs` 可调起。

## 它是什么

把**单张物体/角色参考图**重建为**代码生成的程序化 Three.js 模型**（THREE.Group factory），不是摄影测量/网格提取/素材包。分阶段雕刻流水线 + AI 视觉自校正循环。

- 纯 Python 3.10+ 标准库，**零依赖**（无 pip/PIL/numpy/Playwright；PNG 用 struct+zlib 手写）
- Agent-agnostic（Claude Code / Codex / OpenCode 都行）
- 本机 git clone github.com **没被墙**（直接 `git clone --depth 1 https://github.com/img2threejs/img2threejs.git ~/.claude/skills/img2threejs` 成功）

## 怎么用

```
# 入口：附图 + 一句话，skill 自己分类/盘点细节/逐 pass 门控
/img2threejs 把图里这个物体重建为 Three.js 模型，保持比例/角度/颜色
```

关键：**第一步永远先跑** `python3 forge/next.py <spec>`，它会告诉你当前解锁到第几个 pass、下一条确切命令、未满足的验收标准。

## 流水线（forge/ 目录下脚本）

1. **stage1_intake** — `probe_image` 校图、`extract_pbr_evidence` 抽 PBR、`build_detail_inventory` 切片盘点、`extract_landmarks`/`solve_camera_pose`/`delight_albedo`（角色用）
2. **stage2_spec** — `new_pre_spec_assessment` 分类+复杂度、`new_sculpt_spec` 出 ObjectSculptSpec、`validate_sculpt_spec --strict-quality` 卡浅规格
3. **stage3_build** — `orchestrate_passes` 锁 pass 状态、`generate_threejs_factory` 出 `createObjectNameModel(spec,options)` TS factory、`bake_projected_texture` 投影贴图
4. **stage4_review** — `make_comparison_sheet` 出「参考图 vs 渲染」并排对照单、`append_review` 记评审、`cs2_review` 卡 CS2 刀审合约

**脚本做强制，模型做判断**：验证/门控/spec/PBR/对照单打包全在脚本里，模型 token 只花在「看对照单判 pass/fail」这一件事上（token-efficient，详见 `docs/TOKEN_COST.md`）。

## 产出

- `ObjectSculptSpec.json` — 完整组件树/材质/重复系统/socket/评审历史
- `createObjectNameModel(spec, options)` TS factory，`root.userData.sculptRuntime` 暴露 nodes/sockets/colliders/destruction groups
- 渲染图 + 各 pass 对照单

## 注意

- 跟项目 [[glass-console-system]] 无关，是独立 3D 重建工具，别和前端视觉系统混
- 单图无法揭示背面/精确几何，skill 会明确说哪些是推断/近似，别要求它伪造置信度
- grimoire/ 下是各 gate 的详细评分细则
