---
name: config-qty-capability-clamp
description: 配置数量上限双通道定调：控件夹紧(A)+规则告警(C)；warning不阻断是手改优先延续；碰配置页数量/能力约束/选型规则先看
metadata:
  node_type: memory
  type: project
  originSessionId: d1fd530b-9af4-4fe7-8611-f371e678339d
  modified: 2026-10-02T08:05:03.136Z
---

2026-10-02 用户发现配置页 CPU 数量不受基准配置 max_cpu 约束，审计后定调并实施 A+C 双通道：

- **A 控件夹紧**：KpCategoryCard 加 `maxQty` prop（CPU→max_cpu / Memory→max_dimm / GPU→gpu_slots / HDD/SSD→bays；未配置→不限；上限按类别总数算多行分摊），ConfigWizard 与报价 Workspace 都接；机箱弹窗电源步进器夹 `psu_bays`。后面板 riser 本来就按槽位 cap 夹（useRearState），是全站唯一的"守规矩样板"。
- **C 规则告警**：规则库(rules.compatibility_rules, category=机箱能力校验) 五条上限规则全 active——CPU id25 / 内存 id26 / GPU id35 / 盘位 id36 / 电源 id37，均 recommend/warning。**warning 不阻断是刻意设计**（[[derive-must-have-manual-fallback]] 手改优先；生成规格书确认弹窗只认 conflict/require），别再提"把上限改成硬拦截"除非用户拍板。
- **上下文注入是坑源**：Workspace.buildRuleContext 此前只注 series/盘类，连 CPU/内存上限规则都从不触发；后端 plan_builder 传候选层 baseline 也会缺 gpu_slots/bays——已改为 DB 基准配置行权威补齐。新增能力字段必须同时接三处：ConfigWizard / Workspace 的 buildRuleContext + plan_rule_context，否则规则静默不命中。
- 规则字段路径按 `.` 切，`kp.HDD/SSD.qty` 合法（类别名不含点）；无规则代码种子，DB 是唯一来源（repo 注释明示）。
