# AI Office 需求分析 Skill 改革执行状态

> 用途：本会话上下文固化。新会话/后续执行先读本文件，再读 AGENTS.md。
> 当前分支：main。最近状态：AI 角色计划执行器主链、选件规则化、model_reason/kp_reason 工具通道均已真实落地并跑通 N1/N2/C1；提示词已单源化到 reasoning_node_defaults.json（prompt_store/reasoning_prompt_defaults.json 已退役）；剩余为 LLM 延迟调优（用户暂缓批准）与 agent_fill 抽取波动兜底。

## 已拍板目标

- AI 角色是唯一会话大脑：负责意图、引导、措辞、卡片生成。
- Skill 节点只做进度广播、产物保存、契约校验，不自己起 LLM 决策。
- 进入需求分析 Skill = 必然产出 BOM；Skill 主链无“自己配/智能配”分叉。
- 料号/价格/兼容性全部来自工具返回；LLM 只决定“选哪个/怎么配”。

## Skill 主链

`input → agent_fill → model_reason → kp_reason → compose → output`

- `input`：只接收并保存 `skill_context`。
- `agent_fill`：AI 结构化填线索登记表 + 契约校验，只问缺失必填字段。
- `model_reason`：AI 调 `select_models/get_server_model`，只从工具返回候选中选机型。
- `kp_reason`：AI 调 `list_kp_categories/select_parts`，料号从工具返回回收，禁止编造。
- `compose/output`：不调 LLM，用已锁定机型+配件调 `build_plan`，落 BOM 草稿并交接。

## 当前状态（未提交，主链与工具通道已真实落地）

- 新建唯一执行器 `backend/app/services/ai_plan_executor.py`：`run_ai_skill_plan` 按图声明步骤执行。
- 删除旧固定图执行器 `capability_executor.run_fixed_workflow` 及其意图/节点决策逻辑；该模块仅保留 `_graph_maps/_trace_preview/停止信号`。
- 删除旧配件规则选料 `candidate_search.pick_kp_parts` 及 33 个配套辅助函数；新选料工具为 `part_selector.select_parts`。
- 删除 `reasoning_executor` 中旧 `_handle_model_reason/_handle_kp_reason/run_graph_executor` 等节点级 LLM 流程，`_dispatch` 只作为单节点动作分发。
- `colleague_turn_service` / `reasoning_flow` 试运行统一走 `run_ai_skill_plan`，不再引用 `run_fixed_workflow`。
- 更新 `reasoning_node_defaults.json`：`kp_reason.enabled_tools` 改为 `list_kp_categories/select_parts`。
- `part_selector` 增加型号归一化（空格/连字符），保证 LLM 输出“9560 16i”能命中真实料号。
- 2026-08-27 选件规则化 + 工具分层（已批准并落地）：
  - `requirement_rule_catalog` 增加 `part_selection_policy`；`rules.requirement_rules` 新增 `part_selection` 规则类型，`part_selector` 读取策略目录而非内联 `A100→A800` 兜底。
  - `part_selector._ground_gpu` 改为：型号 token 命中失败时白盒 `unmatched`，禁止按显存容量静默替换；容量只作为无型号信号时的合法匹配和型号命中后的二次校验。
  - `agent_tools.py` 拆薄为 `agent_tool_registry.py`（注册/执行门面）、`agent_tool_handlers.py`（参数适配+digest）、`agent_tool_specs.py`（schema+registry 构建），旧模块保留兼容门面。
- 2026-08-27 架构修正（已批准）：
  - 机型字段锁定：`model_reason` 锁定候选后，把 `server_type_name/series/form` 回写到 `ext/requirement`，下游不再读 LLM 抽槽自由值；`model_reason` 增加 `list_server_types` 工具并要求先查目录类型。
  - 抽取契约收紧：`AGENT_FILL_FINAL_CONTRACT`/`agent_fill` prompt 要求结构化 `memory.speed_mt / drives.interface+qty / raid_levels`；`slot_extractor` 解析字符串形式的 `DDR5-4800×16` 与 `RAID 0,1,10`。
  - `select_parts`：内存速度默认精确匹配（`comparison=gte/lte` 才放宽），不静默 4800→6400；RAID 级别不再任取代表件；GPU/RAID 型号匹配改为双向 token；所有落地件回传 `request_spec/grounded_spec/spec_mismatch`。
  - `agent_tools._tool_select_parts` / `_kp_reason_step` 透传并统计 `spec_mismatch`。
- 2026-08-27 本轮真实落地（校对后，均已运行验证）：
  - 根因一（旧配置误导）：`reasoning_node_contract._defaults_for_node` 曾把旧 `model_reason`/`kp_reason` 节点提示词注入生效配置，导致 `model_reason` 用「只做确认与引导，不决定」话术在推理阶段无限绕圈、`kp_reason.enabled_tools` 仍指向已删除的 `pick_kp_parts`。已改为只注入 `model_reason_ai`/`kp_reason_ai`，并在 `reasoning_flow_repo.self_heal_agent_node_configs` 清除 DB 遗留 `system_prompt/selection_mode/grounding_tool/…/proposal_*/pick_kp_parts` 等旧字段。
  - 根因二（执行器读旧配置）：`ai_plan_executor` 的 `model_reason`/`kp_reason` 强制使用 `*_ai` 提示词与固定工具集，不再 `config.get("system_prompt")`/`config.get("enabled_tools")`。
  - 根因三（AI 少传字段丢配件）：`kp_reason` 改为「完整结构化 slots 打底 + AI select_parts 参数只补缺」深合并，避免 AI 漏传整类配件；`part_selector.select_parts` 改为按在场信号字段补齐类目（不再仅依赖 categories）；`_ground_drives` 兼容 `capacity`/`interface` 别名。
  - `capability_spec` 的 `model_reason`/`kp_reason` 提示词源改为 `*_ai`；前端 `ReasoningNodeDrawer` 的 kp_reason 默认工具由 `pick_kp_parts` 改为 `list_kp_categories/select_parts`。

- 2026-08-27 提示词单源化（已批准并落地，替代此前 reasoning_prompt_defaults.json + prompt_store 平行库）：
  - 删除 `backend/app/services/prompt_store.py` 与 `backend/app/services/reasoning_prompt_defaults.json`；DB `system_config.reasoning_prompts` 行在 `init_defaults` 中幂等退役删除。
  - 提示词并入 `reasoning_node_defaults.json`：`agent_fill.prompt.system_prompt`、`model_reason.system_prompt`、`kp_reason.system_prompt`（内容即原 `*_ai`）。
  - `reasoning_node_contract._defaults_for_node` 改为「种子 JSON 为底 + DB 覆盖」，`effective_config` 直接给抽屉回显提示词。
  - `ai_plan_executor._model_reason_step/_kp_reason_step` 改为读 `config["system_prompt"]`，抽屉改的提示词现在真正生效。
  - `capability_spec` 移除 `prompt_node`；`self_heal` 不再删节点 `system_prompt`，改为缺失时补默认，并继续清理 `selection_mode/grounding_tool/proposal_*` 等旧字段。
  - 验证：`pytest -q backend/tests` → 265 passed；拦截验证 `effective_config` 默认/覆盖生效，且 `model_reason`/`kp_reason` 的 LLM 调用实参 `system_prompt` 等于抽屉传入值。
## 验证

- 全量后端测试：`pytest -q backend/tests` → `260 passed`（含新增 `test_part_selector` 型号/速度/RAID 用例）。
- mock 垂直切片 `backend/scripts/_verify_ai_plan2.py`：6 个真实料号、`unmatched_count=0`、机型 `ESA24V3-P`、总价 `516813.63`。
- 全量测试收集无旧符号残留：`pick_kp_parts/run_match_kp_rule/run_fixed_workflow` 等 rg 为空。
- 真实 LLM 5 案例 E2E（2026-08-27，低频串行，未通过）：
  - case1 机型漂移：抽成 `ES22V3-P`，预期 `ESA24V3-P`；`server_type_name=GPU计算服务器`（应为 AI/加速计算服务器）、`form=机架式`（应为 4U）。CPU/内存/盘/GPU/NIC 命中真实料号；`LSI 9560 16i 8G缓存` 因归一化方向未命中，1 个空 RAID 料号。
  - case2 CPU 错选 `AMD EPYC 9124`；GPU `RTX PRO 4500 Server 32G` 冗余词未命中。
  - case3 CPU 错选 `AMD EPYC 9334`；`raid_groups=[{"model":"RAID 0,1,10"}]` 未映射兼容卡，RAID 未命中。
  - case4 `480G SATA×4` 被抽成 `960G×2`；内存 64G 5600 落成 64G 6400；HDD 错成 960G NVMe。
  - case5 内存 32G 4800 丢 `speed` 后落成 32G 6400；`7680G U.2 NVME` 库无未命中。
- 2026-08-27 本次落地回归：`pytest -q backend/tests` → `265 passed`。
- 真实 `select_parts` 快速验证：`gpu_groups=[{"tokens":["A100"],"qty":8,"cap":"80G"}]` 返回 `unmatched=True`，不再静默落 A800。
- 2026-08-27 进程内真实 LLM 三案例（`scripts/run_one_trace.py`，非打地鼠对照）：
  - `N1-A100x8`：机型 `ESA24V3-P / AI·加速计算服务器 / 4U / Orion`；CPU/1.92T SATA/7.68T NVMe/25G 网卡/9560-16i 全部命中；128G 单条内存与 A100 白盒 `UNMATCH`（不落 A800），共 7 件，总耗时 42.8s。
  - `N2-9334`：机型 `ES22V3-P / 通用计算服务器 / 2U / Orion`；CPU/32G 4800 内存/480G SATA/25G 网卡/9540-8i 全部命中，总耗时 121.7s（kp_reason 108s，属延迟问题）。
  - `C1-A800x2`：机型 `ESA24V3-P / AI·加速计算服务器 / 4U / Orion`（不再漂移 ES22V3-P）；CPU/64G 4800/1.92T SATA/3.84T NVMe/A800/10G 网卡/9560-16i/9364-8i 双 RAID 全部命中，0 未命中，总耗时 49.9s。

## 2026-08-27 本轮（阶段2/3）真实落地（已回看核对）

- 阶段 2 验证：`resolve_part_alias`/`compose_memory` 已注册并可用；全量测试通过。`兆芯` 初始为空（规则未入库），已补种子规则并 `seed_missing_defaults` 入真实库。
- 阶段 3 删静默兜底（白盒化，不回退严格 1:1）：
  - `candidate_search.py` 删除「去掉 type 再试」旧兜底：某类型 0 机型返空，不再混入其他类型；`_fallback_note` 不再把放宽谎报为精确匹配。
  - `part_selector._ground_cpu` 删除 `fallback_all` 静默代表件分支：型号给到但库无命中 → `unmatched` 白盒；未给型号才允许代表件。
  - `requirement_rule_catalog.py` / `requirement_rule_repo.py` 移除 `cpu.fallback_all`。
  - 新增回归：`test_select_models_fallback.test_type_mismatch_returns_empty_not_other_type`。
- 语义归一下沉到落地层（不依赖 AI 工具参数回填）：
  - `part_selector._alias_rows`：part_alias 规则 → 名称检索 → 型号 token 归一；`resolve_part_alias` 与 `_ground_cpu` 共用。
  - 真实库验证：`Intel Xeon 6430` → `Intel 6430`（白盒 reason）；`兆芯` → `KH50000 48C`（别名规则）。
  - 新增回归：`test_part_selector.test_cpu_token_normalization_matches_short_model`、`test_cpu_alias_rule_resolves_semantic_term`。
- 数据修正（阶段 4 部分）：存储机型 `ZS25V2-P` 原 `is_published=False` 被 `select_models(published_only=True)` 过滤；已置为 `True`。`select_models(存储服务器, series=Intel, form=4U)` 现正确返回 `ZS25V2-P` 并白盒标注「放宽平台系列、机箱形态」。
- 全量测试：`pytest -q backend/tests` → `271 passed`。

## 本轮待完成（真实剩余项）

- LLM 延迟调优：`kp_reason` 单节点 27–108s、整案 42–122s，主因 deepseek-v4-flash 推理模型在工具循环里产生大量 reasoning token 才收敛；用户已明确暂缓，待架构稳定后再决定调优方案。
- agent_fill 抽取波动已按「原文为真相源、登记表仅作缓存」处理（2026-08-27）：`kp_reason` 现在注入需求原文，AI 对照原文补全缺失/冲突信号，`select_parts` 参数改为 AI 补全优先、登记表缺省兜底，落地后回写 `ctx.ext/ctx.requirement`。旧“登记表唯一事实源/冻结快照”文案已退役；仍禁止离线正则兜底（正则覆盖不了 `NMVE` 等任意拼写变体）。
- 前端抽屉 `ReasoningNodeDrawer.vue` 仍保留旧文案（“优先走 pick_kp_parts/JSON 黑盒”等）与旧字段表单，需后续对齐，避免再次把旧配置写回。
- 数据完整性：AI 类型还有一台 `ESA25V3-P` 未发布；CPU 目录仍为 `Intel 6430`（缺 `Xeon`，现由 token 归一兜底，但目录名仍建议修正）；`兆芯/开胜/海光` 别名建议补全进策略中心。

## 待办（后续）

- 真实 LLM 低频复验：先跑 case1 确认机型/类型/形态稳定，再对照 5 案例，重点看 `spec_mismatch_count` 与未命中项。
- 已清理 `backend/scripts/_*.py` 遗留临时脚本（87 个，跟踪中文件已删除）。
- 后端需重启进程加载新代码；当前 8000 端口可能仍是旧进程。

## 环境/红线

- Python：`D:\CPQ_Platform_V1\backend\.venv\Scripts\python.exe`；设置 `PYTHONUTF8=1`、`PYTHONPATH=D:\CPQ_Platform_V1\backend`。
- 登录：admin / fA5zXkyWv_RyrAqe（不得删除/重置）。
- CC Switch 上限约 30-40 req/min；禁止并行大扇出。
- 动手改代码前先说明原因+方案并等批准；用户手改文件不要动。
