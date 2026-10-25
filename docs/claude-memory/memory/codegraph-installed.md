---
name: codegraph-installed
description: "codegraph v1.5.0 已装(npm 全局 + 顶层 MCP 注册),替代 graphify;用法见全局 CLAUDE.md 的 CODEGRAPH 块"
metadata: 
  node_type: memory
  type: reference
  originSessionId: 9ba53ac3-1081-44b9-a289-17b7f7436540
  modified: 2026-07-25T05:20:07.254Z
---

2026-07-25 装 **codegraph** v1.5.0,替代刚删的 graphify(见 [[claude-3p-environment]])。用法/触发规则已写在全局 `~/.claude/CLAUDE.md` 的 `CODEGRAPH_START/END` 块里(每会话自动加载,codegraph 安装时自动写入),**不在此重复**——核心就一句:代码理解/定位/影响面优先 `mcp__codegraph__codegraph_explore`,别自己拼 grep+read 循环。

## 安装位置(排查时用)

- **CLI**: `codegraph`(npm 全局,`AppData/Roaming/npm/codegraph`),兜底命令 `codegraph explore "<问题>"`
- **MCP**: 注册在 `~/.claude.json` **顶层** `mcpServers.codegraph`(`codegraph serve --mcp`)——注意是顶层不是项目级,排查时别只看 project 段
- **索引 db**: 项目内 `.codegraph/codegraph.db`(~9.6MB),`.codegraph/.gitignore` 已自动排除(db/日志/socket 都不进 git)

## 坑

- **MCP 工具是会话启动时加载的**:若某会话里 `mcp__codegraph__*` 缺失,是中途装的没挂载 → **重启 Claude Code** 即可,不用重装。(2026-07-25 装完当会话就没工具,重启后才出现。)
- **首次索引 `errors.log` 报 5 个 ENOENT**(`opportunity_file.py` / `opportunity_file_repo.py` / `fix_encoding.py` / `generate_import_sql.py` / `import_opportunities.py`)= git 里已删、codegraph 还想读的文件,无害,不用修。
