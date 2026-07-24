-- 清理 confirmed_price 字段
-- 该字段是历史遗留的冗余字段，实际业务只使用 base_price 和 final_price

BEGIN;

-- 1. 删除 opportunities.opportunity_items 表的 confirmed_price 列
ALTER TABLE opportunities.opportunity_items DROP COLUMN IF EXISTS confirmed_price;

-- 2. 验证删除成功
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_schema = 'opportunities' 
        AND table_name = 'opportunity_items' 
        AND column_name = 'confirmed_price'
    ) THEN
        RAISE NOTICE '✓ confirmed_price 列已成功删除';
    ELSE
        RAISE EXCEPTION '✗ confirmed_price 列删除失败';
    END IF;
END $$;

COMMIT;
