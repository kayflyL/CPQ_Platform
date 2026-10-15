-- 报价行价时点锚：quotation_items 加 price_set_at（TEXT，ISO 时间）。
-- base_price 最近一次被人为改动（手填/同步/采纳）的时点；与配件库最新价日期比新旧，
-- 决定 KP 行亮「同步价格」还是「采纳库价」。NULL=从未单独改价，回落单据 exported_at/created_at。
-- boot 自愈见 app/core/startup.py::ensure_quotation_item_price_set_at（幂等，本文件供手工对齐）。
ALTER TABLE opportunities.quotation_items ADD COLUMN IF NOT EXISTS price_set_at TEXT;
