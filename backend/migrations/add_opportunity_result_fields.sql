-- D1 商机结果与复盘字段（蓝图 A1-A2 / 数据底座）
-- 新增 5 列：industry / customer_type / result / win_reason / lost_reason
-- result 与 status 正交：status=数据生命周期(active/archived/deleted)，result=业务结果(pending/won/lost)
-- 对应 model: backend/app/models/opportunity.py

ALTER TABLE opportunities.opportunities
    ADD COLUMN IF NOT EXISTS industry       VARCHAR,
    ADD COLUMN IF NOT EXISTS customer_type  VARCHAR,
    ADD COLUMN IF NOT EXISTS result         VARCHAR DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS win_reason     TEXT,
    ADD COLUMN IF NOT EXISTS lost_reason    TEXT;

-- 回填历史行：result 为 NULL 的统一置为 pending
UPDATE opportunities.opportunities
SET result = 'pending'
WHERE result IS NULL;
