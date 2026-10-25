---
name: frontend-typecheck-env
description: 本工作区 frontend/ 现已有 node_modules，可直接 `npm run build` 自验（vue-tsc+bundle 全跑）；npx vue-tsc 单跑仍撞 TS6 exports，统一用 npm run build
metadata: 
  node_type: memory
  type: project
  originSessionId: 5330d479-181e-4510-8800-cc3647a2a9af
  modified: 2026-07-29T07:58:57.523Z
---

**更新（2026-07-29 实测）：** 本工作区 `frontend/` 现在**有 `node_modules`**，`npm run build`（= `vue-tsc -b && vite build`）可直接跑通用于自验（含类型检查 + 打包，约 3s）。改完前端后**自己跑 `npm run build` 验证**，别再让用户兜底（[[feedback-verify-yourself-dont-bounce-user]]）。

`npx vue-tsc` 单独跑仍会抛 `ERR_PACKAGE_PATH_NOT_EXPORTED: './lib/tsc'`（vue-tsc 内部 `require('typescript/lib/tsc')`，项目 `typescript ~6.0.2` 的 `exports` 不暴露该子路径）——所以**别用 `npx vue-tsc`，统一 `npm run build`**。

**Why:** 早先（07-25）此工作区无 node_modules；现已安装可自验。`npx vue-tsc` 与 TS6 的冲突是工具链问题，绕开它用 `npm run build` 即可。
**How to apply:** 改完前端 TS → 自己 `cd frontend && npm run build`；有类型/编译错就地修，循环到绿再交付。前端启动方式见 [[app-startup]]。
