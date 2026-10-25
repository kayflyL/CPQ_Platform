---
name: consult-frontend-pages-first
description: 答前端「规则/流程/分类怎么定」类问题先查 docs/frontend-pages 对应页，缺口就补，别每次重新 grep 代码
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 550ba548-9e3b-4307-b0fd-be85d007f608
  modified: 2026-07-30T17:09:52.551Z
---

回答「X 怎么定的 / 什么规则 / 什么流程 / 分类怎么走」类前端问题（尤其按钮行为、判定逻辑、分类归属、API 归属），**第一步先 Read `docs/frontend-pages/{域}/{页}.md`**；文档没覆盖再查代码；查完若发现文档缺这块，顺手补回去。

**Why:** 用户维护 frontend-pages 文档体系（每页含功能概述/路由/API/表/注意事项）就是为了沉淀这些规则、避免每次重查。每次上来就 codegraph/grep 既浪费又无视已有沉淀，用户已就此当面批评（「你为什么每次都需要新去查」）。

**How to apply:** 先文档后代码。例：问「报价工作台入库新配件的分类怎么定」→ 先读 `opportunities/workspace.md`；本次实测该页没收录 KP 同步/入库接口（`/api/quote/kp/sync-price`、`/kp/history`）、没列 `kp.kp_parts/kp_categories/kp_price_history` 表、没写 db_price/isNewPart 判定——属文档缺口，查代码后应补进文档。与 [[frontend-pages-doc-sync]]（改页面必同步文档·产出侧）互补，这条是消费侧。
