# AGENTS.md

## CodeGraph

This repository is indexed by CodeGraph — `.codegraph/` exists at the repo root (DB: `.codegraph/codegraph.db`, CLI v1.5.0 on PATH).

- For any task that requires understanding or locating code (symbols, call paths, dynamic dispatch such as FastAPI routers / Vue components / React hooks), run `codegraph explore "<symbol or question>"` FIRST — before grep/find or reading files. It returns verbatim, line-numbered current source plus call paths.
- If the index looks stale relative to on-disk code, rebuild it from the repo root with `codegraph index`, then re-query.
- Fallbacks: `codegraph query <search>` for symbol search; `codegraph node <name>` for a single symbol's source + caller/callee trail.
- If `.codegraph/` is ever removed from the repo, skip CodeGraph entirely.
