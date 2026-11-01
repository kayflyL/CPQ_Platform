-- 服务器3D模型管理表(2026-11-01):参数化3D配置台的模型登记
-- 名称可改;model_id 关联 l6.server_models(像图纸那样绑机型):绑定即上架(配置页中部显示该3D场景),
-- 解绑即隐藏——无独立上下架状态。layout_config 为前端不透明JSON(布局覆盖),后端整存整取。
-- 首条种子「4U8卡服务器模型」按用户指定命名,并预绑 ESA240 V3(如存在),绑定可随时在管理面修改。
CREATE TABLE IF NOT EXISTS l6.server_3d_models (
    id            SERIAL PRIMARY KEY,
    name          VARCHAR NOT NULL DEFAULT '',
    model_id      INTEGER REFERENCES l6.server_models(id) ON DELETE SET NULL,
    layout_config TEXT,
    created_at    VARCHAR,
    updated_at    VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_server_3d_models_model_id ON l6.server_3d_models(model_id);

INSERT INTO l6.server_3d_models (name, model_id, created_at, updated_at)
SELECT '4U8卡服务器模型',
       (SELECT id FROM l6.server_models WHERE name = 'ESA240 V3' ORDER BY id LIMIT 1),
       to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
       to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
WHERE NOT EXISTS (SELECT 1 FROM l6.server_3d_models WHERE name = '4U8卡服务器模型');
