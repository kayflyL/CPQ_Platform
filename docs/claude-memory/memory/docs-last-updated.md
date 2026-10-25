---
name: docs-last-updated
description: "每次更新 docs 文档必须加/刷新\"最后更新：YYYY-MM-DD\"时间戳（H1 标题下 blockquote）"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 3045d5d6-c948-44e1-bc00-564c2a6f2ede
  modified: 2026-07-25T13:11:38.403Z
---

每次更新 `docs/` 下任何文档（含 `docs/frontend-pages/**/*.md`、README 总纲、`docs/CHANGELOG.md` 等）时，在文件 H1 标题正下方加或刷新一行 `> 最后更新：YYYY-MM-DD`（取当天日期）。

**Why:** 用户 2026-07-25 明确要求，便于追踪文档新鲜度、判断是否落后于代码。

**How to apply:**
- 任何 docs 文件被 Edit/Write 改动的那次，顺带更新该文件的"最后更新"行——哪怕只改一个字。
- 日期取当天（见系统 `currentDate`），格式 `YYYY-MM-DD`。
- 位置：H1 标题正下方，独立一行 blockquote（`> 最后更新：…`）。
- 新建文档时一并加上。
- 关联 [[frontend-pages-doc-sync]]（改前端页面同步文档的总体规范）。
