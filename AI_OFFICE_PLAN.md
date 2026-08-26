# AI Office 需求分析 Skill 改革执行状态

> 用途：本会话上下文固化。新会话/后续执行先读本文件，再读 AGENTS.md。
> 当前分支：main。最近 checkpoint：`6f178b3`（移除节点级自然语气 LLM 调用）。

## 已拍板目标

- AI 角色是唯一会话大脑：负责意图、引导、措辞、卡片生成。
- Skill 节点是确定性任务 + 工具 + 契约 + 校验，不背话术、不自己起 LLM 决策。
- 只推服务器卡片 = 角色层能力，不进需求分析 Skill。
- 进入需求分析 Skill = 必然产出 BOM；Skill 主链无“自己配/智能配”分叉。
- 配件/BOM 阶段确定性优先；发现明显不合理才由 AI 审核修正，不打断正常推进。
- 进 Skill 加边界：普通聊天/调工具不进；检测到配置需求后确认再进。

## 分层

交互层 → Agent 编排中枢（唯一决策源）→ 工具层 → 数据/规则层 → 契约/安全层。

## Skill 主链

`input → agent_fill → model_reason → kp_reason → compose → output`

- `input`：只接收 `skill_context`（对话摘要 + 最近消息 + 商机上下文）。
- `agent_fill`：AI 角色结构化填线索登记表 + 契约校验，只问缺失必填字段。
- `model_reason`：确定性 `select_models` 出候选；用户确认后锁定并继续，不再出现自配分叉。
- `kp_reason`：确定性 `pick_kp_parts` 选配件；无未匹配项时直接继续 compose，不再停下确认。
- `compose/output`：确定性组装 BOM，输出可配置数量的方案。

## 本轮已改

- `backend/app/services/reasoning_executor.py`：删除 `_ask_model_intro`/`await_mode` 分叉；机型确认后直接继续；配件匹配完整时自动继续。
- `backend/app/services/colleague_turn_service.py`：进入 `requirement_analysis` 时优先用会话上下文预填线索登记表；self_config 退出改推目录候选卡；退出文案改为 `reasoning_prompt_defaults.json` 可配置。
- `backend/app/services/skill_router.py`：路由提示词改为仅在明确要求配置并产出 BOM 时触发需求分析。
- `backend/app/services/reasoning_prompt_defaults.json`：新增 model_reason/kp_reason 的可配置话术键。

## 本轮整改（已批准并落地）

- `agent_fill` System Prompt 重写：只描述本节点职责，不再复制下游目标层；context 删除平铺目录文本，改为调用目录工具查询。
- 字段配置收拢为「层级」单一开关：移除 `required / ask / default_ok` 三列及相关运行时逻辑；`L0` 必问、`L1` 提示可补、`L2` 系统推导。
- 资源与权限层补回真实工具/数据源：`agent_fill` 默认 `list_server_types/list_server_models/get_server_model`；运行时传入 `enabled_tools`、角色 `allowed_tool_ids/allowed_data_sources`；`support_engineer` 增加 `server_catalog/server_product_content` 及三个目录工具。
- 校验闸门改为目录事实 + 层级判定：AI 服务器目录只有 4U，不再出现 2U；仅未填 `L0` 才反问，`L1/L2` 不卡流程。
- 修复节点 trace 重开时清空已完成节点输出的问题；修复 BOM 后仍推「自己配置」卡片（仅 `target === 'server_config'` 显示）。

## 本轮验证

- `pytest backend/tests/test_requirement_intel.py backend/tests/test_requirement_slots.py backend/tests/test_agent_tools.py backend/tests/test_agent_fill_smoke.py -q` → 36 passed。
- 真实抽取「我需要AI服务器，预算10万」：`server_type_name=AI / 加速计算服务器`、`purchase_qty=1`、`missing_critical=["platform_type","chassis_form"]`，无伪造 2U。
- 后端需重启进程加载新代码；当前 8000 端口可能仍是旧进程。

## 交互层刚落地（未提交）

- 后端 `_handle_agent_fill` 反问改为生成真实目录选项：`server_type/platform_type/chassis_form/server_model` 取 `_catalog_whitelist()`，`purchase_qty` 给常用档位；`need_input` 事件携带 `options + slot_options`。
- `colleague_turn_service` 把 `need_input` 持久化为 `kind=input_options` 消息（含结构化选项），重放历史也能渲染。
- 前端 `AssistantMessageItem` 渲染可点击选项条，点选项回填发送，仍允许自由输入。
- 计划条改为由 `pipeline_start.steps` 预置整条链路（pending→running→done），`useAssistant.postSend` / `AssistantPanel.sendText` 不再清空，只有取消/自配退出才清。
- 验证：backend 相关单测 35 passed；`vue-tsc -b` 通过；`_agent_fill_options` 冒烟输出正确目录值。

## 待办（后续）

- 清理 `colleague_turn_service.py` / `reasoning_executor.py` 中仍残留的非配置话术与退出固定句。
- 节点级 per-node `duration_ms` 可观测性（当前 pipeline 事件没有耗时字段）。
- 真实 LLM 低频 E2E：清晰/模糊/闲聊/委托/点名/自配/取消各一轮，对照 SPEC_ASSISTANT 基线。
- `bom_compare.py` 等非需求分析域未经批准不动。

## 环境/红线

- Python：`D:\CPQ_Platform_V1\backend\.venv\Scripts\python.exe`；设置 `PYTHONUTF8=1`、`PYTHONPATH=D:\CPQ_Platform_V1\backend`。
- 登录：admin / fA5zXkyWv_RyrAqe（不得删除/重置）。
- CC Switch 上限约 30-40 req/min；禁止并行大扇出。
- 动手改代码前先说明原因+方案并等批准；用户手改文件（dashboard.py、opportunities.py、portal.py、flow_repo.py、opportunity_repo.py、role_repo.py、portal.ts、OpportunityProcessBoard.vue、OpportunityList.vue、PortalWorkstationView.vue、CreateOpportunityModal.vue、test_agent_fill_smoke.py、components.d.ts）不要动。
