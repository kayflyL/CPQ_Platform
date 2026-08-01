-- 商机「归档」语义并入 result：status=archived → result=expired, status=active
-- 归档不再作为独立状态；status 只剩 active / deleted(回收站)
-- 执行前快照：status=archived 110 行（全部 result=pending），active 2 行，deleted 1 行
-- 回滚（如需）：UPDATE opportunities.opportunities SET result='pending', status='archived' WHERE result='expired';
UPDATE opportunities.opportunities
SET result = 'expired', status = 'active'
WHERE status = 'archived';
