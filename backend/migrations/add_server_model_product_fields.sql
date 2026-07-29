-- 服务器管理页改造 · 阶段一 Step 1
-- 为 l6.server_models 增加产品级字段：简介 / 主图 / 生命周期状态
-- 机型从「薄目录表」向「产品实体」演进，避免「加了列无人写」的死字段（管理面同步上 UI）。
--
-- 注意：PostgreSQL 的 ADD COLUMN 每子句只接一列，多列必须重复 ADD COLUMN。

ALTER TABLE l6.server_models
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS image_url TEXT,
    ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(20) DEFAULT 'active';

-- 修正历史脏数据：未显式赋值的机型回填为 active（DEFAULT 已对新行生效，此句兜底旧行）。
UPDATE l6.server_models
SET lifecycle_status = 'active'
WHERE lifecycle_status IS NULL;
