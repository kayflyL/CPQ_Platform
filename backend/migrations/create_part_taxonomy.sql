-- 料号库分类管理 SSOT：大类(major)/STEP(step) 的可增/改名/删分类表。
--
-- list_taxonomy 读本表决定主导航顺序与显示；改名/删除由 parts_master_repo 批量传播到
-- parts_master.major_category / parts_master.section（kind→列映射见 _TAXONOMY_COL）。
-- 删除被料号引用的分类时后端拒绝（需先把相关料号迁到别的分类）。
--
-- 幂等：可重复执行。种子用 ON CONFLICT DO NOTHING，不覆盖用户改名/增删后的现有数据。

CREATE TABLE IF NOT EXISTS l6.part_taxonomy (
  id          SERIAL PRIMARY KEY,
  kind        TEXT NOT NULL,            -- major（大类）| step（STEP 部段）
  name        TEXT NOT NULL,
  sort_order  INT  NOT NULL DEFAULT 0,
  updated_at  TIMESTAMP NOT NULL DEFAULT now(),
  UNIQUE (kind, name)
);

-- 默认分类（仅首次写入：ON CONFLICT DO NOTHING，已存在的同名分类保持不动）
INSERT INTO l6.part_taxonomy (kind, name, sort_order) VALUES
  ('major', '机箱主体与结构件', 1),
  ('major', '主板及核心板卡',   2),
  ('major', '存储背板系统',     3),
  ('major', '扩展IO与Riser',    4),
  ('major', '散热系统',         5),
  ('major', '电源系统',         6),
  ('major', '线缆组件',         7),
  ('major', '结构附件',         8),
  ('major', '紧固件与辅材',     9),
  ('major', '包装与标识',       10),
  ('step',  '基准件',           1),
  ('step',  '前面板件',         2),
  ('step',  '后面板件',         3),
  ('step',  '电源件',           4)
ON CONFLICT (kind, name) DO NOTHING;
