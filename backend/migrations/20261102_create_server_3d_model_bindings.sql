-- 服务器3D模型 × 机型 绑定关系表(2026-11-01):一个3D模型可绑定多台服务器产品机型。
-- 绑定即上架:机型在 bindings 里即配置页显示该3D场景,移除即隐藏(无独立上下架状态)。
-- 迁移:server_3d_models.model_id 单值绑定 → 绑定表,随后删除单值列。
CREATE TABLE IF NOT EXISTS l6.server_3d_model_bindings (
    model_3d_id INTEGER NOT NULL REFERENCES l6.server_3d_models(id) ON DELETE CASCADE,
    model_id    INTEGER NOT NULL REFERENCES l6.server_models(id) ON DELETE CASCADE,
    PRIMARY KEY (model_3d_id, model_id)
);
CREATE INDEX IF NOT EXISTS idx_s3d_bindings_model_id ON l6.server_3d_model_bindings(model_id);

INSERT INTO l6.server_3d_model_bindings (model_3d_id, model_id)
SELECT id, model_id FROM l6.server_3d_models
WHERE model_id IS NOT NULL
ON CONFLICT DO NOTHING;

ALTER TABLE l6.server_3d_models DROP COLUMN IF EXISTS model_id;
