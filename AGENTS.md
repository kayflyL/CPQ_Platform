# AGENTS.md

## CodeGraph

This repository is indexed by CodeGraph — `.codegraph/` exists at the repo root (DB: `.codegraph/codegraph.db`, CLI v1.5.0 on PATH).

- For any task that requires understanding or locating code (symbols, call paths, dynamic dispatch such as FastAPI routers / Vue components / React hooks), run `codegraph explore "<symbol or question>"` FIRST — before grep/find or reading files. It returns verbatim, line-numbered current source plus call paths.
- If the index looks stale relative to on-disk code, rebuild it from the repo root with `codegraph index`, then re-query.
- Fallbacks: `codegraph query <search>` for symbol search; `codegraph node <name>` for a single symbol's source + caller/callee trail.
- If `.codegraph/` is ever removed from the repo, skip CodeGraph entirely.


## 协作规则（用户明确要求 · 必须遵守）

- **动手改代码前，先说明「原因 + 改动方案」，等用户明确批准后再改。** 不要默认执行、不要边解释边动手。
- 调查类请求（"先调查下原因"）只输出调查结论与修复方案，**等批准**才改文件。
- 用户对"不断加代码/打补丁/堆功能"高度敏感：默认**不加**，只加明确要求的；删减类改动同样先列清单等批准。
- 执行后如实汇报：改了什么文件、验证结果；如用户不满意可回退。
