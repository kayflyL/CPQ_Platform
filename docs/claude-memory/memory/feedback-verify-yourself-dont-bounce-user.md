---
name: feedback-verify-yourself-dont-bounce-user
description: 用户报的 bug 反复修不好时，别再让用户刷新/重启/手测——自己起 dev server 复现并给证据
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 898afee2-2d52-43a6-8b15-e2d859df99b2
---

报错反复出现时，**自己起 dev server 复现、抓网络/控制台证据给用户看**，不要把"硬刷新 / 重启 dev server / 看 Network 面板"这类手动步骤丢回给用户让他们做。

**Why:** CPQ 项目修"新建报价变新商机"这个 bug 时，我连续几轮让用户 `Ctrl+Shift+R`、重启 5173、看 Network 截图发我。用户明确说"你不要再折腾我了"。反复让用户做手动验证会消磨信任，尤其是前端 HMR/Pinia store 缓存这类问题,用户那边刷新未必见效,而我手里有 preview_start 可以起自己的前后端完整复现。

**How to apply:** 如果我已经让用户刷新/重启过一次、用户反馈"还是不行",立即切换到自验证模式:用 preview_start 起自己的 frontend(必要时连共享后端 8000),走完整 UI 流程,抓 XHR 请求体/响应/DB 状态作为证据。不要第二次让用户做手动步骤。抓 XHR 的办法:在 preview_eval 里临时覆盖 `XMLHttpRequest.prototype.open/send` 记录 url+body+responseText。相关:[[systematic-cleanup-not-whackamole]]
