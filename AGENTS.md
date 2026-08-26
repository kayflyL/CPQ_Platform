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
- **修复类改动禁止最小修复或只打局部补丁**：先看清系统边界、数据流和长期演进，给出更稳的根因方案与取舍，再等用户批准执行；宁可在方案里多说明，也不要只改眼前报错点。
- 执行后如实汇报：改了什么文件、验证结果；如用户不满意可回退。

## 本地开发环境登录凭据（用户提供、永久保留）
- 账号：admin／密码：fA5zXkyWv_RyrAqe（后端 http://localhost:8000 、前端 http://localhost:5173）
- 不得删除该 admin 账号或重置其密码；弃用时需用户明确同意。


## CC Switch 防断连规则（每次会话必须遵守）

本地代理链路：客户端 → CC Switch（127.0.0.1:15721）→ cloudprime 上游（api.cloudprime.com.cn:5567）。已知两类断连根因，都会表现为 502。

### 根因一：命令/参数超长截断

超过约 7359 字符的命令参数或较大输出会导致 502/`EOF while parsing a string`。

- `shell_command` 保持简短；长脚本先通过 `apply_patch` 写成 `.py`/`.ps1` 文件，再执行该文件。
- 若报错含 `Invalid function_call arguments for 'shell_command' ... EOF while parsing a string at line 1 column N`，就是同一条 `shell_command` 参数超长被截断；`N` 可能从约 7000 到 18000+ 不等，必须拆成更小的命令或改用脚本文件。
- 搜索代码优先用 CodeGraph；必须用 `rg` 时先 `rg -l` 只列文件名，再针对具体文件 `rg -n`。
- 不要直接全量 `rg -n` 大目录；如确需全量搜索，先重定向到文件，再分段读取：`rg -n "..." ... > matches.txt`，然后 `Get-Content matches.txt -TotalCount 200`。
- 大文件读取用 `Get-Content <file> | Select-Object -First N` / `-Skip N` 分段读取，避免一次性输出整个文件。
- 代码改动按文件拆成小 `apply_patch`，不要一次性提交整段大补丁或长任务内容。
- 遇到 502 或解析截断时，立即缩小本次命令长度/输出量，分多次执行。

### 根因二：上游 cloudprime 限流（2026-08-16 日志实测）

- 额度线约 **30-40 请求/分钟**：基线 8-13/分安全，冲到 38-45/分即连环 `429 [1302] Rate limit reached`；限流压力大时上游直接掐连接，CC Switch 报 `502 上游请求失败: client error (SendRequest)`，重试全挂会话即断。失败瞬间客户端还会 1 秒内齐射约 25 个重试请求，加剧雪崩。
- 诊断日志在 `~/.cc-switch/logs/cc-switch.log`（找 `[FWD-003]` / `HTTP 429` / `SendRequest` 行）。
- **禁止并行大扇出**：subagent / 并行工具调用一次最多 1-2 个、顺序执行——所有会话与客户端（Claude Code / Codex / claude-desktop）共享同一 RPM 池。
- **重任务一次只开一个会话**，多会话并跑会叠加请求速率。
- 会话断了不丢上下文：重开发「继续」接上即可，勿重建会话。
- 已在 `~/.claude/settings.json` 落地：`CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`（砍后台非必要调用）、`API_TIMEOUT_MS=600000`（防长思考被客户端误杀）。
- failover 尚无备胎：claude / claude-desktop 应用仅有 cloudprime 一家（codex 已配「公司→公司 copy」自动切换可参照）；完整根因调研存于 Claude 记忆 `cc-switch-502-root-causes`。


## 当前执行计划（每次会话先读）

AI Office 整改方案与执行清单已写入 `AI_OFFICE_PLAN.md`。开工前先读取该文件，按其中步骤执行；用户已要求“先记录再执行”，但具体代码改动仍按本文件协作规则逐项确认后推进。
