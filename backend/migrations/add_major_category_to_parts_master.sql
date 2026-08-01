-- 料号库分类重构（大类主导航）：为 l6.parts_master 增加一级分类列 major_category（大类）。
--
-- 大类是一级导航维度，用户可增/改名/删（定义在 l6.part_taxonomy, kind='major'）；
-- 改名/删除由后端 parts_master_repo.rename_taxonomy / delete_taxonomy 批量传播到本列。
-- section（STEP 部段）语义未变，仍是报价配置流取料的关键维度，本迁移不动它。
--
-- 注意：major_category 的取值无法从现有数据自动推导（来自「服务器机箱料号专业分类表」的人工映射），
-- 故本迁移只建列、不回填；具体料号的大类归属由导入/编辑或 create_part_taxonomy 之外的数据维护。
-- 幂等：可重复执行。

ALTER TABLE l6.parts_master ADD COLUMN IF NOT EXISTS major_category TEXT;

COMMENT ON COLUMN l6.parts_master.major_category IS '一级大类（主导航），用户可增改名删，SSOT=l6.part_taxonomy(kind=major)';
