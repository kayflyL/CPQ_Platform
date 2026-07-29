-- 删除 opportunities.opportunities.folder_name 列
--
-- 背景:早期设计在商机创建时按 {日期}_{销售}_{机箱}_{平台}_{配置数}配置_{台数}台 生成业务命名文件夹,
-- folder_name 列存这个名字。文件归档已迁到 FeedAttachment + StorageAdapter(UUID key,不依赖业务字段),
-- folder_name 列 + 物理业务文件夹沦为死数据。代码侧已清理:
--   - opportunities.py 不再调用 generate/create_opportunity_folder,不再写 folder_name
--   - FileStorage 类已删除 generate_opportunity_folder_name / create_opportunity_folder 等死方法
--   - Opportunity model / OpportunityRepository 已移除 folder_name 字段
--   - 前端 types/opportunity.ts 已移除 folder_name
-- 本脚本仅 DROP 物理列(不可逆)。执行前确认无报表/外部系统读取该列。
-- 幂等:可重复执行。

ALTER TABLE opportunities.opportunities DROP COLUMN IF EXISTS folder_name;
