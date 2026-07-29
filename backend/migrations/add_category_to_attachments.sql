-- 为 opportunity_attachments 表添加 category 列（存档区业务语义分类）
-- category: requirement（客户需求文档）| technical（技术方案/BOM）| sent_quote（已发报价）| NULL（未分类）
-- 与 kind 正交：kind 描述来源（upload/export），category 描述业务语义。
-- 幂等，可重复执行。

ALTER TABLE opportunities.opportunity_attachments
  ADD COLUMN IF NOT EXISTS category TEXT;

CREATE INDEX IF NOT EXISTS idx_att_category
  ON opportunities.opportunity_attachments(category);

-- 语义明确回填：系统导出文件归为「已发报价」
UPDATE opportunities.opportunity_attachments
  SET category = 'sent_quote'
  WHERE kind = 'export' AND category IS NULL;

-- 其余一律留 NULL = 未分类，由用户在存档区手动归类（不自动猜，避免误归类）
