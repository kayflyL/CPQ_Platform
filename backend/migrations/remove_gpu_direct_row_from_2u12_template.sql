-- 2U12标准 模板去掉「GPU 直连」汇总行（2026-08-09）。
--
-- 背景：KP 配件区已有 GPU，机箱(L6)部分再显示 GPU 直连汇总冗余 → 从模板 2U12标准 删除该行。
-- 只删该模板行，不动规则引擎的 gpu_direct scope（仍是通用能力，其它模板/编辑 UI 可选）。
-- 幂等：可重复执行（该行不存在时 WHERE 不命中，无副作用）。

UPDATE l6.bom_templates
SET rows = (
  SELECT jsonb_agg(elem ORDER BY ord)
  FROM jsonb_array_elements(rows) WITH ORDINALITY AS t(elem, ord)
  WHERE elem->>'label' <> 'GPU 直连'
)
WHERE name = '2U12标准'
  AND EXISTS (SELECT 1 FROM jsonb_array_elements(rows) e WHERE e->>'label' = 'GPU 直连');
