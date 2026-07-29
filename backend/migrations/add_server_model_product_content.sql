-- 机型管理页产品化包装升级
-- 为 l6.server_models 增加产品内容字段（JSONB）：结构化分块承载产品介绍/参数
-- （概述 / 核心特性 / 技术参数 / 应用场景）。
-- 后端按不透明 JSON 透传（与 template_json 同模式），前端定义结构、加减分块无需改后端/迁移。

ALTER TABLE l6.server_models
    ADD COLUMN IF NOT EXISTS product_content JSONB;
