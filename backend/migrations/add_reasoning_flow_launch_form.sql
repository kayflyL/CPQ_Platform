-- 启动表单独立列：launch_form 从 graph JSON 内迁出到专属列。
-- 根因：graph 是多写者文档（画布保存/规则微调/脚本），各写者只认识自己的键，
-- 整份写回会剥掉不认识的键（entity_binding/launch_form 均已两度实测被剥）。
-- 流级配置与画布布局分存储后，画布保存物理碰不到它——该类 bug 结构性消失。
ALTER TABLE rules.reasoning_flow ADD COLUMN IF NOT EXISTS launch_form JSONB;

-- 一次性迁移：graph 内已有 launch_form 的搬到列（搬后留在 graph 里无害，读取以列为准）
UPDATE rules.reasoning_flow
SET launch_form = (graph::jsonb) -> 'launch_form'
WHERE (graph::jsonb) ? 'launch_form'
  AND (graph::jsonb) -> 'launch_form' IS NOT NULL
  AND launch_form IS NULL;
