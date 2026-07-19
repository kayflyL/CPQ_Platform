-- 清理 parts_master 中与 kp.kp_parts 重复的 KP 核心配件数据
-- 排除被 l6.base_config_parts 外键引用的行
DELETE FROM parts.parts_master
WHERE category IN (
  'CPU', 'GPU', 'NIC', 'RAID卡',
  'Fibre Channel', 'Bridge', 'HBA', 'Key Parts', 'MB',
  '内存', '硬盘', '主板'
)
AND pn NOT IN (SELECT pn FROM l6.base_config_parts);

-- 统计清理后剩余
SELECT category, COUNT(*) FROM parts.parts_master GROUP BY category ORDER BY category;
