---
name: quote-price-direction
description: "报价工作台KP行价方向感知——price_set_at锚点vs库价日期,分流「同步价格/采纳库价」;碰报价比价/同步/采纳先看"
metadata:
  node_type: memory
  type: project
  originSessionId: 9a381e47-a2f0-4a0a-969c-e344745b5ca1
  modified: 2026-10-09T08:48:24.024Z
---

报价工作台 KP 行与配件库价不一致时按「谁更新」分流(2026-10-09 落地,治旧单解冻后旧价误导回写库盖新价):

- **判定**:`quoteCommon.kpPriceAction(item, anchorIso)`(取代已删的 kpSyncable)。锚点=行级 `price_set_at` → 单据 `exported_at`(解冻后为空)→ `created_at`;库侧日期= `getKpHistory` 首条 `date`。库价新→「采纳库价」;行新/日期判不了→「同步价格」(保守回退);库无件→「入库新配件」。
- **锚点落库**:`quotation_items.price_set_at` 列;`quotation_repo._stamp_price_set_at`(纯函数,有单测 test_price_set_at_stamp.py)在 `save_items` 全删全插前逐行 diff base_price——变了盖 now、没变沿用旧锚、新行盖 now;`patch_items`(门户)改 KP 价同样盖;复制报价单克隆时随价走。
- **前端**:改价/同步/采纳即时盖 `price_set_at=nowIso()`(本地时间,非 UTC);`refreshKpDbPrices` 顺手存 `db_price_date`;差异状态文案拆「⏬ 库价已更新 / 📈 行价新」。
- **闭环**:同步后同单同型号旧行锚点早于今天→自动转亮「采纳库价」;采纳=库价经 calcUnitCost+rmbToBasePrice 折算回填,不写库;同步弹窗有「改用库价」逃生门,采纳弹窗可勾选一并采纳同型号 N 行。
- **边界**:同日/缺日期判不了方向→保守给同步;成本表 CostSheetWorkbench 的「获取最新价格」是显式批量库→行,方向天生正确,未纳入此机制,换算共用 quoteCommon。

关联 [[quote-kp-row-price-edit]] [[opportunity-identity]]
