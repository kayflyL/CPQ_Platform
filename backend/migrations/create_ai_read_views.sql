-- AI 可读视图（2026-10-11）：opportunities 域对 query_data 只暴露 ai_read.*，
-- 行级排除 status IN ('ai_office','deleted')——AI 生成的线索不进 AI 的任何读取面，
-- 与 opp_stats/商机线索页统计口径物理对齐。白名单改道见 data_boundary._AI_VIEW_MAP。
-- 运行时机：startup.ensure_ai_read_views() 每次启动幂等重建（基表加列自愈）；本文件供手工执行/审阅。
CREATE SCHEMA IF NOT EXISTS ai_read;

CREATE OR REPLACE VIEW ai_read.opportunities AS
SELECT * FROM opportunities.opportunities
WHERE status NOT IN ('ai_office', 'deleted');

CREATE OR REPLACE VIEW ai_read.opportunity_requirements AS
SELECT r.* FROM opportunities.opportunity_requirements r
JOIN opportunities.opportunities o ON o.opportunity_id = r.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted');

CREATE OR REPLACE VIEW ai_read.opportunity_bom_schemes AS
SELECT b.* FROM opportunities.opportunity_bom_schemes b
JOIN opportunities.opportunities o ON o.opportunity_id = b.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted');

CREATE OR REPLACE VIEW ai_read.quotations AS
SELECT qt.* FROM opportunities.quotations qt
JOIN opportunities.opportunities o ON o.opportunity_id = qt.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted');

CREATE OR REPLACE VIEW ai_read.quotation_items AS
SELECT qi.* FROM opportunities.quotation_items qi
JOIN opportunities.quotations qt ON qt.quotation_id = qi.quotation_id
JOIN opportunities.opportunities o ON o.opportunity_id = qt.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted');

-- 业务现场（2026-10-16）：流程/成本表/附件/审批，query_data 按需自查的视野。
-- 权威源 = startup.ensure_ai_read_views()（本文件同步供手工执行/审阅）。

CREATE OR REPLACE VIEW ai_read.opportunity_flows AS
SELECT f.* FROM opportunities.opportunity_flows f
JOIN opportunities.opportunities o ON o.opportunity_id = f.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted');

CREATE OR REPLACE VIEW ai_read.opportunity_flow_nodes AS
SELECT n.* FROM opportunities.opportunity_flow_nodes n
JOIN opportunities.opportunity_flows f ON f.flow_id = n.flow_id
JOIN opportunities.opportunities o ON o.opportunity_id = f.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted');

-- 成本表只暴露元数据：configs 是 JSON、内含价格，query_data 的列级脱敏
-- （按列名命中）管不住 JSON 内部——配置细节走 import_cost_sheet（有 price_ok 门）
CREATE OR REPLACE VIEW ai_read.opportunity_cost_sheets AS
SELECT c.id, c.opportunity_id, c.bom_scheme_id, c.name, c.status,
       c.quotation_id, c.created_by, c.created_at, c.updated_at
FROM opportunities.opportunity_cost_sheets c
JOIN opportunities.opportunities o ON o.opportunity_id = c.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted');

-- 暂存附件（opportunity_id IS NULL）经 INNER JOIN 天然排除：私人暂存不进 AI 读面
CREATE OR REPLACE VIEW ai_read.opportunity_attachments AS
SELECT a.attachment_id, a.opportunity_id, a.message_id, a.uploader_user_id,
       a.original_filename, a.file_size, a.mime_type, a.kind, a.category,
       a.quotation_id, a.flow_card_id, a.requirement_version, a.version,
       a.created_at, a.deleted_at
FROM opportunities.opportunity_attachments a
JOIN opportunities.opportunities o ON o.opportunity_id = a.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted') AND a.deleted_at IS NULL;

-- margin_pct/threshold 列名命中价格脱敏正则，运行时对无价格权限者整列剔除
CREATE OR REPLACE VIEW ai_read.opportunity_pricing_approvals AS
SELECT p.* FROM opportunities.opportunity_pricing_approvals p
JOIN opportunities.opportunities o ON o.opportunity_id = p.opportunity_id
WHERE o.status NOT IN ('ai_office', 'deleted');
