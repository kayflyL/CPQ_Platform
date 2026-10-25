---
name: echarts-use-array-not-spread
description: "本仓库 echarts 注册必须用数组形式 use([...])，散参形式 use(A,B,C) 会让 renderer 静默不注册、图表不渲染报 Renderer 'undefined'"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: ad92d97b-7a9e-4f75-be15-da15b638c76a
---

在本仓库（echarts + vue-echarts）里，`echarts/core` 的 `use()` **必须用数组形式**：`use([GridComponent, LineChart, CanvasRenderer, ...])`。

**Why:** 散参形式 `use(GridComponent, LineChart, CanvasRenderer)`（多参数）在本构建里**不会**把 CanvasRenderer 的 painter 注册进 zrender 的 `painterCtors`，导致 `painterCtors` 全空 → echarts 初始化时 `keys(painterCtors)[0]` 取到 undefined → 抛 `Renderer 'undefined' is not imported. Please import it first.`，图表 canvas 根本不渲染。报错堆栈在 `new ZRender`，极易误判为 renderer 没导入。改用数组形式即修复。参考 `frontend/src/views/opportunity/OpportunityList.vue:210`（一直用数组形式，正常工作）。

**How to apply:** 新增任何 echarts 图（vue-echarts `<VChart>`）时，`use()` 一律数组形式；并给 `<VChart>` 传 `:init-options="{ renderer: 'canvas' }"`（即使 renderer 已注册，传上更稳，与现有价格历史图一致）。排查「图表不渲染 / canvas 0 个」时，先看 `use()` 是不是散参形式。另见 [[charts-canvas-no-css-var]]（图表色用真实值，非 CSS 变量）。
