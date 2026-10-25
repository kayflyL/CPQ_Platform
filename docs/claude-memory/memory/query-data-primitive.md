---
name: query-data-primitive
description: query_data 只读原语（物理强制层保留）；09-13工具即权限；10-11 opportunities域一律改道ai_read视图(AI线索隔离)+query_parts双模式(流程锁换权限锁)；端到端已通
metadata: 
  node_type: memory
  type: project
  originSessionId: 103415a3-4b46-42b1-a04c-db5d6194e356
  modified: 2026-10-12T03:05:30.529Z
---

# query_data 原语（步骤2，2026-08-29；09-13 工具即权限重构）

**架构**：query_data = SELECT-only 读原语，物理强制层在 `data_boundary.execute_read`（白名单表/敏感列脱敏/只读事务/行数上限/超时），工具层只接线。宪法写在工具 description 里：先查 information_schema 自查地图、SQL 报错原样回传自纠、白名单外报错。

**2026-09-13 工具即权限（用户定调「靠工具调数据，单独的数据权限不要了」）**：
- 可读表白名单改为**工具自有**配置 `system_config.query_data_tables_allow`（默认 8 张业务表：opportunities 5 + l6 3…实际 l6 4 减 server 系列为 server_types/server_models/base_configs），与同事无关，`tool_boundary(price_ok)` 执行期构造
- 价格脱敏 = 同事级 `price_access` 布尔（[[price-access-role-control]]，colleague_price_ok）
- 按同事的 data_boundary/data_sources 全删（含 DATA_SOURCE_CATALOG/scope-options 端点/员工页数据来源选择器/节点抽屉派生展示）；存量迁移 `scripts/retire_colleague_data_permissions.py`
- 白名单不能废的原因：DB 有 feed_users.password_hash、llm_config API key——工具开关只说"能跑SQL"，白名单说"能读哪些表"（实测 feed_users 拒、opportunities 通、价格列脱敏）

**试点状态**：只开方案助手（assistant）——tool_ids=["query_data"]。migration 中 query_cpq_data→query_data 映射**仅限 assistant**，其余角色直接剔除。

**2026-10-11 AI 线索隔离（用户定调「AI生成的线索不进统计口径，也不能骗 AI」）**：opportunities 域 5 表对 query_data **一律改道 `ai_read.*` 视图**（行级排除 status IN ('ai_office','deleted')，与 opp_stats/商机线索页口径物理对齐）——`data_boundary._AI_VIEW_MAP` 在 query_tables_allow 出口统一改道，手配白名单写基础表也打不穿；视图由 `startup.ensure_ai_read_views()` 每次 boot CREATE OR REPLACE 自愈（基表加列跟随），SQL 存档 migrations/create_ai_read_views.sql。实测：库内 326 条 ai_office 线索，裸 SQL `FROM opportunities` 自动落视图只回 active 188。**同日 query_parts 双模式（流程锁换权限锁）**：流程外开放日常浏览（只读检索、series 置空、limit≤10、rows 拒绝、返回 mode=browse），价格列仍 price_access×用户 RBAC；挂载仍看同事 tool_ids。测试 test_data_boundary 新 3 例 + test_query_parts_browse 5 例。

**Why**: 旧 query_cpq_data 是硬编码查询集（写死表+字段），3 个 server browse 工具是冗余只读通道；全部退役换成通用原语，模型用 information_schema 自发现。09-13 再收敛：data_sources 唯一消费点是 ToolRegistry 里恒真的重言校验（allowed=同事∪工具必需），纯死配置。

**How to apply**:
- 验证（2026-09-13 复测）：664 backend tests + 真库探针三连（feed_users 拒/opportunities 461 行/价格列脱敏）全过。
- ✅ **2026-09-26 端到端打通**（方案助手 DM 直查真数 502）：根因三层已全修——
  1. **编排重构丢路由**：run_colleague_turn 的 else 分支只剩 _run_plain_turn，_run_tool_turn 成孤儿（实现/导入/模块文档全在但零调用方），提示词承诺 query_data 而运行时没挂工具 → 模型把查询演出来并编造整张表（华信/蓝海假商机 vs 真实 502）。修法：else 里按 allowed_tool_ids 分流接回（工作流会话/launcher 分支在前不受影响）。
  2. **裸表名坑**：白名单唯一后缀匹配放行裸名，但 PG search_path 解析落 public → UndefinedTable → 模型探索死胡同。修法：execute_read 前确定性补全 `_qualify_bare_tables`。
  3. **契约盲区**：ToolRegistry.schemas() 只暴露 summary——白名单清单必须挂进 brief（brief=model_brief 覆盖或 spec summary），挂 description 模型看不见。
  - 配套：降级纯文本轮注入「[系统事实：本轮工具查询未收敛，未获得任何数据]」防演戏；_run_native_tool_loop 补 agent_round 逐轮 trace（原零可观测）。
  - **09-27 工具轮流式化**：_run_tool_turn 弃 run_react_loop 换 run_stream_chat_loop（技能流同一台机器），正文 chunk 直推+工具活动 chat_status+办公事件收窄到工具粒度（publish 落库，chunk 粒度会每 token 一条 DB 写）。新增 chunk_reset 协议位（第2+次流式尝试正文首字前发，前端清 streamingText）解旁白连拼——emit_chunk_reset 参数默认 False（引擎 brain 回合旁白累积语义不能重置），仅同事聊天轮开。
  - ⚠️ uvicorn --reload 有时不跟盘：改完代码线上行为没变先 touch app/main.py 触发重载再复测。
- ⚠️ 被转角色的幻觉风险：无读工具的角色会编造查询结果；无工具角色的诚实拒绝话术需加强。
- **09-27 六角色冲突审计收口**：data_analyst 补 opportunity_stats+query_data、quote_specialist 补 query_data（原都是零工具+提示词承诺系统数据=必编造）；全角色提示词补「私聊口头引荐不声称已转接」条款；_handoff_hint 头部「【同事转接】」退役改中性「在册同事（职责与技能参考）」（语义归提示词层=禁令不进黑盒代码）。名册 digest「职责」=system_prompt 前 120 字自动跟随，skills 裸 key 是判官路由数据勿删。**待拍板**：data_analyst/quote_specialist 的 price_access（利润率/价格构成分析当前被脱敏挡住，白名单现仅 assistant/cost_analyst）。回滚点 backend/_ai_colleagues_backup_0927.json。
- 相关：[[price-access-role-control]]、[[agent-architecture-decision]]、[[skill-takeover-diagnosis]]

# 评测瘦版（步骤3，2026-08-29）

**契约测试**：已随步骤0/1/2 落地（test_stream_chat_loop / test_data_boundary / test_query_data_tool / test_price_access / test_dispatch_llm / test_skill_contracts，09-13 起 664 条），不另造重复测试文件。

**黄金对话冒烟**：`backend/scripts/golden_smoke.py` + `backend/tests/golden_conversations.json`（20条：六角色×反问/登记/转接/价格泄漏/鲁棒性）。直调 run_colleague_turn 产品路径，宽松断言（error_free/asks_question/handoff_any/no_handoff/artifact/mentions_any/no_price_digits/any_of），报告含人工复核区。样例 g01（模糊需求反问✓）g13（闲聊不转接✓）已验证 harness 可用；**全量未跑**（60-100次LLM调用+cloudprime限流风险），命令：`cd backend && python -X utf8 scripts/golden_smoke.py --all`，跑前用户过目对话集。
