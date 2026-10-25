---
name: ops-workflow-gotchas
description: 本项目操作微坑合集——Edit长载荷掺杂质/小批量读防断流/避免批量读写/curl TLS/命令带目录;执行长任务前扫一眼
metadata:
  node_type: memory
  type: feedback
  originSessionId: 1b626d52-5a43-436d-bdb8-cf89b7bb25e4
  modified: 2026-10-15T08:56:57.056Z
---

操作微坑五合一（原独立条目：edit-long-payload-corruption / small-batch-reads-avoid-stream-drop / avoid-batch-file-ops / windows-curl-ssl-no-revoke / commands-need-directory，原文件仍在磁盘可深查）：

1. **Edit/Write 长载荷掺杂质**：掺假 token 静默落盘；逐字拷贝+读回核对+通读+构建验证（本次会话实测两次中招）。
2. **小批量读防断流**：单轮少并行，读 ≤400 行，优先 codegraph_explore。
3. **避免批量读写文件**：分步小批量；Bash 间 cwd 漂移用绝对路径。
4. **Windows curl TLS 坑**：加 `--ssl-no-revoke`；Python requests 不受影响。
5. **命令须指明目录**：让用户跑命令必须带目录。

关联 [[app-startup]] [[frontend-typecheck-env]]。
