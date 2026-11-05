-- 2026-11-05 线索交付地区列：opportunities.opportunity_leads 加 delivery_region（VARCHAR 40）。
-- 用途：/lead 公开登记表采集交付地区（国内到省 / 海外按大洲选国 / 不在列表中），
-- 取值形如 国内-广东 / 海外-日本 / 海外-不在列表中；线索转化时原样写入商机
-- extra_fields.delivery_region（权威字段，分价引擎按关键词分桶 已兼容该取值形态）。
-- boot 自愈见 app/core/startup.py ensure_lead_delivery_region。存量行默认 ''（空=未采集）。

ALTER TABLE opportunities.opportunity_leads
  ADD COLUMN IF NOT EXISTS delivery_region VARCHAR(40) DEFAULT '';
