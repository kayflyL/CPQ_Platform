---
name: requirement-gap-match-grading
description: 需求单与配件库的 gap 怎么处理——库外项不拦截、匹配度三态分级标注
metadata: 
  node_type: memory
  type: project
  originSessionId: 63c2b4c8-8f11-4344-a520-5e0ea41a5453
  modified: 2026-08-13T15:36:55.687Z
---

需求单（业务填）是"客户想要什么"，配件库（parts_master/kp_parts）是"我们有什么"，两者天然有 gap。例：库里只有 Orion(AMD)/兆芯(Polaris)，业务填 Intel。**2026-08-13 定调处理方式**（协作流程方案业务商机详情页）：

**Why:** 业务填的是客户意图，不是我们能卖的。用配件库主数据校验拦截业务，会逼他瞎选近似项污染数据、或退回自由文本放弃结构化——都比"存一个库外值"更糟。库外≠错误，可能是真要走特殊代理通道的真实业务。

**How to apply:**
1. **需求单存储绝不拦截**：业务填什么存什么。平台系列用下拉（system_config.server_series SSOT）+ 允许手输自由值（a-select 自定义输入口）。需求单是独立宽松的意图记录，不靠配件库校验。
2. **匹配度三态**（提交时后端判定，复用现有 `_filter_cpu_parts_for_platform` 返回 None + series 白名单 `validate_pipeline_slots` 逻辑）：✅已匹配（库里有对应件）/ ⚠️部分匹配（有同类缺规格）/ ❌未匹配（库里完全没有）。
3. **流程不阻塞**：库外项只标注不拦截。技术员在执行工作台看到醒目"库外"标注，BOM 区是空的（不硬塞 Orion 等近似平台件），技术员手动配/发起采购/退回业务改 Orion。
4. 整单匹配度标签（全匹配/部分外采/含库外项）挂在门户卡片+详情页头，管理员一眼看到哪些单要特殊处理。
5. 这和 [[derive-must-have-manual-fallback]] 一脉相承：推导/匹配只作参考，人始终能兜底。需求单结构化录入对齐 [[agent-understand-pure-llm]] 的 RequirementSlots 契约（series/form/cpu/memory/storage[]/gpu[]/nic[]），后端选型/推理能直接消费。

碰需求单录入/选型匹配/库外件处理前先看。
