-- 服务器管理页改造 · 阶段一 Step 2（🔴 破坏性，手动执行）
-- 机型不再自维护 form/bays，改为从关联的基准配置（l6.base_configs）继承。
--
-- 执行顺序（必须按步，每步确认后再下一步）：
--
-- 【1】前置空值检查 —— 必须先跑，确认 0 条空值再继续。
--     SELECT id, name FROM l6.server_models WHERE base_config_id IS NULL;
--     有人工补全或清理这些机型，否则下一步 SET NOT NULL 会直接失败。
--
-- 【2】收紧 base_config_id 约束（确认上面返回 0 行后执行）。
ALTER TABLE l6.server_models
    ALTER COLUMN base_config_id SET NOT NULL;

-- 【3】删除冗余列（机型形态/盘位改由 base_config JOIN 提供）。
ALTER TABLE l6.server_models
    DROP COLUMN IF EXISTS form,
    DROP COLUMN IF EXISTS bays;

-- 回滚（仅在上线失败、需回退 schema 时；数据不可恢复，务必先备份）：
-- ALTER TABLE l6.server_models ADD COLUMN form VARCHAR(20);
-- ALTER TABLE l6.server_models ADD COLUMN bays INTEGER;
-- ALTER TABLE l6.server_models ALTER COLUMN base_config_id DROP NOT NULL;
