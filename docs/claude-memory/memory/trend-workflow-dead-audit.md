---
name: trend-workflow-dead-audit
description: 09-15专家审计定论：趋势分析workflow四层断裂完全不可用——skill_manifest断线(实际跑的是需求分析流)+引擎零大脑步+final_gate硬编码+done收尾硬编码；修复前别信任何「趋势分析可用」的表象
metadata: 
  node_type: memory
  type: project
  originSessionId: d9980c57-58ad-4257-bac2-907fd9408192
  modified: 2026-09-15T12:29:23.474Z
---

2026-09-15 专家审计结论：AI办公室「趋势分析」workflow（trend_analysis）**端到端不可用**，四层独立断裂，任一层都足以致死。

**Why:** 入口门面齐全（skill_catalog行/data_analyst绑定/前端"+"菜单/workflow_launcher分发都正常），但执行链从未打通：
1. `handle_skill_chat_turn` 不收 skill_key；`skill_chat.py:150` 硬编码 `ensure_skill_flow("requirement_analysis")` → 发起趋势分析实际跑需求分析六步流水线
2. DB flow 126（trend）agent 节点无配置行（有孤儿 agent_fill 行），capability_spec.SPECS 无 "agent" 条目无机制保底 → `steps_payload` 返回 []，零大脑步零 query_data
3. `final_gate`（skill_plan_runtime.py:433）硬编码要求机型已锁 → 用真实 DB 流实测：引擎立即 gaps「机型未锁定，不能交付」，会话 ACTIVE 死循环
4. `agent_result` 全库无写入点 → payload_map `ctx.agent_result.answer` 永远为空；`_run_skill_chat` done 分支硬编码「需求分析完成/BOM方案草稿/record_mission(requirement_analysis)」
   （migrate_left_panel_single_home_20260912.py:10 注释明说 trend flow 126 是「遗留 agent 运行时不属本次范围」）
测试只覆盖绑定解析（test_colleague_skill_binding.py），执行链零测试。

**How to apply:** 用户要求修趋势分析/新增 workflow 型 skill 时，先过这四层：①skill_key 穿透 handle_skill_chat_turn→_prepare ②DB 节点配置+SPECS 保底 ③final_gate/收尾按 output_kind 分派（data_answer≠机型锁）④agent_result 写入点。别只补一层就宣布修好。相关：[[skill-tree-trunk-architecture]] [[skill-current-state-2026-09-12]]
