---
name: node-card-single-header
description: 商机流程节点卡=单层卡头铁律：操作按钮上移到 OpportunityProcessBoard 卡头，工作区组件不准自带标题头
metadata: 
  node_type: memory
  type: project
  originSessionId: 3e25167f-09dd-43ff-bdd4-cf7236d62b0c
  modified: 2026-09-20T02:34:16.129Z
---

2026-09-20 定调：商机流程节点卡（线索登记/方案配置/成本核算/报价）卡头=唯一标题层，
结构 = `.card-shell-head`/`.rw-head`（图标+眉题+标题 | `.card-shell-actions`/`.rw-head-actions` 操作区（@click.stop）+ 折叠箭头收在操作区尾部）。

**Why:** 曾经工作区组件（BomSchemeWorkbench/CostSheetWorkbench）自带「方案配置/BOM 方案工作区」二层头，
与外层节点卡头背靠背重复（成本核算一次卡里出现三遍同词）；用户点名后合并为单层。

**How to apply:** 给节点卡加操作按钮→加在 OpportunityProcessBoard 的卡头操作区，别在工作区组件里造头；
新建类按钮经工作区 `defineExpose({ openNew })` + 模板 ref 远调（BomSchemeWorkbench/CostSheetWorkbench 均已暴露）。
空态铁律：RecordTable 的 `:empty` 必须把插槽里所有条件渲染的占位行算进去（pendingRequirements/pendingBomSchemes 曾漏算导致「有行还喊尚无」自相矛盾）。
占位行禁止把流程提示塞进数据列。关联 [[portal-flow-perms-audit]] [[admin-card-pattern]]。
