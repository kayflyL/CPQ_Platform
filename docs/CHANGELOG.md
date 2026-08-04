# 更新日志

> 最后更新：2026-08-04
>
> 定位：**轻量变更索引**（接手导航）——每条 = 变更 + 根因一句 + 涉及面；细节与 why 以代码注释为准。
> 图例：🔄 撤回/纠正 · ⚠️ 破坏性/严重 · 💡 认知定论（最值得看）。

---

## [0.1.41] - 2026-08-04 — IO/Riser 数据补齐 + 基准配置编辑器补 UI + 防简介保存清字段

- **IO 空根因**：ZS22V2-P 基准配置（bc 20）`config_content` 只有测试残留（`{"spec_diff":"22222","description":"123123"}`），没配 `standard_riser`/`riser_x16` → 模板 eval 走"未配置留空手填" → IO1/IO2 空
- **bc 20 数据补齐**（Polaris 2U12 三模版）：`standard_riser={"IO1":"1*X16+1*X8 FHFL","IO2":"1*X16+1*X8 FHFL"}`、`riser_x16="1*X16+1*X8 FHFL"`、`standard_mem_speed="4800"`（技术员单口径；顺带清掉 UI 会显示的测试残留文案）
- **基准配置编辑器补 UI**：原页面只有 rear_slots（IO1-4 + 容量），`config_content` 无编辑入口（文档超前于 UI）→ 新增「IO/Riser 与内存速率」编辑区：各 IO 槽 `standard_riser`（按槽位 dict）+ `riser_x16` 升级规格 + `standard_mem_speed`；留空的槽不落库=手填；`ConfigContent` 类型同步扩展
- **修 clobber 坑**：ModelEditorPage 保存"简介"原来整体替换 `config_content`（只带 description/spec_diff）→ 会把 standard_riser 等字段清掉 → 改为合并保存（保留 riser/内存字段）
- 实测验证：该需求重跑 → IO1/IO2 = 1*X16+1*X8 FHFL、Memory = 32GB DDR5 4800（对齐技术员单）；pytest 282 · vue-tsc ✓ · npm test 56 ✓

## [0.1.40] - 2026-08-04 — 代码瘦身第一轮：删一次性脚本/死代码/死依赖（-4k+ 行）

- **一次性脚本 36 个（~3100 行）**：`backend/scripts` 45→9。删 migrate_*/seed_*/drop_*/clean_*/diag_*/update_bom_template_* 等已执行完的脚本；保留 6 个长期工具（replay_cases/simulate_requirement/online_verify/audit_reasoning_batch/strategy_insights/analyze_kp_data）+ 3 个被前端注释当同步契约的脚本（seed_pricing_strategies/seed_strategy_fields/migrate_base_config_capability）
- **requirement_check 死代码整段拆除**：0.1.36 已从流程删节点，本轮把残留全清——executor handler、linear fallback 调用、PIPELINE_STEPS 条目、`_VALID_NODE_KEYS`、默认节点配置、v6 迁移方法 + startup 调用、`check_plan` 全家桶（DEFAULT_CHECK_CONFIG/load_check_config/helper）+ 9 个对应测试、前端 RequirementCheck 类型/字段/IO 定义/步骤文案/节点抽屉表单；DB 清 30 条孤儿 node_config；`audit_plan`（review 校对）保留
- **死文件/死依赖**：`bom_similar.py`+test（experience_alerts 引擎，0.1.38 已下线，零引用）、前端 3 个零引用组件（ActivityStream/ShowcasePreviewModal/SelectionNode）、`selectionConfig.ts`（已删画布的配置）、`dagre.d.ts`+package.json 移除未用 `dagre` 依赖、旧 `scripts/_backup/` 6 个 BOM 模板备份
- **死常量**：`requirement_checker._PLATFORM_SERIES`（只定义未引用）
- **过期注释 3 处**：startup.py / ruleMeta.ts / bomRuleEngine.l6.test.ts 里指向已删脚本的引用
- **llm 占位节点拆除**：通用 `llm` 节点（role=extract_enhance）从未被任何流程图连接（34 个 flow 全无），其能力已被 extract 节点自带 enable_llm 增强取代 → 删 executor handler/默认配置/_VALID_NODE_KEYS/前端 palette/抽屉表单/IO 定义 + 2 个 dispatch 测试 + DB 32 条孤儿 node_config；extract/scene/review 三节点自己的 enable_llm 开关保留
- 验证：pytest 284（-18 测试：9 check_plan + 5 bom_similar + 4 其他）· vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归（BI 0 差异）

## [0.1.39] - 2026-08-04 — 国产 CPU 厂商分家：Polaris=兆芯，KH-50000 不再标"海光"

- **根因**：系统只有"系列"维度没有"芯片厂商"维度，Polaris 被当成"信创大杂烩"桶（兆芯+海光+飞腾+鲲鹏混装），"海光"又被当成 Polaris 代称 → 用户需求 `KH-50000`（兆芯开胜）被整条链路当成海光
- **口径定论（用户确认）**：Polaris 只配兆芯、Orion 只配 AMD；海光/飞腾/鲲鹏/龙芯不是 Polaris
- **改动（代码 + 配置双修）**：
  - 系列词表摘除海光/hygon：extract 节点 lex_series（默认 + active 流配置）+ scene_mapping series_hints（默认 + system_config）→ `KH-50000/兆芯/zhaoxin/开胜/开先` 独属 Polaris
  - CPU 平台过滤按厂商分家（candidate_search）：需求点名厂商 → 只留该厂商家族（海光需求绝不落兆芯 KH/KX）；只写"信创/国产"或平台=Polaris → 留兆芯家族；`_XINCHUANG_RE` 补"国产"；修中文前缀 `KH` 词边界不匹配问题
  - review 校对厂商感知（requirement_checker）：海光/飞腾/鲲鹏/龙芯需求不再提示"应为 Polaris"，海光需求配 Polaris（兆芯）也 blocked
  - 系列确认别名（requirement_intel_service）："海光"→Polaris 别名删除，只留兆芯/开胜/信创/国产
  - 前端 chassisMeta 常量 `REAR_SLOTS_2U_HAIGUANG` → `REAR_SLOTS_2U_POLARIS`（Polaris=兆芯）
- **验证**：pytest 298 · vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归；`KH-50000` 需求实测 → ZS22V2-P（Polaris）CPU=KH50000×2、事件零"海光"、audit ok；`海光` 需求实测 → 系列 None + 校对 blocked（Polaris 是兆芯不能替代海光）

## [0.1.38] - 2026-08-04 — experience_alerts 在线展示下线（案例库防偏差误报噪音）

- **用户实测**：ZS22V2-P（兆芯 KH-50000）需求被 `attach_experience_alerts` 拿 ES22V3-P（AMD）案例做规格级对照 → 跨平台满屏差异（CPU platform/HDD cap/iface/Memory speed/NIC/数量…）
- **处理**：review 节点不再挂 `experience_alerts`（案例库对照只保留在训练 bom_compare/重放），PlanCard 撤掉 experience_alerts 展示；在线"重大偏差"由 audit_plan 硬校验兜底（缺件/平台冲突/严重超预算）
- 方案卡最终只剩「校对通过 ✓ / 需修改：…」，零噪音警告
- 验证：pytest 290 · vue-tsc ✓；海光需求实测：requirement_check 不存在、experience_alerts=0、selection_alerts=[]、audit ok

## [0.1.37] - 2026-08-04 — 阶段 2：LLM 接入（extract/scene/review 三节点增强 + 节点级开关 + 槽位清单可视化）

- **LLM 三节点接入（每个节点抽屉独立开关 enable_llm && 全局「设置-AI 设置-启用 AI」双重约束）**：
  - extract：LLM 结构化抽取并入 extract 节点（`run_extract_enhance`，schema 收口 + merge 只补缺、规则赢、能力声明不产配置）；失败降级规则结果
  - scene_analysis：`run_scene_infer` 规则推不出系列时 LLM 从语义补推断（如 A800 8卡→Orion），明说/已定不动
  - review：`run_llm_audit` 语义校对（方案是否真满足需求意图），规则硬校验兜底；LLM 存疑 → status=review（需人工确认）
- **节点抽屉 UI**：extract/review/scene_analysis 抽屉顶部加「启用 LLM 增强」开关；llm 节点保留（通用）
- **槽位清单可视化**：新增 `SlotListEditor.vue` 放 clarity_check 抽屉（编辑全局 `requirement_slots`：L0/L1/L2 层级 + label + default_ok + 反问阈值），替换已弃用的信号规则编辑
- **降级验证**：extract enable_llm=True 但 LLM 未配置 → chat_json 失败 → 静默降级规则，不阻塞主流程
- 验证：pytest 290 · 前端 vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归

## [0.1.36] - 2026-08-04 — 需求分析流程重构（R29）：槽位覆盖度 + 系列确认 + AI 统一开关 + 删差异报告

- **删 requirement_check**：在线「需求核对差异报告」实测警告泛滥（把库缺口/替代/措辞全当警告）→ active flow 移除节点 + PlanCard 撤警告行；`bom_compare`/重放（训练对照）保留
- **明确度=槽位覆盖度**：`requirement_slots` 期望清单可配置（L0 底线[场景/系列/CPU/内存]/L1 重要[形态/GPU/网卡]/L2 推导[RAID/电源]），`evaluate_slot_coverage` 按已填槽位差距判 explicit/partial；存储 default_ok（缺了给默认盘），AI 场景缺 GPU 反问
- **系列确认 confirm_series（新节点）**：scene_analysis 输出 `series_source`（explicit=需求明说 / inferred=系统推断）+ `scene_determined`；cond_scene 判据改 `scene_determined`；推断系列→问「是否 XX 系列？」，推不出→列在售系列选，明说/已确认→直接选型；答复（是/不是/系列名/平台别名）解析持久化 `requirement_confirmed_series`
- **review 改校对**：`audit_plan` 阻塞式 通过/不通过 + 必改项≤2（缺 CPU/内存、信创需求配非信创、严重超预算），挂 plan.audit，PlanCard 展示「校对通过 ✓ / 需修改：…」
- **AI 统一设置**：`llm_config.enabled` 全局开关（设置-AI 设置-API 设置「启用 AI」），`llm_client.stream_chat/chat_json` 统一 gate + `is_llm_enabled()`；关闭后所有 AI 能力走规则/不调 LLM，llm 节点双重开关（节点 enable_llm && 全局）
- 验证：pytest 290 · 前端 vue-tsc ✓ · npm test 56 ✓ · 重放 5 案例无回归（BI 0 ✓）

## [0.1.35] - 2026-08-04 — ESA24V3-P（4U）首测：RAID 显式型号分组 + NIC SKU 归一 + PSU 冗余数量

- **RAID 显式型号分组（R28）**：需求逐行给阵列卡型号（`RAID卡：LSI 9560 16i 8G缓存 *1`）→ `_extract_raid_groups` 归一 `9560-16i` 按组精确出件（不再泛配 9540-8i）；stage-1 跳过 RAID 组 token（含完整型号串，修 BI/LLW 回归），无型号（RAID 0,1,10）交回 I22 applicable 兼容选件
- **NIC 型号归一**：`X710DA2BLK` 去 BLK 后缀 → 命中库件 `Intel X710-DA2` 含光模块（原选国产无光模块件）；连字符归一放匹配侧（保留 ConnectX-6 形态）；`光口含模块/含模块` 识别为光模块信号
- **PSU 冗余数量（R28）**：`2700W 2+2/3+1冗余` → 4 个（N+M 求和；原按「冗余=双电源」出 2）；4U 8 卡机电源 2700W×4 对齐技术员单
- **噪音过滤**：`TDP360W`（CPU TDP 连写）不再当型号 token 报 unmatched
- **新案例入库**：ESA24V3-P · HK-2026-0707（4U8-Switch，model_id=16 / bc25 / tpl3），校对 BOM 以技术员单为准；待确认：GPU A800 需求 ×2 vs 技术员 ×8、Switch 行 `3*X16` 口径、L6 文案 KH50000 vs AMD 实配
- 验证：pytest 283 · 重放 5 案例（BI 0 差异 ✓ / ESA24 3 [GPU业务+2库缺口] / YLL 1 / YC 1 / LLW 3 已知）

## [0.1.34] - 2026-08-04 — IO/Riser 配置经验沉淀 + 对照引擎 riser 内容级比对

- **riser 数据驱动落地（R25/R26/R27）**：`config_content.standard_riser`（默认，per-slot dict、大小写不敏感）+ `riser_x16`（GPU/100G 升级）；未配置留空手填，零硬编码。ES22V3-P 三连版=满配 `1*X16+1*X8 FHFL`、直连版=预算 `1*X8 FHFL`（对上 LLW/BI/YLL 技术员单）
- **对照引擎新增 riser 内容级比对**：行数一致时比槽位规格（`_riser_signature` 归一，`2*X8` vs `1*X16+1*X8` 报 l6 差异；FHFL 形态词/槽位顺序不算）→ 重放立即抓出 YC IO2=2*X8 缺口（待更多样本定 per-slot 覆盖）
- **经验与规则入系统**：文档写入「策略中心-选型配置-📄文档库」（`rules.policy_docs` module=selection，操作指南「IO 与 Riser：配置经验与填充规则」）——联网调研 + 4 案例实证 + 填充规则 + 改哪里
- **Riser 配置优先级文档**：文档库新增操作指南「Riser 配置优先级：系统自动填充规则」（sort_order=4）——系统自动填充 IO1/IO2 的可执行优先级（GPU→全槽 riser_x16 / 100G+ 网卡→IO1 riser_x16 / 否则 standard_riser / 未配置留空手填）+ 实测输出表 + 数据改哪里
- 验证：pytest 277 · npm test 56 ✓

## [0.1.33] - 2026-08-03 — 需求分析收尾：意图感知开场白 + 完整清单直接出 BOM + 推理 BOM 完整性

- **对话更聪明**：意图感知开场白（你好→问候 / 我要服务器→问用途 / 贴规格→识别）；"你帮我推荐/你定"= 全局授权直接出方案（区别于"还没定"只跳当前字段）；负载原型按原文匹配（最近补充 > 全文 > usage），修"数据库/OLTP"被 server_type 词表折叠后错配"通用/Web 业务"；删开场白"现成配置清单"引导（已贴清单还问清单=荒谬）
- 💡 **完整配置清单直接出 BOM**：clarity 新增 4 规则（品类≥4+内存/型号→明确、型号token≥3→明确、品类≥3+内存+用途→明确）；无规则命中兜底改按信号推导缺口（修"请补充需求描述不够具体"假死循环）
- **推理 BOM 完整性**：`buildPlanCfg` 接料号库后面板数据——IO1/IO2=1×X16+1×X8、OCP=X8、按 KP 盘型推线缆（SATA/SAS÷8、NVMe÷2，镜像 CRE）、NVMe→背板 tri；模板 Cable 行 manual→推导（改动已备份 `backend/scripts/_backup/bom_template_1_20260803.json`）
- **内存解析**：`DDR564G*8`=DDR5-64G×8=512G（原把代际"5"算进容量→564G→9 条）；`_extract_mem_signal` 加代际剥离 + 单条×条数
- 验证：pytest 92 · `npm run build` ✓ · `npm test` 48 ✓

## [0.1.32] - 2026-08-02~03 — 需求分析对话机制（反问修复+负载引导+会话重置）

> 合并原 0.1.39 / 0.1.40 / 0.1.41 / 0.1.42 / 0.1.43 / 0.1.44 六条。
- **反问三连修**：① cond_clarity 阈值写反（只对 unclear 反问、partial 放行）→ 改非 explicit 都反问；② 补充不累积"没记性"→ `requirement_clarity_base/supplements` 跨轮持久化；③ round 跨会话不重置→重新生成报价=新对话重置 round=0（清理 3 存量卡死商机）
- `model_token_in_category` 原失效（"EPYC9354"不含"CPU"）→ 型号→品类关键词表；extract 加 `usage_inferred` 区分"用户明说/系统兜底"
- 死循环防护：轮次上限 3→6；修 R-22 编辑事故（赋值行丢失→NameError→假死循环）+ 防回归测试
- **Spec Assistant 式引导**：新规则类型 `workload`（6 负载原型 + drill_down 追问树，策略中心 ask_user 节点可 CRUD）；首轮抛负载菜单、选 AI→问 GPU；`_field_satisfied` 防跨轮重复问
- **M1 会话语义**：`_merge_clarify_text` 新对话清空旧补充（修"重复上一轮"）；一次一问 take=1；"不确定/你推荐/还没定"=已答只跳当前字段；推理面板「🔄 重新开始」按钮
- LLM 预留（不接，离线可跑）：llm 节点 passthrough + `chat_json()` 桩（extract_enhance / question_gen / best_fit 三 role）

## [0.1.31] - 2026-08-02 — 需求→BOM 引擎校正（训练循环）

> 合并原 0.1.33 / 0.1.34 / 0.1.35 / 0.1.36 / 0.1.37 / 0.1.38 六条。
- 🔄 **BOM 填充层位纠正**：PSU/后面板填充从 `build_plan.bom_excel_rows` 回退（那是无模板 excel 兜底路径，模板模式不读）→ 改 `chassis_signals.psu_wattage` + 前端模板渲染；修 `deriveVars` gpu_qty/drive_count/psu_qty 全 0 bug（GPU/盘不在机箱件里）
- 🔄 OCP 不再自动填（2 轮真实样本：网络走 PCIe 网卡 KP 件、从不占 OCP，推翻 Dell 行业假设）；IO1/IO2 有 GPU 才填 X16 Riser
- PSU 瓦数按 GPU 分档：≥8 高功耗→2700W / 有 GPU→2000W / 无→1600W（修 R9700 误估 2700）
- KP 数量串台(R-6) + 过匹配(R-8)：数量解析改位置绑定+方向感知（修 SSD 盗内存 16、GPU 漏 ×1、NIC 串 8）；stage-1 跳纯容量碎片、Memory 交容量反推
- 型号正则修 H100/A100 漏匹配(R-15)：加 `[A-Za-z][0-9]{3,}` 分支；非 AI 需求 abort 修复（规格清单无用途词→usage 兜底"通用计算"）
- 🔄 撤回 4U 补件：4U=整机箱 lump 是有意的（未拆件，L6 行偏粗是预期）；GPU电源线属按 GPU 数人工加、不属机箱标配层；风扇占位件 `S.E.M.0000501` 挂 2U ×6（价 0 待补）
- R-17 Cable 调研（未实现）：SAS→Mini-SAS 线、NVMe→PCIe/MCIO；模板 `struct_count(front_cables)`+`frontCableQty` 机制已备、仅推理喂 0

## [0.1.29] - 2026-08-02 — 机箱能力主数据对齐

> 合并原 0.1.31 / 0.1.32 两条。
- 15 份真实配置校准 5 类底座（AMD/海光 × 2U/4U × 直连/Switch）；4U GPU 槽恒 8；OCP 是 AMD 平台特性（海光 2U 无、4U 有）
- 后面板槽位标准化：`chassisMeta` `REAR_SLOTS_2U_AMD/HAIGUANG/4U` + `rearSlotsFor(form,series)`；「恢复标准布局」按 form+series 取模板
- 能力档案回填 `backfill_chassis_capability.py`（4U→psu=4/gpu=8、2U→psu=2、2U 海光去 OCP），10 条校正（不覆盖已填值）
- 🔄 4U 后面板纠正：`REAR_SLOTS_4U` 从误克隆 IO1-4+OCP → 仅 OCP（GPU 槽与 IO 槽物理分区）；4U GPU 走 gpu_slots=8 + gpu_arch(direct/switch)
- 待确认：ZSA24V2-P gpu_arch 建议 switch；id=21/24/26 数据不一致；内存速率分档待权威 MT/s

## [0.1.28] - 2026-08-01~02 — 选型配置重构（L0/L1/L2 架构）

> 合并原 0.1.28 / 0.1.29 / 0.1.30 三条。
- 💡 **两层兼容架构**：L0 机箱能力档案（base_config psu_bays/rear_slots/gpu_slots/max_tdp）+ L1 配件适配（料号库 specs 声明，`partFit.ts`）+ L2 跨件规则 CRE（require/exclude/derive/recommend）
- CRE 双端：`selection_engine.py`（Python 移植 selectionEngine.ts），DB 规则 SSOT 双端共用；补 3 条 exclude 互斥（同型号不混搭）；`seed_missing_defaults` 按名补种
- 硬编码清零：`chassisMeta.ts` SSOT、L6ChassisConfig 清 5 处硬编码、GPU 架构读 `gpu_arch_default`
- 兼容规则加"业务分类"维度（category 列，仅组织用；编辑器分类过滤条+主题分组；API `?category=`）
- 机箱能力并入 `BaseConfigEditorPage`（修 save payload 写死 gpu_arch_default='none' 的 clobber bug）；删冗余 ChassisCapabilityEditor；选型配置瘦身两标签；PartFitMatrix 迁服务器管理（L0/L1 目录主数据归服务器管理、仅 L2 CRE 归选型配置）

## [0.1.27] - 2026-08-01 — 推理流编排可解释性

- 节点 IO 元数据（`reasoningNodeIo.ts` consumes/produces）+ 试运行步骤显示输入/输出；方案卡「回溯路径」高亮生成链；palette 三环节分组；condition 分支必连校验（防路由死路）
- 明确不做：全改显式变量系统、单节点调试、LLM 节点化（二期）

## [0.1.26] - 2026-08-01 — 需求分析试运行 + 两个潜伏 bug

- 画布加试运行 playground：`POST /api/reasoning-flow/test-run` 复用线上 `run_graph_executor`（force_complete 跳反问），节点逐步高亮+IO 明细+候选方案；抽 PlanCard/useTestRun 共享
- ⚠️ simpleeval 从未进 requirements（缺它 `_eval_condition` 永远 True → cond_clarity 永远反问）；build_plan 货币混算（USD 件当 RMB 混加，按 `store/quote.ts` 口径折算成含税 RMB）

## [0.1.25] - 2026-07-31 — 策略文档库

- 报价策略加左目录（定价策略/策略文档）；文档复用 `rules.strategies`（domain=policy，零新表）；marked+dompurify Markdown 渲染；5 篇定价手册种子（空表才灌，绝不覆盖用户改动）
- 推迟：版本快照/回滚（改动直接覆盖）

## [0.1.24] - 2026-07-30 — 报价策略重构：查表→加法定价引擎

- 💡 定价模型：查表三档 → 六维加法叠加（平台+行业+区域）×订单×成本×台数，夹 [保底,封顶]；7 条维度策略、零新增列
- 纯 TS 引擎 `pricingEngine.ts`+单测；`pricingMeta.ts` 维度元数据 SSOT；VueFlow 固定流水线画布+维度抽屉+演算器；工作台告警 floor 改 guardrail（仍只警告不锁价）
- 移除旧 scope→三档模型（PricingStrategyCanvas、MarginTier、seed）；L3 溯源输出 pricing_additive

## [0.1.23] - 2026-07-30 — 选型配置大整理：清退 DerivationEngine

- 💡 线缆/背板规则收敛进 CRE 唯一真相源：删 `derivation_engine.py`、`/api/derive`、DerivationRulesPanel；SATA/SAS÷8、NVMe÷2、GPU 供电线、背板 tri（含 NVMe→tri）迁入 CRE；删整机功耗/PSU/Switch 三条规则
- `ruleMeta.ts` 元数据 SSOT（规则类型标签/语义色/算子符号/ctx 字段）；选型配置页重做（紧凑卡片+弹窗编辑+三列因果流拓扑）
- 修 NVMe 线缆恒 0（`"NVME".includes("NVMe")` 恒 false）→ 引擎层 `normalizeDriveKind` 大小写无关 + 优先读 KP specs
- 移除"按商机平台过滤候选机型"filter 规则（只过滤候选机型、与基准配置下拉表现不一致）

## [0.1.22] - 2026-07-30 — 回退 Excel 表头自适应列定位

- 🔄 移除 0.1.20 引入的 `header_labels` 自适应列定位：频繁定位错列（子串匹配误命中）、扫描窗口难覆盖所有排版、与显式 `col` 双真相冲突 → 回归固定列字母 `source_config.col`（所见即所取）；存量 header_labels 自动忽略无需迁移

## [0.1.21] - 2026-07-30 — 趋势洞察下沉为方案助手快捷指令

- 删商机线索页趋势洞察卡片、`/api/dashboard/ai-insights`、`ai_insights_config` → 并入助手「📈 分析本期趋势」快捷指令
- 快捷指令 prompt/context 支持函数；AI 设置可配 prompt 模板；新增 `/api/dashboard/trend-overview`（周/月/近半年聚合+重点商机，LLM 输出 8 段报告）
- 修 `get_trend_overview` 裸调路由函数 500（Query 默认对象被 strptime）——带 Query 默认值的路由函数不能当普通函数裸调

## [0.1.20] - 2026-07-29 — 清理 pricing_engine 历史包袱

- 💡 `pricing_engine` 1094→425 行（-61%）：拆纯算法引擎 + 业务服务（QuoteService，商机 CRUD 迁入）+ 解析器（ExcelParser）；删 7 个遗留解析方法、Excel 导出样式块、死导入；parse_file 统一走规则驱动（异常直接暴露而非旧实现掩盖）；`_safe_eval_math` 移入 excel_parser（替换 eval()）
- 删 l6/kp_region_config 残留（rules_repo/models/api 共 -263 行）+ 物理删表脚本 `drop_l6_kp_region_config.py`
- 商机详情页报价单解析预览弹窗（热力图+区域/字段规则可调）；Excel 表头自适应列定位（0.1.22 回退）
- 修报价单列表价格/利润不显示（回退误加的按 items 重算逻辑，直接读 quotation 表存量值）

## [0.1.19] - 2026-07-28 — 商机存储文件夹可读命名 + 附件清理

- 文件夹 `OPP-xxx` → `客户名_OPP-xxx`（客户名变更自动重命名+同步路径）；迁移脚本 `migrate_opportunity_folders.py`（--dry-run）
- 修附件物理文件残留：存档区删除、永久删除报价单 Feed 附件时同步清磁盘文件

## [0.1.18] - 2026-07-28 — 料号库体验

- 分页（50/页）、批量导入/导出（解析预览标注新增/更新/无效）、响应式（侧栏可折叠/移动端覆盖层）、卡片去圆角
- 修卡片泛白（玻璃层嵌套叠加近纯白）；PN 可编辑（此前不可编辑是误判）

## [0.1.17] - 2026-07-27 — 工作台规格书 + 行级货币 + 推理流增强

- 工作台规格书预览（SpecSheet+打印 PDF，后端零改动）；KP 行级 RMB/USD（QuotationItem.currency，按币种联动重算）
- ⚠️ 修 USD 计价放大 ~9 倍（税率/汇率是字符串，`1+"0.13"="10.13"`，源头统一 Number()）
- 推理流：结构化 BOM 解析（`3.84T×4+960G×2` 按件独立计数）、per-机型 KP 套餐、预算驱动选件、underspend/超预算双向标注
- 料号库 description 拆 `spec_text`/`description`；系列枚举统一 `system_config.server_series` SSOT；推理流硬编码挪前端抽屉可配（机型套餐/数量格式/型号正则/underspend/select 策略）

## [0.1.16] - 2026-07-23 — 料号库/驾驶舱/主题

- 料号库机型系列筛选；背板回归普通配件（不再走 bp_tri_pn/bp_dc_pn 特殊字段）；驾驶舱自定义时间区间+图表粒度自适应；列表排序
- 修主题切换被浏览器扩展篡改（MutationObserver 守护+首屏预写主题）、L6 价格历史快照丢失（l6_repo 写错 schema）、序列未同步（`sync_sequences.py`）、料号编辑 500
- 服务器管理面接入玻璃视觉系统；文档：Frontend_Style_Guide 重写（Soft Glassmorphism）

## [0.1.15] - 2026-07-17 — 清理

- 修预览数据不完整（preview 接口缺 quotationId）；移除冗余 `confirmed_price`（统一 base_price+final_price）、item 冗余 model_name/server_model

## [0.1.14] - 2026-07-16 — 修导出模板编辑器边缘发灰（Dark 主题暗角装饰罩住全屏编辑器，z-index 提升）

## [0.1.13] - 2026-07-16 — 修导出模板 L6/KP 保修字段预览错位（动态绑定插行未同步静态绑定行号，改用行偏移表累加）

## [0.1.12] - 2026-07-16

> ⚠️ 破坏性：SQLite 四库 → 单一 PostgreSQL（schema 隔离 opportunities/kp/l6/rules/l6_history/public），必须跑迁移脚本，旧 SQLite 不再兼容；`DATABASE_URL` 环境变量替代硬编码路径。

## [0.1.11] - 2026-07-11 — 导出模板 + 文档

- 动态绑定自动保存（bindingForm 深度 watcher，修切 tab 绑定丢失）；新增 CLAUDE.md / Pricing_Engine.md / Excel_Parsing.md / Engineering_Guide.md + API 路由文档补全 119 端点

## [0.1.10] - 2026-07-09 — 硬编码清理

- 后端路径 `DATA_PATH` 环境变量；前端 14 组件 100+ 处色值改 `--cpq-*` CSS 变量；CORS 读环境变量；新增 docs/README.md、Deployment.md

## [0.1.9] - 2026-07-04 — 项目文件管理

- 拖拽多文件上传、新建项目自动建标准文件夹；修详情页路由白屏、文件列表加载失败（filename vs file_name 字段名不匹配）

## [0.1.8] - 2026-07-04 — L6 三栏对比 + 导出模板引擎

- L6 三栏对比（需求/匹配/定价）；导出模板引擎（`${xxx}` 变量 + `#for` 循环块）+ 卡片 CRUD + 所见即所得编辑器；配置页预览复刻 Excel 结构
- L6 匹配：主板降级、机箱模糊匹配；修匹配引擎空指针、导出合并单元格错位、Excel 空行渲染横线

## [0.1.7] - 2026-07-03 — 文件归档/评论

- 文件按项目自动归档+实时扫描+重命名/删除/上传/打开；项目评论（@提及/回复）；工作台侧边栏（文件列表+评论流）双栏
- ⚠️ 修文件下载路径穿越（路径白名单校验，拒绝 ../）

## [0.1.6] - 2026-07-03 — 质保独立计算

- 质保服务费 L6/KP 独立计算；质保年限自动识别（"质保3年"→3 年）；质保卡片重构

## [0.1.5] - 2026-07-03 — 质保可编辑 + 修复

- CPU 价格 0 警告；质保可编辑（年限/费率）；L6 匹配状态显示；价格失焦重算；修前端税率多乘 13%、综合毛利率口径不一致

## [0.1.4] - 2026-07-03 — 导出规则 + 评论

- 导出描述引擎：循环块、动态分类（按配件类别自动分组）、拖拽排序、智能展开（空行自动跳过）；工作台侧边栏评论流

## [0.1.3] - 2026-07-02 — L6 价格库

- 五维规格匹配筛选（机箱/机型/盘位/PSU/主板）；卡片网格重构；抽 `L6SpecFilter` 公共组件

## [0.1.2] - 2026-07-02 — L6 匹配规则可视化

- 规则可视化配置页（拖拽排序/降级开关/模糊规则/多结果手选）；L6 匹配引擎增强（主板降级、机箱模糊）；"基准价格"更名"KP价格库"

## [0.1.1] - 2026-07-01 — 四库分离 + 规则在线化

- kp/l6/rules/cpq_platform 四库分离；规则在线化（Excel 锚点/L6 维度/KP 映射/主板映射）；KP/L6 在线 CRUD+价格历史趋势图；回收站软删除；项目管理看板

## [0.1.0] - 2026-06-29

> ⚠️ 破坏性：从旧系统 0.2.5（Streamlit 单体）全面重写为 Vue3+FastAPI 前后端分离，数据不兼容。

- 智能上传（Excel 拖拽→自动解析→多配置拆分→入库）；报价工作台（实时精算/独立调价/财务三维联动）；五维匹配引擎；质保按需；WYSIWYG 导出
- 技术栈：Vue3+TS+Vite+AntD+Pinia / FastAPI+SQLAlchemy / SQLite×4（0.1.12 迁 PostgreSQL）
