---
name: repro-writes-hit-real-db
description: 复现写接口的请求会直接写生产库——先备份目标行再复现，或一律走 fake-repo 单测
metadata: 
  node_type: memory
  type: feedback
  originSessionId: d9980c57-58ad-4257-bac2-907fd9408192
  modified: 2026-09-16T10:39:31.994Z
---

用 TestClient/requests 复现写端点（PUT/POST）时，请求会真实落到生产数据库，不是沙箱。

**Why:** 2026-09-16 连续两次自伤：复现角色保存 422 时把 business 角色权限覆盖成单 key；给回归测试忘挂 monkeypatch 又把 te 角色写坏。两次都靠 `_DEFAULT_ROLES` 种子值手动恢复。

**How to apply:** 复现写接口前先 SELECT 备份目标行（打印/存变量）；能写 fake-repo 单测就不打真实端点；跑完测试若怀疑写了库，立刻 `role_repo.list_all()` 核对全部角色。**e2e 脚本造的测试数据同样共库**：perm_matrix_e2e 曾只软删（status=deleted），43 个 `[权限测试*]` 假商机残留生产库，用户点进其中一个踩出「方案配置尚未提交」409（2026-09-16 已 536 行硬删清光，脚本 cleanup 已改子表→父表硬删）。e2e 收尾必须物理清数据，软删≠清理。关联 [[auth-rbac-system]]。
