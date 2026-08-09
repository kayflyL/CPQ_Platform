-- 线缆大类按 section 细化 + STEP(section) 正式退役（2026-08-09，取料改从大类取）。
--
-- 背景：方案A 把大类统一为解剖分组后，线缆（高速存储信号线/电源分配线缆）是按「类别」整体归大类的，
-- 丢失了 前面板件/后面板件/基准件 的细分语义；而报价/配置流取料（前面板线缆、GPU 供电线）依赖该细分。
-- 本迁移把这两类改为「category + section」组合归大类，使大类能承载原 section 的全部语义；
-- 之后 section 列、STEP 分类正式退役（报价流取料改按 major_category）。
--
-- 幂等：可重复执行。步骤 1 用 DO 块判断 section 列仍存在才执行（列已删=已执行过，跳过）。

-- 1) 线缆大类按 section 细化（仅当 section 列还在时执行）
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'l6' AND table_name = 'parts_master' AND column_name = 'section'
  ) THEN
    UPDATE l6.parts_master
    SET major_category = CASE
      WHEN category = '高速存储信号线' AND section = '前面板件' THEN '前面板'
      WHEN category = '高速存储信号线' AND section = '后面板件' THEN '后面板'
      WHEN category = '高速存储信号线' AND section = '基准件'   THEN '机箱主体'
      WHEN category = '电源分配线缆'   AND section = '后面板件' THEN '后面板'
      WHEN category = '电源分配线缆'   AND section = '基准件'   THEN '机箱主体'
      ELSE major_category
    END
    WHERE category IN ('高速存储信号线', '电源分配线缆');
  END IF;
END $$;

-- 2) STEP 分类退役：删除 part_taxonomy 中 kind='step' 的记录（幂等）
DELETE FROM l6.part_taxonomy WHERE kind = 'step';

-- 3) 删 parts_master.section 列（幂等）
ALTER TABLE l6.parts_master DROP COLUMN IF EXISTS section;
