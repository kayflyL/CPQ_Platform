---
name: small-batch-reads-avoid-stream-drop
description: 长会话里工具调用要分小批、避免大批量读写——用户明确要求写进记忆，防止触发第三方代理断流
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a9bb336a-7755-4380-973e-36884d9505dd
  modified: 2026-08-18T02:28:59.138Z
---

工具调用分小批执行：单轮少并行、每次读写控制在个位数文件/几百行级别，读完一批再发下一批。

**Why:** 本项目环境走第三方 LLM 代理（见 [[cc-switch-502-root-causes]]，cloudprime 限流 429 + 高压掐连接），单轮塞太多并行大结果容易把连接打爆触发断流错误。用户 2026-08-18 看商机详情页时当面叮嘱"分小批读（避免大批量读写触发断流）这个要写在记忆里"。另见 [[avoid-batch-file-ops]]（曾因批量读写触发错误 + Bash cwd 漂移）。

**How to apply:** 探索大文件/多文件时用多次小 Read（每次 ≤400 行左右）顺序读，别一次并行七八个大文件；优先用 codegraph_explore 一次拿结构化源码代替 grep+read 循环；Grep 用 -A/-B/head_limit 收窄输出。新会话默认按此节奏，不等用户提醒。
