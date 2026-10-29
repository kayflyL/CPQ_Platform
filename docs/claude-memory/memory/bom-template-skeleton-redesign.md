---
name: bom-template-skeleton-redesign
description: "09-15定调:BOM模板=纯骨架(type/label/slot/mode),取值语义=行类型固定属性TYPE_RULES(前后端镜像),逐行规则DSL已退役;碰BOM模板/左栏L6生成前先看"
metadata: 
  node_type: memory
  type: project
  originSessionId: 699fe594-bf22-4bed-b2bf-382d8c7e4540
  modified: 2026-09-19T06:48:26.232Z
---

BOM 模板（设置-服务器管理-基准配置）2026-09-15 三轮收敛定稿：

- **数据模型**：`l6.bom_templates.rows` = 骨架（type/label/slot/mode）+ **可选 `rule`**（逐行完整覆盖类型默认：省略=跟随 TYPE_RULES 零配置即合理；填了=完全按行规则求值）。编辑页点「取值方式」→「自定义这行」从类型默认拷贝起步可改任何来源/兜底，一键「恢复类型默认」清 rule。
- **引擎**：`ruleForRow`/`_rule_for_row` 逐行 rule 优先，然后类型默认（TYPE_RULES 前后端镜像 + OCP 槽未选→整行隐藏 + fan 兜底数量按 form 2U=6/4U=12）。
- **透明度机制 09-19 三次改版=可读行内 v3（重要演化）**：v2 行内直编表（09-18，描述/数量列常驻 8-10 个控件）被用户判「整个非常凌乱」打回。v3：取值方式列每行**一句可读文字**（`srcLabel` 翻人话，FAN 行=`料号字段[fan]·name｜数量 跟[fan]件数｜兜底 固定 系统风扇 / 固定 6`；cable 行=`SATA 每8盘1组 · SAS 每8盘1组 · NVMe 每2盘1组｜恒 1 组｜9361 SATA cable*1、NVMe cable*2`，示例直接跑 `cableSegments` 同口径实算），零点击见全部生效值；点行内文字（尾 ✎）展开 `.tr-edit` 编辑面板（`editUid` 单开，描述/数量并排，cable 通栏三件套）。**机制自 v2 起不变**：显示读生效规则（srcAt→ruleForRow），任一格改动才物化整条 rule（touch），物化后与类型默认 JSON 深度相等即自动撤销（commit）——改回默认=自动解除自定义。自定义行左蓝边+操作列↺；添加行=表格尾行「＋选类型」。**演化全史**：深奥链路文字→人话化→删→按钮直达弹层→行内直编表→可读行内 v3；**核心教训（两条）**：①透明度最终形态=值常驻可见，不是说明文字/弹层；②「不需二次点击」指的是**看值**零点击——编辑控件按需展开即可，控件常驻=凌乱（v2 翻车根因）。预览只标异常胶囊（兜底/留空）。
- **Cable 行专属算法（09-17 用户定调）**：单行汇总、qty 恒 1（线缆整体一组），描述按盘型分段写组数——⌈盘数/分组⌉，默认 SATA/SAS 8 盘 1 组带 RAID 型号前缀（`9361 SATA cable*4`，无 RAID 去前缀）、NVMe 2 盘 1 组直接写；模板占位符 `${raid_model}/${n}/${count}`+分组大小逐类可配（弹层是 cable 专属三件套，非通用规则链）。求值 `cableSegments`/`_cable_segments`（前后端镜像），变量 raid_model/sata_count/sas_count（报价页 Workspace.kpSummaryFor 提取）；没盘整行隐藏；旧 cableDescFrom/front_cables 兜底已删。**教训：通用规则编辑器对有专属业务算法的行（cable）=凌乱且对不上，此类行走类型专属 rule 形状（cable_groups）+专属编辑 UI**。
- **模板拼装行编辑增强（09-17 方案A，用户在 A/B 两案中选 A）**：前置背板这类单模板行不做专属规则形状，走通用编辑增强——默认弹层加实时示例（demoVars 渲染）+`${bp_type_desc}` 来源说明（跟盘走 NVMe→三模）；自定义态「＋变量」中文下拉点选插入占位符+示例随输入实时变（缺变量显 ？）。纯编辑器 UI（BomTemplateManager tplExample/insertTplVar/VAR_MENU），引擎/后端零改动。**选型逻辑：只有单一模板、无结构化参数可拆的行走 A；有真实业务参数（分组大小/盘尺寸映射）才值得 B（专属形状）**。
- **三轮教训（重要）**：①嫌"复杂"嫌的是呈现（规则摘要常驻+四行展开编辑器），不是能力——把能力砍成纯骨架被用户连续两轮打回（"完全没法配置=硬编码"，连白名单常量覆盖 ov 都不够）；②终稿=能力回到旧版完整规则+呈现做减法（默认零配置、编辑收进弹层）；③改配置能力前先问用户具体场景，别拿"从未有人用过"当砍功能的依据。
- **How to apply**：改类型默认取值 → TYPE_RULES（前后端同步）；开放新来源种类 → DESC_KINDS/QTY_KINDS（前端弹层）+ describeSrc + 引擎 tryDesc/tryQty（前后端）；存量模板全是骨架，新增自定义走编辑页即可，无迁移。相关：[[skill-tree-trunk-architecture]]、[[no-patch-on-patch]]。

风扇事故背景（同日修）：分级匹配 `findBomPart`/`_find_part` ①category 精确/子串/别名 ②name 子串仅兜底——防「风扇背板转接线」（name 含"风扇"）蹭进 FAN 行；别名表 `system_config.bom_category_aliases` 可配。
