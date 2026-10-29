---
name: parts-vs-kp-distinction
description: 料号库(PartsLibrary)与KP配件库(Parts.vue)是两套独立系统，别混淆
metadata: 
  node_type: memory
  type: project
  originSessionId: 826d0898-962c-4196-9600-057b54c26c6c
  modified: 2026-07-28T07:38:30.340Z
---

**关键区分（用户多次纠正）：**

| 系统 | 前端页面 | 数据表 | 后端 API | 内容 |
|------|----------|--------|----------|------|
| **料号库** | `components/server-admin/PartsLibrary.vue` | `l6.parts_master` | `/api/parts` → PartsMasterRepository | L6机箱件：机箱/主板/散热/背板/电源/Riser/线缆 |
| **KP配件库** | `views/admin/Parts.vue` | `kp.kp_parts` | `/api/admin/kp/parts` → KPRepository | KP部件：CPU/GPU/内存/硬盘/网卡/NVSwitch |

**用户定调（见 [[kp-parts-unification-roadmap]]）：两张表分开管理，不合并。**

**常见错误：**
- 把料号库问题查成 KP 配件库（查错 API/表/文件）
- 混淆 `pn` 字段：料号库用 `pn`，KP 库用 `oem_sku`

**How to apply:**
- 用户说"料号库"→ PartsLibrary + `l6.parts_master` + `/api/parts`
- 用户说"KP配件"或"配件库"→ Parts.vue + `kp.kp_parts` + `/api/admin/kp/parts`
- 碰到任何"配件/料号"相关 bug，先确认是哪个系统

相关：[[parts-section-taxonomy]]、[[kp-parts-unification-roadmap]]