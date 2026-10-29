---
name: scoped-global-pitfall
description: "Vue scoped CSS 里 :global() 不能和后代选择器混用，会抽出裸 [data-theme] 规则贴到 html 上把整页隐藏"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 95a658bf-38d4-4794-92cc-55312dce6dc1
---

Vue scoped CSS 里 `:global([data-theme='light']) .main-scroll` 这种写法**是错的**——`:global()` 包裹的选择器会被单独抽成全局规则、丢掉后面的 `.main-scroll` 后代，编译结果变成 `[data-theme="light"] { ... }` 直接命中 `<html data-theme>`。

**Why:** 2026-07 主题改造时踩过：DefaultLayout 浅色覆盖块写了 `:global([data-theme='light']) .main-scroll::after { display: none }`，Vue 编译出 `[data-theme="light"] { display: none }` 贴到 html 上，整个 light 主题页面空白。DOM innerHTML 有内容、computed color 正常，但 `getBoundingClientRect()` 全是 0×0——dark 主题正常（不匹配该规则），只有 light 空白，排查极困难，用户截图才暴露。

**How to apply:**
1. scoped CSS 里写"祖先在组件外（html 上的 data-theme）+ 后代在组件内"的组合，**直接写 `[data-theme='light'] .main-scroll`**，不要包 `:global()`——Vue scoped 只给组件内后代加 `[data-v-xxx]`，祖先选择器原样保留，正好是想要的效果。`:global()` 只用于整段选择器都要全局的场景。
2. **本环境 screenshot 工具会返回 [Unsupported Image]，验证视觉不能只靠 `innerHTML`/`computed color`**——必须查 `getBoundingClientRect()` 确认尺寸非 0，否则会漏掉 `display:none`/`visibility:hidden`/`transform:scale(0)` 类视觉 bug（DOM 有内容但视觉空白）。
