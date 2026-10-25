---
name: opportunity-identity
description: "商机/报价标识语义 — opportunity_name 字段已移除,商机靠 customer_name 标识,报价单靠 quotation_id 唯一"
metadata: 
  node_type: memory
  type: project
  originSessionId: ab996efd-7394-43be-b643-dc843fe4f337
  modified: 2026-07-24T07:52:14.483Z
---

2026-07-24 用户定调,移除了 `opportunity_name` 字段(原详情页被标成"备注",实际被列表搜索/报价引擎/模板编辑器/Workspace 当核心名称用)。迁移:**109 条历史值已迁入活动流**(system 消息「（原备注迁移）X」),DB 列 + `rules.business_fields` 种子记录一并删除。

**Why:** 用户认为商机靠 customer_name 标识就够,不需要独立名称字段;报价单靠 quotation_id 唯一,不再需要 name fallback。

**How to apply:**
- 商机列表/搜索:走 customer_name / sales_person 等,别再引入 name 字段
- 报价单标识:只用 quotation_id,别加 fallback 到 name
- 报价引擎从上传 Excel 只提取 L6/KP 信息,不再提取「商机名称/Project Name」
- 详情页备注:统一走活动流(ActivityStream),不要在信息卡加回 name 字段

碰商机/报价标识、列表、搜索、导出、模板绑定时先看。关联 [[docs-code-drift]]。
