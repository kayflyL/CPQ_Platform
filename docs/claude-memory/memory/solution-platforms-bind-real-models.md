---
name: solution-platforms-bind-real-models
description: 解决方案适配平台必须绑机型目录真实机型(model_id)，禁虚构型号，点卡片跳机型详情页
metadata: 
  node_type: memory
  type: feedback
  originSessionId: b3bbd3fa-5940-4296-8850-f894ccbc2694
  modified: 2026-09-27T09:07:58.723Z
---

2026-09-27 用户发现解决方案库的适配平台全是虚构型号（Orion ES22V3/Titan TS33V2/Vault VS24V1 等），且点击跳 `/strategies/selection`（选型配置）而不是服务器介绍页——用户定调这是错的。

**Why:** 解决方案的「适配平台」是对外叙事，引用不存在的机型=假数据；跳转落点应该是机型自己的详情页（介绍），不是工作台。

**How to apply:**
- platforms 形状 `{name, spec, model_id?, link?}`；model_id → `l6.server_models`。详情页 `platformLink()` 优先 model_id 生成 `/servers/models/:id`，link 仅兜底。
- 编辑器第 1 列是机型下拉（`catalogApi.listModels(publishedOnly)`，选中自动带出 name+link），不要恢复成自由文本链接输入。
- 种子 `solution_seed._SEED` 只写真实型号；改种子不会影响存量行（ensure_solutions_seeded 按 key 幂等不覆盖），存量修复走 `backend/scripts/fix_solution_platforms.py`（幂等护栏：行内已有 model_id 视为人工整理过、整行跳过；运行前自动备份 platforms 到 scripts/_backup_*.json）。
- 新增 baseline 方案或新增机型后要重新核对种子绑定；碰解决方案模块先看 [[strategy-center]] 与 docs/frontend-pages/strategies/strategies.md。
