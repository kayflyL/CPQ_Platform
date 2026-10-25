---
name: excel-l6-reference-bom-excel-rows
description: Excel 模式 L6 仅作参考（存 config_l6_picks.bom_excel_rows，不进 items）；上传路径必须填 bom_excel_rows，否则左栏+规格书丢 L6
metadata: 
  node_type: memory
  type: project
  originSessionId: 6c5e52d0-27f0-44e2-9f3e-ae48d65c1089
  modified: 2026-07-29T11:46:32.098Z
---

Excel 上传报价单里，L6 区域是「仅参考、不计价」的：L6 行**不进 quotation_items**（这避免了规格书导出时 L6 显示两遍），而是存进 `config_l6_picks[cfg].bom_excel_rows`，左栏 BomTable 和规格书导出都从这里读（同源、靠 preview_data_loader 的 `covered_cfgs` 判定去重）。

**Why:** 历史 commit `848fead`（"L6 报价链路修复：excel 参考化"）本意是「左栏与导出同源 bom_excel_rows」，但只做了一半——把 L6 从 items 里移除了（pricing_engine `_parse_items`/`_convert_parser_items` 的 "L6 region - SKIPPED" 注释），却没在上传路径填 bom_excel_rows。结果：直接上传生成的报价单左栏 BOM 参考里 L6 整段消失（KP 还在，因为 KP 仍在 items 里、前端用 items 兜底）。规格书导出也悄无声息丢了 L6。

**How to apply:**
- 上传路径 `quote.upload_to_opportunity` 必须持久化 `config_l6_picks={cfg:{bom_source:'excel', bom_excel_rows: l6_rows + kp_rows}}`（形如 `candidate_search.build_plan`）。L6 行由 pricing_engine `_parse_l6_rows` 从 L6 区域提取（起"L6"→止"Keyparts,KP"，读 D/E/F 列）。
- 前端 BomTable excel 模式只读 `cfg.bom_excel_rows`；loadData 的兜底是 `processedItems.filter(L6/整机/KeyParts)`——items 不含 L6，所以兜底救不了 L6，必须后端填 bom_excel_rows。
- 改上传/解析/L6 流程时，确认 bom_excel_rows 仍被填上，别再只删不补。旧数据（本修复前上传的报价单）config_l6_picks 为空，需重新上传才能恢复 L6 参考。
- **列错位修复（2026-07-29）**：不同 Excel 模板的 L6/KP 列偏移不同——Lena 模板数据在 C/D/E，LLW/自研 在 D/E/F，而区域配置(parse_field_rules / l6_region_config)写死 D/E/F。`_parse_l6_rows` 改成**按表头行标签定位列**（Catalogue/Description/Quantity，以 Quantity 标签为锚，无表头回落配置列），对三种模板都正确。KP(`_convert_parser_items`/`_parse_items`)有**同样的列错位 bug 未修**（KP 的 category/model/qty/price 全错位），用户尚未要求修 KP，碰前确认。
- 与 [[kp-parts-unification-roadmap]]、[[rear-panel-unified-to-parts-master]] 相关（都是 L6/配件体系）。
