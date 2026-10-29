---
name: requirement-rules-domain
description: 09-14需求规则页+知识化注入落地：规则渲染成知识块进brain系统提示,system_config存绑定,影子校验永不代填;09-16绑定编辑终态=节点抽屉·规则层「已选卡+＋添加」picker范式(四步定调);碰需求规则页/基线/平台推导/skill注入/节点抽屉前先看
metadata: 
  node_type: memory
  type: project
  originSessionId: eba9e191-91a0-40d3-99bc-5b91569c0fd6
  modified: 2026-09-16T15:54:41.461Z
---

2026-09-14 策略中心-需求分析规则页落地（原型 v3）+ 当晚**知识化注入已实施**（设计方案 `docs/需求分析/01_架构与契约/需求规则知识化注入-设计方案.md` §10 清单 B1-B5/F1-F5/T1 全落地；该文档是权威）。

**机制现状（取代摆桌）**：规则不再由 Python contains 预求值塞 hint，改为 `requirement_knowledge` 把规则按组**确定性渲染成知识块注入 brain 系统提示**（`skill_turn_engine._knowledge_for` → `_build_step_call` sys_prompt 拼装：persona→手工规则→知识块→当前步骤；逐字节稳定 KV cache 友好，预算 2000 字）。AI 读规则语义外推（KH-40000 按 KH 系列就近归置）；`scenario_baselines_for_registration` 已删、两处 prepare 摆桌已删。

**落地事实（改链路前对账）**：
- 绑定存 `system_config` 单键 `requirement.knowledge_bindings` = {node_key:[组名]}（startup `ensure_knowledge_bindings_bootstrapped` 只在 key 缺失时补；显式空对象=全解绑被尊重）。默认 agent_fill→[平台归置]、kp_reason→[平台归置+场景配置基线]（kp 拿平台词典=P1 平台冲突源头修复）。
- 影子校验（平台组专属，永不代填）：`shadow_check_platform` 对 probe 副本（pop platform_type）走 `catalog_derivations_for_registration`；词典卡选项一致→AskCard「规则推荐」徽标、不一致→「与规则不符」+engine contract_warnings（reason_code=platform_shadow_conflict）。选项标注穿透三处重建点（_ask_gap/_emit_gap_card/_emit_ask_card）。
- ⚠️ 2026-09-16 五步定调：①「预览 UI 鸡肋，全删」——注入预览条/「AI 将读到」预览 + `/knowledge/preview`、`/knowledge/preview-rule` + `render_rule_preview` + `KNOWLEDGE_BUDGET` 永久退役（看真实注入文本=`knowledge_for_node(node_key)`）。②「绑定入口进节点抽屉」——ReasoningNodeDrawer 规则层（目标层1→规则层2→工具层3；大脑节点显示）。③初版「每组一个开关」被打回（粒度不清），重做树形勾选双粒度。④树形勾选被打回（未选的组常驻抽屉不收敛），改「已选卡+＋添加」picker。⑤**终态**：点「＋」开**选择弹窗**（工具层「＋添加工具」同步从内联展开改弹窗）+ **卡片设计语言全站统一**——`RuleCard.vue`（组/条两型，idle/selected 态，语法对齐 ToolCard）+ `RulePickerModal.vue`（打开即实时拉取策略中心当前清单，按组分节：组头「整组加入」/规则卡单条加入，catalog 事件回传刷新已选区）；已选区=RuleCard selected 网格+虚线尾卡，移除组卡清该组全部单条，**完全不引入=不注入**。同日加：抽屉三分区头（目标/规则/工具层）可点击折叠（用户点名「像商机详情页中部栏」，照搬 card-chevron+grid-rows 1fr→0fr 范式）。存储/注入语义③定稿后未再动：`{node_key: {groups, rule_ids}}`（旧 list 形状读时归一，写回自愈）；注入=组活跃规则∪单条勾选。规则页零绑定控件；影子校验/bootstrap/渲染确定性不变。**教训四条：绑定粒度「组或单条」一体可选；绑定 UI 随规模收敛「已选+添加」而非全量常驻；同屏选择器要弹窗化+卡片语言全站统一（内联展开池和第二套 pill 脸都被打回）；点「＋」必须实时拉源数据（预放缓存再遮挡=用户点名的掩耳盗铃）。**
- 测试：test_platform_derive.py 9 例+test_requirement_rules.py 13 例（夹具=DB 导出规则原样，显式传 rules= 不依赖 DB）。

**定位三分工**：需求域管「配得对不对」；选型配置 CRE 管「配了行不行」；BOM 案例库给「成品长什么样」。规则本体同住 `rules.compatibility_rules` 靠 domain 分域，list 默认 domain=selection。

**两大类**：
- 平台归置（type=derive）：`kp.CPU.spec.text` contains → `opportunity.platform_type`。库内：兆芯/KH→Polaris、AMD/EPYC/霄龙→Orion、Intel/至强→Intel（待复核）；海光待业务拍板。
- 场景配置基线（type=recommend，then.action=baseline）：`config.scenario_blob`（=server_type+需求原文）contains → items[{category,text}]。AI训练5条/AI推理3条/通用3条。**训练信号不含「大模型」**——防「大模型推理」双命中，互斥是语义适用前提。

**Why:** 用户初衷「AI 读规则像读配件库，不是当计算器」+WYSIWYG（你编辑的就是 AI 读到的）；铁律③ 规则只住 DB（[[skill-tree-trunk-architecture]]），渲染器只格式化。

**How to apply:**
- evidence 必填存 **body.evidence**（repo 项级 evidence 不持久化，必须进 body JSON——踩过）。
- server_type 含场景词（如「通用计算服务器」）本身命中通用基线——产品正确，别当 bug。
- 前端 `RequirementRules.vue`（/strategies/requirement）；页面壳对齐选型配置页同款（用户明示）；CSS token 真名 --cpq-color-success/--cpq-color-warning（--cpq-success 不存在）。
- 种子机制已退役（「单一存储单一来源」）：代码无规则副本，空库靠 DB 备份恢复；DB 漂移改测试夹具或 DB。
- 改 skill 注入/绑定/影子时先读设计文档 §5.1（绑定存储落地修订）与 §11 铁律（规则只住 DB/影子永不代填/推断槽位必确认不变/规则页是绑定编辑唯一入口）。

关联 [[skill-current-state-2026-09-12]] [[inferred-slots-must-confirm]] [[strategy-center]]。
