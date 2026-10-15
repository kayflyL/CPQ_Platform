-- 需求单内嵌附件：opportunity_attachments 加 requirement_version（线索登记附件与需求单版本绑定）
-- NULL=未归版：存量 lead_requirement 散件（降级合并显示，不迁移）+ 粘贴/上传时草稿尚未落库的文件。
-- 草稿提交仅翻状态版本号不变，绑定稳定；草稿删除时应用层解绑回 NULL（版本号 max+1 会被复用）。
-- 回滚（如需）：ALTER TABLE opportunities.opportunity_attachments DROP COLUMN requirement_version;

ALTER TABLE opportunities.opportunity_attachments ADD COLUMN IF NOT EXISTS requirement_version INTEGER;
