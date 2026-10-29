---
name: docs-sync-rules
description: 文档同步三规则合一——改docs刷最后更新日期/改前端页同步docs+README/先查frontend-pages再查代码
metadata:
  node_type: memory
  type: feedback
  originSessionId: 1b626d52-5a43-436d-bdb8-cf89b7bb25e4
  modified: 2026-10-15T08:57:06.946Z
---

文档同步三规则合一（原独立条目：docs-last-updated / frontend-pages-doc-sync / consult-frontend-pages-first，原文件仍在磁盘可深查）：

1. **改 docs 必刷** H1 下 `> 最后更新：YYYY-MM-DD`。
2. **改前端页面必须同步** docs/frontend-pages 对应页 + README 总纲。
3. **先查文档**：碰前端页面先读 docs/frontend-pages 对应页，没覆盖再查代码。

关联 [[frontend-typecheck-env]]。
