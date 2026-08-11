-- 2U12标准 模板加「OCP」网络槽行（2026-08-10）。
--
-- 背景：规格书 L6 表按实际选配显示 OCP 转接适配板（desc 跟 ocp_x8/ocp_x16 走，
-- 由规则引擎 io_slot scope + slot=OCP 求值），没选 OCP → desc/qty 都空 → 整行隐藏
-- （BomTable / preview_data_loader / bom_template_eval 均有空行隐藏）。
-- 只加 2U 模板；4U 模板已有 rear_summary 汇总行（含 OCP），避免重复出现两次。
-- 幂等：该行已存在时 NOT EXISTS 不命中，可重复执行。
-- 插入位置：IO2 之后（ord 3.5，位于 Heatsink 前）。

UPDATE l6.bom_templates
SET rows = (
  SELECT jsonb_agg(elem ORDER BY ord)
  FROM (
    SELECT elem, ord
    FROM jsonb_array_elements(rows) WITH ORDINALITY AS t(elem, ord)
    WHERE (elem->>'slot') IS DISTINCT FROM 'OCP'
    UNION ALL
    SELECT '{"type":"io_slot","slot":"OCP","label":"OCP","rule":{"desc":{"kind":"struct_count","scope":"io_slot"},"qty":{"kind":"config_calc","key":"ocp_qty"}}}'::jsonb, 3.5
  ) u
)
WHERE name = '2U12标准'
  AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(rows) e WHERE e->>'slot' = 'OCP');
