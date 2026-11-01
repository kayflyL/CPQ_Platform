-- 报价人字段反转的一次性回填（2026-11-01 定调：报价人=quoting 节点处理人的同步镜像）。
-- 此前登记页手填 quotation_person 并充当 quoting 节点默认处理人（方向已反转、优先级已断环移除），
-- 两套数据长期漂移；本脚本把每个商机 quoting 节点当前处理人渲染成姓名回写镜像列。
-- 规则：
--   · assignees->>'quoting' 存 user_id 或自由姓名：join feed_users 渲染姓名，查无此人原样保留
--     （与 flow_repo.render_flow_assignees 同口径）；
--   · quoting 无指派的商机不动——保留手填旧值，等首次指派/转交时由同步钩子接管覆盖；
--   · 一商机一流（opportunity_flows 每商机至多一行），直接按 opportunity_id 关联。
-- 幂等可重跑（覆盖式回写）。
-- 执行前备份（仓库外留存，D:\CPQ_Archive\）：
--   \copy (SELECT opportunity_id, quotation_person FROM opportunities.opportunities) TO 'D:\CPQ_Archive\quotation_person_backup_20261101.csv' CSV

UPDATE opportunities.opportunities o
SET quotation_person = COALESCE(u.name, fa.assignee, '')
FROM opportunities.opportunity_flows f
CROSS JOIN LATERAL (SELECT f.assignees->>'quoting' AS assignee) fa
LEFT JOIN opportunities.feed_users u ON u.user_id = fa.assignee
WHERE f.opportunity_id = o.opportunity_id
  AND fa.assignee IS NOT NULL
  AND fa.assignee <> '';
