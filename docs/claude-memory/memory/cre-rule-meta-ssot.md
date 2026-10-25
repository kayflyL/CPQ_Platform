---
name: cre-rule-meta-ssot
description: CRE 选型规则元数据(label/色/符号/字段/文案)的 SSOT 位置；碰规则编辑器/拓扑图别再硬编码
metadata: 
  node_type: memory
  type: project
  originSessionId: 4d154b82-9bd9-4419-b4a8-49bb8f52e5a9
  modified: 2026-08-02T08:03:35.445Z
---

CRE 选型规则的所有展示元数据集中在 `frontend/src/constants/ruleMeta.ts`，是选型规则编辑器([CompatibilityRuleEditor.vue](frontend/src/views/admin/CompatibilityRuleEditor.vue)) 与规则拓扑图([CompatibilityImpactGraph.vue](frontend/src/views/admin/CompatibilityImpactGraph.vue) + [ImpactNode.vue](frontend/src/views/admin/ImpactNode.vue)) 共用的唯一真相源。

导出：`RULE_TYPE_DEFS/RULE_TYPE_MAP`(类型→label+cssVar+hex)、`RULE_OP_DEFS/RULE_OP_MAP`(操作符→符号)、`CONFIG_FIELD_LABEL/OPP_FIELD_LABEL/ctxFieldLabel`(CRE ctx 字段中文)、`RULE_GRAPH_TEXT`(拓扑/卡片展示文案与符号)、`excludeText()`、`ALERT_SEVERITY_DEFS/alertIcon/isBlockingSeverity`(告警 severity 图标/标签/是否阻断)、`RULE_CATEGORY_SEED/RULE_CATEGORY_COLOR/CATEGORY_PALETTE/categoryColor`(规则业务分类 category 配色——seed 语义色 + 马卡龙调色板按名稳定散列取色)。

**Why:** 用户定调「尽量消灭一切硬编码，包括展示的字」——之前类型/操作符/字段中文、类型色值散落在 editor 与 graph 各一套裸字面（editor 用 CSS var、graph 用 hex 还对不上），改名/换主题会漂移。

**How to apply:** 碰这三个组件里规则类型名、操作符符号、config/opportunity 字段中文、拓扑展示文案（总是生效/满足任一/向上取整/候选机型/不混搭/条件/结果/空状态等）、告警 severity 图标、**业务分类(category) 的色值**，一律从 ruleMeta 取，别再裸写中文字面或新造映射表。config.* 是 CRE 引擎上下文字段，不属于商机字段表(见 [[canonical-field-labels]])也不属于料号 spec 字段族([[parts-section-taxonomy]])，故在此独立维护。VueFlow edge.style.stroke 需真实色值——用 RULE_TYPE_MAP[x].hex（非 cssVar）。纯渲染装饰(中性灰虚线连接、白标签底)除外。
