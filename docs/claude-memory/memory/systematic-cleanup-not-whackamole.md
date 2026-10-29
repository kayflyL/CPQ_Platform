---
name: systematic-cleanup-not-whackamole
description: 修单点问题时要主动扫同类/相邻问题一并梳理，用户偏好系统性根治而非打地鼠
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 795572e9-9a71-413e-9774-64b0fe4ae9f5
---

遇到用户报告的单个 bug 或改进点，主动审视同模式的其他字段/组件/页面，把同类问题一并纳入范围，而不是只修报告的那一个。

**Why:** 用户在 CPQ 项目里多次遇到「同一类系统性问题」——典型是料号库 `specs` 与顶层列的多处冗余（`specs.kind`≡`sub_type`、`specs.description`≡顶层 `description`、`specs.note` 无对应列、前端 `supplier` 死字段等），根因都是早期迁移脚本把旧表字段同时塞两处。用户原话「要学会举一反三，看看其他的有没有这种问题」。期望一次性根治，而不是反复来回打地鼠。

**How to apply:**
- 修单个字段/属性问题时，扫一遍同一表/组件的其他字段是否有类似冗余或语义不清
- 用户报告问题时若主动提到「还有 XX 也类似/重复」，必须把那些纳入同一轮范围
- 改造深度先问清楚（轻量清数据 vs 中量按类别重构 vs 重量+修隐藏 bug），不要默认最轻
- 用真实数据分布（查库 / 拉 API 统计）驱动字段设计，而非凭空猜类别有哪些
- 相关：[[admin-card-pattern]]、[[derive-must-have-manual-fallback]]
