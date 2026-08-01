-- 商机字段「客户类型」→「订单类型」：物理列 customer_type → order_type + business_fields 元数据
-- 仅改商机域。策略中心「订单系数」维度按商机列的「值」匹配（直签/渠道…），列改名不影响
--   （Workspace.vue 读 order_type 进 ctx.customerType，值不变；定价 order_mult 仍按值命中）。
-- 执行前快照：opportunities.opportunities.customer_type 存在；rules.business_fields 一条 customer_type 行(source_column='customer_type')。
-- 回滚（如需）：
--   ALTER TABLE opportunities.opportunities RENAME COLUMN order_type TO customer_type;
--   UPDATE rules.business_fields SET key='customer_type', label='客户类型', source_column='customer_type' WHERE key='order_type';

-- ① 物理列改名（数据随列迁过去，值不变）
ALTER TABLE opportunities.opportunities RENAME COLUMN customer_type TO order_type;

-- ② business_fields 机会字段元数据（详情页信息栏按此渲染 key/label，field-history 按此查列）
UPDATE rules.business_fields
SET key = 'order_type', label = '订单类型', source_column = 'order_type'
WHERE key = 'customer_type' AND source_column = 'customer_type';
