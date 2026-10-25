---
name: parts-section-taxonomy
description: 料号库三级分类，大类/STEP 由 l6.part_taxonomy 用户可管理(增/改名/删·改名批量传播)；子类开放；section(STEP)语义未变故报价流零改动
metadata:
  node_type: memory
  type: project
  originSessionId: 6d38b75b-2448-4f30-8b7d-05b100fc75e6
  modified: 2026-08-01T16:00:21.994Z
---

料号库 `l6.parts_master` 分类三级（2026-08 按「服务器机箱料号专业分类表」重构）：

- **一级 `major_category`（大类）**：PartsLibrary 左栏主导航。**用户可增/改名/删**，定义在 `l6.part_taxonomy(kind='major',name,sort_order)`。
- **二级 `category`（子类，23）**：机箱主体/主板/PCIe Riser卡/电源模块/高速存储信号线… 大类内 chips，**开放自由输入**（auto-complete，可加新子类）。
- **快速筛选 `section`（STEP，4）**：基准件/前面板件/后面板件/电源件，对应报价表 STEP1~4。**用户可增/改名/删**，定义在 `l6.part_taxonomy(kind='step')`。左栏「STEP 筛选」组。

**分类管理 SSOT = `l6.part_taxonomy`**（不是前端常量，旧的 `constants/partSections.ts` 已删）。改名/删除由后端批量传播到 parts_master：
- `rename_taxonomy(kind,old,new)`：`UPDATE parts_master SET major_category/section=new WHERE =old` + 更新 taxonomy 表。
- `delete_taxonomy(kind,name)`：被料号使用时**拒绝**（需先迁移），否则删 taxonomy 行。
- `list_taxonomy(kind)`：读 taxonomy 有序列表 + LEFT JOIN parts 计数/子类；`major_categories()`/`sections()` 是其兼容包装。
- API：`/api/parts/taxonomy`(GET/POST)、`/taxonomy/rename`(PUT)、`/taxonomy`(DELETE)。前端 `partsApi.taxonomy.{add,rename,remove}`。
- 前端管理 UI：PartsLibrary 左栏每项 hover 出 ✎改名/✕删除 + 分组头「+」新增。

**关键：section(STEP) 语义未变**，报价配置流（L6ChassisConfig/Workspace）按 `section` 取料的逻辑一行没动（取料按 category+section 精筛，高速存储信号线/电源分配线缆等横跨多 STEP 的子类要带 section 缩到具体 STEP）。新增 major_category 列 + part_taxonomy 只是叠加维度。

**别再加闭集校验/固定常量锁大类·STEP** —— 用户定调要可增改删（曾一度误解成锁定，已回滚；那条路别走）。

相关：[[parts-vs-kp-distinction]]、[[ocp-is-networking-not-pcie]]、[[canonical-field-labels]]。
