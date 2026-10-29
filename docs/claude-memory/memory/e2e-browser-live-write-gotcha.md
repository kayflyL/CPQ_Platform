---
name: e2e-browser-live-write-gotcha
description: "浏览器E2E合成键盘事件会真实走通交互链(keyCode=13→antd pressEnter),直调setupState handler同样触发真实写库/企微;测评论类功能前先断企微"
metadata:
  node_type: memory
  type: feedback
  originSessionId: bd032897-de27-4e43-95a6-c6341c37ec0d
  modified: 2026-10-15T14:59:11.055Z
---

浏览器 preview_eval 做 UI 测试时，合成键盘事件（注入 `keyCode:13`）会**真实走通** antd `pressEnter` → 提交链路；直接调用 Vue `setupState` 里的 handler（如 `onDraftEnter`）同样会执行真实分支。本次实测中一次探针回车真实发送了带 @ 的评论 → 建了真通知 + 企微群 webhook 广播出局。

**Why**: 本地 `notify.wecom.webhook_url` 是配置且启用的（见 [[wecom-notify-channel]]），任何走真实后端的 @评论都会广播到团队真群；合成事件不可信 ≠ 无副作用。

**How to apply**: ① 测交互逻辑优先 pytest+TestClient+stub 外推（[[comment-mention-notify]] 的测试范式）；② 浏览器里只测浮层/插入/渲染，绝不真实提交带 @ 的内容；③ 需要测发送时先用假名册 monkeypatch 或临时确认知 webhook 指向测试地址；④ 直调 setupState handler 前先想清楚它会走哪个分支。
