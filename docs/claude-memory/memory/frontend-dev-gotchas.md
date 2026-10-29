---
name: frontend-dev-gotchas
description: 前端开发微坑合集——scoped透传/:global/v-show多根/auto-complete/图表色/rAF饿死/信息栏输入框;写前端样式与交互前扫一眼
metadata:
  node_type: memory
  type: feedback
  originSessionId: 1b626d52-5a43-436d-bdb8-cf89b7bb25e4
  modified: 2026-10-15T08:56:53.154Z
---

前端微坑七合一（原独立条目：child-component-scoped-css / scoped-global-pitfall / vue-vshow-multi-root / antd-autocomplete-use-vmodel / charts-canvas-no-css-var / preview-pane-raf-starvation / infobar-editable-input-style，原文件仍在磁盘可深查）：

1. **子组件 scoped 样式透传**：父的 scoped 类透不进子组件 popover 触发器；先查 computed 再动样式。
2. **scoped :global 陷阱**：`:global()` 别和后代选择器混用；视觉验证必查 getBoundingClientRect，别信截图。
3. **v-show 挂多根组件静默失效**：fragment 根不继承 v-show（仅 dev warning）；面板泄漏到兄弟 tab 先查多根。
4. **a-auto-complete 两坑**：必须 `v-model:value`；options 只吃 `{value,label}[]`。
5. **图表色不能用 CSS 变量**：canvas 读不到 var()；走 useChartTheme；echarts use() 必须传数组。
6. **预览窗格 rAF 饿死假象**：窗格被遮挡时 rAF 停发，过渡卡住像失效假 bug；preview_screenshot 强制出帧即解。
7. **信息栏可编辑输入框样式**：常驻可编辑字段带边框+width:220px，别用隐框。

关联 [[design-spec-tokens]] [[no-card-color-strips]]。
