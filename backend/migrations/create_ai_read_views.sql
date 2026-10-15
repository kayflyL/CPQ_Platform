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
