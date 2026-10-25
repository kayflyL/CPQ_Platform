---
name: quote-kp-row-price-edit
description: 报价工作台 KP 行原始单价 09-29 开放行内手改；编辑口径=RMB含税所见即所改，USD行反解；此前0价行四路全死
metadata:
  node_type: memory
  type: project
  originSessionId: b1343b1c-0083-4969-afe3-469b25f8a733
  modified: 2026-09-29T07:26:41.393Z
---

2026-09-29 修通报价工作台 KP 行「原始单价」行内手改（此前 0 价行四路全死：单元格只读、利润率乘 0 仍 0、同步弹窗拒开"价格为空"、历史弹窗只改库价不动行）。

**口径定调（改价格编辑前先看）**：
- 原始单价列显示与编辑统一为 **RMB 含税价，所见即所改**；USD 行经 `quoteCommon.rmbToBasePrice` 反解回原币种 `base_price`（÷汇率÷(1+税率)，不取整防回显漂移）。全工作台只显示人民币的既定约定不破。
- 手改后 `computeKpMatch` 重算（❌ 缺失→🆕 新部件），同步/入库按钮自动恢复，补的价可顺手入库——修价与入库是两条独立路径，不强制联动。
- 改动面=Excel 模式 KP 表（Workspace.vue kpExcelRows 表格）+ 新建模式 KP 卡（KpCategoryCard quoteMode）；无 `field.quote.price` 权限显 `***`（后端 mask_price_fields 本就把 base_price 置 None）。

相关：[[quote-export-reveal]]、[[price-access-role-control]]、[[excel-parse-rules-header-anchor]]（解析时点是另一个补价窗口）
