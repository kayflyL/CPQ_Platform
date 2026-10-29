---
name: avoid-batch-file-ops
description: 长任务分步小批量工具调用，单轮读写文件控制在个位数；批量读写曾触发错误
metadata: 
  node_type: memory
  type: feedback
  originSessionId: cb122e70-9a97-4594-84d6-87adf2303c17
  modified: 2026-07-25T16:52:19.698Z
---

不要在单轮里突然大批量读写文件（一批 Read / Write / Edit 并行，或一次读十几个文件），会触发错误。

**Why:** 用户明确「切记不要突然大规模读写文件，会触发错误，我记得之前遇到过」——真实踩坑。

**How to apply:**
- 长任务拆成小步，每轮工具调用控制在个位数，尤其读写文件；宁可多轮串行也别一次并行一堆 Read/Write
- codegraph_explore 摸底也分批（别一次 4-6 个并行查询）
- Bash 间 cwd 可能漂移（如 `cd backend` 后下条又 `cd backend` 找不到），读写/执行文件尽量用绝对路径 `cd /d/CPQ_Platform_V1/... && ...`
