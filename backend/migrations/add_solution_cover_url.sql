-- 解决方案卡片封面(2026-11-03):可选项,空则前端按场景色自动生成封面
ALTER TABLE rules.solutions ADD COLUMN IF NOT EXISTS cover_url VARCHAR(255) DEFAULT NULL;
