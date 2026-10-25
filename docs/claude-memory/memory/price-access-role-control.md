---
name: price-access-role-control
description: "价格机密,AI角色price_access布尔默认关(白名单assistant/cost_analyst);09-13起唯一事实源直存,不再由data_boundary派生"
metadata: 
  node_type: memory
  type: project
  originSessionId: 103415a3-4b46-42b1-a04c-db5d6194e356
  modified: 2026-09-26T17:25:51.183Z
---

用户定调（2026-08-29）：**价格很机密**。AI 角色价格可见性 = colleague 的 `price_access` 布尔（**默认关**），白名单只有方案助手（assistant）+ 成本核算（cost_analyst）。关闭的角色全链路无价格：catalog_search 工具剥 price 字段（模型物理拿不到）、query_data 边界脱敏价格列（tool_boundary→execute_read）、引擎 model_options/选型候选剥价。

2026-09-13 工具即权限重构：price_access 升格为**唯一事实源**（直存布尔，不再由 data_boundary masked_fields 派生；判定函数 `colleague_price_ok(colleague)` 在 data_boundary.py）。按同事的 data_boundary/data_sources 配置已退役，读侧 normalize_colleague 剥离存量键。

**2026-09-27 修通 DM 工具轮强制（此前 price_access 管不住这条路）**：handler 层读 `TOOL_CTX.price_ok`（skill_tool_context.py），但全项目只有技能会话（skill_chat.py:286）和引擎（skill_turn_engine.py:271）两处 set——`_run_tool_turn` 没设，落到 handler 各自缺省：query_data 用 `bool(ctx.get("price_ok"))`=bool(None)=False 过严（价开角色也被脱敏）、catalog_search 用 `ctx.get("price_ok", True)` 漏价（价关角色拿裸价，实测坐实）。修法：`_run_tool_turn` 里 run_stream_chat_loop 外包 `TOOL_CTX.set({role_key, price_ok: colleague_price_ok(colleague), …})` + token/finally 复位。**catalog_search 的缺省 True 是刻意行为别翻**（test_price_ok_default_in_tool_ctx 锚定「与引擎默认一致」，推理流引擎路依赖价可见；翻了会静默剥掉方案推理价格）。验证走 `build_tool_registry({"enabled_tools":[…]}, …)` 显式集——`{}` 会落 default_enabled 全集而 query_data 是 default_enabled=False，探针会全假阴性。

「AI 角色访问权限」面板在员工页签（ColleagueAccessPanel.vue，自包含+独立保存）；团队页签「智能转接规则」collapse 复用 `tm-access-collapse` 类名，别误认成访问面板。

**Why:** 用户发现技术支持工程师聊天直接报出「参考价 11,536.83 元」；价格管控按角色而非按用户；09-13 再定调「靠工具调数据，单独的数据权限不要了」——能力面收敛为 tool_ids。

**How to apply:** 新增会输出价格的 AI 角色时必须在员工页显式开 price_access；给任何对话工具/引擎产物加新价格字段时，接 `_TOOL_CTX.price_ok` / `engine_ctx.price_access` 门控。方案/成本核算页面价格展示仍走既有 RBAC price_mask（按用户），与角色门控并行。文档见 docs/frontend-pages/settings/ai-office-team.md。关联 [[auth-rbac-system]] [[query-data-primitive]]。
