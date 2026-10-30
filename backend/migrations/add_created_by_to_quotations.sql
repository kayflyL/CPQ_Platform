-- 报价单创建人：opportunities.quotations 加 created_by（TEXT，创建者姓名，与 flow_cards.created_by 同口径）。
-- 报价单列表「创建人 / 时间」列展示；存量行为 NULL，前端回落 '—'。
-- 创建链路打点见 quotation_repo.create（created_by 参数，四个创建入口均已传入）。
-- boot 自愈见 app/core/startup.py::ensure_quotation_created_by（幂等，本文件供手工对齐）。
ALTER TABLE opportunities.quotations ADD COLUMN IF NOT EXISTS created_by TEXT;
