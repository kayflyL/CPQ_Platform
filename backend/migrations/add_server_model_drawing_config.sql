-- 服务器可视化图纸配置：为 l6.server_models 增加 JSONB 字段
-- 结构（前端定义，后端不透明透传）：
-- {
--   "views": {
--     "top":  { "svg_url": "...", "viewBox": [0,0,411,739], "regions": [{uid,name,region_type,x,y,width,height,remark}] },
--     "front": null,
--     "rear":  null
--   }
-- }
-- 回滚：ALTER TABLE l6.server_models DROP COLUMN drawing_config;
ALTER TABLE l6.server_models
    ADD COLUMN IF NOT EXISTS drawing_config JSONB;
