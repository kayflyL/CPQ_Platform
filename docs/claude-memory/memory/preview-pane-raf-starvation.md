---
name: preview-pane-raf-starvation
description: "Browser 预览窗格被遮挡时 rAF 停发，Vue 过渡卡死像\"关闭失效\"假 bug；截图可强制出帧；__vueParentComponent 可驱动 3D 验证"
metadata: 
  node_type: memory
  type: project
  originSessionId: baa9695c-e3a8-4370-a1c0-d0e1c044ede8
  modified: 2026-09-27T10:08:18.042Z
---

用 preview_* 工具在 AI 办公室页做浏览器验证时（2026-09-27 点显示器看任务一役实测）：

1. **rAF 饿死假象**：预览窗格被遮挡/不出帧时 `requestAnimationFrame` 完全不触发（`document.visibilityState` 仍报 "visible"！）。后果：Vue `<Transition>` 的 leave 卡在 `leave-from/leave-active`，元素永不消失——看起来像「关闭按钮失效」的产品 bug，其实状态早已变 false。判定法：eval 里 `let f=false; requestAnimationFrame(()=>f=true); setTimeout(()=>res(f),700)` 得 `rafFired:false` 即饿死。**解法：调一次 preview_screenshot（CDP 截图强制 BeginFrame），挂起的 rAF/过渡立刻走完。**

2. **合成事件噪音**：向 three.js 画布派发合成 `PointerEvent` 会让 OrbitControls 的 `setPointerCapture` 抛 NotFoundError（console 一堆 Uncaught）——无害，别当产品问题。

3. **驱动 3D 场景的捷径**：vite dev 模式下 DOM 元素带 `__vueParentComponent`，`setupState` **自动解包 refs**（直接 `s.missionPanelOpen`，别再 `.value`）；可拿到 scene/camera/actorMap 等闭包变量。算某个 mesh 的屏幕像素：`mesh.getWorldPosition(v.clone()).project(camera)` → NDC → 乘 rect，然后对准派发事件，比像素网格盲扫快得多。沿 parent 链走 `__vueParentComponent.parent` 可到宿主组件实例。

相关：[[mobile-adaptation-pattern]]（切视口必 reload 同源——预览环境响应式状态不自动重算）
