-- 料号库分类管理 SSOT：大类(major) 的可增/改名/删分类表。
--
-- list_taxonomy 读本表决定主导航顺序与显示；改名/删除由 parts_master_repo 批量传播到
-- parts_master.major_category（kind→列映射见 _TAXONOMY_COL）。
-- 删除被料号引用的分类时后端拒绝（需先把相关料号迁到别的分类）。
--
-- 幂等：可重复执行。种子用 ON CONFLICT DO NOTHING，不覆盖用户改名/增删后的现有数据。
-- 注：STEP(step) 分类已于 2026-08-09 退役（align_cables_major_by_section.sql），本表只保留 major。

CREATE TABLE IF NOT EXISTS l6.part_taxonomy (
  id          SERIAL PRIMARY KEY,
  kind        TEXT NOT NULL,            -- major（大类）
  name        TEXT NOT NULL,
  sort_order  INT  NOT NULL DEFAULT 0,
  updated_at  TIMESTAMP NOT NULL DEFAULT now(),
  UNIQUE (kind, name)
);

-- 默认分类（仅首次写入：ON CONFLICT DO NOTHING，已存在的同名分类保持不动）。
-- 大类与基准配置编辑页的「解剖分组」一一对应（①机箱主体 ②前面板 ③后面板 ④主板
-- ⑤处理器 ⑥内存 ⑦供电 ⑧硬盘 ⑨扩展 ⑩散热）——料号库左栏大类与编辑页从此同一套数据。
-- 历史版本（2026-08-02）的 10 个专业大类（机箱主体与结构件/主板及核心板卡/…）已被
-- align_major_category_to_anatomy.sql 替换为本套解剖大类，存量库请执行该迁移。
INSERT INTO l6.part_taxonomy (kind, name, sort_order) VALUES
  ('major', '机箱主体', 1),
  ('major', '前面板',   2),
  ('major', '后面板',   3),
  ('major', '主板',     4),
  ('major', '处理器',   5),
  ('major', '内存',     6),
  ('major', '供电',     7),
  ('major', '硬盘',     8),
  ('major', '扩展',     9),
  ('major', '散热',     10)
ON CONFLICT (kind, name) DO NOTHING;
