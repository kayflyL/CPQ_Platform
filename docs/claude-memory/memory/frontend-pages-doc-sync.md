---
name: frontend-pages-doc-sync
description: "改前端页面要同步更新 docs/frontend-pages/ 对应文档(每页一个 md,按功能域分目录)"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 927971b0-cbc3-4271-8b28-71e4f06f095a
  modified: 2026-07-24T04:08:14.352Z
---

改任何前端页面(新增页面 / 改路由 / 改功能 / 改 API 调用)后,必须同步更新 `docs/frontend-pages/` 下对应文档。

**Why:** 用户 2026-07-24 明确要求。`docs/frontend-pages/` 是"方案编写参考 + 新会话快速上下文加载"的前端权威索引(见其 README)。文档与代码漂移会误导后续会话(参见 [[docs-code-drift]])。

**How to apply:**
- 路径约定:`docs/frontend-pages/{功能域}/{页面名}.md`(现有域:servers / opportunities / parts / settings)
- 格式参照 `servers/base-config-editor.md`:功能概述 → 前端路由表 → API 端点表 → 数据库表 → 关键组件
- **新页面**:新建 md + 在 `README.md` 的目录树和路由总览里登记
- **改现有页面**:更新对应 md(功能 / 路由 / API 任一变更都要落)
- `README.md` 总纲里的目录树、路由总览、API 前缀总览也要同步
- 收尾前 grep 自己改过的 .vue 文件,逐个核对有无对应 md 需更新;别只改代码漏文档
