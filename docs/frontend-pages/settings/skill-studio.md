# 工作流编辑器（原 Skill Studio）

> 最后更新：2026-09-26（「Skill Studio」更名「工作流」；能力包（type≠workflow）轨下线——DB 存量为零，目录只剩工作流型，员工编辑器「能力」区只留工作流+工具绑定）

AI 办公室 → 「Manage Teams」 → 顶部导航 **工作流** → 点击工作流卡（如「需求分析」）进入编辑器。

## 三栏布局（2026-09-07 编排权移交）

| 栏 | 内容 | 说明 |
|---|---|---|
| **左栏（AI 视角）** | ① 任务规则（可编辑）② 大脑视角预览（只读） | ① 保存写入 flow（`graph.manual_rules`），大脑下一回合即读到，不升画布版本；② 调 `render_skill_manual` 的实时渲染结果，与 AI 开局读到的说明书同源同刻。改抽屉/规则后点「刷新预览」即见 |
| **中栏** | 节点画布（vue flow） | 单击节点开抽屉配置：目标层 / 规则层 / 工具层。三个分区头都可点击折叠收起（同商机详情页中部栏 `card-chevron` + grid-rows 1fr→0fr 动画范式）。工具层=机制锁卡+已挂载卡+尾卡「＋ 添加工具」开弹窗选择器（卡片与工具目录同一张 `ToolCard`）；规则层=已引入组卡/单条卡（`RuleCard`，与 ToolCard 同套卡片语法）+ 尾卡「＋ 添加规则」开弹窗（打开即实时拉取策略中心规则清单，整组加入/单条卡加入） |
| **右栏** | 试运行 | 复用真实 AI 角色对话（support_engineer、skill_studio_preview 入口，每轮独立线程） |

## 大脑执行模型（编排权移交后）

大脑开局读到说明书（左栏预览所见即所得），**自主按步骤**调工具完成：

- 步骤工具：`begin_step(步骤key)` 触发该步确定性预处理（候选池构建/配件行装配/前置校验）并广播 node_trace 进度；`end_step(步骤key)` 做步末校验（缺关键信息/行未落地 → 返回原因，大脑按原因补：缺客户信息调 ask_user 问客户）。
- 步骤顺序在说明书里，跳步（如未选机型就组装）被 `begin_step("compose")` 的前置校验硬拦。
- 交付前终检 `final_gate`：机型未锁定 / 登记大类无落地行 / 客户未放弃的行缺失 → 拦截交付并如实说明（回归测试 `tests/test_final_gate.py`）。
- 客户回复后状态回灌（登记表 + 工作记忆 brain_notes + 已完成步骤 + 检索索引），大脑从断点继续。

## 工具集（唯一清单在 agent_tool_specs.py；启用=抽屉 enabled_tools ∪ 机制保底）

现行 10 个：`fill_requirement`（登记）、`choose_model`（锁机型，池外拒绝）、`query_parts`（配件检索）、`inspect_parts`（钻取/定向搜索）、`select_parts`（行落地+数量上限闸）、`ask_user`（客户决策卡，一回合一卡）、`catalog_search`（目录接地）、`search_cases`、`query_data`（只读原语）、`opportunity_stats`（商机统计口径工具，2026-09-16：与商机线索页同一份实现——口径核心在 `app/repository/opp_caliber_repo.py` 单点，传入数据范围一次返回 KPI/逐期序列/平台与机箱分布/销售榜/本周本月小窗；趋势报告的统计数字唯一来源，`query_data` 只作维度钻取）。抽屉工具层为卡片 UI，与「工具目录」页同卡同源（`ToolCard` + `GET /api/assistant/tools`）；卡面显示人类层（中文名+一句话，`agent_tool_display`），卡详情弹窗双栏（左=详解+模型契约，右=参数+被引用，920px）；**「编辑文案」入口只在「工具目录」页**（DB 权威层 `agent_tool_text`），抽屉里的卡**只读**（仅挂载/移除，文案改动去目录页）。

## 目标层（agent 节点已开放 document 报告插头，2026-09-16）

目标层 = 节点要产出的目标（`config.target.artifacts` 描述符，DB 唯一权威）：

- **agent_fill 节点**：表单/表格类（登记策略、字段契约、真实预览），见下文各弹窗分支。
- **agent 节点（2026-09-16 泛化）**：「＋ 添加输出物」开放 **document 报告**插头（`{kind:'document', slot:'data_report', name, data_range, sections:[{key,title,requires}]}`）。弹窗左侧编辑报告名称 + **数据范围**（自动按数据边界 / 近30天 / 近90天 / 近半年 / 今年 / 自定义起止——后端 `_report_window` 确定性计算窗口写进契约，大脑不得越窗统计）+ 章节列表（**拖拽手柄排序**，BOM 模板编辑器同款 grid 表行：手柄｜序号｜章节标题｜内容要求｜删，尾卡「＋ 添加章节」），右侧结构预览（含数据范围行与中文序号大纲）。契约注入大脑提示（steps 清单），运行时节点完成产物 chip 可点开 `NodeArtifactModal` 看 markdown 全文（`MarkdownContent` 渲染）。趋势分析流已由迁移脚本 `scripts/seed_trend_flow_target_20260916.py` 播种七节结构（周数据/月数据/半年度趋势/平台格局/机箱形态/业务TOP3/关键洞察）+ 数据范围近半年。**数据范围交付终检（2026-09-16）**：`_data_answer_gate` 在交付前物理核对报告首部与配置窗口——大脑会复读对话历史里旧报告的自算窗口（锚定效应，提示词压不住），不符即拦截交付并把该节点从已完成摘出重跑（暂停卡带原因）。契约文本只陈述形状（首行=配置窗口），行为禁令一律住左栏 manual_rules，不进共享代码。**输入卫生为主、终检为保险丝（同日二次修正）**：document 产物节点组装大脑上下文时，确定性剔除历史里「报告形状」的 assistant 消息（指纹=首行「数据范围：」）——旧报告既是锚定毒源、统计数字也早已过期，复读风险在入口移除，而不是在出口拦截重烧。
- 后端扩展点 = 注册表三件套（机制零改动）：`skill_target_contract._CONTRACT_FORMATTERS["document"]`（结构契约→大脑文本）、`skill_node_artifacts.BUILDERS["data_report"]`（agent_result.answer→产物）、`NodeArtifactModal` kind 分支。

## 输出节点抽屉（按输出契约门控，2026-09-15）

输出节点是交付契约层，控件按 `output_kind` 门控、不留跨类型死控件：

- **输出类型**：绑定 Skill 的画布上一律**锁定**（分派轴=skill_key 选流 + output_kind 定交付语义，节点级改它会断交付链）；无契约的独立流才可编辑。节点配置里的陈旧值会被契约治愈（契约优先于节点存量）。
- **方案名称**：仅 `requirement_draft`/`bom_scheme_draft`（业务实体落库命名）显示，其余类型隐藏且保存时清残留。
- **文件产物**：仅 `data_answer` 显示——开关 + 格式（v1 仅 PDF 报告）+ 报告标题，写 `config.artifacts=[{kind:'document',format:'pdf',title}]`（关闭/其他类型写 `[]`）。开启即得：交付时后端 `report_pdf.py` 把大脑的 markdown 结论确定性渲染成 PDF（中文字体链 msyh→STSong-Light，表格/列表/标题全覆盖），落 `storage/office/reports/`，会话出文件卡（下载/预览）+ 任务看板产物可下载；渲染失败只记日志不挡交付。任何 data_answer 流开开关即得，渲染器不认识具体流。趋势分析 flow 已由迁移脚本 `scripts/fix_trend_flow_artifacts_20260915.py` 默认开启（标题「商机趋势分析报告」）。
- **高级交接配置**：仅剩 `payload_map`（ctx 点分路径→交接 payload）——它是输出节点自身的插座契约、引擎每次交付必读，保留可编辑、默认折叠。原「交接动作 actions」「输出模板/schema」（generic）已删：actions 唯一读者 `downstream_guard` 从未接线、template/output_schema 全库零消费者，保存时自动清残留（别在节点配置里再手写，写了也不生效）。

## 已删除的旧机制（不要找回）

硬编排引擎 `run_skill_plan_core`（节点推进/gate/兜底卡）、`skill_phases` 的编排阶段函数、缺口转述 LLM 调用、`skill_plan_executor.py`、`capability_spec.py` 三处工具定义重复。确定性计算保留为预处理纯函数（`prepare_model_step` / `phase_kp_reason`）。

agent 节点抽屉的「节点提示 System Prompt」折叠（2026-09-16 删）：`config.system_prompt` 是死字段——引擎人设恒非空，`agent_react` 的节点配置兜底走不到；且与「指令唯一出处 = 左栏使用说明（manual_rules）」定调相抵触。给流播种任务说明走 `graph.manual_rules`（趋势流已播种）。
