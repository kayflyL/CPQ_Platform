-- 旧文件系统表清理(代码层已迁移到 FeedAttachment / opportunities.opportunity_attachments)
--
-- 执行前提:
--   - /files/* 扫盘 API 已从 opportunities.py 移除
--   - OpportunityFile model + OpportunityFileRepository 已删除
--   - 保存流程不再写本表
-- 本脚本仅 DROP 物理表(不可逆)。历史归档若已无价值再执行;否则保留为死数据无副作用。
-- 幂等:可重复执行。

DROP TABLE IF EXISTS opportunities.opportunity_files;
