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
