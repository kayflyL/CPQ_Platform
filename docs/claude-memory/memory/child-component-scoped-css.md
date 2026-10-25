---
name: child-component-scoped-css
description: "父组件 scoped 类透不进子组件内部(popover 触发器重灾),新控件样式必须自带完整定义;OnlinePill 白块案例"
metadata:
  node_type: memory
  type: project
  originSessionId: c59955d9-24d4-4a7f-90d5-8943adb3ca0a
  modified: 2026-09-30T06:28:18.041Z
---

09-30 在线胶囊(OnlinePill)首版渲染成白块:模板写了 `class="action-pill online-pill"` 想继承 DefaultLayout scoped 的 `.action-pill`,但按钮在 `<a-popover>` 触发器里,父组件的 scope 属性(data-v-*)透传不进 popover 的 DOM,`.action-pill[data-v-x]` 永远匹配不上 → 按钮裸奔成浏览器默认白底。夜间模式 token 全换对了用户仍说"不适配"——根因根本不是颜色,是整层样式没挂上。

**Why:** Vue scoped 属性只落在「本组件模板元素 + 子组件根节点」;a-popover/drawer/modal 这类Teleport+触发器结构没有可落的根,和 [[excel-parse-rules-header-anchor]] 里"网格着色类 scoped 缺失"同根。**Why2: 用户报"样式不对"先查样式有没有挂上(computed style),别急着想 token/颜色值。**

**How to apply:** 新控件(尤其带 popover/tooltip 触发器的)样式一律在自身 scoped 块里完整定义,别依赖父级 scoped 类继承;无效类名删掉。验证套路:preview_inspect 查 computed background/color 是否等于预期 token 值,一眼分层"没挂上"vs"挂错值"。
