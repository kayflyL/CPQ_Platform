---
name: commands-need-directory
description: 给用户 shell 命令必须指明 frontend/backend 目录，别只说命令名
metadata: 
  node_type: memory
  type: feedback
  originSessionId: f12c5f67-9984-4a53-92ec-e99f71691235
  modified: 2026-07-29T14:21:33.989Z
---

让用户执行命令（`npm run build`、`pytest` 等）时，必须带目录或明确说"在 frontend/backend 目录"，不要只丢一个命令名。

**Why:** 用户多次遇到我只说"跑 npm run build"而不指前端还是后端，明确表达过不满（"你老是这样，是在前端还是后端运行，你要说一下"）。本项目后端是 Python（无 npm），凡是 `npm` / `npm run` 一律是 `frontend` 目录；后端命令（pytest 等）在 `backend` 目录。

**How to apply:** 让用户跑命令时一律写成形如 `cd D:\CPQ_Platform_V1\frontend && npm run build` 的带目录形式，或文字明确"在 frontend 目录跑"。关联 [[feedback-verify-yourself-dont-bounce-user]]（那条讲"能自己验证就自己验证"，这条讲"让用户跑时要说清目录"）。
