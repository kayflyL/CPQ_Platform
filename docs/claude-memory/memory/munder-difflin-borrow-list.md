---
name: munder-difflin-borrow-list
description: 2026-09-13 调研 GitHub munder-difflin 多智能体框架后的借鉴清单（P0记忆成本/断路器/可见化，P1 turn持久化/同事消息协议），含明确不抄项
metadata: 
  node_type: memory
  type: project
  originSessionId: eba9e191-91a0-40d3-99bc-5b91569c0fd6
  modified: 2026-10-22T02:37:28.116Z
---

2026-09-13 应用户要求深调 [chaitanyagiri/munder-difflin](https://github.com/chaitanyagiri/munder-difflin)（7k星，Electron 多智能体 harness，包装 Claude Code 等 12 个 CLI 跑"办公室"），与 AI办公室子系统对照，产出借鉴清单。

**Why:** AI办公室当时三大短板——无同事间协作通道、turn 无持久化(进程内asyncio)、记忆注入=最近N条+抽取每轮全读200条成本线性涨。munder 的解法全部命中。

**How to apply:** 碰 AI办公室/消息管道/记忆/断路器相关改动时先对照此清单：

- **P0 已全部落地（2026-09-13，用户只批 P0）**：
  - ①记忆：durable 集（pinned∪manual 恒注入恒可见）+ 抽取可见窗= durable+最近40条自动（`EXTRACT_RECENT_WINDOW`）+ 注入按 user_text 走 fastembed 相关性召回（`colleague_memory_search.rank_by_relevance`，失败降级最近N）——见 [[colleague-structured-memory]]
  - ②断路器：`turn_breaker.py`（healthy→steering 180s→constrained 360s，900s 硬上限不动；信号=墙钟/无进展150s/同节点重入≥3；**armed=False observe-only**，线上验证误报率后武装）挂 `skill_chat._run_task` 的 supervise；agent_react 两循环加 `ToolRepeatGuard` 同参连续≥6 次即止损（此项直接生效）
  - ③排队可见化：后端入队/drain/stop 广播 `queue_state{depth}` → 前端 queuedCount → AssistantComposer `queued` prop 蓝点徽标「已排队 ×N」；60s 计时提示与重连 toast 评估后砍掉（statusText 已流式可见+看门狗静默自愈，再加是噪音）
- ~~**P1** ④turn/run 持久化=append-only 事件流+cursor 幂等（参考其 log.jsonl+tasks.json schema）；⑤同事间消息协议 FIPA-lite 子集（act/hops/requires_reply 反活锁三字段）+确定性 router，**不是自治god**（守 [[agent-architecture-decision]] B2 定调）；⑥升级策略从代码进提示词配置~~（⚠️2026-10-22 用户定调放弃，P1 不再计划做）
- **明确不抄**：文件/git 协调层（DB 是我们权威源，守 [[skill-tree-trunk-architecture]]）、全自治 god agent、PTY/Pixi 楼层（动画必须传达信息否则是玩具——office_brain 拟真同判）
- 其工程习惯可学：policy-only 无副作用模块、detect-and-degrade 降级、提示词前缀字节恒定吃 prompt cache、单门消息仲裁（自动消息永不删用户草稿，推断式标志必须带过期）

相关：[[dispatch-llm-judge]] [[skill-latency-program]] [[colleague-structured-memory]]
