---
name: charts-canvas-no-css-var
description: chart.js/echarts 用 canvas 渲染读不到 CSS 变量，图表色必须真实色值（走 useChartTheme composable）
metadata: 
  node_type: memory
  type: project
  originSessionId: 95a658bf-38d4-4794-92cc-55312dce6dc1
---

chart.js 和 echarts 都用 canvas 渲染，**传 CSS 变量（`var(--cpq-*)`）作颜色无效**——canvas 不解析，图表会用默认色或渲染异常。

**Why:** 2026-07 主题改造时踩过：脚本把图表里的 `rgba()` 批量换成 `var(--cpq-overlay-*)` 后，OpportunityList 的 echarts 和 BasePricing 的 chart.js 的 grid/accent/tooltip 色全部失效。

**How to apply:** 图表色必须给真实 hex/rgba。已抽 `frontend/src/composables/useChartTheme.ts`，按当前主题（[[store/theme.ts]] 的 isDark）返回对应真实色板（accent/grid/splitLine/tick/axisLabel/tooltipBg/tooltipText/barStart/barEnd 等），computed 驱动主题切换时重算。未来加新图表，颜色一律从 `useChartTheme().chartColors.value` 取，别直接 `var()` 或硬编码。
