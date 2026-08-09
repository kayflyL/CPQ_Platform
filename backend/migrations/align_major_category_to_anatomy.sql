-- 料号库大类对齐基准配置编辑页「解剖分组」（2026-08-09，方案A）。
--
-- 背景：料号库左栏「大类」(major_category) 原为专业分类（机箱主体与结构件/主板及核心板卡/
-- 存储背板系统/扩展IO与Riser/散热系统/电源系统/线缆组件/结构附件/紧固件与辅材/包装与标识），
-- 与基准配置编辑页的解剖分组（①机箱主体 ②前面板 ③后面板 ④主板 ⑤处理器 ⑥内存 ⑦供电
-- ⑧硬盘 ⑨扩展 ⑩散热）是两套互不关联的分类，导致两侧对不上。本迁移把大类统一为解剖分组，
-- 并回填 parts_master.major_category（按 category 二级子类映射；category 仍是开放自由输入）。
--
-- 幂等：可重复执行。只删除旧的 10 个种子大类（保留用户自建的大类）；只回填已知 category。
-- STEP(section) 语义不变（报价配置流取料仍按 section），本迁移不动它。

-- 1) 删除旧的 10 个专业大类种子（改名/增删请走料号库 UI 或 parts_master_repo API）
DELETE FROM l6.part_taxonomy
WHERE kind = 'major' AND name IN (
  '机箱主体与结构件', '主板及核心板卡', '存储背板系统', '扩展IO与Riser',
  '散热系统', '电源系统', '线缆组件', '结构附件', '紧固件与辅材', '包装与标识'
);

-- 2) 写入 10 个解剖大类（幂等）
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

-- 3) 按 category 回填 major_category（对应编辑页解剖分组；分类可增，新增料号在料号库表单选大类）
UPDATE l6.parts_master
SET major_category = CASE category
  -- ①机箱主体（机箱 + 辅料 + 线缆固定件，编辑页①组）
  WHEN '机箱主体'     THEN '机箱主体'
  WHEN '滑轨'         THEN '机箱主体'
  WHEN '标签'         THEN '机箱主体'
  WHEN '包装材料'      THEN '机箱主体'
  WHEN '扎带'         THEN '机箱主体'
  WHEN '螺丝'         THEN '机箱主体'
  WHEN '电源线'       THEN '机箱主体'
  WHEN '电源分配线缆'   THEN '机箱主体'
  -- ②前面板（前面板线缆，编辑页②组选择器）
  WHEN '高速存储信号线' THEN '前面板'
  -- ③后面板（OCP 网卡，编辑页③组后面板选择器）
  WHEN 'OCP网卡模组'   THEN '后面板'
  -- ④主板
  WHEN '主板'         THEN '主板'
  WHEN '主板托盘'      THEN '主板'
  WHEN 'SCM/后IO控制板' THEN '主板'
  WHEN 'BMC管理板'    THEN '主板'
  WHEN '低速控制信号线'  THEN '主板'
  -- ⑤处理器
  WHEN 'CPU散热器'    THEN '处理器'
  WHEN 'CPU支架/载体'  THEN '处理器'
  -- ⑦供电（PSU，编辑页⑦组选择器）
  WHEN '电源模块'      THEN '供电'
  -- ⑧硬盘
  WHEN '前置硬盘背板'   THEN '硬盘'
  -- ⑨扩展
  WHEN 'PCIe Riser卡' THEN '扩展'
  WHEN '后置SATA模组'  THEN '扩展'
  WHEN '后置NVMe模组'  THEN '扩展'
  -- ⑩散热
  WHEN '机箱风扇'      THEN '散热'
  WHEN '导风罩'        THEN '散热'
  ELSE major_category
END
WHERE category IN (
  '机箱主体', '滑轨', '标签', '包装材料', '扎带', '螺丝', '电源线', '电源分配线缆',
  '高速存储信号线', 'OCP网卡模组', '主板', '主板托盘', 'SCM/后IO控制板', 'BMC管理板',
  '低速控制信号线', 'CPU散热器', 'CPU支架/载体', '电源模块', '前置硬盘背板',
  'PCIe Riser卡', '后置SATA模组', '后置NVMe模组', '机箱风扇', '导风罩'
);

-- 4) 兜底：任何仍挂在旧专业大类名下的料号置空（本迁移覆盖全部已知 category，正常不会命中）
UPDATE l6.parts_master
SET major_category = NULL
WHERE major_category IN (
  '机箱主体与结构件', '主板及核心板卡', '存储背板系统', '扩展IO与Riser',
  '散热系统', '电源系统', '线缆组件', '结构附件', '紧固件与辅材', '包装与标识'
);
