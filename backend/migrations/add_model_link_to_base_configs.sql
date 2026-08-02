-- 机型↔基准配置 改为一对多：base_configs 增加 model_id 反向关联 + config_content 配置级介绍。
--
-- 现状：server_models.base_config_id 单值（NOT NULL，保留作「主/默认配置」不变）。
-- 本迁移在 base_configs 侧加 model_id，让一个机型可关联多个基准配置（配置变体）；
-- config_content 是轻量配置级介绍 JSONB {description?, spec_diff?}，后端按不透明 JSON 透传
-- （与 product_content 同模式）。
--
-- 反向回填：仅把「已被机型通过 base_config_id 挂载」的配置写上 model_id——纯数据派生，
-- 零业务名硬编码（无 Orion/Polaris 等字样）。其余孤儿配置保持 model_id NULL，
-- 由用户在机型编辑页手动归属（可随时改）。
--
-- 外键 ON DELETE SET NULL：删机型时其下配置变回孤儿，不阻塞删除。
-- 幂等：可重复执行（ADD COLUMN IF NOT EXISTS；回填 WHERE model_id IS NULL）。
-- 回滚：ALTER TABLE l6.base_configs DROP COLUMN model_id, DROP COLUMN config_content;

ALTER TABLE l6.base_configs
    ADD COLUMN IF NOT EXISTS model_id INTEGER REFERENCES l6.server_models(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS config_content JSONB;

-- base_config_id 允许空：新建机型可先无主配置，保存后关联配置变体再设主（去掉旧 NOT NULL）
ALTER TABLE l6.server_models ALTER COLUMN base_config_id DROP NOT NULL;

-- 反向回填（仅当前机型挂载的；孤儿不动）
UPDATE l6.base_configs bc
SET model_id = (SELECT id FROM l6.server_models sm WHERE sm.base_config_id = bc.id)
WHERE bc.model_id IS NULL
  AND EXISTS (SELECT 1 FROM l6.server_models sm WHERE sm.base_config_id = bc.id);

CREATE INDEX IF NOT EXISTS idx_base_configs_model_id ON l6.base_configs(model_id);

COMMENT ON COLUMN l6.base_configs.model_id IS '所属机型（一对多反向关联）；NULL=孤儿配置待归属，机型编辑页管理';
COMMENT ON COLUMN l6.base_configs.config_content IS '配置级介绍 JSONB {description?, spec_diff?}，不透明透传';
