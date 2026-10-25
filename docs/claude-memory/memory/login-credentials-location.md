---
name: login-credentials-location
description: 本地登录凭据：AGENTS.md 已删（09-13 核实），admin 密码是用户自设（引导只在首次打印），别猜也别重置
metadata:
  node_type: memory
  type: reference
  originSessionId: 44b878c3-d0dc-4c31-ad38-9029c6d784b1
  modified: 2026-09-13T06:49:18.088Z
---

仓库根 `AGENTS.md` 已不存在（2026-09-13 核实，根目录只剩 guide/handbook/ratel.md）。admin 密码机制（startup.py `ensure_bootstrap_admin`）：首次启动创建并打印一次随机密码，之后**绝不重置**——密码是用户自己在「用户与权限」页改的，我无从得知。

**How to apply:** 需要登录验证前端时：①确认登录页能渲染、后端 401/200 应答即可证明链路通，不必真登录；②绝不重置 admin 密码或建后门账号；③如确需登录态，问用户要密码。后端 http://localhost:8000、前端 http://localhost:5173。关联 [[auth-rbac-system]]。
