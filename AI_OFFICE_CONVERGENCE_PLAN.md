# AI Office「需求分析 Skill」交接方案（新会话执行版）

> 本文件是给**全新会话**看的自包含执行方案。当前会话已跑太多轮，有中断风险，故把全部上下文固化到这里。
> 会话交接时：新会话先读本文件，再读 AGENTS.md，然后**只做只读核实 + 向用户说明方案，等批准后才改代码**。

---

## 0. 一句话任务

把「需求分析 Skill」从 **确定性 if-else 引擎 + 双引擎并存**收敛为**单一 LLM 工具循环 + 配置驱动的智能体**，遵循范式：
Agent = 角色 + 目标 + 工具 + 规则 + 输出格式。
**不许重写整个技术栈，不许打地鼠，不许在 py 里新增业务 if-else/词表。**
## 1. 现状（已只读核实）

### 1.1 双引擎并存（核心病灶）
- **技能路径（确定性）**：colleague_turn_service.py -> run_fixed_workflow（capability_executor.py）-> reasoning_executor._dispatch（capability_executor.py:218）-> capabilities.py:166 仍 import run_agent_fill。
- **ReAct 路径（通用）**：colleague_turn_service.py:1097 调 agent_react.run_react_loop（文本式 ReAct，provider 无关）。
### 1.2 硬编码残留（用户最忌，需处理或明确不改）
- backend/app/services/capabilities.py（1251 行 / 32 函数）：仍含 _infer_series_from_requirement、_catalog_whitelist、_infer_series_from_selected_model、_apply_extracted_slots、_slot_now_filled、_confirmed_text、_compose_config、_get_nested 等业务 if-else。
- backend/app/api/candidate_search.py（2009 行）：pick_kp_parts 关键词匹配、PER_KEYWORD_LIMIT、_load_psu_inference 仍为确定性判断。
- backend/app/services/bom_compare.py（490 行）：_L6_ITEMS 品类正则。属 BOM 对比域，默认不动（除非用户明确批准）。
- backend/app/services/reasoning_executor.py（790 行）/ capability_executor.py（232 行）：仍为旧 node 分发宿主。
### 1.3 已完成（勿重复做）
- 三层抽屉已落地：ReasoningNodeDrawer.vue 含「AI 层（节点名 + System Prompt）」「目标层（字段配置/部件映射/反问阈值）」「资源与权限」。
- BOM 卡渲染：AssistantPanel.vue:242 已改 d?.entity || d?.bom_scheme（与办公面板一致）。
- 输出节点物：capability_executor.py:133 已改成 bom_draft or {plans_count:...}，带真实 bom_scheme。
- 别名迁移已验证：agent_tools.py（_PERIOD_ALIASES/_FOCUS_ALIASES 已删）、bom_template_eval.py（_CAT_ALIASES 已删，改读 system_config.bom_category_aliases）、前端 bomRuleEngine.ts/bomCategoryAliases.ts/usePlanBom.ts/L6ChassisConfig.vue/BomTemplateManager.vue。
- requirement_normalizer.py 已删，后端无引用（rg 0 命中）。
- 新文件已存在：capability_spec.py、slot_contract.py、slot_extractor.py、slot_state.py、skill_router.py、semantic_contract.py、feasibility_guard.py、requirement_rule_catalog.py、prompt_store.py、prompt_defaults.json、capability_executor.py、agent_react.py。
## 2. 结论：不重写，做「删除 + 收敛」

你的直觉（重写同栈不会强多少）是对的。病灶不是技术栈，而是**两套引擎并存**且旧引擎在替 LLM 做决定。因此：

- **只保留一套引擎**：skill 节点统一走 ReAct 工具循环（agent_react.run_react_loop），每个节点 = System Prompt + 工具白名单 + 输出契约。这正是你定的范式与三层抽屉已表达的形态。
- **确定性逻辑只当工具**：select_models / pick_kp_parts 等返回数据，不返回「决定」；「决定」由 LLM 推理。这样 capabilities.py 的 smart 分支被删掉，硬编码大多随之消失。
- **删文件多于写文件**：若收敛后 reasoning_executor / capability_executor 的旧 node 分发冗余，归入历史遗留清理。新代码量很小，大头是删 + 接线 + 行为级复测。
## 3. 用户红线（新会话必须遵守）

1. 动手改代码前先说明「原因 + 方案」等批准；调查类只输出结论。
2. 禁止在 py 里写业务 if-else / 词表 / 关键字；业务知识只放配置与规则库（system_config、requirement_rule_catalog、server_catalog、prompt 模板）。
3. 拒绝「硬编码 + 黑盒」：不许出现前端没配置入口、后端却悄悄运行的逻辑。
4. 不新增冗余字段；不加「补丁式」功能。
5. 不要「最小改动、打地鼠」；要根上解决。
6. 不改动无关域，尤其 bom_compare.py（BOM 对比域）未经明确批准不动。
7. 改完如实汇报改了什么、验证了什么。
## 4. 执行顺序（先根后叶，避免打地鼠）

### 4.1 冻结 + 精确盘点（只读，先做）
用 CodeGraph / rg 精确定位以下文件中所有「业务判断 / 词表 / if-else / 关键字」并列出 文件+行号：
- backend/app/services/capabilities.py
- backend/app/api/candidate_search.py
- backend/app/services/reasoning_executor.py
- backend/app/services/capability_executor.py
- backend/app/services/agent_tools.py（确认别名迁移后是否还有残留）
产出「删除清单 + 边界图」，交用户拍板后再改码。

### 4.2 收敛引擎（核心改动）
将 skill 节点的执行统一到 run_react_loop（ReAct 工具循环）：
- 每个节点 = {System Prompt + 工具白名单 + 输出契约}（slot_contract / semantic_contract 已具备）。
- 删除 capabilities.py 里的 run_agent_fill / run_model_reason / run_kp_reason 的「smart 分支」，改为走通用工具循环。
- 保留 select_models / pick_kp_parts / list_server_types 等「返回数据」工具；移除它们内部的「替你决定」逻辑（关键词/匹配阈值本身挪到配置）。
- 确认之前 CapabilitySpec（capability_spec.py）是否已被真正用于驱动，而非仅声明。

### 4.3 删除历史遗留
收敛后若下面文件成为死代码，清理并删除对应测试：
- reasoning_hub.py / reasoning_orchestrator.py / reasoning_session.py（若仍在）
- scene_analyzer.py / agent_understand.py / llm_audit.py / config_schemes.py（若仍在）
- requirement_normalizer.py（已删，确认无引用）
- 删除后端测试文件里对已死模块的引用。

### 4.4 前端核验
- 确认各节点 Drawer 都是「三层卡片」（AI / 目标 / 资源与权限）。
- 确认机型推荐是「候选卡」而非纯文本；卡片可点击进入自配。
- 确认输出节点 BOM 物点开有 configs（NodeArtifactModal 读到 bomScheme.configs）。
- 确认聊天里 BOM 卡能渲染（AssistantPanel.vue 兜底逻辑已改，需跑通）。

### 4.5 行为级复测（模拟真实用户）
构造多种输入跑完整链路：清晰需求、模糊需求、闲聊、英文、用户点名系统不存在机型、用户要自配、用户委托「你推荐」。
校验：需求分析稳定登记→不越权反问/不重复问/不乱编字段；机型选型给候选+自配入口；配件选配；最终 BOM 物可点开有 configs；耗时合理。
## 5. 验证方式
- 前端：npm run build 或 vue-tsc -b（在 frontend/ 下执行）。
- 前端单测：node --test src/utils/bomRuleEngine.l6.test.ts、src/composables/usePlanBom.test.ts（在 frontend/ 下）。
- 后端：cd backend && .venv/Scripts/python.exe -m py_compile <改动文件>；跑 test_agent_tools.py、test_skill_router.py、test_requirement_slots.py、test_agent_fill_smoke.py、test_model_reason_shortcut.py。
- 全程用 codegraph 定位，避免全量 rg。短命令，禁并行大扇出。

## 6. 环境与防断连（每轮必读）
- 本地代理链路：客户端 -> CC Switch(127.0.0.1:15721) -> cloudprime 上游。限额约 30-40 req/min，基线 8-13/min 安全。
- 命令参数超约 7359 字符会 502 / EOF while parsing；长脚本先写成 .py/.ps1 再执行（apply_patch 当前不可用，用 .venv 的 python 脚本编辑；写文件用 io.open(..., newline=\ \)，按 \\r\\n 或 \\n 判断换行）。
- Remove-Item 可能被拦截；删临时文件用 python os.remove/glob。
- 前端脚本文件确保落在 frontend/ 下执行。
- 会话断了不丢上下文：重开「继续」接上，勿新建。

## 7. 需用户拍板的边界
- bom_compare.py 是否动（默认不动）。
- capabilities.py 是「废弃」还是「仅删 smart 分支、保留引擎壳」——建议：保留引擎壳，删 smart 分支，业务规则下沉到配置。
- 消息结构是否允许微调（当前 BOM 卡靠前端兜底 d?.entity || d?.bom_scheme，后端不强改；若强改需用户同意）。
