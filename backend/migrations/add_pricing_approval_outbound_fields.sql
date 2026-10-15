-- 报价外发审批门（M1）：opportunity_pricing_approvals 泛化为「外发许可」单。
-- 批准 = 对 content_hash 内容的外发许可（客户版导出冻结/平台内发送/规格书 PDF 三口一闸），改价 hash 失配自动失效重批。
-- assigned_to/assigned_name = 调度面板 approval 节点规则路由的责任总监（空=广播降级）。
-- 回滚（如需）：ALTER TABLE opportunities.opportunity_pricing_approvals
--   DROP COLUMN trigger_reason, DROP COLUMN content_hash, DROP COLUMN assigned_to,
--   DROP COLUMN assigned_name, DROP COLUMN route_snapshot, DROP COLUMN request_note,
--   DROP COLUMN transfers, DROP COLUMN escalated_at, DROP COLUMN reminded_at;

ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS trigger_reason VARCHAR DEFAULT 'outbound';
ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS content_hash VARCHAR;
ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS assigned_to VARCHAR;
ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS assigned_name VARCHAR;
ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS route_snapshot TEXT;
ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS request_note TEXT;
ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS transfers TEXT;
ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS escalated_at VARCHAR;
ALTER TABLE opportunities.opportunity_pricing_approvals ADD COLUMN IF NOT EXISTS reminded_at VARCHAR;
