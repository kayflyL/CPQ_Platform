---
name: admin-card-pattern
description: "管理面同类实体(基准配置/BOM模板/料号库/机型)都用\"独立列表卡片+编辑modal\"模式,不要把一个实体的管理UI嵌进另一个实体的编辑流程"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: a7ba733e-76fa-4a34-8047-f1533193865f
  modified: 2026-09-17T16:24:47.168Z
---

CPQ 管理面(`/servers` admin tab)里同类可管理实体——基准配置、BOM 模板、料号库、机型管理——都用**一致的模式**:一张独立 `.panel` 卡片(列表表格 + 新建/编辑/删除按钮) + 点编辑弹 modal。实体之间通过下拉/外键关联,**不要把一个实体的管理 UI 嵌进另一个实体的编辑 modal 里**。

**Why:** 用户原话——"BOM模板和基准配置一样,基准配置不是有个表里面有很多配置吗,用户可以新增,BOM模板放到这个基准配置表,注意是列表下面做一个卡片,不是让你把他放到基准配置编辑页的下面"。上轮误把 BomTemplateEditor 塞进基准配置编辑 modal(L133),被纠正挪成独立卡片(BomTemplateManager)挂在基准配置列表下方。

**How to apply:** 新增任何 admin 可管理实体时,默认做成独立 `.panel` 卡片(参考 `BaseConfigBuilder.vue`/`BomTemplateManager.vue`/`PartsLibrary.vue` 结构:lib-head 标题+新建 / a-table 列表 / a-modal 编辑),挂在对应 admin tab 下;实体间关联用下拉(如基准配置选 BOM 模板 = `a-select`,绑 `bom_template_id`)。别把管理 UI 嵌进别的编辑流程。Related: [[l6-chassis-legacy-flow]]

**例外(2026-07-22 起,2026-07-23 调整):** 基准配置的「编辑」环节破例做成**全页双面板**(`views/server-admin/BaseConfigEditorPage.vue`,路由 `/servers/base-configs/:id`),不走 modal。最初(07-22)右栏做了一套 5 区 SVG 机箱预览 + 缺料 warn-card + 推导 derived-card,理由是「完整性引导」。**07-23 用户判定那套预览鸡肋,整块砍掉**(连同 ChassisPreview.vue 组件文件、categoryZone/missingByZone/derived 等计算逻辑),右栏现在只留一个轻量 `summary-card`(料件数/合计/估算功耗)。即:全页双面板形态保留,但右栏已退化为纯摘要侧栏,不再有 anatomy/缺料检测。注意:列表管理仍是独立卡片。**教训:别再给这个编辑器加 SVG 预览或缺料高亮——用户已否过一次**;缺料检测若要做应放别处(如报价时)。

**2026-09-18 空间重构定调(用户确认两选):** ①左栏 10 个解剖分组卡**默认全收起**,折叠模式学商机详情中部栏(整头可点+chevron+`grid-template-rows 1fr→0fr` 动画),**头部即摘要**——②前面板=线缆✓/–、③后面板=每槽规格签名、⑤=CPU数/TDP、⑥=条数/通道/速率、⑦=电源槽+默认型号+档位、⑨=GPU槽/架构、其余=件数+合计价(`sectionSummary`),组标签行带全部展开/收起;②基准信息卡头可折叠+收起时头部内联摘要,BOM 模板并进首行字段行。通用件行**单行化**(选择器+规格170px截断+单价+数量内联一行)。**铁律:②前面板/③后面板/⑦供电的卡内内容 UI 是用户专门设计的,只动外壳不动内容**。Related: [[bom-template-skeleton-redesign]]
