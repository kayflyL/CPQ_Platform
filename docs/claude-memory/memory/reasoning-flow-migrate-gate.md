---
name: reasoning-flow-migrate-gate
description: 推理流 startup migrate 被 active_is_current() 单点 gate；别加无 guard 的建流 migrate（114 条膨胀教训）
metadata: 
  node_type: memory
  type: project
  originSessionId: 351c2cea-bcbd-4c60-b025-08db1d053dab
  modified: 2026-08-07T01:48:22.270Z
---

推理流版本迁移（reasoning_flow_repo.migrate_v1~v8_*_if_needed）在 startup.py 被 **active_is_current() 单点 gate** 兜底：
active 流节点集 ⊇ DEFAULT_GRAPH 全部节点 → 跳过所有「建流 migrate」，只跑「不建流的配置自愈」（fix_cond_clarity_threshold / migrate_extract_model_token_regex / migrate_ask_user_to_catalog）。

**为什么**：历史上 rules.reasoning_flow 积了 114 条 created_by=migrate 的垃圾流（每次启动建一条）。根因：active 被 persistGraph 污染 / 旧 migrate 漏 guard → 判成缺节点 → 反复建+激活。2026-08-07 已清（116→2 流，active #106 完好）+ 加 gate + persistGraph 端的 GET-compare 防覆盖。

**How to apply**：以后加新 migrate（v9+）——(1) 函数内部先查「目标节点已存在 → return None」；(2) startup 顶层 active_is_current() gate 会兜底（active 已最新就全跳）。建流 migrate 只在 active 真缺新节点时跑一次（跑完 active 即最新，下次启动 gate 跳过）。**绝不写无脑建流的 migrate**。

关联 [[reasoning-flow-viz]] [[agent-architecture-decision]]。
